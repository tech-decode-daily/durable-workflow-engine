# PROJECT: DURABLE — A Durable Workflow Orchestration Engine

## ROLE AND EXPECTATIONS

Act as a senior distributed systems engineer, backend architect, frontend engineer, database engineer, and QA engineer.

Your responsibility is to build a complete, locally runnable MVP of a software product called **Durable**.

This is not a UI-only demonstration, static dashboard, or CRUD application. It must be a functional workflow orchestration engine with persistent execution state, asynchronous workers, retry mechanisms, task leasing, failure recovery, and a usable frontend.

You have permission to inspect, modify, create, and test files throughout the existing project repository.

You must implement the actual application, not merely produce a plan or code snippets.

Work systematically. Inspect the existing repository before making changes. Preserve functional components, existing architectural decisions, database migrations, and working features wherever possible.

Do not rewrite the project unnecessarily.

---

# 1. PRODUCT VISION

Durable is a self-hostable workflow orchestration platform that allows developers to define, execute, monitor, and recover multi-step background workflows.

A workflow consists of multiple sequential tasks.

Example:

An automated document-processing workflow:

1. Receive a document.
2. Validate its format.
3. Extract document information.
4. Process extracted information.
5. Generate a result.
6. Store the result.
7. Mark the workflow as completed.

Every task must have a persistent execution record.

If a task fails, the engine should retry it according to its retry policy.

If a worker crashes while executing a task, the engine must eventually detect the abandoned execution and make it eligible for recovery.

If the API or worker restarts, workflow state must remain available.

The PostgreSQL database is the authoritative source of execution state.

Redis may be used for task notifications, coordination, and queue acceleration, but Redis must never become the only source of truth for pending or executing work.

## Primary product objectives

- Durable execution state.
- Asynchronous task execution.
- Configurable retry policies.
- Task leases and worker heartbeats.
- Worker failure detection.
- Recovery of abandoned tasks.
- Idempotent execution support.
- Workflow execution history.
- Execution event logs.
- Manual retry, cancellation, pause, and resume.
- Operational dashboard.
- Developer-friendly REST API.

## MVP limitation

Build a reliable, single-machine, Docker-based prototype.

Do not claim distributed production-grade guarantees that have not been implemented and tested.

The architecture should be extendable toward multi-worker distributed execution later.

---

# 2. EXISTING PROJECT ENVIRONMENT

The project already has a prototype.

Expected existing stack:

- Python 3.12
- FastAPI
- React
- PostgreSQL 16
- Redis 7
- Docker Compose
- Alembic migrations
- Python background worker

Existing development configuration:

- API host: 127.0.0.1:8001
- API container: port 8000
- Frontend: port 5173
- Health endpoint: GET /healthz

An initial Alembic migration already exists.

Some Docker-related issues were previously fixed, including copying alembic.ini and migrations into the backend image.

## Mandatory first action

Inspect:

- Entire repository structure.
- Existing backend source code.
- Existing frontend source code.
- Dockerfiles.
- docker-compose.yml.
- Database models.
- Existing Alembic migrations.
- Worker implementation.
- Existing API routes.
- Tests.
- Environment configuration.

Create an implementation assessment.

Identify:

1. What is already functional.
2. What is partially implemented.
3. What is missing.
4. What needs fixing.
5. What must not be rewritten.

Do not replace functioning code merely to match your preferred architecture.

---

# 3. TECHNOLOGY REQUIREMENTS

## Backend

- Python 3.12+
- FastAPI
- Pydantic v2
- SQLAlchemy 2.x
- Alembic
- PostgreSQL 16
- Redis 7
- Asyncio
- HTTPX
- Pytest
- pytest-asyncio

Use clean separation between:

- API routes.
- Application services.
- Domain models.
- Database repositories.
- Worker execution.
- Queue coordination.
- Recovery mechanisms.

Avoid putting business logic directly inside route handlers.

## Frontend

- React.
- TypeScript.
- Vite.
- Tailwind CSS.
- shadcn/ui.
- React Flow.
- TanStack Query.
- Recharts.
- Lucide icons.

Reuse existing frontend tooling if already configured correctly.

## Infrastructure

- Docker.
- Docker Compose.
- PostgreSQL.
- Redis.
- Separate API and worker containers.

The application must start locally with:

docker compose up --build

The exact startup instructions must be documented.

---

# 4. CORE ARCHITECTURE

Implement the following components.

## A. API service

Responsibilities:

- Expose REST endpoints.
- Validate incoming requests.
- Manage workflow definitions.
- Create workflow runs.
- Persist execution state.
- Manage workflow lifecycle.
- Expose execution history.
- Provide monitoring endpoints.

## B. Workflow execution engine

Responsibilities:

- Load workflow definitions.
- Create step execution records.
- Determine which steps are eligible to execute.
- Dispatch eligible work.
- Track execution state.
- Enforce retry policies.
- Manage execution transitions.
- Handle cancellation and pause requests.

## C. Worker service

Responsibilities:

- Claim available tasks.
- Acquire execution leases.
- Execute registered task handlers.
- Report execution results.
- Record errors.
- Renew leases through heartbeats.
- Release or complete leases.
- Recover from transient failures.

Workers must execute actual registered Python functions.

Do not implement fake execution using frontend timers or simulated status changes.

## D. PostgreSQL

PostgreSQL must persist:

- Workflow definitions.
- Workflow versions.
- Workflow runs.
- Step executions.
- Execution attempts.
- Worker registrations.
- Execution events.
- Idempotency records where appropriate.

## E. Redis

Use Redis for:

- Task dispatch notifications.
- Queue acceleration.
- Optional worker coordination.

The engine must be able to recover pending work by inspecting PostgreSQL even if Redis loses its contents.

Do not rely exclusively on Redis queue state.

---

# 5. DATABASE DESIGN

Use SQLAlchemy models and Alembic migrations.

Implement these primary entities.

## workflows

Fields:

- id: UUID primary key.
- name: string.
- description: nullable text.
- workflow_key: unique string.
- status: draft or active.
- created_at.
- updated_at.

## workflow_versions

Fields:

- id: UUID primary key.
- workflow_id: foreign key.
- version: integer.
- definition: JSONB.
- created_at.

Published workflow definitions must be immutable.

A workflow run must reference the exact workflow version used when it was created.

## workflow_runs

Fields:

- id: UUID primary key.
- workflow_id.
- workflow_version_id.
- status.
- input_data: JSONB.
- output_data: nullable JSONB.
- error_message: nullable text.
- created_at.
- started_at.
- completed_at.
- updated_at.
- idempotency_key: nullable string.

Statuses:

- PENDING
- RUNNING
- PAUSED
- COMPLETED
- FAILED
- CANCELLED

## workflow_steps

Fields:

- id: UUID primary key.
- workflow_version_id.
- step_key.
- step_name.
- task_type.
- configuration: JSONB.
- position: integer.
- retry_limit: integer.
- retry_delay_seconds: integer.
- timeout_seconds: integer.
- created_at.

## step_executions

Fields:

- id: UUID primary key.
- workflow_run_id.
- workflow_step_id.
- status.
- input_data: JSONB.
- output_data: nullable JSONB.
- error_message: nullable text.
- attempt_count.
- max_attempts.
- available_at.
- lease_owner: nullable string.
- lease_expires_at: nullable timestamp.
- heartbeat_at: nullable timestamp.
- started_at.
- completed_at.
- created_at.
- updated_at.

Statuses:

- PENDING
- QUEUED
- RUNNING
- RETRY_WAIT
- COMPLETED
- FAILED
- CANCELLED

## execution_attempts

Fields:

- id: UUID primary key.
- step_execution_id.
- attempt_number.
- worker_id.
- status.
- input_data: JSONB.
- output_data: nullable JSONB.
- error_message: nullable text.
- started_at.
- completed_at.
- duration_ms.

Keep an individual record for every attempt.

Never overwrite earlier attempt history.

## workers

Fields:

- id: UUID primary key.
- worker_name.
- hostname.
- status.
- registered_at.
- last_heartbeat_at.
- current_task_id: nullable UUID.

## execution_events

Fields:

- id: UUID primary key.
- workflow_run_id.
- step_execution_id: nullable UUID.
- event_type.
- message.
- metadata: JSONB.
- created_at.

Events must be append-only.

Use appropriate indexes, foreign keys, unique constraints, and database transactions.

Use timezone-aware timestamps consistently.

---

# 6. WORKFLOW DEFINITION FORMAT

Use a simple, validated JSON workflow definition.

Example:

{
  "name": "Document Processing",
  "description": "Process an uploaded document",
  "steps": [
    {
      "key": "validate",
      "name": "Validate Document",
      "task_type": "document.validate",
      "config": {
        "strict": true
      },
      "retry": {
        "max_attempts": 3,
        "delay_seconds": 5
      },
      "timeout_seconds": 30
    },
    {
      "key": "extract",
      "name": "Extract Information",
      "task_type": "document.extract",
      "config": {},
      "retry": {
        "max_attempts": 3,
        "delay_seconds": 10
      },
      "timeout_seconds": 60
    },
    {
      "key": "process",
      "name": "Process Information",
      "task_type": "document.process",
      "config": {},
      "retry": {
        "max_attempts": 2,
        "delay_seconds": 10
      },
      "timeout_seconds": 60
    }
  ]
}

MVP execution semantics:

- Execute steps sequentially.
- Each step receives the workflow input and relevant outputs from previous completed steps.
- A failed step prevents subsequent steps from executing.
- Retries happen before the workflow is marked failed.
- A completed workflow has a persisted final output.
- Workflow definitions are versioned.

Do not implement arbitrary DAG execution yet.

Keep the domain model extensible enough to support parallel branches and dependencies in a future version.

---

# 7. TASK EXECUTION FRAMEWORK

Implement a task registry.

Example conceptual interface:

@register_task("math.add")
async def add_numbers(context, payload):
    return {
        "result": payload["a"] + payload["b"]
    }

Every task handler must receive:

- Execution context.
- Workflow input.
- Previous step outputs.
- Step configuration.
- Execution metadata.

The execution context should provide:

- workflow_run_id.
- step_execution_id.
- attempt_number.
- worker_id.
- cancellation information.

Create the following built-in tasks:

1. math.add
2. math.multiply
3. text.transform
4. text.concatenate
5. system.sleep
6. system.fail
7. system.random_failure
8. data.validate_json

The system.fail task must intentionally fail for testing retry behavior.

The system.random_failure task should support configurable failure probability.

These tasks will allow users to demonstrate actual workflow execution without requiring external APIs.

Do not use eval or execute arbitrary user-provided Python code.

---

# 8. DURABILITY AND RELIABILITY FEATURES

These are the most important engineering requirements.

## A. Persistent task execution

Before executing a task, persist its execution state in PostgreSQL.

A task must not disappear merely because Redis loses its queue contents.

## B. Task claiming

Implement safe concurrent task claiming.

Use PostgreSQL transactions and appropriate row locking, such as FOR UPDATE SKIP LOCKED where applicable.

Ensure that two workers cannot simultaneously acquire the same valid lease.

## C. Lease mechanism

When a worker claims a task:

- Assign a worker ID.
- Set lease expiry.
- Mark task as RUNNING.
- Record attempt information.

A worker must periodically renew its lease.

## D. Heartbeats

Workers must periodically report their health.

Track:

- Worker identity.
- Last heartbeat.
- Current execution.
- Worker status.

## E. Abandoned task recovery

Implement a recovery process.

When a running task's lease expires:

1. Identify the abandoned execution.
2. Verify its lease has not been renewed.
3. Record the previous attempt as abandoned or timed out.
4. Make the task eligible for retry if attempts remain.
5. Otherwise mark it failed.
6. Record an execution event.

Use database transactions and conditional updates to prevent race conditions.

## F. Retry policies

Implement:

- Configurable maximum attempts.
- Configurable retry delay.
- Exponential backoff.
- Maximum retry delay.
- Retry after transient execution errors.
- No retry after permanent failures when explicitly classified.

A retry must create a new execution attempt record.

## G. Idempotency

Support idempotency keys when starting workflow runs.

Repeated requests using the same key and equivalent request payload must not create duplicate runs.

A conflicting payload with the same key must return a clear conflict response.

Do not claim exactly-once execution.

Explain the practical at-least-once execution semantics.

Task handlers that produce external side effects must be designed to use idempotency keys.

## H. Cancellation

Implement cooperative cancellation.

Workers must periodically check whether their execution has been cancelled.

Do not assume arbitrary running Python code can always be forcibly interrupted safely.

## I. Pause and resume

Pausing a workflow must prevent new steps from starting.

Resume must allow the workflow engine to continue from the appropriate persisted state.

## J. Crash recovery

Test the following:

- Worker crashes after claiming a task.
- Worker stops sending heartbeats.
- Redis is restarted.
- API container is restarted.
- Worker container is restarted.
- Task fails during execution.
- Retry limit is exhausted.

The system must preserve execution history.

---

# 9. COMPLETE REST API SPECIFICATION

Use the prefix:

/api/v1

Use consistent response schemas, validation errors, HTTP status codes, and pagination.

## HEALTH AND SYSTEM

GET /healthz

Return basic API health.

GET /api/v1/system/health

Return:

- API status.
- PostgreSQL connectivity.
- Redis connectivity.
- Worker availability.
- Queue status.

GET /api/v1/system/stats

Return:

- Total workflows.
- Total workflow runs.
- Pending tasks.
- Running tasks.
- Completed runs.
- Failed runs.
- Active workers.

GET /api/v1/workers

List registered workers.

GET /api/v1/workers/{worker_id}

Get worker details and current execution.

GET /api/v1/workers/{worker_id}/executions

List recent executions assigned to a worker.

## WORKFLOW MANAGEMENT

POST /api/v1/workflows

Create a workflow draft.

GET /api/v1/workflows

List workflows with pagination, search, and status filters.

GET /api/v1/workflows/{workflow_id}

Get workflow information.

PUT /api/v1/workflows/{workflow_id}

Update a workflow draft.

DELETE /api/v1/workflows/{workflow_id}

Delete an eligible draft. Do not delete workflow definitions referenced by historical executions.

POST /api/v1/workflows/{workflow_id}/validate

Validate the workflow definition and task types.

POST /api/v1/workflows/{workflow_id}/publish

Publish a new immutable workflow version.

GET /api/v1/workflows/{workflow_id}/versions

List published versions.

GET /api/v1/workflows/{workflow_id}/versions/{version}

Retrieve a specific workflow version.

## WORKFLOW EXECUTION

POST /api/v1/workflows/{workflow_id}/runs

Start a workflow execution.

Request should support:

- input_data.
- optional idempotency_key.
- optional version selection.

GET /api/v1/runs

List executions.

Support filters:

- status.
- workflow_id.
- date range.
- search.
- pagination.

GET /api/v1/runs/{run_id}

Get execution details.

GET /api/v1/runs/{run_id}/steps

List step executions.

GET /api/v1/runs/{run_id}/events

Retrieve execution events chronologically.

GET /api/v1/runs/{run_id}/attempts

Retrieve all attempts for a workflow run.

GET /api/v1/runs/{run_id}/timeline

Return an aggregated execution timeline.

POST /api/v1/runs/{run_id}/cancel

Request workflow cancellation.

POST /api/v1/runs/{run_id}/pause

Pause the workflow.

POST /api/v1/runs/{run_id}/resume

Resume the workflow.

POST /api/v1/runs/{run_id}/retry

Retry an eligible failed workflow run.

POST /api/v1/runs/{run_id}/steps/{step_execution_id}/retry

Manually retry an eligible failed step.

## TASK MANAGEMENT

GET /api/v1/tasks

List step executions.

Support filters:

- PENDING.
- QUEUED.
- RUNNING.
- RETRY_WAIT.
- COMPLETED.
- FAILED.

GET /api/v1/tasks/{task_execution_id}

Get detailed execution information.

GET /api/v1/tasks/{task_execution_id}/attempts

List execution attempts.

GET /api/v1/tasks/registry

List registered task types and their descriptions.

## EVENTS

GET /api/v1/events

List recent execution events.

Support filtering by event type, workflow run, and date range.

## API DESIGN RULES

- Use UUIDs.
- Use Pydantic request and response models.
- Use appropriate HTTP status codes.
- Use 404 for missing resources.
- Use 409 for conflicting state transitions or idempotency conflicts.
- Use 422 for invalid requests.
- Use consistent error response formats.
- Implement pagination.
- Validate all state transitions.
- Add API documentation through FastAPI OpenAPI.
- Avoid leaking internal exception traces to API clients.

Implement every endpoint above that belongs in the MVP. Do not create endpoints that simply return hardcoded example data.

For any endpoint that cannot reasonably be implemented in the MVP, document the limitation explicitly rather than pretending it works.

---

# 10. FRONTEND APPLICATION

Build a complete React + TypeScript dashboard.

The frontend must communicate with the actual backend APIs.

No hardcoded dashboard metrics.

No fake execution states.

No nonfunctional buttons.

Use a professional developer-tool aesthetic.

## Design direction

Product: Durable.

Visual style:

- Dark developer dashboard.
- Professional and minimal.
- High information density without visual clutter.
- Clear typography.
- Subtle borders.
- Consistent spacing.
- Neutral dark backgrounds.
- Green for successful execution.
- Red for failures.
- Amber for pending or retry states.
- Blue for active execution.

Use shadcn/ui components and Lucide icons.

The application should look like a serious developer platform rather than a generic admin template.

Use responsive layouts.

## A. Overview dashboard

Route: /

Display:

- Total workflows.
- Total executions.
- Running executions.
- Failed executions.
- Completed executions.
- Active workers.
- Recent executions.
- Execution success rate.
- Execution activity chart.
- System health indicators.

Fetch all information from the API.

## B. Workflow listing

Route: /workflows

Features:

- Search workflows.
- Filter by status.
- Create workflow.
- View workflow details.
- Display workflow versions.
- Publish workflow.

Each workflow row should show:

- Name.
- Description.
- Status.
- Latest version.
- Number of executions.
- Created date.

## C. Workflow builder

Route: /workflows/new

Build a visual workflow editor using React Flow.

Users should be able to:

- Add steps.
- Remove steps.
- Reorder steps.
- Configure task types.
- Edit task configuration.
- Configure retries.
- Configure timeouts.
- Validate the workflow.
- Save as draft.
- Publish.

For the MVP, the visual editor must enforce sequential execution.

Represent steps as nodes connected in order.

Provide a configuration panel when a node is selected.

Include a JSON definition preview.

Do not allow the frontend to create unsupported workflow structures.

## D. Workflow details

Route: /workflows/:workflowId

Display:

- Workflow information.
- Published versions.
- Workflow definition.
- Recent runs.
- Run workflow button.
- Validation and publishing actions.

Provide an input JSON editor when starting a workflow.

## E. Execution monitoring

Route: /runs

Display:

- All workflow runs.
- Status.
- Workflow name.
- Run ID.
- Start time.
- Duration.
- Step count.
- Last error.

Support filtering and searching.

## F. Execution details

Route: /runs/:runId

This is one of the most important screens.

Display:

- Workflow run ID.
- Workflow name.
- Current status.
- Start time.
- End time.
- Total duration.
- Input JSON.
- Final output JSON.
- Error details.

Provide a visual step execution timeline.

For every step display:

- Step name.
- Task type.
- Status.
- Attempt count.
- Start time.
- Duration.
- Worker ID.
- Error details.
- Output data.

Provide controls for:

- Retry.
- Cancel.
- Pause.
- Resume.

Only show actions valid for the current execution state.

Include a chronological event log.

## G. Worker monitoring

Route: /workers

Display:

- Registered workers.
- Worker status.
- Last heartbeat.
- Current task.
- Hostname.
- Number of executions.

Show unavailable or stale workers distinctly.

## H. System monitoring

Route: /system

Display:

- API connectivity.
- Database connectivity.
- Redis connectivity.
- Worker availability.
- Queue statistics.
- Execution metrics.

## I. Settings

Route: /settings

Show:

- API base URL.
- Application version.
- Environment information.
- Available task types.

Keep configuration limited to the MVP.

---

# 11. FRONTEND ENGINEERING REQUIREMENTS

Use:

- React Router.
- TanStack Query.
- Typed API client.
- Reusable components.
- Loading skeletons.
- Empty states.
- Error states.
- Confirmation dialogs.
- Toast notifications.
- Form validation.

Implement polling for live execution monitoring.

Suggested polling intervals:

- Execution details: 2 seconds while running.
- Dashboard metrics: 5 seconds.
- Worker health: 5 seconds.

Stop aggressive polling when data is no longer changing.

Use proper query invalidation after mutations.

Provide useful feedback when API requests fail.

Never silently ignore backend errors.

---

# 12. SAMPLE WORKFLOW AND DEMONSTRATION

Create a working example called:

"Reliable Document Processing Demo"

Include:

1. Validate input.
2. Transform text.
3. Simulate processing.
4. Generate output.
5. Return final result.

Create another demonstration workflow:

"Retry and Failure Recovery Demo"

Include:

1. Start task.
2. Execute random failure task.
3. Retry automatically.
4. Complete after successful retry.

Provide a workflow that intentionally exhausts its retries as well.

The demonstrations must use real backend task handlers and persisted database state.

Add example input JSON files or documented example requests.

---

# 13. TESTING REQUIREMENTS

Testing is mandatory.

## Backend unit tests

Test:

- Workflow definition validation.
- Task registration.
- Task execution.
- Retry calculations.
- State transitions.
- Idempotency.
- Cancellation.
- Workflow versioning.

## Backend integration tests

Test:

- Creating workflows.
- Publishing workflows.
- Starting runs.
- Executing steps.
- Retrieving outputs.
- Recording events.
- Retrying failures.
- Manual retry.
- Pause and resume.
- Cancellation.
- Pagination.
- Invalid state transitions.

## Durability tests

Specifically test:

1. Create a workflow.
2. Start execution.
3. Allow the worker to claim a task.
4. Simulate worker termination.
5. Wait for lease expiration.
6. Run recovery.
7. Verify that the abandoned task becomes eligible for another attempt.
8. Verify that execution history is preserved.

Also test:

- Redis restart and recovery.
- Duplicate start requests.
- Concurrent task claiming.
- Maximum retry exhaustion.
- Worker heartbeat expiration.

Use PostgreSQL for integration tests wherever PostgreSQL-specific locking behavior is being tested.

Do not substitute SQLite for concurrency or lease tests.

## Frontend tests

Test:

- Dashboard rendering.
- Workflow listing.
- Workflow creation.
- Workflow editor validation.
- Starting a workflow.
- Execution status rendering.
- Retry action.
- Error handling.

## Test execution

Run:

- Backend unit tests.
- Backend integration tests.
- Frontend tests.
- Frontend production build.
- Docker Compose startup.
- Health checks.

Report actual test results.

Never report tests as passing if they were not executed.

---

# 14. SECURITY AND INPUT VALIDATION

For the MVP:

- Validate every request.
- Restrict accepted task types to registered handlers.
- Do not execute arbitrary Python code.
- Avoid shell command execution from workflow inputs.
- Limit JSON payload sizes.
- Prevent unrestricted execution time.
- Validate workflow step counts.
- Avoid leaking sensitive information in errors.
- Use environment variables for credentials.
- Configure CORS explicitly.
- Never commit secrets.
- Do not expose internal database credentials to the frontend.

Authentication and multi-tenant authorization are future production requirements, but keep the code structured so they can be added.

Clearly document that the initial MVP is intended for a trusted local development environment and must not be exposed publicly without additional security controls.

---

# 15. DOCKER AND LOCAL DEVELOPMENT

Create or update docker-compose.yml.

Services:

1. api
2. worker
3. frontend
4. postgres
5. redis

Requirements:

- Health checks.
- Service dependencies.
- Persistent PostgreSQL volume.
- Appropriate environment variables.
- Separate API and worker processes.
- Database migration execution.
- Restart policies.
- Internal service networking.

The API should be accessible at:

http://localhost:8001

Frontend:

http://localhost:5173

Swagger documentation:

http://localhost:8001/docs

Health:

http://localhost:8001/healthz

The complete application must start using:

docker compose up --build

Document the clean startup process, including database migration handling.

Ensure that the Docker backend image includes all required application files, Alembic configuration, migrations, and tests where needed.

---

# 16. PROJECT STRUCTURE

Maintain a clean structure similar to:

backend/
    app/
        main.py
        api/
            v1/
                routes/
        core/
            config.py
            logging.py
        db/
            session.py
            base.py
        models/
        schemas/
        repositories/
        services/
        engine/
            scheduler.py
            executor.py
            recovery.py
            leases.py
            state_machine.py
        tasks/
            registry.py
            builtin/
        workers/
            worker.py
            heartbeat.py
        utils/
    migrations/
    tests/
        unit/
        integration/
    Dockerfile
    requirements.txt
    alembic.ini

frontend/
    src/
        api/
        components/
        features/
            dashboard/
            workflows/
            runs/
            workers/
            system/
        hooks/
        layouts/
        pages/
        routes/
        types/
        utils/
    Dockerfile
    package.json

docker-compose.yml
.env.example
README.md

You may adapt this structure to the existing repository.

Avoid unnecessary abstractions and excessive file fragmentation.

---

# 17. LOGGING AND OBSERVABILITY

Implement structured logging.

Include:

- Timestamp.
- Log level.
- Service name.
- Worker ID where applicable.
- Workflow run ID.
- Step execution ID.
- Attempt number.
- Error information.

Record important execution events:

- WORKFLOW_CREATED
- WORKFLOW_PUBLISHED
- WORKFLOW_STARTED
- STEP_QUEUED
- STEP_STARTED
- STEP_COMPLETED
- STEP_FAILED
- STEP_RETRY_SCHEDULED
- WORKER_REGISTERED
- WORKER_HEARTBEAT
- LEASE_EXPIRED
- STEP_RECOVERED
- WORKFLOW_COMPLETED
- WORKFLOW_FAILED
- WORKFLOW_PAUSED
- WORKFLOW_RESUMED
- WORKFLOW_CANCELLED

Make events available through the REST API and frontend.

Do not log secrets or entire sensitive payloads.

---

# 18. PERFORMANCE AND ENGINEERING CONSTRAINTS

For the MVP:

- Support multiple worker processes.
- Use safe concurrent task claiming.
- Avoid blocking the FastAPI event loop.
- Use asynchronous database and Redis operations where appropriate.
- Use database indexes for frequently queried execution states.
- Implement pagination rather than returning unlimited records.
- Avoid N+1 database query patterns.
- Keep task execution isolated from API request handling.
- Keep execution history persistent.
- Handle Redis disconnection gracefully.
- Ensure worker shutdown handles active tasks sensibly.

Do not optimize prematurely.

Prioritize correctness, persistence, and recoverability over raw throughput.

---

# 19. MVP ACCEPTANCE CRITERIA

The project is considered complete only when the following scenario works end-to-end.

### Scenario A: Normal execution

1. Start the application.
2. Open the frontend.
3. Create a workflow.
4. Add three tasks.
5. Configure retry policies.
6. Validate the workflow.
7. Publish it.
8. Start a workflow run.
9. Observe tasks executing.
10. View task outputs.
11. Confirm the workflow reaches COMPLETED.
12. Inspect execution history.

### Scenario B: Automatic retries

1. Create a workflow containing a task that intentionally fails.
2. Configure three maximum attempts.
3. Start the workflow.
4. Observe the initial failure.
5. Observe retry scheduling.
6. Observe another attempt.
7. Confirm final completion or failure according to the task behavior.
8. Inspect all attempt records.

### Scenario C: Worker crash recovery

1. Start a workflow.
2. Let a worker acquire a task.
3. Stop the worker abruptly.
4. Wait for lease expiry.
5. Allow the recovery mechanism to run.
6. Restart the worker if necessary.
7. Confirm the task becomes eligible for execution again.
8. Verify that the previous attempt remains in execution history.
9. Verify that the workflow can eventually complete.

### Scenario D: Persistence

1. Start a workflow.
2. Stop the API.
3. Restart the API.
4. Confirm the workflow state is still available.
5. Stop Redis.
6. Restart Redis.
7. Confirm pending tasks can still be discovered from PostgreSQL.
8. Confirm execution continues.

### Scenario E: Frontend functionality

Verify that:

- Dashboard metrics reflect database state.
- Workflows can be created.
- Workflow definitions can be edited.
- Workflows can be published.
- Runs can be started.
- Execution status updates automatically.
- Failed tasks display error details.
- Retries can be triggered.
- Workers are visible.
- Events can be inspected.

---

# 20. DEVELOPMENT EXECUTION PLAN

Implement in the following order.

## Phase 1 — Repository assessment

Inspect the existing project.

Identify existing implementations and gaps.

Provide a short assessment before modifying files.

## Phase 2 — Backend foundations

Implement or complete:

- Database models.
- Migrations.
- Schemas.
- Repositories.
- Workflow definition validation.
- Workflow versioning.

## Phase 3 — Execution engine

Implement:

- Task registry.
- Workflow executor.
- Step scheduling.
- Worker process.
- Task claiming.
- Lease management.
- Heartbeats.
- Retry logic.
- Recovery mechanism.
- Execution events.

## Phase 4 — REST API

Implement all MVP API endpoints and verify them using integration tests.

## Phase 5 — Frontend

Implement the dashboard, workflow builder, execution monitoring, worker monitoring, and system status screens.

Connect every screen to the real backend.

## Phase 6 — Docker integration

Verify the complete application starts and operates through Docker Compose.

## Phase 7 — Reliability testing

Run all acceptance scenarios.

Fix actual failures.

Do not skip worker crash recovery or Redis restart testing.

## Phase 8 — Documentation

Create a comprehensive README covering:

- Product overview.
- Architecture.
- Technology stack.
- Repository structure.
- Installation.
- Environment variables.
- Docker startup.
- Database migrations.
- API documentation.
- Workflow definition examples.
- Built-in task types.
- Retry behavior.
- Worker recovery.
- Testing.
- Current limitations.
- Future roadmap.

---

# 21. IMPORTANT IMPLEMENTATION RULES

1. Do not stop after generating an architecture document.
2. Do not produce pseudocode in place of working implementations.
3. Do not build a static frontend.
4. Do not use mocked backend responses for the main application.
5. Do not claim functionality that has not been implemented.
6. Do not remove existing functionality without justification.
7. Do not introduce unnecessary frameworks or infrastructure.
8. Do not leave critical endpoints as TODOs.
9. Do not ignore test failures.
10. Do not sacrifice database consistency for implementation speed.
11. Do not claim exactly-once execution.
12. Do not claim production readiness.
13. Do not silently change existing database schemas.
14. Create migrations for every database schema modification.
15. Keep the application runnable throughout development.

When you encounter ambiguity, inspect the existing implementation and choose the simplest technically sound solution.

If an architectural decision has important trade-offs, explain them briefly and proceed with the most appropriate MVP choice.

---

# 22. FINAL DELIVERABLES

At completion, provide:

1. Fully implemented backend.
2. Fully implemented frontend.
3. Working worker service.
4. PostgreSQL schema and migrations.
5. Redis integration.
6. Docker Compose configuration.
7. Complete REST API.
8. Workflow builder.
9. Execution monitoring dashboard.
10. Worker monitoring.
11. Built-in demonstration workflows.
12. Automated tests.
13. Updated README.
14. Environment example.
15. Actual test execution report.

Include a final implementation report containing:

- Features implemented.
- Features partially implemented.
- Features not implemented.
- Architectural decisions.
- Database design.
- REST endpoint inventory.
- Test results.
- Commands to start the project.
- Known limitations.
- Recommended next steps.

## DEFINITION OF DONE

Durable must be a real, locally runnable workflow orchestration platform.

A user must be able to create a workflow, publish it, execute it, monitor its steps, experience actual task failures and automatic retries, terminate a worker, and observe recovery using persisted execution state.

The entire system must be demonstrable through the React frontend and REST API.

**Build the working product, verify it, and document the actual implementation.**