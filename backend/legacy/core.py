import os, uuid, jwt
from datetime import datetime, timedelta, timezone
from passlib.context import CryptContext
from pydantic_settings import BaseSettings
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

class Settings(BaseSettings):
    database_url: str='postgresql+psycopg://workflow:workflow@localhost:5432/workflow'
    redis_url: str='redis://localhost:6379/0'
    jwt_secret: str='change-me-in-production'
    jwt_expire_minutes: int=60
    environment: str='development'
    worker_id: str=f'worker-{uuid.uuid4()}'
    model_config = {"env_file": ".env", "extra": "ignore"}
settings=Settings()
if settings.environment.lower() not in ('development','test') and settings.jwt_secret in ('change-me-in-production','local-development-secret-change-me'):
    raise RuntimeError('JWT_SECRET must be explicitly configured outside development/test')
engine=create_engine(settings.database_url.replace("+asyncpg", "+psycopg"), pool_pre_ping=True)
SessionLocal=sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
pwd=CryptContext(schemes=['bcrypt'], deprecated='auto')
bearer=HTTPBearer()

def get_db():
    db=SessionLocal()
    try: yield db
    finally: db.close()

def hash_password(password): return pwd.hash(password)
def verify_password(password, hashed): return pwd.verify(password, hashed)
def make_token(user): return jwt.encode({'sub':str(user.id),'tenant':user.tenant_id,'exp':datetime.now(timezone.utc)+timedelta(minutes=settings.jwt_expire_minutes)}, settings.jwt_secret, algorithm='HS256')
def current_user(credentials: HTTPAuthorizationCredentials=Depends(bearer), db: Session=Depends(get_db)):
    from .models import User
    try: payload=jwt.decode(credentials.credentials, settings.jwt_secret, algorithms=['HS256']); uid=int(payload['sub'])
    except Exception: raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail='Invalid token')
    user=db.get(User, uid)
    if not user: raise HTTPException(status_code=401, detail='User not found')
    return user
