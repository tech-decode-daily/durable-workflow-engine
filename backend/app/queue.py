import asyncio

from redis.asyncio import Redis
from redis.exceptions import RedisError

from .config import settings

client = Redis.from_url(
    settings.redis_url,
    socket_connect_timeout=0.4,
    socket_timeout=settings.poll_seconds + 1,
)
KEY = "durable:v1:wake"


async def notify():
    try:
        async with client.pipeline(transaction=True) as pipe:
            await pipe.lpush(KEY, "1").ltrim(KEY, 0, 63).execute()
    except (RedisError, OSError):
        pass  # Committed work is independently discoverable through the database.


async def wait():
    try:
        await client.brpop(KEY, timeout=settings.poll_seconds)
    except (RedisError, OSError):
        await asyncio.sleep(settings.poll_seconds)


async def available():
    try:
        return bool(await client.ping())
    except (RedisError, OSError):
        return False
