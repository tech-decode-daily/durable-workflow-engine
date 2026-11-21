import json, logging, uuid, time
from fastapi import FastAPI, Depends, HTTPException, Request
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import select, func
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from redis import Redis
from .core import get_db, current_user, hash_password, verify_password, make_token, settings
from .models import User, Workflow, WorkflowStep, ExecutionLog, OutboxEvent, WorkflowStatus, StepStatus
from .schemas import RegisterRequest, LoginRequest, AuthResponse, WorkflowCreate, WorkflowOut

logging.basicConfig(level=logging.INFO, format='%(message)s'); log=logging.getLogger('workflow-api')
app=FastAPI(title='Durable Workflow Engine', version='0.1.0')
app.add_middleware(CORSMiddleware, allow_origins=['http://localhost:5173'], allow_credentials=True, allow_methods=['*'], allow_headers=['*'])
redis=Redis.from_url(settings.redis_url, decode_responses=True)

@app.middleware('http')
async def rate_limit(request: Request, call_next):
    if request.url.path in ('/healthz','/docs','/openapi.json'): return await call_next(request)
    key=f"rate:{request.client.host}:{request.url.path}:{int(time.time()//60)}"
    try:
        count=redis.incr(key)
        if count==1: redis.expire(key,60)
        if count>120: return JSONResponse({'detail':'Rate limit exceeded'},status_code=429,headers={'Retry-After':'60'})
    except Exception: pass
    return await call_next(request)

def add_outbox(db, workflow_id, dedupe_key):
    db.add(OutboxEvent(event_type='workflow.submitted', aggregate_id=workflow_id, dedupe_key=dedupe_key, payload={'workflow_id':workflow_id}))

def serialize(w):
    return {'id':w.id,'name':w.name,'status':w.status,'input':w.input,'created_at':w.created_at,'started_at':w.started_at,'completed_at':w.completed_at,'error':w.error,'steps':[{'id':s.id,'position':s.position,'name':s.name,'status':s.status,'attempts':s.attempts,'error':s.error,'output':s.output} for s in sorted(w.steps,key=lambda x:x.position)]}

@app.get('/healthz')
def health():
    try: redis.ping(); queue='ok'
    except Exception: queue='degraded'
    return {'status':'ok','queue':queue}
@app.post('/auth/register', response_model=AuthResponse)
def register(body:RegisterRequest, db:Session=Depends(get_db)):
    if db.scalar(select(User).where(User.email==body.email)): raise HTTPException(409,'Email already registered')
    user=User(email=body.email, password_hash=hash_password(body.password), tenant_id=str(uuid.uuid4())); db.add(user); db.commit(); db.refresh(user); return {'token':make_token(user)}
@app.post('/auth/login', response_model=AuthResponse)
def login(body:LoginRequest, db:Session=Depends(get_db)):
    user=db.scalar(select(User).where(User.email==body.email))
    if not user or not verify_password(body.password,user.password_hash): raise HTTPException(401,'Invalid credentials')
    return {'token':make_token(user)}
@app.post('/workflows', response_model=WorkflowOut, status_code=201)
def create_workflow(body:WorkflowCreate,user=Depends(current_user),db:Session=Depends(get_db)):
    if body.idempotency_key:
        old=db.scalar(select(Workflow).where(Workflow.tenant_id==user.tenant_id,Workflow.idempotency_key==body.idempotency_key))
        if old: return serialize(old)
    w=Workflow(id=str(uuid.uuid4()),tenant_id=user.tenant_id,name=body.name,input=body.input,idempotency_key=body.idempotency_key)
    for i,step in enumerate(body.steps): w.steps.append(WorkflowStep(position=i,name=step.name,config=step.model_dump(),max_attempts=step.retries,timeout_seconds=step.timeout_seconds))
    try:
        db.add(w)
        db.flush()
        db.add(ExecutionLog(workflow_id=w.id,message='Workflow submitted',details={'step_count':len(body.steps)})); add_outbox(db,w.id,f'workflow.submitted:{w.id}')
        db.commit()
    except IntegrityError:
        db.rollback()
        existing=db.scalar(select(Workflow).where(Workflow.tenant_id==user.tenant_id,Workflow.idempotency_key==body.idempotency_key)) if body.idempotency_key else None
        if existing: return serialize(existing)
        raise HTTPException(409,'Workflow submission conflicted; retry the request')
    db.refresh(w); return serialize(w)
@app.get('/workflows', response_model=list[WorkflowOut])
def list_workflows(user=Depends(current_user),db:Session=Depends(get_db),limit:int=50):
    ws=db.scalars(select(Workflow).where(Workflow.tenant_id==user.tenant_id).order_by(Workflow.created_at.desc()).limit(min(limit,100))).all(); return [serialize(w) for w in ws]
@app.get('/workflows/{workflow_id}', response_model=WorkflowOut)
def get_workflow(workflow_id:str,user=Depends(current_user),db:Session=Depends(get_db)):
    w=db.scalar(select(Workflow).where(Workflow.id==workflow_id,Workflow.tenant_id==user.tenant_id))
    if not w: raise HTTPException(404,'Workflow not found')
    return serialize(w)
@app.post('/workflows/{workflow_id}/retry', response_model=WorkflowOut)
def retry_workflow(workflow_id:str,user=Depends(current_user),db:Session=Depends(get_db)):
    w=db.scalar(select(Workflow).where(Workflow.id==workflow_id,Workflow.tenant_id==user.tenant_id))
    if not w: raise HTTPException(404,'Workflow not found')
    if w.status not in (WorkflowStatus.FAILED.value,WorkflowStatus.CANCELLED.value): raise HTTPException(409,'Only failed or cancelled workflows can be retried')
    w.status=WorkflowStatus.PENDING.value; w.error=None
    for s in w.steps: s.status=StepStatus.PENDING.value; s.error=None; s.lease_until=None
    db.add(ExecutionLog(workflow_id=w.id,message='Workflow manually retried')); add_outbox(db,w.id,f'workflow.retry:{w.id}:{uuid.uuid4()}'); db.commit(); return serialize(w)
@app.get('/stats')
def stats(user=Depends(current_user),db:Session=Depends(get_db)):
    rows=db.execute(select(Workflow.status,func.count()).where(Workflow.tenant_id==user.tenant_id).group_by(Workflow.status)).all(); return {status:count for status,count in rows}
