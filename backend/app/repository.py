from datetime import timedelta, timezone

from sqlalchemy import case, func, select

from . import queue
from .common import Problem
from .config import settings
from .db import database_time
from .models import Attempt, Event, Execution, Run, Step, Version, Worker, Workflow


def columns(model, omit=()):
    return [
        getattr(model, key) for key in model.__mapper__.attrs.keys() if key not in omit
    ]


def correlated_count(model, condition, parent):
    return (
        select(func.count())
        .select_from(model)
        .where(condition)
        .correlate(parent)
        .scalar_subquery()
    )


def workflow_rows():
    latest = (
        select(func.max(Version.version))
        .where(Version.workflow_id == Workflow.id)
        .correlate(Workflow)
        .scalar_subquery()
    )
    return select(
        *columns(Workflow),
        func.coalesce(latest, 0).label("latest_version"),
        correlated_count(Run, Run.workflow_id == Workflow.id, Workflow).label(
            "run_count"
        ),
    )


def run_rows():
    return select(
        *columns(Run, ["request_hash"]),
        Version.definition["name"].astext.label("workflow_name"),
        Version.version,
        correlated_count(Execution, Execution.workflow_run_id == Run.id, Run).label(
            "step_count"
        ),
    ).join(Version, Run.workflow_version_id == Version.id)


def step_rows():
    last_worker = (
        select(Attempt.worker_id)
        .where(Attempt.step_execution_id == Execution.id)
        .order_by(Attempt.attempt_number.desc())
        .limit(1)
        .correlate(Execution)
        .scalar_subquery()
    )
    return select(
        *columns(Execution),
        last_worker.label("worker_id"),
        Step.step_key.label("key"),
        Step.step_name.label("name"),
        Step.position,
        Step.task_type,
    ).join(Step)


def worker_rows():
    stale = Worker.last_heartbeat_at < func.now() - timedelta(
        seconds=settings.lease_seconds
    )
    status = case(
        (Worker.status == "OFFLINE", "OFFLINE"), (stale, "STALE"), else_=Worker.status
    )
    return select(
        *columns(Worker, ["status"]),
        status.label("status"),
        correlated_count(Attempt, Attempt.worker_id == Worker.id, Worker).label(
            "execution_count"
        ),
    )


def event_rows():
    return select(*columns(Event, ["details"]), Event.details.label("metadata"))


async def page(db, query, limit, offset):
    count = await db.scalar(
        select(func.count()).select_from(query.order_by(None).subquery())
    )
    rows = (await db.execute(query.limit(limit).offset(offset))).mappings().all()
    return dict(items=rows, total=count, limit=limit, offset=offset)


async def one(db, query):
    row = (await db.execute(query)).mappings().first()
    if row is None:
        raise Problem(404, "Resource not found")
    return row


def dates(query, column, start, end):
    for date in (start, end):
        if date is not None and date.utcoffset() is None:
            raise Problem(422, "Date filters require a timezone")
    if start and end and start > end:
        raise Problem(422, "Start date must precede end date")
    if start:
        query = query.where(column >= start)
    if end:
        query = query.where(column <= end)
    return query


async def stats(db):
    async def groups(model):
        return dict(
            (
                await db.execute(
                    select(model.status, func.count()).group_by(model.status)
                )
            ).all()
        )

    runs, tasks = await groups(Run), await groups(Execution)
    active = await active_worker_count(db)
    end = (
        (await database_time(db))
        .astimezone(timezone.utc)
        .replace(minute=0, second=0, microsecond=0)
    )
    buckets = {
        end - timedelta(hours=i): {"started": 0, "failed": 0, "completed": 0}
        for i in reversed(range(24))
    }
    hour = func.date_trunc("hour", Event.created_at)
    types = {
        "WORKFLOW_STARTED": "started",
        "WORKFLOW_COMPLETED": "completed",
        "WORKFLOW_FAILED": "failed",
    }
    rows = await db.execute(
        select(hour, Event.event_type, func.count())
        .where(Event.created_at >= min(buckets), Event.event_type.in_(types))
        .group_by(hour, Event.event_type)
    )
    for stamp, kind, count in rows:
        if stamp in buckets:
            buckets[stamp][types[kind]] = count
    return dict(
        total_workflows=await db.scalar(select(func.count()).select_from(Workflow)),
        total_runs=sum(runs.values()),
        pending_tasks=sum(tasks.get(s, 0) for s in ["PENDING", "QUEUED", "RETRY_WAIT"]),
        running_tasks=tasks.get("RUNNING", 0),
        running_runs=runs.get("RUNNING", 0),
        completed_runs=runs.get("COMPLETED", 0),
        failed_runs=runs.get("FAILED", 0),
        active_workers=active,
        activity=[dict(hour=h, **values) for h, values in buckets.items()],
    )


async def active_worker_count(db):
    return await db.scalar(
        select(func.count())
        .select_from(Worker)
        .where(
            Worker.status != "OFFLINE",
            Worker.last_heartbeat_at
            >= func.now() - timedelta(seconds=settings.lease_seconds),
        )
    )


async def health(db):
    from sqlalchemy.exc import SQLAlchemyError

    cache = await queue.available()
    pg, workers, counts = "healthy", "unavailable", {}
    try:
        counts = dict(
            (
                await db.execute(
                    select(Execution.status, func.count()).group_by(Execution.status)
                )
            ).all()
        )
        workers = "healthy" if await active_worker_count(db) else "unavailable"
    except (SQLAlchemyError, OSError):
        pg = "unavailable"
    return dict(
        api="healthy",
        postgres=pg,
        redis="healthy" if cache else "unavailable",
        workers=workers,
        queue=counts,
        environment=settings.environment,
        version=settings.version,
    )
