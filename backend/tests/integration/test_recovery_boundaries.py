from concurrent.futures import ThreadPoolExecutor
from uuid import uuid4

from sqlalchemy import text

from app import engine
from app.db import transaction
from app.worker import dispatch, register
from legacy import worker as prototype
from legacy.core import SessionLocal
from legacy.models import OutboxEvent, Workflow, WorkflowStep
from .conftest import get_claim, step, submit


async def expire(lease):
    async with transaction() as db:
        await db.execute(
            text(
                "UPDATE durable.step_executions SET lease_expires_at = now() - interval '1 second' WHERE id = :id"
            ),
            {"id": lease.execution_id},
        )
        assert await engine.recover(db)


async def test_abandonment_consumes_final_attempt(api):
    _, rid = await submit(api, [step("final", attempts=1)])
    worker = await register()
    await expire(await get_claim(worker))
    assert await get_claim(worker) is None
    assert (await api.get(f"runs/{rid}")).json()["status"] == "FAILED"
    assert (await api.get(f"runs/{rid}/attempts")).json()["items"][0][
        "status"
    ] == "ABANDONED"


async def test_recovery_respects_operator_pause(api):
    _, rid = await submit(api, [step("pauseable")])
    worker = await register()
    lease = await get_claim(worker)
    await api.post(f"runs/{rid}/pause")
    await expire(lease)
    assert await get_claim(worker) is None
    assert (await api.get(f"runs/{rid}/steps")).json()["items"][0][
        "status"
    ] == "RETRY_WAIT"
    await api.post(f"runs/{rid}/resume")
    await dispatch(await get_claim(worker))
    assert (await api.get(f"runs/{rid}")).json()["status"] == "COMPLETED"


def test_legacy_concurrent_claim_and_outbox(monkeypatch):
    wid = str(uuid4())
    with SessionLocal.begin() as db:
        wf = Workflow(
            id=wid,
            tenant_id=str(uuid4()),
            name="Original prototype",
            input={"value": "stable"},
        )
        wf.steps.append(
            WorkflowStep(position=0, name="echo", config={"action": "echo"})
        )
        db.add(wf)
        db.add(
            OutboxEvent(
                event_type="workflow.submitted",
                aggregate_id=wid,
                dedupe_key=wid,
                payload={"workflow_id": wid},
            )
        )
    with ThreadPoolExecutor(max_workers=2) as pool:
        claims = list(pool.map(prototype.claim_next_step, [wid, wid]))
    assert sum(claim is not None for claim in claims) == 1
    with SessionLocal() as db:
        wf = db.get(Workflow, wid)
        result = prototype.execute_action(wf.steps[0], wf)
        assert result["idempotency_key"] == f"{wid}:step:{wf.steps[0].id}"
        assert prototype.execute_action(wf.steps[0], wf) == result
    deliveries = []
    monkeypatch.setattr(
        prototype.redis, "lpush", lambda name, value: deliveries.append(value)
    )
    prototype.publish_outbox()
    prototype.publish_outbox()
    assert deliveries.count(wid) == 1
