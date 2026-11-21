import json
import logging
from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import select

from .models import Event


class Problem(Exception):
    def __init__(self, status: int, message: str):
        self.status = status
        self.message = message


async def required(session, model, key: UUID, lock=False):
    query = select(model).where(model.id == key)
    row = await session.scalar(query.with_for_update() if lock else query)
    if row is None:
        raise Problem(404, f"{model.__name__} not found")
    return row


def event(session, kind, message, run=None, step=None, **details):
    session.add(
        Event(
            event_type=kind,
            message=message,
            workflow_run_id=run,
            step_execution_id=step,
            details={
                key: str(value) if isinstance(value, UUID) else value
                for key, value in details.items()
            },
        )
    )


def log(service, message, level="INFO", **fields):
    logging.getLogger("durable").log(
        getattr(logging, level),
        json.dumps(
            {
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "level": level,
                "service": service,
                "message": message,
                **fields,
            },
            default=str,
        ),
    )
