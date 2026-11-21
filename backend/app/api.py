from datetime import datetime
from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Response
from pydantic import BaseModel
from sqlalchemy import String, cast, or_, select

from . import engine, queue, repository as repo, workflows
from .common import required
from .db import transaction
from .models import Attempt, Event, Execution, Run, Step, Version, Worker, Workflow
from .schemas import (
    AttemptOut,
    Definition,
    Draft,
    EventOut,
    Health,
    Page,
    RunOut,
    RunState,
    Start,
    Stats,
    StepOut,
    StepState,
    TaskInfo,
    Timeline,
    VersionOut,
    WorkerOut,
    WorkflowOut,
)
from .tasks import registry

router = APIRouter(prefix="/api/v1")
Limit = Annotated[int, Query(ge=1, le=200)]
Offset = Annotated[int, Query(ge=0)]
Search = Annotated[str, Query(max_length=120)]


async def session():
    async with transaction() as db:
        yield db


DB = Depends(session)


@router.get("/system/health", response_model=Health)
async def health(db=DB):
    return await repo.health(db)


@router.get("/system/stats", response_model=Stats)
async def stats(db=DB):
    return await repo.stats(db)


@router.get("/workers", response_model=Page[WorkerOut])
async def workers(limit: Limit = 30, offset: Offset = 0, db=DB):
    return await repo.page(
        db,
        repo.worker_rows().order_by(Worker.registered_at.desc(), Worker.id),
        limit,
        offset,
    )


@router.get("/workers/{worker_id}", response_model=WorkerOut)
async def worker(worker_id: UUID, db=DB):
    return await repo.one(db, repo.worker_rows().where(Worker.id == worker_id))


@router.get("/workers/{worker_id}/executions", response_model=Page[AttemptOut])
async def worker_executions(
    worker_id: UUID, limit: Limit = 30, offset: Offset = 0, db=DB
):
    await required(db, Worker, worker_id)
    return await repo.page(
        db,
        select(*repo.columns(Attempt))
        .where(Attempt.worker_id == worker_id)
        .order_by(Attempt.started_at.desc(), Attempt.id),
        limit,
        offset,
    )


@router.post("/workflows", response_model=WorkflowOut, status_code=201)
async def create(body: Draft, db=DB):
    wf = await workflows.create(db, body)
    return await repo.one(db, repo.workflow_rows().where(Workflow.id == wf.id))


@router.get("/workflows", response_model=Page[WorkflowOut])
async def listing(
    search: Search = "",
    status: Literal["draft", "active"] | None = None,
    limit: Limit = 30,
    offset: Offset = 0,
    db=DB,
):
    query = repo.workflow_rows()
    if search:
        query = query.where(
            or_(
                Workflow.name.icontains(search, autoescape=True),
                Workflow.workflow_key.icontains(search, autoescape=True),
            )
        )
    if status:
        query = query.where(Workflow.status == status)
    return await repo.page(
        db, query.order_by(Workflow.created_at.desc(), Workflow.id), limit, offset
    )


@router.get("/workflows/{workflow_id}", response_model=WorkflowOut)
async def workflow(workflow_id: UUID, db=DB):
    return await repo.one(db, repo.workflow_rows().where(Workflow.id == workflow_id))


@router.put("/workflows/{workflow_id}", response_model=WorkflowOut)
async def edit(workflow_id: UUID, body: Draft, db=DB):
    await workflows.edit(db, workflow_id, body)
    return await workflow(workflow_id, db)


@router.delete("/workflows/{workflow_id}", status_code=204)
async def delete(workflow_id: UUID, db=DB):
    await workflows.delete_draft(db, workflow_id)


class Validation(BaseModel):
    valid: bool
    step_count: int


@router.post("/definitions/validate", response_model=Validation)
async def validate_unsaved(body: Definition):
    return Validation(valid=True, step_count=len(body.steps))


@router.post("/workflows/{workflow_id}/validate", response_model=Validation)
async def validate(workflow_id: UUID, db=DB):
    wf = await required(db, Workflow, workflow_id)
    definition = Definition.model_validate(wf.draft)
    return Validation(valid=True, step_count=len(definition.steps))


@router.post(
    "/workflows/{workflow_id}/publish", response_model=VersionOut, status_code=201
)
async def publish(workflow_id: UUID, db=DB):
    return await workflows.publish(db, workflow_id)


@router.get("/workflows/{workflow_id}/versions", response_model=Page[VersionOut])
async def versions(workflow_id: UUID, limit: Limit = 30, offset: Offset = 0, db=DB):
    await required(db, Workflow, workflow_id)
    return await repo.page(
        db,
        select(*repo.columns(Version))
        .where(Version.workflow_id == workflow_id)
        .order_by(Version.version.desc()),
        limit,
        offset,
    )


@router.get("/workflows/{workflow_id}/versions/{version}", response_model=VersionOut)
async def version(workflow_id: UUID, version: int, db=DB):
    return await repo.one(
        db,
        select(*repo.columns(Version)).where(
            Version.workflow_id == workflow_id, Version.version == version
        ),
    )


@router.post("/workflows/{workflow_id}/runs", response_model=RunOut, status_code=201)
async def start(workflow_id: UUID, body: Start, response: Response):
    async with transaction() as db:
        run, created = await workflows.start(db, workflow_id, body)
        result = await repo.one(db, repo.run_rows().where(Run.id == run.id))
    if created:
        await queue.notify()
    else:
        response.status_code = 200
    return result


@router.get("/runs", response_model=Page[RunOut])
async def runs(
    status: RunState | None = None,
    workflow_id: UUID | None = None,
    search: Search = "",
    date_from: datetime | None = None,
    date_to: datetime | None = None,
    limit: Limit = 30,
    offset: Offset = 0,
    db=DB,
):
    query = repo.dates(repo.run_rows(), Run.created_at, date_from, date_to)
    if status:
        query = query.where(Run.status == status)
    if workflow_id:
        query = query.where(Run.workflow_id == workflow_id)
    if search:
        query = query.where(
            or_(
                cast(Run.id, String).icontains(search, autoescape=True),
                Version.definition["name"].astext.icontains(search, autoescape=True),
            )
        )
    return await repo.page(
        db, query.order_by(Run.created_at.desc(), Run.id), limit, offset
    )


@router.get("/runs/{run_id}", response_model=RunOut)
async def run_detail(run_id: UUID, db=DB):
    return await repo.one(db, repo.run_rows().where(Run.id == run_id))


@router.get("/runs/{run_id}/steps", response_model=Page[StepOut])
async def run_steps(run_id: UUID, limit: Limit = 50, offset: Offset = 0, db=DB):
    await required(db, Run, run_id)
    return await repo.page(
        db,
        repo.step_rows()
        .where(Execution.workflow_run_id == run_id)
        .order_by(Step.position),
        limit,
        offset,
    )


@router.get("/runs/{run_id}/attempts", response_model=Page[AttemptOut])
async def attempts(run_id: UUID, limit: Limit = 50, offset: Offset = 0, db=DB):
    await required(db, Run, run_id)
    query = (
        select(*repo.columns(Attempt))
        .join(Execution)
        .where(Execution.workflow_run_id == run_id)
    )
    return await repo.page(
        db, query.order_by(Attempt.started_at, Attempt.id), limit, offset
    )


@router.get("/runs/{run_id}/events", response_model=Page[EventOut])
async def run_events(run_id: UUID, limit: Limit = 50, offset: Offset = 0, db=DB):
    await required(db, Run, run_id)
    return await repo.page(
        db,
        repo.event_rows()
        .where(Event.workflow_run_id == run_id)
        .order_by(Event.sequence),
        limit,
        offset,
    )


@router.get("/runs/{run_id}/timeline", response_model=Timeline)
async def timeline(run_id: UUID, limit: Limit = 50, offset: Offset = 0, db=DB):
    return dict(
        run=await run_detail(run_id, db),
        steps=(await run_steps(run_id, 40, 0, db))["items"],
        events=await run_events(run_id, limit, offset, db),
    )


async def change(run_id, action, execution_id=None):
    async with transaction() as db:
        await engine.control(db, run_id, action, execution_id)
        result = await run_detail(run_id, db)
    await queue.notify()
    return result


@router.post("/runs/{run_id}/cancel", response_model=RunOut)
async def cancel(run_id: UUID):
    return await change(run_id, "cancel")


@router.post("/runs/{run_id}/pause", response_model=RunOut)
async def pause(run_id: UUID):
    return await change(run_id, "pause")


@router.post("/runs/{run_id}/resume", response_model=RunOut)
async def resume(run_id: UUID):
    return await change(run_id, "resume")


@router.post("/runs/{run_id}/retry", response_model=RunOut)
async def retry(run_id: UUID):
    return await change(run_id, "retry")


@router.post("/runs/{run_id}/steps/{step_execution_id}/retry", response_model=RunOut)
async def retry_step(run_id: UUID, step_execution_id: UUID):
    return await change(run_id, "retry", step_execution_id)


@router.get("/tasks/registry", response_model=list[TaskInfo])
async def registered():
    return [
        dict(
            task_type=k,
            description=t.description,
            config_schema=t.config.model_json_schema(),
        )
        for k, t in registry.items()
    ]


@router.get("/tasks", response_model=Page[StepOut])
async def tasks(
    status: StepState | None = None, limit: Limit = 30, offset: Offset = 0, db=DB
):
    query = repo.step_rows()
    if status:
        query = query.where(Execution.status == status)
    return await repo.page(
        db, query.order_by(Execution.created_at.desc(), Execution.id), limit, offset
    )


@router.get("/tasks/{task_execution_id}", response_model=StepOut)
async def task(task_execution_id: UUID, db=DB):
    return await repo.one(db, repo.step_rows().where(Execution.id == task_execution_id))


@router.get("/tasks/{task_execution_id}/attempts", response_model=Page[AttemptOut])
async def task_attempts(
    task_execution_id: UUID, limit: Limit = 50, offset: Offset = 0, db=DB
):
    await required(db, Execution, task_execution_id)
    return await repo.page(
        db,
        select(*repo.columns(Attempt))
        .where(Attempt.step_execution_id == task_execution_id)
        .order_by(Attempt.attempt_number),
        limit,
        offset,
    )


@router.get("/events", response_model=Page[EventOut])
async def events(
    event_type: Annotated[str | None, Query(max_length=80)] = None,
    workflow_run_id: UUID | None = None,
    date_from: datetime | None = None,
    date_to: datetime | None = None,
    limit: Limit = 50,
    offset: Offset = 0,
    db=DB,
):
    query = repo.dates(repo.event_rows(), Event.created_at, date_from, date_to)
    if event_type:
        query = query.where(Event.event_type == event_type)
    if workflow_run_id:
        query = query.where(Event.workflow_run_id == workflow_run_id)
    return await repo.page(db, query.order_by(Event.sequence.desc()), limit, offset)
