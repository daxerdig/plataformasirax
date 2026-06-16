"""
Punto de entrada principal de la aplicación SynkData Identity Intelligence Platform.

Este módulo configura y arranca la aplicación FastAPI, incluyendo:
- Middleware CORS y de logging
- Manejadores de excepciones globales
- Rutas de health-check
- Eventos de startup/shutdown para conexiones a bases de datos
- Inclusión de todos los routers de la API
"""

from __future__ import annotations

import logging
import time
import uuid
from contextlib import asynccontextmanager
from typing import AsyncGenerator

from fastapi import FastAPI, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.config import Environment, get_settings
from app.database import (
    check_database_health,
    close_db,
    close_neo4j,
    close_redis,
    init_db,
    init_neo4j,
    init_redis,
)

# ---------------------------------------------------------------------------
# Configuración de logging
# ---------------------------------------------------------------------------
logger = logging.getLogger("synkdata")


def _configure_logging() -> None:
    """Configura el sistema de logging según la configuración del proyecto."""
    settings = get_settings()
    logging.basicConfig(
        level=settings.LOG_LEVEL.value,
        format=settings.LOG_FORMAT,
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    # Silenciar loggers ruidosos en producción
    if settings.is_production:
        for noisy in ("uvicorn.access", "httpx", "httpcore"):
            logging.getLogger(noisy).setLevel(logging.WARNING)

    logger.info(
        "Logging configurado — nivel=%s, entorno=%s",
        settings.LOG_LEVEL.value,
        settings.ENV.value,
    )


# ---------------------------------------------------------------------------
# Lifespan — Startup / Shutdown
# ---------------------------------------------------------------------------
@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """
    Gestor del ciclo de vida de la aplicación FastAPI.

    Ejecuta las rutinas de inicialización al arrancar y de limpieza al detener:
    - Inicializa/cierra PostgreSQL, Redis y Neo4j
    - Configura el sistema de logging
    """
    # ── Startup ───────────────────────────────────────────────────────────
    _configure_logging()
    logger.info("🚀 Iniciando SynkData Identity Intelligence Platform...")

    init_db()
    init_redis()
    init_neo4j()

    logger.info("✅ Todas las conexiones a bases de datos inicializadas.")
    yield

    # ── Shutdown ──────────────────────────────────────────────────────────
    logger.info("🛑 Cerrando conexiones a bases de datos...")
    await close_db()
    await close_redis()
    await close_neo4j()
    logger.info("✅ Todas las conexiones cerradas correctamente.")


# ---------------------------------------------------------------------------
# Creación de la aplicación FastAPI
# ---------------------------------------------------------------------------
def create_app() -> FastAPI:
    """
    Fábrica de la aplicación FastAPI.

    Configura middleware, manejadores de excepciones y routers.

    Returns:
        FastAPI: Aplicación configurada y lista para ejecutar.
    """
    settings = get_settings()

    app = FastAPI(
        title=settings.APP_NAME,
        version=settings.APP_VERSION,
        description=settings.APP_DESCRIPTION,
        docs_url=f"{settings.API_PREFIX}/docs" if not settings.is_production else None,
        redoc_url=f"{settings.API_PREFIX}/redoc" if not settings.is_production else None,
        openapi_url=f"{settings.API_PREFIX}/openapi.json"
        if not settings.is_production
        else None,
        lifespan=lifespan,
    )

    # ── Middleware CORS ───────────────────────────────────────────────────
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.CORS_ORIGINS,
        allow_credentials=settings.CORS_ALLOW_CREDENTIALS,
        allow_methods=settings.CORS_ALLOW_METHODS,
        allow_headers=settings.CORS_ALLOW_HEADERS,
    )

    # ── Middleware de Logging ─────────────────────────────────────────────
    @app.middleware("http")
    async def logging_middleware(request: Request, call_next):
        """
        Middleware que registra cada petición HTTP con timing y request ID.

        Agrega un header ``X-Request-ID`` a la respuesta para trazabilidad.
        Registra método, ruta, código de estado y duración de cada petición.
        """
        request_id = request.headers.get(
            "X-Request-ID", str(uuid.uuid4())
        )

        start_time = time.perf_counter()
        method = request.method
        path = request.url.path

        logger.info(
            "→ %s %s [request_id=%s]",
            method,
            path,
            request_id,
        )

        response = await call_next(request)

        duration_ms = (time.perf_counter() - start_time) * 1000
        status_code = response.status_code

        log_level = logging.WARNING if status_code >= 400 else logging.INFO
        logger.log(
            log_level,
            "← %s %s → %d (%.1fms) [request_id=%s]",
            method,
            path,
            status_code,
            duration_ms,
            request_id,
        )

        response.headers["X-Request-ID"] = request_id
        response.headers["X-Response-Time-ms"] = f"{duration_ms:.1f}"
        return response

    # ── Manejadores de excepciones ────────────────────────────────────────
    @app.exception_handler(ValueError)
    async def value_error_handler(request: Request, exc: ValueError):
        """Maneja errores de validación de valores con respuesta 400."""
        logger.warning("ValueError en %s: %s", request.url.path, exc)
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content={
                "detail": str(exc),
                "error_type": "validation_error",
                "path": str(request.url.path),
            },
        )

    @app.exception_handler(PermissionError)
    async def permission_error_handler(request: Request, exc: PermissionError):
        """Maneja errores de permisos con respuesta 403."""
        logger.warning("PermissionError en %s: %s", request.url.path, exc)
        return JSONResponse(
            status_code=status.HTTP_403_FORBIDDEN,
            content={
                "detail": str(exc),
                "error_type": "permission_denied",
                "path": str(request.url.path),
            },
        )

    @app.exception_handler(FileNotFoundError)
    async def file_not_found_handler(request: Request, exc: FileNotFoundError):
        """Maneja errores de archivo no encontrado con respuesta 404."""
        logger.warning("FileNotFoundError en %s: %s", request.url.path, exc)
        return JSONResponse(
            status_code=status.HTTP_404_NOT_FOUND,
            content={
                "detail": str(exc),
                "error_type": "resource_not_found",
                "path": str(request.url.path),
            },
        )

    @app.exception_handler(Exception)
    async def generic_exception_handler(request: Request, exc: Exception):
        """Maneja excepciones no capturadas con respuesta 500."""
        logger.exception(
            "Excepción no manejada en %s: %s",
            request.url.path,
            exc,
        )
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={
                "detail": "Error interno del servidor. Intente de nuevo más tarde.",
                "error_type": "internal_server_error",
                "path": str(request.url.path),
            },
        )

    # ── Health Check ──────────────────────────────────────────────────────
    @app.get("/health", tags=["Salud"], summary="Verificación de salud del servicio")
    async def health_check():
        """
        Verifica el estado de salud de la plataforma y sus dependencias.

        Retorna el estado de PostgreSQL, Redis y Neo4j junto con
        la versión de la aplicación y el entorno actual.
        """
        db_health = await check_database_health()
        all_healthy = all(db_health.values())

        return {
            "status": "healthy" if all_healthy else "degraded",
            "version": settings.APP_VERSION,
            "environment": settings.ENV.value,
            "services": db_health,
        }

    @app.get(
        "/ready",
        tags=["Salud"],
        summary="Verificación de readiness para orquestadores",
    )
    async def readiness_check():
        """
        Verifica si el servicio está listo para recibir tráfico.

        Diferencia de ``/health`` en que retorna 503 si alguna
        dependencia crítica no está disponible.
        """
        db_health = await check_database_health()
        all_healthy = all(db_health.values())

        if not all_healthy:
            return JSONResponse(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                content={
                    "status": "not_ready",
                    "services": db_health,
                },
            )

        return {"status": "ready", "services": db_health}

    @app.get("/", tags=["Raíz"], include_in_schema=False)
    async def root():
        """Redirige a la documentación de la API."""
        return {
            "name": settings.APP_NAME,
            "version": settings.APP_VERSION,
            "docs": f"{settings.API_PREFIX}/docs",
        }

    # ── Routers ───────────────────────────────────────────────────────────
    _register_routers(app)

    return app


def _register_routers(app: FastAPI) -> None:
    """
    Registra todos los routers de la API en la aplicación.

    Cada router se monta bajo el prefijo ``API_PREFIX`` configurado.
    Los routers se importan de forma diferida para evitar importaciones
    circulares y permitir que cada módulo se cargue independientemente.
    """
    from app.routers import analytics, curp, identity, risk, rfc, screening, verify

    routers = [
        (verify.router, "verify", "Verificación de Identidad"),
        (curp.router, "curp", "CURP — Registro Nacional de Población"),
        (rfc.router, "rfc", "RFC — Registro Federal de Contribuyentes"),
        (screening.router, "screening", "Screening — Listas Restrictivas"),
        (identity.router, "identity", "Identidad — Grafo de Relaciones"),
        (risk.router, "risk", "Riesgo — Análisis y Scorings"),
        (analytics.router, "analytics", "Analítica — Métricas y Reportes"),
    ]

    for router, prefix, tag in routers:
        app.include_router(
            router,
            prefix=f"{get_settings().API_PREFIX}/{prefix}",
            tags=[tag],
        )

    logger.info("Routers registrados: %s", ", ".join(r[1] for r in routers))


# ---------------------------------------------------------------------------
# Instancia de la aplicación
# ---------------------------------------------------------------------------
app = create_app()


# ---------------------------------------------------------------------------
# Punto de entrada directo (desarrollo)
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
        log_level="info",
    )
