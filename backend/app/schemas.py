from datetime import datetime
from typing import Any, Generic, Literal, TypeVar
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from .tasks import registry

RunState = Literal["PENDING", "RUNNING", "PAUSED", "COMPLETED", "FAILED", "CANCELLED"]
StepState = Literal[
    "PENDING", "QUEUED", "RUNNING", "RETRY_WAIT", "COMPLETED", "FAILED", "CANCELLED"
]
Json = dict[str, Any]


class Strict(BaseModel):
    model_config = ConfigDict(
        extra="forbid", str_strip_whitespace=True, allow_inf_nan=False
    )


class Retry(Strict):
    max_attempts: int = Field(3, ge=1, le=20)
    delay_seconds: int = Field(2, ge=0, le=3600)
    max_delay_seconds: int = Field(300, ge=1, le=3600)


class StepSpec(Strict):
    key: str = Field(pattern=r"^[a-z][a-z0-9_-]{0,63}$")
    name: str = Field(min_length=1, max_length=120)
    task_type: str
    config: Json = Field(default_factory=dict)
    retry: Retry = Field(default_factory=Retry)
    timeout_seconds: int = Field(30, ge=1, le=600)

    @model_validator(mode="after")
    def known_task(self):
        if self.task_type not in registry:
            raise ValueError("Unknown task type")
        registry[self.task_type].config.model_validate(self.config)
        return self


class Definition(Strict):
    name: str = Field(min_length=1, max_length=120)
    description: str = Field(default="", max_length=2000)
    steps: list[StepSpec] = Field(min_length=1, max_length=40)

    @field_validator("steps")
    @classmethod
    def sequential(cls, steps):
        keys = set()
        for step in steps:
            if step.key in keys:
                raise ValueError("Step keys must be unique")
            source = step.config.get("source")
            if source is not None and source not in keys:
                raise ValueError("A source must name an earlier step")
            keys.add(step.key)
        return steps


class Draft(Definition):
    workflow_key: str | None = Field(None, pattern=r"^[a-z][a-z0-9_-]{0,119}$")


class Start(Strict):
    input_data: Json = Field(default_factory=dict)
    idempotency_key: str | None = Field(None, min_length=1, max_length=200)
    version: int | None = Field(None, ge=1)


class Record(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID


class WorkflowOut(Record):
    name: str
    description: str | None
    workflow_key: str
    status: str
    draft: Definition
    latest_version: int = 0
    run_count: int = 0
    created_at: datetime
    updated_at: datetime


class VersionOut(Record):
    workflow_id: UUID
    version: int
    definition: Definition
    created_at: datetime


class RunOut(Record):
    workflow_id: UUID
    workflow_version_id: UUID
    workflow_name: str
    version: int
    status: RunState
    input_data: Json
    output_data: Json | None
    error_message: str | None
    created_at: datetime
    started_at: datetime | None
    completed_at: datetime | None
    updated_at: datetime
    step_count: int
    idempotency_key: str | None


class StepOut(Record):
    workflow_run_id: UUID
    workflow_step_id: UUID
    name: str
    key: str
    task_type: str
    position: int
    status: StepState
    input_data: Json
    output_data: Json | None
    error_message: str | None
    attempt_count: int
    max_attempts: int
    available_at: datetime
    worker_id: UUID | None
    lease_owner: UUID | None
    lease_expires_at: datetime | None
    heartbeat_at: datetime | None
    started_at: datetime | None
    completed_at: datetime | None


class AttemptOut(Record):
    step_execution_id: UUID
    attempt_number: int
    worker_id: UUID
    status: str
    input_data: Json
    output_data: Json | None
    error_message: str | None
    started_at: datetime
    completed_at: datetime | None
    duration_ms: int | None


class EventOut(Record):
    workflow_run_id: UUID | None
    step_execution_id: UUID | None
    event_type: str
    message: str
    metadata: Json
    created_at: datetime
    sequence: int


class WorkerOut(Record):
    worker_name: str
    hostname: str
    status: str
    registered_at: datetime
    last_heartbeat_at: datetime
    current_task_id: UUID | None
    execution_count: int


T = TypeVar("T")


class Page(BaseModel, Generic[T]):
    items: list[T]
    total: int
    limit: int
    offset: int


class Timeline(BaseModel):
    run: RunOut
    steps: list[StepOut]
    events: Page[EventOut]


class TaskInfo(BaseModel):
    task_type: str
    description: str
    config_schema: Json


class Bucket(BaseModel):
    hour: datetime
    completed: int
    failed: int
    started: int


class Stats(BaseModel):
    total_workflows: int
    total_runs: int
    pending_tasks: int
    running_tasks: int
    running_runs: int
    completed_runs: int
    failed_runs: int
    active_workers: int
    activity: list[Bucket]


class Health(BaseModel):
    api: str
    postgres: str
    redis: str
    workers: str
    queue: dict[str, int]
    version: str
    environment: str
