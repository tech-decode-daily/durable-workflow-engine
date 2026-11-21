# Durable

Durable is a locally runnable workflow orchestration engine. Publish a sequential workflow, submit JSON input, and follow every step, lease, retry and output in the React console. PostgreSQL owns execution state. A Redis wake-up reduces dispatch latency, and workers continue polling PostgreSQL when Redis is unavailable.

## Start

Install Docker with the Compose plugin, start its engine, and run this command in the repository root.

```sh
docker compose up --build
```

Open the [console](http://localhost:5173), [Swagger API documentation](http://localhost:8001/docs), or [health endpoint](http://localhost:8001/healthz). The first build downloads dependencies. The API applies the Alembic migrations and publishes three demo definitions before it starts serving. The worker waits for API readiness. The frontend serves the built Vite application and proxies API requests internally.

For background operation use `docker compose up --build -d --wait`. Inspect containers with `docker compose ps` and logs with `docker compose logs -f api worker`. Stop the stack with `docker compose down`. PostgreSQL data survives this command in the named volume. To run a second worker use `docker compose up -d --scale worker=2`.

The v1 API assumes a trusted local operator. Both published ports bind to loopback. Keep this MVP private. Public deployment requires authentication and authorization for v1, TLS, secrets management, resource isolation, backups and operational controls.

## Try the demos

Open **Workflows**, choose a published definition, select **Run workflow**, and enter its JSON input. Each execution detail page shows the step timeline, input, output, attempts and chronological events.

- **Reliable Document Processing Demo** accepts `{"text":"Quarterly delivery report"}`. It validates the text, converts it to uppercase, waits two seconds, generates a result and returns `{"text":"Document: QUARTERLY DELIVERY REPORT"}`.
- **Retry and Failure Recovery Demo** accepts `{"job":"example-001"}`. Its registered probability-based handler has a 100% failure probability on attempt one and a bounded failure window. Attempt two succeeds deterministically.
- **Retry Exhaustion Demo** accepts `{}`. Its intentional transient failure exhausts three attempts. **Retry** grants the failed step one extra attempt while preserving its complete history.

The seed is idempotent and only creates missing definitions. Example inputs are under [examples](examples/). To build your own workflow, use **Create workflow**, name the definition, add steps, configure their JSON, and select **Validate**. Save a draft or publish a version. Edit a published workflow's draft to prepare a new version.

## Architecture and storage

The API validates requests and writes draft, version and run records through application services. Submitting a run creates all execution rows and marks the first eligible in one transaction. The API commits before sending a wake-up. The worker claims an eligible row, commits its attempt, executes the Python handler outside the transaction and completes or retries the step in a new transaction.

```text
React console ──HTTP── FastAPI ─────────────── PostgreSQL 16
                         │                         ▲
                         └── Redis 7 wake-up ── worker
                                                   │
                                            Python task registry
```

- **Definitions.** `durable.workflows` stores the editable draft and stable key. `workflow_versions` and `workflow_steps` store immutable published snapshots. Database triggers reject updates and deletions to published rows.
- **Runs.** `workflow_runs` pins a version and holds the input, final output and status. A workflow-scoped unique idempotency key and canonical request hash serialize equivalent submissions and detect conflicts. Omitting a version always represents the same request on replay, even after another publication.
- **Execution history.** `step_executions` stores each step's current state, availability and lease. `execution_attempts` stores the input, worker, duration, output and error for each individual claim. Earlier attempts survive automatic recovery and manual retry.
- **Monitoring.** `workers` tracks each worker process lifetime. `execution_events` is append-only and has an ordered sequence for events with identical timestamps. Definition and idle-worker events have no run ID. Dashboard counts and hourly activity come from PostgreSQL.
- **Compatibility.** The original migration and public schema remain available to the prototype tenant API. The original console is accessible under **Settings → Open prototype console**. Its worker uses the original queue. Legacy submissions and JWT accounts stay in their original subsystem; v1 runs and metrics use the new schema. The default Compose project `durable-local` owns a separate volume. See the [initial assessment](docs/ASSESSMENT.md).

### Claiming, retry and recovery

Writers acquire the workflow run lock first. Workers select a candidate with PostgreSQL `FOR UPDATE OF ... SKIP LOCKED`, refresh the execution under lock, and check its eligibility. A lease is fenced by the worker UUID, execution UUID, attempt number and database time. A completion from an expired or replaced owner is discarded. Heartbeats renew active leases independently of asynchronous handler progress. A worker that misses the lease window appears stale.

A live worker scans for expired leases, closes an abandoned attempt, and either schedules a retry or fails the run when the budget is spent. Recovery resumes when a worker is available. On success the worker persists the output and queues the following step in the same transaction. Redis can lose every wake-up without losing work.

The retry budget includes the first attempt. After failed attempt `n`, the delay is the minimum of the configured step cap, the deployment cap, and `delay_seconds × 2^(n−1)`. Permanent input errors fail immediately. Timeouts, intentional transient errors and abandonment consume attempts. Manual retry preserves completed predecessor steps, adds one attempt to the failed step and reuses its persisted input.

**Pause** blocks new claims and allows an in-flight step to finish. A last step can therefore complete a paused run. **Resume** reopens eligibility. **Cancel** revokes the lease, closes the active attempt and cancels unfinished steps atomically. The worker observes cancellation at its next heartbeat and cooperatively stops the coroutine. On graceful shutdown the worker finishes its current task within Docker's grace period. A forced stop follows the lease-recovery path.

Execution is **at least once**. A worker may perform an external side effect and die before recording success. Trusted custom handlers should pass `context.idempotency_key` (stable across attempts of the same execution) to the external service. Task implementations must yield to asyncio and bound their external calls.

## Define a workflow

Create a draft with `POST /api/v1/workflows` using this JSON. `workflow_key` is optional on creation. A draft may be edited repeatedly. Both saving and publishing validate the structure, task types, configuration and sequential source references.

```json
{
  "name": "Format message",
  "description": "Normalize and label a message.",
  "steps": [
    {
      "key": "normalize",
      "name": "Normalize text",
      "task_type": "text.transform",
      "config": {"mode": "upper"},
      "retry": {"max_attempts": 3, "delay_seconds": 2, "max_delay_seconds": 30},
      "timeout_seconds": 10
    },
    {
      "key": "label",
      "name": "Label message",
      "task_type": "text.concatenate",
      "config": {"source": "normalize", "prefix": "Message: "}
    }
  ]
}
```

Publish with `POST /api/v1/workflows/{id}/publish`. Start with `POST /api/v1/workflows/{id}/runs` and body `{"input_data":{"text":"hello"},"idempotency_key":"example-01","version":1}`. Read the returned run ID from `GET /api/v1/runs/{id}/timeline`. A new start returns 201, an equivalent replay returns 200 and a conflicting payload returns 409.

### Registered handlers

All handlers receive the execution context, selected input and validated configuration. The context exposes the original workflow input, preceding outputs, run/step/worker IDs, attempt number, stable side-effect key and cancellation event. The optional `source` config selects an earlier step's output. It defaults to the original workflow input.

- `math.add` and `math.multiply` use numeric `a` and `b` from the input or configuration and return `{"result": ...}`.
- `text.transform` applies `upper`, `lower`, `strip` or `title` to `text`.
- `text.concatenate` joins `parts` with `separator` or wraps `text` with `prefix` and `suffix`.
- `system.sleep` waits for the configured `seconds` and forwards its input.
- `system.fail` fails each attempt. Set `permanent` to stop automatic retries.
- `system.random_failure` accepts `probability` from zero to one and an optional `until_attempt` for repeatable demonstrations.
- `data.validate_json` requires the listed object fields and forwards the validated input.

The registry endpoint exposes the actual Pydantic configuration schema of each handler. Register new trusted Python functions in [tasks.py](backend/app/tasks.py) and rebuild the API and worker images together.

## REST inventory

The prefix is `/api/v1`; basic liveness is `GET /healthz`. Resource IDs are UUIDs. Lists accept `limit` (1–200) and `offset` and return `items`, `total`, `limit`, and `offset`. The bounded registry and the steps embedded in a timeline are arrays. The timeline paginates events. Run events and attempts are chronological. Global events are newest first.

- **System and workers.** `GET /system/health`, `/system/stats`, `/workers`, `/workers/{id}`, `/workers/{id}/executions`.
- **Definitions.** `POST /workflows`, `GET /workflows`, and `GET|PUT|DELETE /workflows/{id}`. Listing accepts `search` and `status`. Only never-published drafts are deletable.
- **Validation and versions.** `POST /definitions/validate` validates an unsaved definition. `POST /workflows/{id}/validate` checks the persisted draft. `POST /workflows/{id}/publish`, `GET /workflows/{id}/versions`, and `GET /workflows/{id}/versions/{version}` manage snapshots.
- **Execution.** `POST /workflows/{id}/runs`, `GET /runs`, `GET /runs/{id}`, and `GET /runs/{id}/{steps|attempts|events|timeline}`. Filter the list by `status`, `workflow_id`, `search`, `date_from` and `date_to`. Send timezone-qualified ISO timestamps.
- **Control.** `POST /runs/{id}/{pause|resume|cancel|retry}` and `POST /runs/{id}/steps/{step_execution_id}/retry`.
- **Tasks.** `GET /tasks` (optional `status`), `/tasks/registry`, `/tasks/{id}` and `/tasks/{id}/attempts`.
- **Events.** `GET /events` accepts `event_type`, `workflow_run_id`, `date_from` and `date_to`.

Missing resources return 404, invalid transitions and idempotency conflicts return 409, and invalid request data returns 422. Request bodies over 64 KiB return 413. API errors have a `detail` field. Execution errors are recorded on the attempt and exposed on the run and step. Handlers produce at most 64 KiB of JSON output. Definitions allow 1–40 sequential steps, 1–20 automatic attempts per step, and 1–600 seconds per attempt.

## Configuration and migrations

Compose works with its loopback development defaults. Optionally copy `.env.example` to `.env` before first startup. Use URL-safe credentials when interpolating the database password into the connection URL.

- `POSTGRES_PASSWORD` initializes the database volume. `JWT_SECRET` applies to the prototype login flow.
- `API_PORT` and `FRONTEND_PORT` default to 8001 and 5173. `CORS_ORIGINS` is a comma-separated allowlist. `APP_ENV` is displayed in Settings.
- `LEASE_SECONDS`, `HEARTBEAT_SECONDS`, `POLL_SECONDS` and `MAX_RETRY_DELAY_SECONDS` default to 12, 2, 1 and 300. Heartbeats must be more frequent than twice per lease interval.
- Compose supplies internal `DATABASE_URL` and `REDIS_URL` to Python services. Native development requires an asyncpg SQLAlchemy URL. `VITE_API_BASE` can override the same-origin API base at frontend build time. The Vite proxy uses `API_PROXY` for its upstream.
- Alembic revisions are in `backend/migrations/versions`. `0001_initial` is the original schema. `0002_versioned_engine` adds the isolated `durable` schema. `0003_history_queries` widens duration storage and indexes event timestamps. Check the deployed revision with `docker compose exec api alembic current`. Startup automatically executes `alembic upgrade head`.

## Tests

```sh
# Run these from the repository root with the local Compose stack up.
docker compose exec -T api python -m tests.run
python scripts/verify_resilience.py

cd frontend
npm ci
npm test
npm run build
npx playwright install chromium
npm run test:e2e
```

The Python test runner provisions a unique disposable PostgreSQL database, migrates it, runs unit and integration tests, and removes only that database. It requires a database account with permission to create databases. The Compose resilience script creates its own project, network and volume, chooses a free API port, abruptly kills its own worker and removes its own test resources. The Playwright tests run against the selected live stack, creating workflow and execution history there. Override the target with `DURABLE_UI_URL` and the browser with `PLAYWRIGHT_CHANNEL`. Use `chrome` for an installed Google Chrome.

## Source map and limitations

`backend/app` contains the async API, application services, query repository, task registry, scheduler and worker. `backend/legacy` contains the compatible tenant API and worker. `frontend/src/pages` contains routed React views; `frontend/src/components` contains shared controls. The visual sequence editor uses React Flow. TanStack Query handles polling and cache invalidation. Recharts renders execution activity, and Lucide icons, Tailwind and shadcn-style Radix controls provide the interface.

The MVP targets one machine with cooperative, trusted tasks and PostgreSQL 16. It has no DAG scheduler, external activity sandbox, v1 tenant authorization, event retention job, high-availability deployment or external tracing. History, including heartbeat events and per-attempt inputs, grows with use. The console polls for updates, and hourly activity counts execution events, including a later completion after a manual retry. Future work should prioritize v1 identity and access controls, tested backup/restore, history retention, and isolated execution before adding parallel workflow branches.

See the [implementation and test report](docs/IMPLEMENTATION-REPORT.md) and [original brief](docs/PROJECT-BRIEF.md).
