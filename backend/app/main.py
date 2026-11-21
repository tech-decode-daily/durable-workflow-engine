import json
import logging
import math
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy.exc import IntegrityError

from . import queue
from .api import router
from .common import Problem, log
from .config import settings
from .db import engine

logging.basicConfig(level=logging.INFO, format="%(message)s")


@asynccontextmanager
async def lifespan(app):
    yield
    await queue.client.aclose()
    await engine.dispose()


app = FastAPI(title="Durable", version=settings.version, lifespan=lifespan)
app.include_router(router)


def error(status, message):
    return JSONResponse({"detail": message}, status_code=status)


@app.exception_handler(Problem)
async def problem(request, exc):
    return error(exc.status, exc.message)


@app.exception_handler(RequestValidationError)
async def invalid(request, exc):
    issues = [
        ".".join(map(str, item["loc"])) + " — " + item["msg"]
        for item in exc.errors()[:8]
    ]
    return error(422, " | ".join(issues))


@app.exception_handler(IntegrityError)
async def conflict(request, exc):
    return error(409, "Operation conflicts with an existing record")


@app.exception_handler(Exception)
async def unexpected(request, exc):
    log("api", "Request failed", "ERROR", error=type(exc).__name__)
    return error(500, "Internal service error")


def check_json(value, depth=0):
    if depth > 48:
        raise ValueError()
    if isinstance(value, dict):
        for key, part in value.items():
            check_json(key, depth + 1)
            check_json(part, depth + 1)
    elif isinstance(value, list):
        for part in value:
            check_json(part, depth + 1)
    elif isinstance(value, str):
        if "\x00" in value:
            raise ValueError()
        value.encode("utf-8")
    elif isinstance(value, float) and not math.isfinite(value):
        raise ValueError()


class BodyLimit:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http" or scope["method"] not in {"PUT", "POST", "PATCH"}:
            return await self.app(scope, receive, send)
        body = bytearray()
        while True:
            msg = await receive()
            if msg["type"] == "http.disconnect":
                return
            body.extend(msg.get("body", b""))
            if len(body) > 65536:
                return await error(413, "Request body exceeds 64 KiB")(
                    scope, receive, send
                )
            if not msg.get("more_body"):
                break
        if body:
            try:
                check_json(json.loads(body))
            except (ValueError, RecursionError, UnicodeError):
                return await error(422, "Invalid or unsupported JSON")(
                    scope, receive, send
                )
        pending = True

        async def replay():
            nonlocal pending
            if pending:
                pending = False
                return {"type": "http.request", "body": bytes(body), "more_body": False}
            return await receive()

        await self.app(scope, replay, send)


app.add_middleware(BodyLimit)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins.split(","),
    allow_methods=["GET", "POST", "PUT", "DELETE"],
    allow_headers=["Content-Type", "Authorization"],
)


@app.get("/healthz")
async def healthz() -> dict[str, str]:
    return {"status": "ok", "queue": "ok" if await queue.available() else "degraded"}


if os.getenv("ENABLE_LEGACY", "1") == "1":
    from legacy.main import app as legacy_app

    app.mount("/", legacy_app)
