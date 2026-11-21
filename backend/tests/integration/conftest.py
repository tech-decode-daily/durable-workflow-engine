import os

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.engine import make_url

from app import engine
from app.db import transaction
from app.main import app
from app.models import Base
from app.worker import dispatch, register


@pytest.fixture(autouse=True)
async def isolated():
    url = make_url(os.environ.get("DATABASE_URL", "postgresql:///unknown"))
    if url.database != os.getenv("DURABLE_TEST_DB") or not url.database.startswith(
        "durable_test_"
    ):
        pytest.skip("Use python -m tests.run to provision the isolated database")
    async with transaction() as db:
        tables = ", ".join("durable." + t.name for t in Base.metadata.tables.values())
        await db.execute(text("TRUNCATE " + tables + " RESTART IDENTITY"))


@pytest.fixture
async def api():
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test/api/v1"
    ) as client:
        yield client


def step(key, task="data.validate_json", config=None, attempts=3, timeout=30):
    return dict(
        key=key,
        name=key.title(),
        task_type=task,
        config=config or {},
        retry=dict(max_attempts=attempts, delay_seconds=0),
        timeout_seconds=timeout,
    )


async def submit(api, steps, data=None):
    w = await api.post("workflows", json={"name": "Testing", "steps": steps})
    assert w.status_code == 201, w.text
    wid = w.json()["id"]
    assert (await api.post(f"workflows/{wid}/publish")).status_code == 201
    r = await api.post(f"workflows/{wid}/runs", json={"input_data": data or {}})
    assert r.status_code == 201, r.text
    return wid, r.json()["id"]


async def get_claim(wid):
    async with transaction() as db:
        return await engine.claim(db, wid)


async def drain():
    worker = await register()
    while lease := await get_claim(worker):
        await dispatch(lease)
    return worker
