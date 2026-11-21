"""Publish the three example definitions once. Startup never launches a run."""

import asyncio

from sqlalchemy import select, text

from . import workflows
from .db import engine, transaction
from .models import Workflow
from .schemas import Draft


def step(key, name, task, config=None, attempts=3):
    return dict(
        key=key,
        name=name,
        task_type=task,
        config=config or {},
        retry=dict(max_attempts=attempts, delay_seconds=1),
        timeout_seconds=30,
    )


DEMOS = [
    dict(
        workflow_key="document-processing",
        name="Reliable Document Processing Demo",
        description="Validate a document, normalize its text and assemble the final result.",
        steps=[
            step(
                "validate",
                "Validate input",
                "data.validate_json",
                {"required": ["text"]},
            ),
            step(
                "transform",
                "Transform text",
                "text.transform",
                {"source": "validate", "mode": "upper"},
            ),
            step(
                "process",
                "Simulate processing",
                "system.sleep",
                {"source": "transform", "seconds": 2},
            ),
            step(
                "generate",
                "Generate output",
                "text.concatenate",
                {"source": "process", "prefix": "Document: "},
            ),
            step(
                "result",
                "Return final result",
                "data.validate_json",
                {"source": "generate", "required": ["text"]},
            ),
        ],
    ),
    dict(
        workflow_key="retry-recovery",
        name="Retry and Failure Recovery Demo",
        description="Observe a first-attempt failure followed by a successful retry.",
        steps=[
            step("start", "Start task", "data.validate_json"),
            step(
                "recover",
                "Recover on retry",
                "system.random_failure",
                {"probability": 1, "until_attempt": 1},
            ),
            step(
                "complete", "Return result", "data.validate_json", {"source": "recover"}
            ),
        ],
    ),
    dict(
        workflow_key="retry-exhaustion",
        name="Retry Exhaustion Demo",
        description="Follow three intentional failures and inspect their attempt records.",
        steps=[step("fail", "Exhaust retry budget", "system.fail")],
    ),
]


async def seed():
    async with transaction() as db:
        await db.execute(text("select pg_advisory_xact_lock(73190512)"))
        for data in DEMOS:
            if not await db.scalar(
                select(Workflow.id).where(Workflow.workflow_key == data["workflow_key"])
            ):
                wf = await workflows.create(db, Draft.model_validate(data))
                await workflows.publish(db, wf.id)
    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(seed())
