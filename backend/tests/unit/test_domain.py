import asyncio
from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.engine import ALLOWED, backoff
from app.schemas import Definition
from app.tasks import Context, PermanentFailure, execute, register, registry


def spec(key="first", task="data.validate_json", **values):
    return {"key": key, "name": key, "task_type": task, **values}


@pytest.mark.parametrize(
    "steps",
    [
        [],
        [spec(), spec()],
        [spec(task="missing")],
        [spec(config={"source": "next"})],
        [spec(retry={"max_attempts": 0})],
        [spec(timeout_seconds=601)],
        [spec(task="system.sleep", config={"seconds": 400})],
        [spec(task="math.add", config={"typo": 1})],
        [spec(key="A")],
        [spec(key="a" + str(i)) for i in range(41)],
    ],
)
def test_definition_rejects_invalid_steps(steps):
    with pytest.raises(ValidationError):
        Definition(name="Test", steps=steps)


def test_backoff_and_terminal_states():
    assert [backoff(2, n, 7) for n in range(1, 5)] == [2, 4, 7, 7]
    assert backoff(0, 1, 5) == 0
    assert "COMPLETED" not in set.union(*ALLOWED.values())
    assert ALLOWED["retry"] == {"FAILED"}


def test_registry_rejects_duplicate_handlers():
    task = registry["math.add"]
    with pytest.raises(ValueError):
        register("math.add", task.config, task.description)(task.handler)


@pytest.mark.parametrize(
    "kind,data,config,result",
    [
        ("math.add", {"a": 2, "b": 3}, {}, {"result": 5}),
        ("math.multiply", {"a": 2}, {"b": 4}, {"result": 8}),
        ("text.transform", {"text": "hello"}, {}, {"text": "HELLO"}),
        (
            "text.concatenate",
            {},
            {"parts": ["a", "b"], "separator": "."},
            {"text": "a.b"},
        ),
        ("data.validate_json", {"a": 1}, {"required": ["a"]}, {"a": 1}),
        ("system.random_failure", {}, {"probability": 0}, {}),
        ("system.sleep", {}, {"seconds": 0}, {}),
    ],
)
async def test_builtin(kind, data, config, result):
    ctx = Context(uuid4(), uuid4(), 1, uuid4(), asyncio.Event())
    assert (
        await execute(
            ctx, kind, {"workflow_input": data, "previous_outputs": {}}, config
        )
        == result
    )
    assert ctx.idempotency_key == str(ctx.step_execution_id)


async def test_cancelled_sleep_and_permanent_validation_error():
    ctx = Context(uuid4(), uuid4(), 1, uuid4(), asyncio.Event())
    ctx.cancelled.set()
    with pytest.raises(asyncio.CancelledError):
        await execute(
            ctx,
            "system.sleep",
            {"workflow_input": {}, "previous_outputs": {}},
            {"seconds": 10},
        )
    with pytest.raises(PermanentFailure):
        await execute(
            ctx, "math.add", {"workflow_input": {}, "previous_outputs": {}}, {}
        )
