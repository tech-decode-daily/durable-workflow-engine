"""Versioned engine in a separate schema. The original public tables retain their data."""
from alembic import op

revision = "0002_versioned_engine"
down_revision = "0001_initial"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("""
CREATE SCHEMA durable
""")
    op.execute("""
CREATE TABLE durable.workflows (
	name VARCHAR(120) NOT NULL,
	description TEXT,
	workflow_key VARCHAR(120) NOT NULL,
	status VARCHAR(12) NOT NULL,
	draft JSONB NOT NULL,
	id UUID NOT NULL,
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
	updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
	PRIMARY KEY (id),
	CHECK (status in ('draft','active')),
	UNIQUE (workflow_key)
)
""")
    op.execute("""
CREATE TABLE durable.workers (
	worker_name VARCHAR NOT NULL,
	hostname VARCHAR NOT NULL,
	status VARCHAR NOT NULL,
	registered_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
	last_heartbeat_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
	current_task_id UUID,
	id UUID NOT NULL,
	PRIMARY KEY (id)
)
""")
    op.execute("""
CREATE INDEX ix_durable_workers_last_heartbeat_at ON durable.workers (last_heartbeat_at)
""")
    op.execute("""
CREATE TABLE durable.workflow_versions (
	workflow_id UUID NOT NULL,
	version INTEGER NOT NULL,
	definition JSONB NOT NULL,
	id UUID NOT NULL,
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
	PRIMARY KEY (id),
	UNIQUE (workflow_id, version),
	FOREIGN KEY(workflow_id) REFERENCES durable.workflows (id)
)
""")
    op.execute("""
CREATE TABLE durable.workflow_steps (
	workflow_version_id UUID NOT NULL,
	step_key VARCHAR NOT NULL,
	step_name VARCHAR NOT NULL,
	task_type VARCHAR NOT NULL,
	configuration JSONB NOT NULL,
	position INTEGER NOT NULL,
	retry_limit INTEGER NOT NULL,
	retry_delay_seconds INTEGER NOT NULL,
	max_delay_seconds INTEGER NOT NULL,
	timeout_seconds INTEGER NOT NULL,
	id UUID NOT NULL,
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
	PRIMARY KEY (id),
	UNIQUE (workflow_version_id, step_key),
	UNIQUE (workflow_version_id, position),
	FOREIGN KEY(workflow_version_id) REFERENCES durable.workflow_versions (id)
)
""")
    op.execute("""
CREATE TABLE durable.workflow_runs (
	workflow_id UUID NOT NULL,
	workflow_version_id UUID NOT NULL,
	status VARCHAR NOT NULL,
	input_data JSONB NOT NULL,
	output_data JSONB,
	error_message TEXT,
	started_at TIMESTAMP WITH TIME ZONE,
	completed_at TIMESTAMP WITH TIME ZONE,
	idempotency_key VARCHAR,
	request_hash VARCHAR,
	id UUID NOT NULL,
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
	updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
	PRIMARY KEY (id),
	UNIQUE (workflow_id, idempotency_key),
	CHECK (status in ('PENDING','RUNNING','PAUSED','COMPLETED','FAILED','CANCELLED')),
	FOREIGN KEY(workflow_id) REFERENCES durable.workflows (id),
	FOREIGN KEY(workflow_version_id) REFERENCES durable.workflow_versions (id)
)
""")
    op.execute("""
CREATE INDEX ix_durable_workflow_runs_status ON durable.workflow_runs (status)
""")
    op.execute("""
CREATE INDEX ix_durable_workflow_runs_workflow_id ON durable.workflow_runs (workflow_id)
""")
    op.execute("""
CREATE INDEX ix_runs_created ON durable.workflow_runs (created_at)
""")
    op.execute("""
CREATE TABLE durable.step_executions (
	workflow_run_id UUID NOT NULL,
	workflow_step_id UUID NOT NULL,
	status VARCHAR NOT NULL,
	input_data JSONB NOT NULL,
	output_data JSONB,
	error_message TEXT,
	attempt_count INTEGER NOT NULL,
	max_attempts INTEGER NOT NULL,
	available_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
	lease_owner UUID,
	lease_expires_at TIMESTAMP WITH TIME ZONE,
	heartbeat_at TIMESTAMP WITH TIME ZONE,
	started_at TIMESTAMP WITH TIME ZONE,
	completed_at TIMESTAMP WITH TIME ZONE,
	id UUID NOT NULL,
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
	updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
	PRIMARY KEY (id),
	UNIQUE (workflow_run_id, workflow_step_id),
	CHECK (status in ('PENDING','QUEUED','RUNNING','RETRY_WAIT','COMPLETED','FAILED','CANCELLED')),
	FOREIGN KEY(workflow_run_id) REFERENCES durable.workflow_runs (id),
	FOREIGN KEY(workflow_step_id) REFERENCES durable.workflow_steps (id),
	FOREIGN KEY(lease_owner) REFERENCES durable.workers (id)
)
""")
    op.execute("""
CREATE INDEX ix_leases ON durable.step_executions (status, lease_expires_at)
""")
    op.execute("""
CREATE INDEX ix_ready ON durable.step_executions (status, available_at)
""")
    op.execute("""
CREATE INDEX ix_durable_step_executions_workflow_run_id ON durable.step_executions (workflow_run_id)
""")
    op.execute("""
CREATE TABLE durable.execution_attempts (
	step_execution_id UUID NOT NULL,
	attempt_number INTEGER NOT NULL,
	worker_id UUID NOT NULL,
	status VARCHAR NOT NULL,
	input_data JSONB NOT NULL,
	output_data JSONB,
	error_message VARCHAR,
	started_at TIMESTAMP WITH TIME ZONE NOT NULL,
	completed_at TIMESTAMP WITH TIME ZONE,
	duration_ms INTEGER,
	id UUID NOT NULL,
	PRIMARY KEY (id),
	UNIQUE (step_execution_id, attempt_number),
	FOREIGN KEY(step_execution_id) REFERENCES durable.step_executions (id),
	FOREIGN KEY(worker_id) REFERENCES durable.workers (id)
)
""")
    op.execute("""
CREATE INDEX ix_durable_execution_attempts_worker_id ON durable.execution_attempts (worker_id)
""")
    op.execute("""
CREATE TABLE durable.execution_events (
	workflow_run_id UUID,
	step_execution_id UUID,
	event_type VARCHAR NOT NULL,
	message VARCHAR NOT NULL,
	metadata JSONB NOT NULL,
	sequence BIGINT GENERATED BY DEFAULT AS IDENTITY,
	id UUID NOT NULL,
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
	PRIMARY KEY (id),
	FOREIGN KEY(workflow_run_id) REFERENCES durable.workflow_runs (id),
	FOREIGN KEY(step_execution_id) REFERENCES durable.step_executions (id),
	UNIQUE (sequence)
)
""")
    op.execute("""
CREATE INDEX ix_durable_execution_events_event_type ON durable.execution_events (event_type)
""")
    op.execute("""
CREATE INDEX ix_events_run_sequence ON durable.execution_events (workflow_run_id, sequence)
""")
    op.execute("""
ALTER TABLE durable.workers ADD CONSTRAINT fk_worker_current_task FOREIGN KEY(current_task_id) REFERENCES durable.step_executions (id)
""")
    op.execute("""
CREATE FUNCTION durable.reject_history_change() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    RAISE EXCEPTION 'Immutable Durable record';
END $$
""")
    op.execute("""
CREATE TRIGGER immutable_rows BEFORE UPDATE OR DELETE ON durable.execution_events FOR EACH ROW EXECUTE FUNCTION durable.reject_history_change()
""")
    op.execute("""
CREATE TRIGGER immutable_rows BEFORE UPDATE OR DELETE ON durable.workflow_versions FOR EACH ROW EXECUTE FUNCTION durable.reject_history_change()
""")
    op.execute("""
CREATE TRIGGER immutable_rows BEFORE UPDATE OR DELETE ON durable.workflow_steps FOR EACH ROW EXECUTE FUNCTION durable.reject_history_change()
""")


def downgrade():
    op.execute("""
ALTER TABLE durable.workers DROP CONSTRAINT fk_worker_current_task
""")
    op.execute("""
DROP TABLE durable.execution_events
""")
    op.execute("""
DROP TABLE durable.execution_attempts
""")
    op.execute("""
DROP TABLE durable.step_executions
""")
    op.execute("""
DROP TABLE durable.workflow_runs
""")
    op.execute("""
DROP TABLE durable.workflow_steps
""")
    op.execute("""
DROP TABLE durable.workflow_versions
""")
    op.execute("""
DROP TABLE durable.workers
""")
    op.execute("""
DROP TABLE durable.workflows
""")
    op.execute("""
DROP FUNCTION durable.reject_history_change()
""")
    op.execute("""
DROP SCHEMA durable
""")
