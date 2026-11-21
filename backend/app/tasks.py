"""Trusted, cooperative handlers. User input never selects executable code."""

import asyncio
import random
from dataclasses import dataclass
from typing import Any, Awaitable, Callable, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class PermanentFailure(Exception):
    """The same input will fail again."""


class TransientFailure(Exception):
    """An attempt can be retried."""


@dataclass
class Context:
    workflow_run_id: UUID
    step_execution_id: UUID
    attempt_number: int
    worker_id: UUID
    cancelled: asyncio.Event

    workflow_input: dict | None = None
    previous_outputs: dict | None = None

    @property
    def idempotency_key(self):
        return str(self.step_execution_id)


class Config(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)
    source: str | None = None


class Math(Config):
    a: float | None = None
    b: float | None = None


class Transform(Config):
    mode: Literal["upper", "lower", "strip", "title"] = "upper"
    text: str | None = None


class Concat(Config):
    prefix: str = ""
    suffix: str = ""
    separator: str = ""
    parts: list[str] | None = None


class Sleep(Config):
    seconds: float = Field(default=1, ge=0, le=300)


class Fail(Config):
    permanent: bool = False


class RandomFailure(Config):
    probability: float = Field(default=0.5, ge=0, le=1)
    # A bounded failure window makes a repeatable recovery demonstration possible.
    until_attempt: int | None = Field(default=None, ge=1, le=20)


class Validate(Config):
    required: list[str] = Field(default_factory=list, max_length=64)


@dataclass(frozen=True)
class Task:
    description: str
    config: type[Config]
    handler: Callable[..., Awaitable[dict]]


registry: dict[str, Task] = {}


def register(name, config, description):
    def decorator(handler):
        if name in registry:
            raise ValueError(f"Duplicate task type {name}")
        registry[name] = Task(description, config, handler)
        return handler

    return decorator


def numbers(data, cfg):
    values = [
        getattr(cfg, key) if getattr(cfg, key) is not None else data.get(key)
        for key in ("a", "b")
    ]
    if any(type(value) not in (int, float) for value in values):
        raise PermanentFailure("Expected numeric fields a and b")
    return values


@register("math.add", Math, "Add numeric fields a and b.")
async def add(ctx, data, cfg):
    a, b = numbers(data, cfg)
    return {"result": a + b}


@register("math.multiply", Math, "Multiply numeric fields a and b.")
async def multiply(ctx, data, cfg):
    a, b = numbers(data, cfg)
    return {"result": a * b}


@register("text.transform", Transform, "Apply upper, lower, strip or title to text.")
async def transform(ctx, data, cfg):
    value = cfg.text if cfg.text is not None else data.get("text")
    if not isinstance(value, str):
        raise PermanentFailure("Expected a text field")
    return {"text": getattr(value, cfg.mode)()}


@register(
    "text.concatenate", Concat, "Join parts or wrap text with a prefix and suffix."
)
async def concatenate(ctx, data, cfg):
    parts = (
        cfg.parts if cfg.parts is not None else data.get("parts", [data.get("text")])
    )
    if not isinstance(parts, list) or any(not isinstance(part, str) for part in parts):
        raise PermanentFailure("Expected text or a list of string parts")
    if sum(map(len, parts)) + len(cfg.separator) * max(0, len(parts) - 1) > 65536:
        raise PermanentFailure("Joined text exceeds the output limit")
    return {"text": cfg.prefix + cfg.separator.join(parts) + cfg.suffix}


@register("system.sleep", Sleep, "Wait cooperatively, then forward the selected input.")
async def sleep(ctx, data, cfg):
    try:
        await asyncio.wait_for(ctx.cancelled.wait(), cfg.seconds)
    except TimeoutError:
        return data
    raise asyncio.CancelledError


@register("system.fail", Fail, "Raise an intentional transient or permanent error.")
async def fail(ctx, data, cfg):
    raise (PermanentFailure if cfg.permanent else TransientFailure)(
        "Intentional task failure"
    )


@register(
    "system.random_failure", RandomFailure, "Fail with a configurable probability."
)
async def random_failure(ctx, data, cfg):
    if (
        cfg.until_attempt is None or ctx.attempt_number <= cfg.until_attempt
    ) and random.random() < cfg.probability:
        raise TransientFailure("Random failure triggered")
    return data


@register(
    "data.validate_json", Validate, "Require named fields in the selected JSON object."
)
async def validate_json(ctx, data, cfg):
    if any(key not in data for key in cfg.required):
        raise PermanentFailure("A required input field is missing")
    return data


async def execute(
    ctx: Context, task_type: str, payload: dict[str, Any], configuration: dict
):
    import json

    ctx.workflow_input = payload["workflow_input"]
    ctx.previous_outputs = payload["previous_outputs"]
    task = registry[task_type]
    config = task.config.model_validate(configuration)
    data = (
        payload["previous_outputs"][config.source]
        if config.source
        else payload["workflow_input"]
    )
    result = await task.handler(ctx, data, config)
    try:
        size = len(json.dumps(result, allow_nan=False, ensure_ascii=False).encode())
    except (ValueError, OverflowError) as exc:
        raise PermanentFailure(
            "Task output is outside the supported JSON range"
        ) from exc
    if size > 65536:
        raise PermanentFailure("Task output exceeds 64 KiB")
    return result
