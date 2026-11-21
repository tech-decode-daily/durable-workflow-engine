"""Run PostgreSQL tests in a unique disposable database on the configured server."""

import os
import subprocess
import sys
from uuid import uuid4

import psycopg
from psycopg import sql
from sqlalchemy.engine import make_url


def main():
    url = make_url(os.environ["DATABASE_URL"])
    name = "durable_test_" + uuid4().hex
    admin = url.set(drivername="postgresql", database="postgres").render_as_string(
        hide_password=False
    )
    env = {
        **os.environ,
        "DATABASE_URL": url.set(database=name).render_as_string(hide_password=False),
        "DURABLE_TEST_DB": name,
        "LEASE_SECONDS": "2",
        "HEARTBEAT_SECONDS": "0.3",
        "POLL_SECONDS": "0.2",
        "REDIS_URL": os.environ["REDIS_URL"].rsplit("/", 1)[0] + "/15",
    }
    with psycopg.connect(admin, autocommit=True) as db:
        db.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(name)))
        try:
            subprocess.run(
                [sys.executable, "-m", "alembic", "upgrade", "head"],
                env=env,
                check=True,
            )
            return subprocess.run(
                [sys.executable, "-m", "pytest", "-q", *sys.argv[1:]], env=env
            ).returncode
        finally:
            db.execute(
                sql.SQL("DROP DATABASE {} WITH (FORCE)").format(sql.Identifier(name))
            )


if __name__ == "__main__":
    sys.exit(main())
