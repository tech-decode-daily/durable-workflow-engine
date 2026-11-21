"""Exercise real container loss in a disposable Compose project using only the standard library."""

import json
import os
import subprocess
import time
import urllib.error
import urllib.request
from pathlib import Path
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]


def until(probe, seconds=90):
    finish = time.monotonic() + seconds
    last = None
    while time.monotonic() < finish:
        try:
            last = probe()
            if last:
                return last
        except (urllib.error.URLError, ConnectionError, TimeoutError) as exc:
            last = type(exc).__name__
        time.sleep(0.25)
    raise AssertionError(
        f"Condition did not become true in {seconds}s. Last observation {last}"
    )


def main():
    project = "durable-qa-" + uuid4().hex[:12]
    env = {
        **os.environ,
        "API_PORT": "0",
        "LEASE_SECONDS": "4",
        "HEARTBEAT_SECONDS": "0.5",
        "POLL_SECONDS": "0.25",
    }

    def compose(*args, capture=False):
        result = subprocess.run(
            ["docker", "compose", "-p", project, *args],
            env=env,
            cwd=ROOT,
            check=True,
            text=True,
            stdout=subprocess.PIPE if capture else None,
        )
        return result.stdout.strip() if capture else None

    try:
        compose("up", "--build", "-d", "--wait", "api", "worker", "redis")
        addr = compose("port", "api", "8000", capture=True)
        base = "http://" + addr + "/api/v1"

        def call(path, body=None, method=None):
            req = urllib.request.Request(
                base + path,
                data=None if body is None else json.dumps(body).encode(),
                method=method,
                headers={"Content-Type": "application/json"},
            )
            with urllib.request.urlopen(req, timeout=5) as result:
                return json.load(result)

        compose("stop", "worker")
        wf = call(
            "/workflows",
            {
                "name": "Container recovery probe",
                "steps": [
                    {
                        "key": "work",
                        "name": "Claimed work",
                        "task_type": "system.sleep",
                        "config": {"seconds": 6},
                        "retry": {"max_attempts": 2, "delay_seconds": 1},
                        "timeout_seconds": 25,
                    }
                ],
            },
        )
        path = "/workflows/" + wf["id"]
        call(path + "/publish", method="POST")
        payload = {"idempotency_key": "stable", "input_data": {"job": "recovery-probe"}}
        run = call(path + "/runs", payload)
        rid = run["id"]
        rpath = "/runs/" + rid
        compose("restart", "api")
        until(lambda: call(rpath)["status"] == "PENDING")
        assert call(path + "/runs", payload)["id"] == rid
        print(
            "PASS API restart preserved the queued run and idempotency record",
            flush=True,
        )

        compose(
            "exec", "-T", "redis", "redis-cli", "SET", "qa:volatile-sentinel", "present"
        )
        compose("stop", "redis")
        assert call("/system/health")["redis"] == "unavailable"
        compose("start", "worker")
        until(lambda: call(rpath + "/steps")["items"][0]["status"] == "RUNNING")
        owner = call(rpath + "/attempts")["items"][0]["worker_id"]
        print(
            "PASS Worker claimed pending PostgreSQL work while Redis was stopped",
            flush=True,
        )

        # Disable automatic Docker restart only for the worker in this generated project.
        container = compose("ps", "-q", "worker", capture=True)
        subprocess.run(["docker", "update", "--restart=no", container], check=True)
        subprocess.run(["docker", "kill", "--signal=KILL", container], check=True)
        until(lambda: call("/workers/" + owner)["status"] == "STALE")
        assert call(rpath + "/attempts")["items"][0]["status"] == "RUNNING"
        print(
            "PASS Abruptly killed worker became stale after heartbeat expiry",
            flush=True,
        )

        compose("start", "redis")
        until(lambda: call("/system/health")["redis"] == "healthy")
        assert not compose(
            "exec",
            "-T",
            "redis",
            "redis-cli",
            "--raw",
            "GET",
            "qa:volatile-sentinel",
            capture=True,
        )
        compose("up", "-d", "--force-recreate", "--no-deps", "worker")
        until(lambda: call(rpath)["status"] == "COMPLETED")
        hist = call(rpath + "/attempts")["items"]
        assert [h["status"] for h in hist] == ["ABANDONED", "COMPLETED"]
        assert hist[0]["worker_id"] != hist[1]["worker_id"]
        assert call(rpath)["output_data"] == payload["input_data"]
        types = {e["event_type"] for e in call(rpath + "/events")["items"]}
        assert {
            "LEASE_EXPIRED",
            "STEP_RECOVERED",
            "STEP_RETRY_SCHEDULED",
            "WORKFLOW_COMPLETED",
        } <= types
        print(
            "PASS Empty Redis and replacement worker recovered the run with both attempts intact",
            flush=True,
        )
        compose("restart", "api")
        until(lambda: call(rpath)["output_data"] == payload["input_data"])
        assert call(rpath + "/attempts")["total"] == 2
        print(
            "PASS Final output and attempt history survived a second API restart",
            flush=True,
        )
    finally:
        compose("down", "--volumes", "--remove-orphans")


if __name__ == "__main__":
    main()
