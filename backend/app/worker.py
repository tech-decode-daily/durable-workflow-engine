import asyncio
import os
import signal
import socket
from contextlib import suppress
from pathlib import Path
from tempfile import gettempdir
from uuid import UUID


from . import engine as scheduler, queue
from .common import event, log, required
from .config import settings
from .db import database_time, engine, transaction
from .models import Worker
from .tasks import Context, PermanentFailure, TransientFailure, execute

IDENTITY = Path(gettempdir()) / "durable-worker-id"


async def register():
    async with transaction() as db:
        worker = Worker(
            worker_name=os.getenv("WORKER_NAME")
            or f"worker-{socket.gethostname()[:12]}",
            hostname=socket.gethostname(),
            status="IDLE",
        )
        db.add(worker)
        await db.flush()
        event(db, "WORKER_REGISTERED", "Worker registered", worker_id=worker.id)
        return worker.id


async def heartbeat(worker_id):
    async with transaction() as db:
        worker = await required(db, Worker, worker_id, lock=True)
        now = await database_time(db)
        if (
            now - worker.last_heartbeat_at
        ).total_seconds() >= settings.heartbeat_seconds:
            worker.last_heartbeat_at = now
            event(db, "WORKER_HEARTBEAT", "Worker available", worker_id=worker_id)


async def dispatch(lease):
    cancel = asyncio.Event()
    ctx = Context(
        lease.run_id, lease.execution_id, lease.attempt, lease.worker_id, cancel
    )

    async def timed():
        async with asyncio.timeout(lease.timeout):
            return await execute(
                ctx, lease.task_type, lease.payload, lease.configuration
            )

    task = asyncio.create_task(timed())
    fields = dict(
        worker_id=lease.worker_id,
        workflow_run_id=lease.run_id,
        step_execution_id=lease.execution_id,
        attempt_number=lease.attempt,
    )
    log("worker", "Attempt started", **fields)
    result = {}
    try:
        while not task.done():
            done, _ = await asyncio.wait({task}, timeout=settings.heartbeat_seconds)
            if not done:
                async with transaction() as db:
                    if not await scheduler.renew(db, lease):
                        return
        try:
            result["output"] = task.result()
        except TimeoutError:
            result = dict(
                error="Task exceeded its execution timeout", status="TIMED_OUT"
            )
        except (PermanentFailure, TransientFailure) as exc:
            result = dict(error=str(exc), permanent=isinstance(exc, PermanentFailure))
        except Exception as exc:
            log(
                "worker",
                "Handler exception",
                "ERROR",
                error=type(exc).__name__,
                **fields,
            )
            result = dict(error="Handler raised an unexpected error")
        async with transaction() as db:
            accepted = await scheduler.finish(db, lease, **result)
        log(
            "worker",
            "Attempt finished",
            accepted=accepted,
            error=result.get("error"),
            **fields,
        )
        await queue.notify()
    finally:
        cancel.set()
        task.cancel()
        with suppress(asyncio.CancelledError, Exception):
            await task


async def run():
    stop = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGTERM, signal.SIGINT):
        with suppress(NotImplementedError):
            loop.add_signal_handler(sig, stop.set)
    worker_id = await register()
    IDENTITY.write_text(str(worker_id))
    # The compatibility worker uses the original queue and public schema.
    legacy = None
    if os.getenv("ENABLE_LEGACY", "1") == "1":
        import sys

        legacy = await asyncio.create_subprocess_exec(
            sys.executable, "-m", "legacy.worker"
        )
    try:
        while not stop.is_set():
            try:
                if legacy and legacy.returncode is not None:
                    raise SystemExit("Compatibility worker stopped")
                async with transaction() as db:
                    await scheduler.recover(db)
                await heartbeat(worker_id)
                async with transaction() as db:
                    lease = await scheduler.claim(db, worker_id)
                if lease:
                    await dispatch(lease)
                else:
                    await queue.wait()
            except Exception as exc:
                log("worker", "Polling interrupted", "ERROR", error=type(exc).__name__)
                await asyncio.sleep(settings.poll_seconds)
    finally:
        if legacy and legacy.returncode is None:
            legacy.terminate()
            await legacy.wait()
        async with transaction() as db:
            worker = await required(db, Worker, worker_id, lock=True)
            worker.status = "OFFLINE"
        await queue.client.aclose()
        await engine.dispose()


async def healthy():
    async with transaction() as db:
        worker = await db.get(Worker, UUID(IDENTITY.read_text()))
        now = await database_time(db)
        return (
            worker
            and worker.status != "OFFLINE"
            and (now - worker.last_heartbeat_at).total_seconds()
            < settings.lease_seconds
        )


if __name__ == "__main__":
    import logging
    import sys

    logging.basicConfig(level=logging.INFO, format="%(message)s")
    if "--health" in sys.argv:
        sys.exit(0 if asyncio.run(healthy()) else 1)
    asyncio.run(run())
