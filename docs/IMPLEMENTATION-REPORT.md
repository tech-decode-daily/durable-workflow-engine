# Durable MVP implementation report

Verified on 21 November 2026 using Docker Desktop on Windows, Python 3.12.15, PostgreSQL 16.15, Redis 7.4.11 and Node 22.23.4. The repository includes the [original brief](PROJECT-BRIEF.md), [initial assessment](ASSESSMENT.md), [startup guide and REST inventory](../README.md#rest-inventory), source, migrations and executable tests.

## Delivered

- The versioned REST API provides 33 documented operations including liveness and unsaved-definition validation. All MVP endpoint families in the brief are implemented. OpenAPI is served at `/openapi.json`.
- The asynchronous engine persists version-pinned runs, sequential steps, attempt inputs and outputs, worker leases, heartbeats and append-only events. It handles idempotent starts, manual transitions, exponential retries, recovery and stale-owner fencing.
- The React console supports creating and editing workflows, validating and publishing versions, entering run input, examining a step timeline, retrying a failed step or run, inspecting events, and monitoring worker availability. Failed API calls surface in the interface.
- Eight built-in Python task handlers and three published demo workflows exercise success, automatic recovery and retry exhaustion. Metrics and chart data come from the database.
- Five Compose services start the console, API, worker, PostgreSQL and Redis. The database uses a named volume. Only the API and frontend publish host ports, both on loopback.

## Design decisions

The initial checkout was empty. Docker metadata led to the neighboring prototype. The new private repository includes its original migration and preserves its login, tenant-scoped API, queue and console in a compatibility path. The versioned MVP uses a separate schema and a new default Compose project. The original source and volume remain available independently.

PostgreSQL serializes changes within a run. Distinct runs can execute concurrently. Each claim commits a new attempt before invoking a handler. Only a valid owner with the current attempt number and an unexpired lease can report success or failure. Workers periodically check PostgreSQL even when Redis wake-ups are unavailable. Manual retry grants one attempt to the failed step so earlier successful steps keep their output and history.

The eight principal tables, their relationships, execution semantics and endpoint groups are described in the [architecture and API guide](../README.md#architecture-and-storage). Revision `0003_history_queries` is the tested migration head. Alembic's metadata comparison found no pending schema changes.

## Actual test execution

- **Backend.** `docker compose exec -T api python -m tests.run` passed **34 tests** in 11.79 seconds. The suite includes 20 unit cases and 14 PostgreSQL integration cases. It covers concurrent starts and claims, input equivalence, version pinning, sequencing, permanent errors, timeouts, attempt exhaustion, manual retry, pause/resume/cancel, expired leases, stale results, events, filters, pagination, validation, draft deletion and prototype compatibility.
- **Frontend.** `npm test` passed **7 tests**. They exercise dashboard values, workflow listing, editor validation, ordered draft submission, run input, confirmed retry and error propagation. Test doubles are confined to the component tests.
- **Browser.** `npm run test:e2e` passed **2 Playwright tests** in 12.5 seconds against the running Compose stack using Chrome. One created, configured, validated, published and executed a three-step workflow, observed the final text and reloaded the history. The other inspected workers and system health, searched the library, ran the exhaustion demo, manually retried it and navigated the console at mobile width.
- **Build and startup.** TypeScript checking and the Vite production build passed on the host and in the frontend image. `docker compose up --build -d --wait` completed successfully with all five services healthy. The console, Swagger and liveness endpoint returned HTTP 200. The proxied detailed health response reported healthy API, PostgreSQL, Redis and workers.
- **Migration parity.** `docker compose exec -T api alembic check` reported no new upgrade operations. The preserved initial migration matched the source prototype.
- **Demo outputs.** The document workflow completed five attempts and returned `{"text":"Document: QUARTERLY DELIVERY REPORT"}`. The recovery demo completed three steps in four attempts. The exhaustion demo reached FAILED after exactly three attempts.

### Container fault injection

`python scripts/verify_resilience.py` completed successfully in a disposable Compose project. It exercised these six assertions against real containers.

1. Restarting the API preserved a queued run and replaying its idempotency key returned the same run ID.
2. With Redis stopped, a worker discovered and claimed that run through PostgreSQL.
3. Killing the worker with SIGKILL during execution stopped its heartbeats. The worker became stale after the configured lease expired.
4. Restarting Redis removed a sentinel key. A replacement worker recovered the run, produced the expected output and retained two ordered attempt records, ABANDONED and COMPLETED.
5. A second API restart preserved that final output and both attempts.
6. Two simultaneous worker containers acquired different runs, held overlapping live leases and completed each run in exactly one attempt.

The script removes its generated project, containers, network and volume after execution. Browser and demo verification intentionally leave example history in the main local console.

### Issues found during verification

The legacy regression test initially reproduced a foreign-key error when the prototype inserted its first log before its workflow. Submission now flushes the parent inside the same transaction. The first container restart test lost contact because Docker reassigned an ephemeral **test** port. The harness now reads the actual mapping after each restart. Both cases passed on rerun.

The passing suites emit nonfatal dependency warnings from legacy Passlib and React Router. Recharts reports zero chart dimensions in jsdom, which lacks browser layout. The desktop browser rendered the chart. Vite also reports a main chunk larger than its default 500 kB advisory threshold.

## Scope and follow-up

The requested single-machine sequential execution and monitoring flows are implemented. Cancellation is cooperative, worker loss can repeat side effects, and external handlers require their own idempotency discipline. Worker and API outage detection have been exercised on this machine. Multi-host failover, sustained load, disaster recovery from backups and external side-effect integrations remain unverified.

V1 authentication, multi-tenant authorization, arbitrary DAGs, event retention policies and isolation for untrusted task code are outside this MVP. The legacy login applies only to legacy routes. Before operating beyond trusted local development, prioritize access control, restore testing, retention and isolated workers.

## Start or reopen

```sh
docker compose up --build
```

The [console](http://localhost:5173) listens on port 5173. The [API documentation](http://localhost:8001/docs) listens on port 8001.
