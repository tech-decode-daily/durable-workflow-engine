import json, logging, time, uuid
from datetime import datetime, timezone, timedelta
from redis import Redis
from sqlalchemy import and_, or_, select, update
from legacy.core import SessionLocal, settings
from legacy.models import Workflow, WorkflowStep, ExecutionLog, OutboxEvent, WorkflowStatus, StepStatus

logging.basicConfig(level=logging.INFO, format='%(message)s'); log=logging.getLogger('workflow-worker')
redis=Redis.from_url(settings.redis_url, decode_responses=True)

def utcnow(): return datetime.now(timezone.utc)
def log_event(db,wid,sid,msg,details=None,level='INFO'): db.add(ExecutionLog(workflow_id=wid,step_id=sid,message=msg,details=details or {},level=level))

def activity_echo(step, workflow, idempotency_key): return {'value': workflow.input.get('value', workflow.input), 'idempotency_key': idempotency_key}
def activity_sleep(step, workflow, idempotency_key): time.sleep(min(int(workflow.input.get('seconds',1)), step.timeout_seconds)); return {'slept': True, 'idempotency_key': idempotency_key}
def activity_fail(step, workflow, idempotency_key): raise RuntimeError(workflow.input.get('error','requested failure'))
ACTIVITY_REGISTRY={'echo':activity_echo,'sleep':activity_sleep,'fail':activity_fail}

def execute_action(step, workflow):
    action=step.config.get('action'); activity=ACTIVITY_REGISTRY.get(action)
    if activity is None: raise RuntimeError(f'Unknown activity: {action}')
    # Stable across attempts: providers can deduplicate retries using this key.
    provider_key=step.config.get('provider_idempotency_key') or f'{workflow.id}:step:{step.id}'
    return activity(step, workflow, provider_key)

def claim_next_step(workflow_id):
    db=SessionLocal()
    try:
        now=utcnow(); wf=db.scalar(select(Workflow).where(Workflow.id==workflow_id).with_for_update())
        if not wf or wf.status in (WorkflowStatus.COMPLETED.value,WorkflowStatus.CANCELLED.value): return None
        wf.status=WorkflowStatus.RUNNING.value
        if wf.started_at is None: wf.started_at=now
        for step in sorted(wf.steps,key=lambda s:s.position):
            if step.status==StepStatus.COMPLETED.value: continue
            due=step.available_at is None or step.available_at<=now
            expired=step.status==StepStatus.RUNNING.value and (step.lease_until is None or step.lease_until<=now)
            eligible=step.status in (StepStatus.PENDING.value,StepStatus.RETRY_WAIT.value) and due or expired
            if not eligible: db.commit(); return None
            token=str(uuid.uuid4())
            predicates=[WorkflowStep.id==step.id, WorkflowStep.status.in_([StepStatus.PENDING.value,StepStatus.RETRY_WAIT.value])]
            if expired: predicates=[WorkflowStep.id==step.id, WorkflowStep.status==StepStatus.RUNNING.value, or_(WorkflowStep.lease_until.is_(None),WorkflowStep.lease_until<=now)]
            result=db.execute(update(WorkflowStep).where(and_(*predicates)).values(status=StepStatus.RUNNING.value, claim_token=token, lease_until=now+timedelta(seconds=step.timeout_seconds), started_at=step.started_at or now, attempts=WorkflowStep.attempts+1))
            if result.rowcount==1:
                db.commit(); return workflow_id, step.id, token
        db.commit(); return None
    finally: db.close()

def process(workflow_id):
    claim=claim_next_step(workflow_id)
    if not claim: return
    _, step_id, token=claim; db=SessionLocal()
    try:
        step=db.get(WorkflowStep,step_id); wf=db.get(Workflow,workflow_id)
        if not step or not wf: return
        log_event(db,wf.id,step.id,'Step started',{'attempt':step.attempts,'claim_token':token}); db.commit()
        try:
            output=execute_action(step,wf); now=utcnow()
            result=db.execute(update(WorkflowStep).where(WorkflowStep.id==step.id,WorkflowStep.status==StepStatus.RUNNING.value,WorkflowStep.claim_token==token).values(output=output,status=StepStatus.COMPLETED.value,completed_at=now,lease_until=None,error=None))
            if result.rowcount!=1: log.warning(json.dumps({'event':'stale_step_success_ignored','workflow_id':wf.id,'step_id':step.id})); return
            db.commit()
        except Exception as exc:
            step=db.get(WorkflowStep,step_id); now=utcnow()
            if not step or step.claim_token!=token or step.status!=StepStatus.RUNNING.value: log.warning(json.dumps({'event':'stale_step_failure_ignored','workflow_id':workflow_id,'step_id':step_id})); return
            if step.attempts < step.max_attempts:
                delay=step.config.get('backoff_seconds',2)*(2**(step.attempts-1)); db.execute(update(WorkflowStep).where(WorkflowStep.id==step.id,WorkflowStep.claim_token==token).values(status=StepStatus.RETRY_WAIT.value,available_at=now+timedelta(seconds=delay),lease_until=None,error=str(exc))); db.commit(); return
            db.execute(update(WorkflowStep).where(WorkflowStep.id==step.id,WorkflowStep.claim_token==token).values(status=StepStatus.FAILED.value,lease_until=None,error=str(exc))); wf.status=WorkflowStatus.FAILED.value; wf.error=f'Step {step.name} failed: {exc}'; wf.completed_at=now; log_event(db,wf.id,step.id,'Workflow failed',{'error':str(exc)},'ERROR'); db.commit(); return
        # A duplicate Redis delivery simply claims the next unfinished step.
        db.close(); db=SessionLocal(); wf=db.get(Workflow,workflow_id); remaining=db.scalar(select(WorkflowStep.id).where(WorkflowStep.workflow_id==workflow_id,WorkflowStep.status!=StepStatus.COMPLETED.value).limit(1))
        if remaining is None: wf.status=WorkflowStatus.COMPLETED.value; wf.completed_at=utcnow(); log_event(db,wf.id,None,'Workflow completed'); db.commit()
        else: db.commit(); redis.lpush('workflow:jobs',workflow_id)
    finally: db.close()

def recover():
    db=SessionLocal()
    try:
        now=utcnow(); due=and_(WorkflowStep.status.in_([StepStatus.PENDING.value,StepStatus.RETRY_WAIT.value]),or_(WorkflowStep.available_at.is_(None),WorkflowStep.available_at<=now)); expired=and_(WorkflowStep.status==StepStatus.RUNNING.value,or_(WorkflowStep.lease_until.is_(None),WorkflowStep.lease_until<=now))
        ids=db.scalars(select(Workflow.id).join(WorkflowStep).where(Workflow.status.in_([WorkflowStatus.PENDING.value,WorkflowStatus.RUNNING.value]),or_(due,expired))).all()
        for wid in set(ids): redis.lpush('workflow:jobs',wid)
    finally: db.close()

def publish_outbox():
    db=SessionLocal()
    try:
        now=utcnow(); events=db.scalars(select(OutboxEvent).where(OutboxEvent.published_at.is_(None),OutboxEvent.available_at<=now).order_by(OutboxEvent.id).limit(50)).all()
        for event in events:
            try:
                redis.lpush('workflow:jobs',event.payload['workflow_id']); event.published_at=utcnow(); event.attempts+=1; db.commit()
            except Exception as exc:
                event.attempts+=1; event.last_error=str(exc); event.available_at=utcnow()+timedelta(seconds=min(60,2**min(event.attempts,6))); db.commit()
    finally: db.close()

def main():
    log.info(json.dumps({'event':'worker_started','worker_id':settings.worker_id}))
    while True:
        try:
            publish_outbox(); recover(); item=redis.brpop('workflow:jobs',timeout=5)
            if item: process(item[1])
        except Exception as exc: log.exception(json.dumps({'event':'worker_loop_error','error':str(exc)})); time.sleep(2)
if __name__=='__main__': main()
