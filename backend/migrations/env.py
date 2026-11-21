import asyncio
from alembic import context
from app.db import engine
from app.models import Base


def include_name(name, type_, parent_names):
    if type_ == "schema":
        return name == "durable"
    return True


def migrate(connection):
    context.configure(
        connection=connection,
        target_metadata=Base.metadata,
        compare_type=True,
        include_schemas=True,
        include_name=include_name,
    )
    with context.begin_transaction():
        context.run_migrations()


async def main():
    async with engine.connect() as conn:
        await conn.run_sync(migrate)
    await engine.dispose()


asyncio.run(main())
