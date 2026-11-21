import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Settings:
    database_url: str = os.getenv(
        "DATABASE_URL", "postgresql+asyncpg://durable@localhost/durable"
    )
    redis_url: str = os.getenv("REDIS_URL", "redis://localhost:6379/0")
    lease_seconds: int = int(os.getenv("LEASE_SECONDS", "12"))
    heartbeat_seconds: float = float(os.getenv("HEARTBEAT_SECONDS", "2"))
    poll_seconds: float = float(os.getenv("POLL_SECONDS", "1"))
    max_retry_delay: int = int(os.getenv("MAX_RETRY_DELAY_SECONDS", "300"))
    cors_origins: str = os.getenv(
        "CORS_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173"
    )
    environment: str = os.getenv("APP_ENV", "local")
    version: str = "0.1.0"

    def __post_init__(self):
        if not 0 < self.heartbeat_seconds < self.lease_seconds / 2:
            raise ValueError(
                "Heartbeat interval must be positive and less than half the lease"
            )
        if self.poll_seconds <= 0 or self.max_retry_delay < 1:
            raise ValueError("Poll interval and retry delay cap must be positive")


settings = Settings()
