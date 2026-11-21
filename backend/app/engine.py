"""All writers lock the run before changing its executions, attempts or worker."""

from dataclasses import dataclass
from datetime import timedelta
from uuid import UUID

from sqlalchemy import func, select

from .common import Problem, event, required
from .config import settings
from .db import database_time
from .models import Attempt, Execution, Run, Step, Worker


@dataclass(frozen=True)
class Claim:
    run_id: UUID
    execution_id: UUID
    worker_id: UUID
    attempt: int
    task_type: str
    payload: dict
    configuration: dict
    timeout: int


def backoff(base, number, cap):
    return min(settings.max_retry_delay, cap, base * 2 ** min(number - 1, 20))


async def candidate(session, *conditions):
    query = (
        select(Run, Execution, Step)
        .join(Execution, Execution.workflow_run_id == Run.id)
        .join(Step, Step.id == Execution.workflow_step_id)
        .where(*conditions)
        .order_by(Execution.available_at, Execution.id)
        .limit(1)
        .with_for_update(of=Run, skip_locked=True)
    )
    return (await session.execute(query)).first()


async def claim(session, worker_id):
    row = await candidate(
        session,
        Run.status.in_(["PENDING", "RUNNING"]),
        Execution.status.in_(["QUEUED", "RETRY_WAIT"]),
        Execution.available_at <= func.clock_timestamp(),
    )
    if not row:
        return None
    run, ex, step = row
    await session.refresh(ex, with_for_update=True)
    if ex.status not in {
        "QUEUED",
        "RETRY_WAIT",
    } or ex.available_at > await database_time(session):
        return None
    worker = await required(session, Worker, worker_id, lock=True)
    if worker.current_task_id:
        return None
    now = await database_time(session)
    ex.status = run.status = "RUNNING"
    ex.attempt_count += 1
    ex.started_at = ex.started_at or now
    ex.error_message = None
    run.started_at = run.started_at or now
    ex.heartbeat_at = now
    ex.lease_owner, ex.lease_expires_at = (
        worker_id,
        now + timedelta(seconds=settings.lease_seconds),
    )
    worker.status, worker.current_task_id, worker.last_heartbeat_at = "BUSY", ex.id, now
    session.add(
        Attempt(
            step_execution_id=ex.id,
            attempt_number=ex.attempt_count,
            status="RUNNING",
            input_data=ex.input_data,
            worker_id=worker_id,
            started_at=now,
        )
    )
    event(
        session,
        "STEP_STARTED",
        f"Started {step.step_name}",
        run.id,
        ex.id,
        worker_id=worker_id,
        attempt_number=ex.attempt_count,
    )
    return Claim(
        run.id,
        ex.id,
        worker_id,
        ex.attempt_count,
        step.task_type,
        ex.input_data,
        step.configuration,
        step.timeout_seconds,
    )


async def owned(session, lease):
    run = await required(session, Run, lease.run_id, lock=True)
    ex = await session.get(Execution, lease.execution_id)
    now = await database_time(session)
    if (
        ex.status != "RUNNING"
        or ex.lease_owner != lease.worker_id
        or ex.attempt_count != lease.attempt
        or ex.lease_expires_at <= now
    ):
        return None
    return run, ex, now


async def renew(session, lease):
    row = await owned(session, lease)
    if not row:
        return False
    run, ex, now = row
    ex.lease_expires_at = now + timedelta(seconds=settings.lease_seconds)
    ex.heartbeat_at = now
    worker = await required(session, Worker, lease.worker_id, lock=True)
    worker.last_heartbeat_at = now
    event(
        session,
        "WORKER_HEARTBEAT",
        "Execution lease renewed",
        run.id,
        ex.id,
        worker_id=worker.id,
        attempt_number=lease.attempt,
    )
    return True


async def close_attempt(session, ex, now, status, error=None, output=None):
    attempt = await session.scalar(
        select(Attempt).where(
            Attempt.step_execution_id == ex.id,
            Attempt.attempt_number == ex.attempt_count,
        )
    )
    attempt.status, attempt.completed_at = status, now
    attempt.duration_ms = max(0, int((now - attempt.started_at).total_seconds() * 1000))
    attempt.error_message, attempt.output_data = error, output
    worker = await required(session, Worker, ex.lease_owner, lock=True)
    if worker.current_task_id == ex.id:
        worker.current_task_id, worker.status = None, "IDLE"
    ex.lease_owner = ex.lease_expires_at = None


async def fail(session, run, ex, step, now, error, status, permanent=False):
    await close_attempt(session, ex, now, status, error)
    ex.error_message = error
    event(
        session,
        "STEP_FAILED",
        error,
        run.id,
        ex.id,
        attempt_number=ex.attempt_count,
        cause=status,
    )
    if not permanent and ex.attempt_count < ex.max_attempts:
        delay = backoff(
            step.retry_delay_seconds, ex.attempt_count, step.max_delay_seconds
        )
        ex.status, ex.available_at = "RETRY_WAIT", now + timedelta(seconds=delay)
        event(
            session,
            "STEP_RETRY_SCHEDULED",
            f"Retry in {delay}s",
            run.id,
            ex.id,
            delay_seconds=delay,
        )
    else:
        ex.status = run.status = "FAILED"
        ex.completed_at = run.completed_at = now
        run.error_message = error
        event(session, "WORKFLOW_FAILED", f"{step.step_name} failed", run.id, ex.id)


async def finish(
    session, lease, output=None, error=None, permanent=False, status="FAILED"
):
    row = await owned(session, lease)
    if not row:
        return False
    run, ex, now = row
    step = await session.get(Step, ex.workflow_step_id)
    if error is not None:
        await fail(session, run, ex, step, now, error, status, permanent)
        return True
    await close_attempt(session, ex, now, "COMPLETED", output=output)
    ex.status, ex.output_data, ex.completed_at = "COMPLETED", output, now
    event(
        session,
        "STEP_COMPLETED",
        f"Completed {step.step_name}",
        run.id,
        ex.id,
        attempt_number=lease.attempt,
    )
    following = await session.scalar(
        select(Execution)
        .join(Step)
        .where(Execution.workflow_run_id == run.id, Step.position == step.position + 1)
    )
    if following:
        following.input_data = {
            "workflow_input": run.input_data,
            "previous_outputs": {
                **ex.input_data["previous_outputs"],
                step.step_key: output,
            },
        }
        following.status, following.available_at = "QUEUED", now
        event(session, "STEP_QUEUED", "Next step ready", run.id, following.id)
    else:
        run.status, run.output_data, run.completed_at = "COMPLETED", output, now
        event(session, "WORKFLOW_COMPLETED", "All steps completed", run.id)
    return True


async def recover(session):
    row = await candidate(
        session,
        Execution.status == "RUNNING",
        Execution.lease_expires_at <= func.clock_timestamp(),
    )
    if not row:
        return False
    run, ex, step = row
    now = await database_time(session)
    await session.refresh(ex, with_for_update=True)
    if ex.status != "RUNNING" or ex.lease_expires_at > now:
        return False
    event(
        session,
        "LEASE_EXPIRED",
        "Worker lease expired",
        run.id,
        ex.id,
        worker_id=ex.lease_owner,
    )
    await fail(session, run, ex, step, now, "Worker lease expired", "ABANDONED")
    if ex.status == "RETRY_WAIT":
        event(
            session,
            "STEP_RECOVERED",
            "Abandoned step returned to the queue",
            run.id,
            ex.id,
        )
    return True


ALLOWED = {
    "pause": {"PENDING", "RUNNING"},
    "resume": {"PAUSED"},
    "retry": {"FAILED"},
    "cancel": {"PENDING", "RUNNING", "PAUSED"},
}


async def control(session, rid, action, execution_id=None):
    run = await required(session, Run, rid, lock=True)
    if execution_id:
        target = await required(session, Execution, execution_id)
        if target.workflow_run_id != rid:
            raise Problem(404, "Step execution not found in this run")
    if run.status not in ALLOWED[action]:
        raise Problem(409, f"Cannot {action} a {run.status.lower()} run")
    now = await database_time(session)
    if action == "pause":
        run.status = "PAUSED"
        event(session, "WORKFLOW_PAUSED", "New claims paused", rid)
    elif action == "resume":
        run.status = "RUNNING" if run.started_at else "PENDING"
        event(session, "WORKFLOW_RESUMED", "Execution resumed", rid)
    elif action == "retry":
        ex = await session.scalar(
            select(Execution).where(
                Execution.workflow_run_id == rid, Execution.status == "FAILED"
            )
        )
        if not ex or (execution_id and execution_id != ex.id):
            raise Problem(409, "Only the failed step is eligible for retry")
        ex.status, ex.available_at, ex.max_attempts = (
            "QUEUED",
            now,
            ex.attempt_count + 1,
        )
        ex.completed_at = ex.error_message = run.error_message = run.completed_at = None
        run.status = "RUNNING"
        event(
            session,
            "STEP_QUEUED",
            "Manual retry granted one additional attempt",
            rid,
            ex.id,
        )
    else:
        rows = await session.scalars(
            select(Execution).where(
                Execution.workflow_run_id == rid, Execution.status != "COMPLETED"
            )
        )
        for ex in rows:
            if ex.status == "RUNNING":
                await close_attempt(
                    session, ex, now, "CANCELLED", "Operator cancelled the run"
                )
            ex.status, ex.completed_at = "CANCELLED", now
        run.status, run.completed_at = "CANCELLED", now
        event(session, "WORKFLOW_CANCELLED", "Operator cancelled the run", rid)
    return run
