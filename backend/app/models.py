from datetime import datetime
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import (
    MetaData,
    BigInteger,
    Identity as AutoIdentity,
    DateTime,
    ForeignKey,
    Index,
    String,
    Text,
    UniqueConstraint,
    CheckConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    metadata = MetaData(schema="durable")
    type_annotation_map = {
        datetime: DateTime(timezone=True),
        dict[str, Any]: JSONB(none_as_null=True),
    }


class Identity:
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)


class Created:
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())


class Updated:
    updated_at: Mapped[datetime] = mapped_column(
        server_default=func.now(), onupdate=func.now()
    )


class Workflow(Base, Identity, Created, Updated):
    __tablename__ = "workflows"
    name: Mapped[str] = mapped_column(String(120))
    description: Mapped[str | None] = mapped_column(Text)
    workflow_key: Mapped[str] = mapped_column(String(120), unique=True)
    status: Mapped[str] = mapped_column(String(12), default="draft")
    draft: Mapped[dict[str, Any]]
    __table_args__ = (CheckConstraint("status in ('draft','active')"),)


class Version(Base, Identity, Created):
    __tablename__ = "workflow_versions"
    workflow_id: Mapped[UUID] = mapped_column(ForeignKey("workflows.id"))
    version: Mapped[int]
    definition: Mapped[dict[str, Any]]
    __table_args__ = (UniqueConstraint("workflow_id", "version"),)


class Step(Base, Identity, Created):
    __tablename__ = "workflow_steps"
    workflow_version_id: Mapped[UUID] = mapped_column(
        ForeignKey("workflow_versions.id")
    )
    step_key: Mapped[str]
    step_name: Mapped[str]
    task_type: Mapped[str]
    configuration: Mapped[dict[str, Any]]
    position: Mapped[int]
    retry_limit: Mapped[int]
    retry_delay_seconds: Mapped[int]
    max_delay_seconds: Mapped[int]
    timeout_seconds: Mapped[int]
    __table_args__ = (
        UniqueConstraint("workflow_version_id", "step_key"),
        UniqueConstraint("workflow_version_id", "position"),
    )


class Run(Base, Identity, Created, Updated):
    __tablename__ = "workflow_runs"
    workflow_id: Mapped[UUID] = mapped_column(ForeignKey("workflows.id"), index=True)
    workflow_version_id: Mapped[UUID] = mapped_column(
        ForeignKey("workflow_versions.id")
    )
    status: Mapped[str] = mapped_column(index=True)
    input_data: Mapped[dict[str, Any]]
    output_data: Mapped[dict[str, Any] | None]
    error_message: Mapped[str | None] = mapped_column(Text)
    started_at: Mapped[datetime | None]
    completed_at: Mapped[datetime | None]
    idempotency_key: Mapped[str | None]
    request_hash: Mapped[str | None]
    __table_args__ = (
        UniqueConstraint("workflow_id", "idempotency_key"),
        Index("ix_runs_created", "created_at"),
        CheckConstraint(
            "status in ('PENDING','RUNNING','PAUSED','COMPLETED','FAILED','CANCELLED')"
        ),
    )


class Worker(Base, Identity):
    __tablename__ = "workers"
    worker_name: Mapped[str]
    hostname: Mapped[str]
    status: Mapped[str]
    registered_at: Mapped[datetime] = mapped_column(server_default=func.now())
    last_heartbeat_at: Mapped[datetime] = mapped_column(
        index=True, server_default=func.now()
    )
    current_task_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("step_executions.id", use_alter=True, name="fk_worker_current_task")
    )


class Execution(Base, Identity, Created, Updated):
    __tablename__ = "step_executions"
    workflow_run_id: Mapped[UUID] = mapped_column(
        ForeignKey("workflow_runs.id"), index=True
    )
    workflow_step_id: Mapped[UUID] = mapped_column(ForeignKey("workflow_steps.id"))
    status: Mapped[str]
    input_data: Mapped[dict[str, Any]]
    output_data: Mapped[dict[str, Any] | None]
    error_message: Mapped[str | None] = mapped_column(Text)
    attempt_count: Mapped[int] = mapped_column(default=0)
    max_attempts: Mapped[int]
    available_at: Mapped[datetime] = mapped_column(server_default=func.now())
    lease_owner: Mapped[UUID | None] = mapped_column(ForeignKey("workers.id"))
    lease_expires_at: Mapped[datetime | None]
    heartbeat_at: Mapped[datetime | None]
    started_at: Mapped[datetime | None]
    completed_at: Mapped[datetime | None]
    __table_args__ = (
        UniqueConstraint("workflow_run_id", "workflow_step_id"),
        Index("ix_ready", "status", "available_at"),
        Index("ix_leases", "status", "lease_expires_at"),
        CheckConstraint(
            "status in ('PENDING','QUEUED','RUNNING','RETRY_WAIT','COMPLETED','FAILED','CANCELLED')"
        ),
    )


class Attempt(Base, Identity):
    __tablename__ = "execution_attempts"
    step_execution_id: Mapped[UUID] = mapped_column(ForeignKey("step_executions.id"))
    attempt_number: Mapped[int]
    worker_id: Mapped[UUID] = mapped_column(ForeignKey("workers.id"), index=True)
    status: Mapped[str]
    input_data: Mapped[dict[str, Any]]
    output_data: Mapped[dict[str, Any] | None]
    error_message: Mapped[str | None]
    started_at: Mapped[datetime]
    completed_at: Mapped[datetime | None]
    duration_ms: Mapped[int | None] = mapped_column(BigInteger)
    __table_args__ = (UniqueConstraint("step_execution_id", "attempt_number"),)


class Event(Base, Identity, Created):
    __tablename__ = "execution_events"
    workflow_run_id: Mapped[UUID | None] = mapped_column(ForeignKey("workflow_runs.id"))
    step_execution_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("step_executions.id")
    )
    event_type: Mapped[str] = mapped_column(index=True)
    message: Mapped[str]
    details: Mapped[dict[str, Any]] = mapped_column("metadata", default=dict)
    # Sequence breaks timestamp ties inside a single transaction.

    sequence: Mapped[int] = mapped_column(BigInteger, AutoIdentity(), unique=True)
    __table_args__ = (
        Index("ix_events_run_sequence", "workflow_run_id", "sequence"),
        Index("ix_events_created", "created_at"),
    )
