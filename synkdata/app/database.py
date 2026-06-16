"""
Configuración de conexiones a bases de datos para SynkData.

Gestiona los pools de conexión asíncronos para:
- PostgreSQL (SQLAlchemy async)
- Redis (caché y rate-limiting)
- Neo4j (grafo de conocimiento de identidades)

Uso:
    from app.database import get_db_session, get_redis, get_neo4j_session
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from typing import AsyncGenerator, Optional

from neo4j import AsyncGraphDatabase, AsyncDriver, AsyncSession
from redis.asyncio import Redis, ConnectionPool as RedisConnectionPool
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.config import get_settings
from app.models.base import Base  # noqa: F401 — re-exported for convenience

logger = logging.getLogger(__name__)

# Base is imported from app.models.base to ensure a single source of truth.
# Re-exported here for backward compatibility: from app.database import Base

# ---------------------------------------------------------------------------
# PostgreSQL — Motor y sesión asíncrona
# ---------------------------------------------------------------------------
_engine: Optional[AsyncEngine] = None
_async_session_factory: Optional[async_sessionmaker[AsyncSession]] = None


def _create_engine() -> AsyncEngine:
    """
    Crea el motor asíncrono de SQLAlchemy para PostgreSQL.

    Returns:
        AsyncEngine: Motor configurado con pool de conexiones.
    """
    settings = get_settings()
    return create_async_engine(
        settings.DATABASE_URL,
        echo=settings.DATABASE_ECHO,
        pool_size=settings.DATABASE_POOL_SIZE,
        max_overflow=settings.DATABASE_MAX_OVERFLOW,
        pool_recycle=settings.DATABASE_POOL_RECYCLE,
        pool_pre_ping=True,
        # Parámetros específicos de asyncpg
        connect_args={
            "statement_cache_size": 0,  # Evita problemas con prepared statements en pooling
            "command_timeout": 60,
        },
    )


def init_db() -> None:
    """
    Inicializa el motor y la fábrica de sesiones de PostgreSQL.

    Debe llamarse durante el startup de la aplicación.
    """
    global _engine, _async_session_factory  # noqa: PLW0603

    settings = get_settings()
    _engine = _create_engine()
    _async_session_factory = async_sessionmaker(
        bind=_engine,
        class_=AsyncSession,
        expire_on_commit=False,
        autocommit=False,
        autoflush=False,
    )
    logger.info(
        "Motor PostgreSQL inicializado — pool_size=%d, max_overflow=%d",
        settings.DATABASE_POOL_SIZE,
        settings.DATABASE_MAX_OVERFLOW,
    )


async def close_db() -> None:
    """
    Cierra el motor de PostgreSQL y libera todas las conexiones.

    Debe llamarse durante el shutdown de la aplicación.
    """
    global _engine, _async_session_factory  # noqa: PLW0603

    if _engine is not None:
        await _engine.dispose()
        logger.info("Motor PostgreSQL cerrado correctamente.")

    _engine = None
    _async_session_factory = None


@asynccontextmanager
async def get_db_session() -> AsyncGenerator[AsyncSession, None]:
    """
    Proveedor de sesión asíncrona de PostgreSQL.

    Utilizable como context manager para garantizar el cierre de la sesión
    y el manejo adecuado de transacciones.

    Yields:
        AsyncSession: Sesión activa de SQLAlchemy.

    Example:
        async with get_db_session() as session:
            result = await session.execute(select(User))
    """
    if _async_session_factory is None:
        raise RuntimeError(
            "La base de datos no ha sido inicializada. "
            "Llame a init_db() durante el startup de la aplicación."
        )

    session: AsyncSession = _async_session_factory()
    try:
        yield session
        await session.commit()
    except Exception:
        await session.rollback()
        raise
    finally:
        await session.close()


# ---------------------------------------------------------------------------
# Redis — Conexión asíncrona para caché
# ---------------------------------------------------------------------------
_redis_pool: Optional[RedisConnectionPool] = None
_redis_client: Optional[Redis] = None


def init_redis() -> None:
    """
    Inicializa el pool de conexiones y el cliente de Redis.

    Debe llamarse durante el startup de la aplicación.
    """
    global _redis_pool, _redis_client  # noqa: PLW0603

    settings = get_settings()
    _redis_pool = RedisConnectionPool.from_url(
        settings.REDIS_URL,
        decode_responses=True,
        max_connections=50,
        socket_connect_timeout=5,
        socket_timeout=5,
        retry_on_timeout=True,
    )
    _redis_client = Redis(connection_pool=_redis_pool)
    logger.info("Cliente Redis inicializado — url=%s", settings.REDIS_URL)


async def close_redis() -> None:
    """
    Cierra la conexión a Redis y libera el pool.

    Debe llamarse durante el shutdown de la aplicación.
    """
    global _redis_pool, _redis_client  # noqa: PLW0603

    if _redis_client is not None:
        await _redis_client.aclose()
        logger.info("Cliente Redis cerrado correctamente.")

    if _redis_pool is not None:
        await _redis_pool.aclose()

    _redis_client = None
    _redis_pool = None


def get_redis() -> Redis:
    """
    Retorna el cliente Redis asíncrono.

    Returns:
        Redis: Cliente Redis configurado.

    Raises:
        RuntimeError: Si Redis no ha sido inicializado.
    """
    if _redis_client is None:
        raise RuntimeError(
            "Redis no ha sido inicializado. "
            "Llame a init_redis() durante el startup de la aplicación."
        )
    return _redis_client


# ---------------------------------------------------------------------------
# Neo4j — Driver asíncrono para el grafo de conocimiento
# ---------------------------------------------------------------------------
_neo4j_driver: Optional[AsyncDriver] = None


def init_neo4j() -> None:
    """
    Inicializa el driver asíncrono de Neo4j.

    Debe llamarse durante el startup de la aplicación.
    """
    global _neo4j_driver  # noqa: PLW0603

    settings = get_settings()
    _neo4j_driver = AsyncGraphDatabase.driver(
        settings.NEO4J_URI,
        auth=(settings.NEO4J_USER, settings.NEO4J_PASSWORD),
        max_connection_pool_size=settings.NEO4J_MAX_CONNECTION_POOL_SIZE,
        connection_timeout=settings.NEO4J_CONNECTION_TIMEOUT,
    )
    logger.info("Driver Neo4j inicializado — uri=%s", settings.NEO4J_URI)


async def close_neo4j() -> None:
    """
    Cierra el driver de Neo4j y libera las conexiones.

    Debe llamarse durante el shutdown de la aplicación.
    """
    global _neo4j_driver  # noqa: PLW0603

    if _neo4j_driver is not None:
        await _neo4j_driver.close()
        logger.info("Driver Neo4j cerrado correctamente.")

    _neo4j_driver = None


@asynccontextmanager
async def get_neo4j_session() -> AsyncGenerator[AsyncSession, None]:
    """
    Proveedor de sesión asíncrona de Neo4j.

    Utilizable como context manager para garantizar el cierre de la sesión
    y el manejo de transacciones Cypher.

    Yields:
        AsyncSession: Sesión activa de Neo4j.

    Example:
        async with get_neo4j_session() as session:
            result = await session.run("MATCH (n:Person) RETURN n LIMIT 10")
    """
    if _neo4j_driver is None:
        raise RuntimeError(
            "Neo4j no ha sido inicializado. "
            "Llame a init_neo4j() durante el startup de la aplicación."
        )

    settings = get_settings()
    session: AsyncSession = _neo4j_driver.session(database=settings.NEO4J_DATABASE)
    try:
        yield session
    finally:
        await session.close()


# ---------------------------------------------------------------------------
# Health-check de todas las conexiones
# ---------------------------------------------------------------------------
async def check_database_health() -> dict[str, bool]:
    """
    Verifica el estado de todas las conexiones a bases de datos.

    Returns:
        dict: Estado de cada servicio (True = saludable, False = error).
    """
    health: dict[str, bool] = {}

    # PostgreSQL
    try:
        async with get_db_session() as session:
            await session.execute(
                __import__("sqlalchemy").text("SELECT 1")
            )
        health["postgresql"] = True
    except Exception as exc:
        logger.error("Health-check PostgreSQL falló: %s", exc)
        health["postgresql"] = False

    # Redis
    try:
        redis = get_redis()
        await redis.ping()
        health["redis"] = True
    except Exception as exc:
        logger.error("Health-check Redis falló: %s", exc)
        health["redis"] = False

    # Neo4j
    try:
        async with get_neo4j_session() as session:
            await session.run("RETURN 1")
        health["neo4j"] = True
    except Exception as exc:
        logger.error("Health-check Neo4j falló: %s", exc)
        health["neo4j"] = False

    return health
