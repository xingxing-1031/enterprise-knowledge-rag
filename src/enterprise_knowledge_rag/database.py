from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI

from enterprise_knowledge_rag.config import Settings


def create_connection_pool(settings: Settings) -> Any:
    """Create a lazy psycopg pool; the FastAPI lifespan owns open and close."""
    from psycopg_pool import ConnectionPool

    return ConnectionPool(
        conninfo=settings.database_url,
        min_size=settings.database_pool_min_size,
        max_size=settings.database_pool_max_size,
        timeout=settings.database_pool_timeout_seconds,
        open=False,
    )


def connection_pool_lifespan(
    pool: Any,
    *,
    timeout_seconds: float,
) -> Callable[[FastAPI], Any]:
    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        del app
        pool.open(wait=True, timeout=timeout_seconds)
        try:
            yield
        finally:
            pool.close()

    return lifespan
