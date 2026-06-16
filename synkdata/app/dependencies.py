"""
Dependencias de FastAPI para la plataforma SynkData.

Provee inyección de dependencias reutilizable para:
- Sesiones de base de datos (PostgreSQL, Redis, Neo4j)
- Autenticación y autorización (JWT)
- Rate limiting
- Parámetros de paginación

Cada dependencia es una función asíncrona que puede inyectarse
directamente en los endpoints mediante ``Depends()``.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import AsyncGenerator, Optional

from fastapi import Depends, HTTPException, Query, Request, status
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError, jwt
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.database import get_db_session, get_redis, get_neo4j_session

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# OAuth2 — Esquema de autenticación con Bearer Token
# ---------------------------------------------------------------------------
oauth2_scheme = OAuth2PasswordBearer(
    tokenUrl=f"{get_settings().API_PREFIX}/auth/login",
    auto_error=True,
)


# ---------------------------------------------------------------------------
# Dependencias de base de datos
# ---------------------------------------------------------------------------
async def db_session() -> AsyncGenerator[AsyncSession, None]:
    """
    Proveedor de sesión asíncrona de PostgreSQL para inyección en endpoints.

    La sesión se compromete (commit) automáticamente al finalizar el
    contexto sin errores, y se revierte (rollback) en caso de excepción.

    Returns:
        AsyncSession: Sesión activa de SQLAlchemy.
    """
    async with get_db_session() as session:
        yield session


async def redis_client() -> Redis:
    """
    Proveedor del cliente Redis asíncrono para inyección en endpoints.

    Returns:
        Redis: Cliente Redis configurado.
    """
    return get_redis()


async def neo4j_session():
    """
    Proveedor de sesión asíncrona de Neo4j para inyección en endpoints.

    Returns:
        AsyncSession: Sesión activa de Neo4j.
    """
    async with get_neo4j_session() as session:
        yield session


# ---------------------------------------------------------------------------
# Autenticación — JWT
# ---------------------------------------------------------------------------
async def get_current_user(
    token: str = Depends(oauth2_scheme),
    redis: Redis = Depends(redis_client),
) -> dict:
    """
    Decodifica y valida un token JWT para obtener el usuario actual.

    Verifica:
    - Firma válida del token
    - Token no expirado
    - Token no revocado (verificado en Redis)

    Args:
        token: Token JWT extraído del header Authorization.
        redis: Cliente Redis para verificar revocación.

    Returns:
        dict: Payload decodificado del JWT con datos del usuario.

    Raises:
        HTTPException 401: Si el token es inválido, expirado o revocado.
    """
    settings = get_settings()
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="No se pudieron validar las credenciales.",
        headers={"WWW-Authenticate": "Bearer"},
    )

    try:
        payload = jwt.decode(
            token,
            settings.SECRET_KEY,
            algorithms=[settings.JWT_ALGORITHM],
            issuer=settings.JWT_ISSUER,
        )
        user_id: Optional[str] = payload.get("sub")
        if user_id is None:
            raise credentials_exception

    except JWTError as exc:
        logger.warning("Error decodificando JWT: %s", exc)
        raise credentials_exception from exc

    # Verificar si el token fue revocado
    revoked = await redis.get(f"token_revoked:{token}")
    if revoked is not None:
        logger.warning("Token revocado utilizado — user_id=%s", user_id)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="El token ha sido revocado.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Agregar metadata de auditoría
    payload["token_issued_at"] = datetime.now(timezone.utc).isoformat()
    return payload


async def get_current_active_user(
    current_user: dict = Depends(get_current_user),
) -> dict:
    """
    Verifica que el usuario actual esté activo.

    Args:
        current_user: Payload del JWT obtenido de ``get_current_user``.

    Returns:
        dict: Payload del usuario activo.

    Raises:
        HTTPException 403: Si el usuario está inactivo.
    """
    if not current_user.get("is_active", True):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="El usuario está inactivo.",
        )
    return current_user


async def require_role(role: str):
    """
    Fábrica de dependencias que exige un rol específico.

    Args:
        role: Nombre del rol requerido (ej. "admin", "analyst").

    Returns:
        Dependencia que valida el rol del usuario.

    Example:
        @router.get("/admin", dependencies=[Depends(require_role("admin"))])
    """

    async def _check_role(
        current_user: dict = Depends(get_current_active_user),
    ) -> dict:
        user_roles = current_user.get("roles", [])
        if role not in user_roles:
            logger.warning(
                "Acceso denegado — usuario=%s requiere rol=%s, tiene=%s",
                current_user.get("sub"),
                role,
                user_roles,
            )
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Se requiere el rol '{role}' para acceder a este recurso.",
            )
        return current_user

    return _check_role


# ---------------------------------------------------------------------------
# Rate Limiting
# ---------------------------------------------------------------------------
async def rate_limiter(
    request: Request,
    redis: Redis = Depends(redis_client),
) -> None:
    """
    Dependencia de limitación de tasa de peticiones por usuario/IP.

    Utiliza Redis para rastrear el número de peticiones en una ventana
    de tiempo fija. El límite se configura en la variable de entorno
    ``SYNKDATA_RATE_LIMIT_DEFAULT``.

    Args:
        request: Objeto de petición de FastAPI.
        redis: Cliente Redis para el contador de rate-limiting.

    Raises:
        HTTPException 429: Si se excede el límite de peticiones.
    """
    settings = get_settings()

    if not settings.RATE_LIMIT_ENABLED:
        return

    # Identificar al cliente por IP o por ID de usuario (si autenticado)
    client_id = request.client.host if request.client else "unknown"

    # Intentar obtener el user_id del token si está presente
    auth_header = request.headers.get("Authorization", "")
    if auth_header.startswith("Bearer "):
        try:
            token = auth_header.split(" ")[1]
            payload = jwt.decode(
                token,
                settings.SECRET_KEY,
                algorithms=[settings.JWT_ALGORITHM],
                options={"verify_exp": False},
            )
            client_id = f"user:{payload.get('sub', client_id)}"
        except JWTError:
            pass

    # Parsear el límite (formato: "60/minute")
    parts = settings.RATE_LIMIT_DEFAULT.split("/")
    limit = int(parts[0])
    period = parts[1] if len(parts) > 1 else "minute"

    period_seconds = {
        "second": 1,
        "minute": 60,
        "hour": 3600,
        "day": 86400,
    }.get(period, 60)

    key = f"rate_limit:{client_id}:{period}"

    # Incrementar contador en Redis
    current = await redis.incr(key)
    if current == 1:
        await redis.expire(key, period_seconds)

    if current > limit:
        retry_after = await redis.ttl(key)
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=(
                f"Límite de peticiones excedido: {limit} peticiones por {period}. "
                f"Intente de nuevo en {retry_after} segundos."
            ),
            headers={"Retry-After": str(max(retry_after, 1))},
        )


# ---------------------------------------------------------------------------
# Paginación
# ---------------------------------------------------------------------------
@dataclass
class PaginationParams:
    """
    Parámetros de paginación estandarizados para endpoints de listado.

    Attributes:
        page: Número de página (base 1).
        page_size: Cantidad de elementos por página.
        offset: Calculado automáticamente como ``(page - 1) * page_size``.
        limit: Alias de ``page_size`` para uso en consultas.
    """

    page: int
    page_size: int
    offset: int
    limit: int


def pagination_params(
    page: int = Query(
        default=1,
        ge=1,
        description="Número de página (base 1).",
    ),
    page_size: int = Query(
        default=20,
        ge=1,
        le=100,
        description="Cantidad de elementos por página.",
    ),
) -> PaginationParams:
    """
    Dependencia para extraer parámetros de paginación de query params.

    Args:
        page: Número de página solicitada.
        page_size: Tamaño de página solicitado.

    Returns:
        PaginationParams: Parámetros de paginación validados.
    """
    settings = get_settings()
    # Respetar límite máximo configurado
    page_size = min(page_size, settings.PAGINATION_MAX_PAGE_SIZE)
    offset = (page - 1) * page_size

    return PaginationParams(
        page=page,
        page_size=page_size,
        offset=offset,
        limit=page_size,
    )


# ---------------------------------------------------------------------------
# Utilidades comunes
# ---------------------------------------------------------------------------
def get_request_id(request: Request) -> Optional[str]:
    """
    Extrae el identificador de petición del header ``X-Request-ID``.

    Args:
        request: Objeto de petición de FastAPI.

    Returns:
        Optional[str]: ID de la petición o None si no está presente.
    """
    return request.headers.get("X-Request-ID")
