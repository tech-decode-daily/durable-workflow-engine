from datetime import datetime, timezone
from enum import Enum
from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, JSON, String, Text, UniqueConstraint
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


def now(): return datetime.now(timezone.utc)

class Base(DeclarativeBase): pass
class WorkflowStatus(str, Enum): PENDING='PENDING'; RUNNING='RUNNING'; COMPLETED='COMPLETED'; FAILED='FAILED'; CANCELLED='CANCELLED'
class StepStatus(str, Enum): PENDING='PENDING'; RUNNING='RUNNING'; RETRY_WAIT='RETRY_WAIT'; COMPLETED='COMPLETED'; FAILED='FAILED'

class User(Base):
    __tablename__='users'
    id: Mapped[int]=mapped_column(primary_key=True)
    email: Mapped[str]=mapped_column(String(320), unique=True, index=True)
    password_hash: Mapped[str]=mapped_column(String(255))
    tenant_id: Mapped[str]=mapped_column(String(100), index=True)
    created_at: Mapped[datetime]=mapped_column(DateTime(timezone=True), default=now)

class Workflow(Base):
    __tablename__='workflows'
    id: Mapped[str]=mapped_column(String(36), primary_key=True)
    tenant_id: Mapped[str]=mapped_column(String(100), index=True)
    name: Mapped[str]=mapped_column(String(200))
    input: Mapped[dict]=mapped_column(JSON, default=dict)
    status: Mapped[str]=mapped_column(String(20), default=WorkflowStatus.PENDING.value, index=True)
    idempotency_key: Mapped[str|None]=mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime]=mapped_column(DateTime(timezone=True), default=now)
    started_at: Mapped[datetime|None]=mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime|None]=mapped_column(DateTime(timezone=True), nullable=True)
    error: Mapped[str|None]=mapped_column(Text, nullable=True)
    steps: Mapped[list['WorkflowStep']]=relationship(back_populates='workflow', cascade='all, delete-orphan')
    __table_args__=(UniqueConstraint('tenant_id','idempotency_key', name='uq_workflow_tenant_idem'),)

class WorkflowStep(Base):
    __tablename__='workflow_steps'
    id: Mapped[int]=mapped_column(primary_key=True)
    workflow_id: Mapped[str]=mapped_column(ForeignKey('workflows.id', ondelete='CASCADE'), index=True)
    position: Mapped[int]=mapped_column(Integer)
    name: Mapped[str]=mapped_column(String(200))
    config: Mapped[dict]=mapped_column(JSON, default=dict)
    status: Mapped[str]=mapped_column(String(20), default=StepStatus.PENDING.value, index=True)
    attempts: Mapped[int]=mapped_column(Integer, default=0)
    max_attempts: Mapped[int]=mapped_column(Integer, default=3)
    timeout_seconds: Mapped[int]=mapped_column(Integer, default=300)
    available_at: Mapped[datetime]=mapped_column(DateTime(timezone=True), default=now)
    lease_until: Mapped[datetime|None]=mapped_column(DateTime(timezone=True), nullable=True)
    claim_token: Mapped[str|None]=mapped_column(String(36), nullable=True, index=True)
    started_at: Mapped[datetime|None]=mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime|None]=mapped_column(DateTime(timezone=True), nullable=True)
    error: Mapped[str|None]=mapped_column(Text, nullable=True)
    output: Mapped[dict|None]=mapped_column(JSON, nullable=True)
    workflow: Mapped[Workflow]=relationship(back_populates='steps')

class ExecutionLog(Base):
    __tablename__='execution_logs'
    id: Mapped[int]=mapped_column(primary_key=True)
    workflow_id: Mapped[str]=mapped_column(ForeignKey('workflows.id', ondelete='CASCADE'), index=True)
    step_id: Mapped[int|None]=mapped_column(ForeignKey('workflow_steps.id', ondelete='SET NULL'), nullable=True)
    level: Mapped[str]=mapped_column(String(20), default='INFO')
    message: Mapped[str]=mapped_column(Text)
    details: Mapped[dict]=mapped_column(JSON, default=dict)
    created_at: Mapped[datetime]=mapped_column(DateTime(timezone=True), default=now)

class OutboxEvent(Base):
    __tablename__='outbox_events'
    id: Mapped[int]=mapped_column(primary_key=True)
    event_type: Mapped[str]=mapped_column(String(100))
    aggregate_id: Mapped[str]=mapped_column(String(36), index=True)
    dedupe_key: Mapped[str]=mapped_column(String(255), unique=True)
    payload: Mapped[dict]=mapped_column(JSON, default=dict)
    attempts: Mapped[int]=mapped_column(Integer, default=0)
    available_at: Mapped[datetime]=mapped_column(DateTime(timezone=True), default=now, index=True)
    published_at: Mapped[datetime|None]=mapped_column(DateTime(timezone=True), nullable=True, index=True)
    last_error: Mapped[str|None]=mapped_column(Text, nullable=True)
