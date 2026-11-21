import hashlib
import json
from uuid import uuid4

from sqlalchemy import func, select

from .common import Problem, event, required
from .models import Execution, Run, Step, Version, Workflow
from .schemas import Definition


async def create(session, draft):
    key = draft.workflow_key or f"wf-{uuid4().hex[:16]}"
    if await session.scalar(select(Workflow.id).where(Workflow.workflow_key == key)):
        raise Problem(409, "Workflow key already exists")
    definition = draft.model_dump(exclude={"workflow_key"})
    wf = Workflow(
        name=draft.name,
        description=draft.description,
        workflow_key=key,
        draft=definition,
    )
    session.add(wf)
    await session.flush()
    event(session, "WORKFLOW_CREATED", "Draft created", workflow_id=wf.id)
    return wf


async def edit(session, wid, draft):
    wf = await required(session, Workflow, wid, lock=True)
    if draft.workflow_key and draft.workflow_key != wf.workflow_key:
        raise Problem(409, "The workflow key is immutable")
    wf.name, wf.description = draft.name, draft.description
    wf.draft = draft.model_dump(exclude={"workflow_key"})
    return wf


async def publish(session, wid):
    wf = await required(session, Workflow, wid, lock=True)
    draft = Definition.model_validate(wf.draft)
    number = (
        await session.scalar(
            select(func.max(Version.version)).where(Version.workflow_id == wid)
        )
        or 0
    )
    version = Version(
        workflow_id=wid, version=number + 1, definition=draft.model_dump()
    )
    session.add(version)
    await session.flush()
    for i, spec in enumerate(draft.steps):
        session.add(
            Step(
                workflow_version_id=version.id,
                position=i,
                step_key=spec.key,
                step_name=spec.name,
                task_type=spec.task_type,
                configuration=spec.config,
                retry_limit=spec.retry.max_attempts,
                retry_delay_seconds=spec.retry.delay_seconds,
                max_delay_seconds=spec.retry.max_delay_seconds,
                timeout_seconds=spec.timeout_seconds,
            )
        )
    wf.status = "active"
    event(
        session,
        "WORKFLOW_PUBLISHED",
        f"Published version {version.version}",
        workflow_id=wid,
        version=version.version,
    )
    return version


async def delete_draft(session, wid):
    wf = await required(session, Workflow, wid, lock=True)
    if wf.status != "draft":
        raise Problem(409, "Published workflows have retained versions")
    await session.delete(wf)


def canonical_numbers(value):
    if isinstance(value, dict):
        return {key: canonical_numbers(item) for key, item in value.items()}
    if isinstance(value, list):
        return [canonical_numbers(item) for item in value]
    if isinstance(value, float) and value.is_integer():
        return int(value)
    return value


async def start(session, wid, request):
    await required(session, Workflow, wid, lock=True)
    signature = hashlib.sha256(
        json.dumps(
            [request.version, canonical_numbers(request.input_data)],
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode()
    ).hexdigest()
    if request.idempotency_key:
        old = await session.scalar(
            select(Run).where(
                Run.workflow_id == wid, Run.idempotency_key == request.idempotency_key
            )
        )
        if old:
            if old.request_hash != signature:
                raise Problem(
                    409, "Idempotency key already used with different input or version"
                )
            return old, False
    query = select(Version).where(Version.workflow_id == wid)
    if request.version is not None:
        query = query.where(Version.version == request.version)
    version = await session.scalar(query.order_by(Version.version.desc()).limit(1))
    if version is None:
        raise Problem(
            404 if request.version is not None else 409,
            "Publish or select an existing version before starting",
        )
    run = Run(
        workflow_id=wid,
        workflow_version_id=version.id,
        status="PENDING",
        input_data=request.input_data,
        idempotency_key=request.idempotency_key,
        request_hash=signature,
    )
    session.add(run)
    await session.flush()
    event(session, "WORKFLOW_STARTED", "Run accepted", run.id, version=version.version)
    steps = await session.scalars(
        select(Step)
        .where(Step.workflow_version_id == version.id)
        .order_by(Step.position)
    )
    for step in steps:
        first = step.position == 0
        row = Execution(
            workflow_run_id=run.id,
            workflow_step_id=step.id,
            status="QUEUED" if first else "PENDING",
            input_data={"workflow_input": request.input_data, "previous_outputs": {}}
            if first
            else {},
            max_attempts=step.retry_limit,
        )
        session.add(row)
        if first:
            await session.flush()
            event(session, "STEP_QUEUED", f"Queued {step.step_name}", run.id, row.id)
    return run, True
