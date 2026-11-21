import asyncio
from uuid import uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from app import engine
from app.db import transaction
from app.worker import dispatch, register
from .conftest import drain, get_claim, step, submit


async def test_sequential_outputs_and_monitoring_inventory(api):
    wid, rid = await submit(
        api,
        [
            step("first", "text.transform"),
            step("second", "text.concatenate", {"source": "first", "suffix": "!"}),
        ],
        {"text": "ok"},
    )
    worker = await drain()
    timeline = (await api.get(f"runs/{rid}/timeline")).json()
    assert (
        timeline["run"]["output_data"] == {"text": "OK!"}
        and timeline["run"]["status"] == "COMPLETED"
    )
    assert [s["attempt_count"] for s in timeline["steps"]] == [1, 1]
    events = timeline["events"]["items"]
    assert (
        events[0]["event_type"] == "WORKFLOW_STARTED"
        and events[-1]["event_type"] == "WORKFLOW_COMPLETED"
    )
    assert [e["sequence"] for e in events] == sorted(e["sequence"] for e in events)
    sid = timeline["steps"][1]["id"]
    for path in [
        "system/stats",
        "system/health",
        "workers",
        f"workers/{worker}",
        f"workers/{worker}/executions",
        "tasks?status=COMPLETED",
        f"tasks/{sid}",
        f"tasks/{sid}/attempts",
        "tasks/registry",
        f"runs/{rid}/steps",
        f"runs/{rid}/attempts",
        f"events?workflow_run_id={rid}",
        f"workflows/{wid}/versions",
    ]:
        res = await api.get(path)
        assert res.status_code == 200, (path, res.text)
    assert (await api.get(f"workers/{worker}")).json()["execution_count"] == 2
    assert (await api.post(f"runs/{rid}/retry")).status_code == 409


async def test_concurrent_idempotency_and_version_replay(api):
    wid, _ = await submit(api, [step("first")])
    path = f"workflows/{wid}/runs"
    requests = [
        api.post(path, json={"input_data": dict(a=1, b=2), "idempotency_key": "k"}),
        api.post(path, json={"input_data": dict(b=2.0, a=1), "idempotency_key": "k"}),
    ]
    responses = await asyncio.gather(*requests)
    assert sorted(r.status_code for r in responses) == [200, 201]
    old = responses[0].json()
    assert responses[1].json()["id"] == old["id"]
    assert (
        await api.put(
            f"workflows/{wid}", json={"name": "Edited", "steps": [step("other")]}
        )
    ).status_code == 200
    assert (await api.post(f"workflows/{wid}/publish")).json()["version"] == 2
    assert (await api.get(f"workflows/{wid}/versions/1")).json()["definition"][
        "name"
    ] == "Testing"
    assert (
        await api.post(
            path, json={"input_data": {"b": 2, "a": 1}, "idempotency_key": "k"}
        )
    ).json()["version"] == 1
    assert (await api.post(path, json={"idempotency_key": "k"})).status_code == 409
    assert (await api.post(path, json={"version": 1})).json()["version"] == 1
    assert (await api.post(path, json={"version": 3})).status_code == 404
    assert (await api.delete(f"workflows/{wid}")).status_code == 409


async def test_pause_running_boundary_and_cancel(api):
    _, rid = await submit(
        api, [step("one"), step("two", "system.sleep", {"seconds": 3})]
    )
    w = await register()
    lease = await get_claim(w)
    assert (await api.post(f"runs/{rid}/pause")).json()["status"] == "PAUSED"
    await dispatch(lease)
    assert await get_claim(w) is None
    assert (await api.post(f"runs/{rid}/resume")).status_code == 200
    lease = await get_claim(w)
    working = asyncio.create_task(dispatch(lease))
    await asyncio.sleep(0.05)
    assert (await api.post(f"runs/{rid}/cancel")).json()["status"] == "CANCELLED"
    await asyncio.wait_for(working, 1.5)
    assert (await api.get(f"runs/{rid}/attempts")).json()["items"][-1][
        "status"
    ] == "CANCELLED"
    assert (await api.post(f"runs/{rid}/resume")).status_code == 409
    assert await get_claim(w) is None


async def test_crash_expiration_heartbeat_and_fencing(api):
    _, rid = await submit(api, [step("claim")])
    a, b = await asyncio.gather(register(), register())
    claims = await asyncio.gather(get_claim(a), get_claim(b))
    assert sum(c is not None for c in claims) == 1
    old = next(c for c in claims if c)
    async with transaction() as db:
        assert await engine.renew(db, old)
        assert not await engine.recover(db)
    await asyncio.sleep(2.1)
    assert (await api.get(f"workers/{old.worker_id}")).json()["status"] == "STALE"
    async with transaction() as db:
        assert not await engine.renew(db, old)
        assert not await engine.finish(db, old, output={"stale": True})
        assert await engine.recover(db)
    new = await get_claim(b if old.worker_id == a else a)
    assert new.execution_id == old.execution_id and new.attempt == 2
    async with transaction() as db:
        assert not await engine.finish(db, old, error="late failure")
    await dispatch(new)
    result = (await api.get(f"runs/{rid}/attempts")).json()
    assert [a["status"] for a in result["items"]] == ["ABANDONED", "COMPLETED"]
    assert (await api.get(f"runs/{rid}")).json()["status"] == "COMPLETED"


async def test_exhaustion_and_manual_step_retry(api):
    _, rid = await submit(
        api, [step("first"), step("bad", "system.fail", attempts=3), step("later")]
    )
    await drain()
    assert (await api.get(f"runs/{rid}")).json()["status"] == "FAILED"
    steps = (await api.get(f"runs/{rid}/steps")).json()["items"]
    assert [s["attempt_count"] for s in steps] == [1, 3, 0]
    assert (
        await api.post(f"runs/{rid}/steps/{steps[0]['id']}/retry")
    ).status_code == 409
    assert (
        await api.post(f"runs/{rid}/steps/{steps[1]['id']}/retry")
    ).status_code == 200
    await drain()
    assert (await api.post(f"runs/{rid}/retry")).status_code == 200
    await drain()
    hist = (await api.get(f"tasks/{steps[1]['id']}/attempts")).json()["items"]
    assert [a["attempt_number"] for a in hist] == [1, 2, 3, 4, 5]


@pytest.mark.parametrize(
    "spec,expected",
    [
        (step("bad", "system.fail", {"permanent": True}), ["FAILED"]),
        (
            step("slow", "system.sleep", {"seconds": 2}, attempts=1, timeout=1),
            ["TIMED_OUT"],
        ),
        (
            step(
                "flaky", "system.random_failure", {"probability": 1, "until_attempt": 1}
            ),
            ["FAILED", "COMPLETED"],
        ),
    ],
)
async def test_failure_classification(api, spec, expected):
    _, rid = await submit(api, [spec])
    await drain()
    assert [
        a["status"] for a in (await api.get(f"runs/{rid}/attempts")).json()["items"]
    ] == expected


async def test_immutability_and_draft_deletion(api):
    wid, rid = await submit(api, [step("one")])
    for sql in [
        "UPDATE durable.workflow_versions SET version=90",
        "DELETE FROM durable.execution_events",
        "UPDATE durable.workflow_steps SET position=90",
    ]:
        with pytest.raises(DBAPIError):
            async with transaction() as db:
                await db.execute(text(sql))
    draft = (
        await api.post("workflows", json={"name": "Unsaved", "steps": [step("a")]})
    ).json()
    assert (await api.delete("workflows/" + draft["id"])).status_code == 204
    assert (await api.get("workflows/" + draft["id"])).status_code == 404


async def test_pagination_validation_and_payload_limits(api):
    await submit(api, [step("first")])
    await submit(api, [step("second")])
    p = (
        await api.get("workflows?status=active&limit=1&offset=1&search=Testing")
    ).json()
    assert p["total"] == 2 and len(p["items"]) == 1
    for path in [
        "runs?limit=0",
        "runs?offset=-1",
        "runs?status=INVALID",
        "runs?date_from=2025-01-01",
        "tasks/not-a-uuid",
    ]:
        assert (await api.get(path)).status_code == 422
    assert (await api.post("workflows", json={"name": "x" * 70000})).status_code == 413
    assert (
        await api.post(
            "workflows",
            content='{"bad":NaN}',
            headers={"content-type": "application/json"},
        )
    ).status_code == 422
    assert (
        await api.post(
            "definitions/validate",
            json={"name": "Bad", "steps": [step("x", "unknown")]},
        )
    ).status_code == 422
    assert (await api.get(f"runs/{uuid4()}/events")).status_code == 404


async def test_legacy_tenant_auth_submission_and_execution(api):
    from httpx import ASGITransport, AsyncClient
    from app.main import app
    from legacy.worker import process

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as c:

        async def auth():
            email = f"{uuid4().hex}@example.com"
            resp = await c.post(
                "/auth/register", json={"email": email, "password": "testing-password"}
            )
            assert resp.status_code == 200, resp.text
            return {"Authorization": "Bearer " + resp.json()["token"]}

        a, b = await auth(), await auth()
        body = dict(
            name="Legacy",
            input={"value": "ok"},
            steps=[dict(name="echo", action="echo")],
            idempotency_key="one",
        )
        old = await c.post("/workflows", json=body, headers=a)
        assert old.status_code == 201, old.text
        rid = old.json()["id"]
        assert (await c.post("/workflows", json=body, headers=a)).json()["id"] == rid
        assert (await c.get("/workflows/" + rid, headers=b)).status_code == 404
        await asyncio.to_thread(process, rid)
        assert (await c.get("/workflows/" + rid, headers=a)).json()["steps"][0][
            "output"
        ]["value"] == "ok"
