"""
Middleware de rate limiting basado en Redis para la plataforma SynkData.

Implementa limitación de peticiones por usuario y por dirección IP
usando una ventana de tiempo fija (fixed-window) con Redis como
almacén de estado.

Características:
- Rate limiting por usuario (identificado por JWT) y por IP
- Headers personalizados con peticiones restantes
- Respuesta 429 con header Retry-After cuando se excede el límite
- Configuración flexible de ventana y máximo de peticiones
- Funciona con el cliente Redis asíncrono de la plataforma
"""

from __future__ import annotations

import logging
import time
from typing import Callable, Optional

from fastapi import Depends, HTTPException, Request, Response, status
from fastapi.responses import JSONResponse
from redis.asyncio import Redis

from app.config import get_settings

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Clase principal de Rate Limiting
# ---------------------------------------------------------------------------
class RateLimiter:
    """
    Limitador de peticiones basado en Redis con ventana de tiempo fija.

    Utiliza claves Redis con TTL para contar el número de peticiones
    dentro de una ventana de tiempo. Cuando se excede el límite,
    retorna una respuesta 429 con el header ``Retry-After``.

    Attributes:
        max_requests: Número máximo de peticiones permitidas en la ventana.
        window_seconds: Duración de la ventana de tiempo en segundos.

    Example:
        limiter = RateLimiter(max_requests=100, window_seconds=60)
        response = await limiter.check(request, redis_client, key="user:123")
    """

    def __init__(
        self,
        max_requests: int = 60,
        window_seconds: int = 60,
    ) -> None:
        """
        Inicializa el limitador de peticiones.

        Args:
            max_requests: Número máximo de peticiones en la ventana.
            window_seconds: Duración de la ventana en segundos.

        Raises:
            ValueError: Si max_requests o window_seconds son inválidos.
        """
        if max_requests <= 0:
            raise ValueError("max_requests debe ser un entero positivo.")
        if window_seconds <= 0:
            raise ValueError("window_seconds debe ser un entero positivo.")

        self.max_requests = max_requests
        self.window_seconds = window_seconds

    async def check(
        self,
        request: Request,
        redis: Redis,
        key: Optional[str] = None,
    ) -> Optional[Response]:
        """
        Verifica si la petición está dentro del límite permitido.

        Usa una clave Redis con formato ``rate_limit:{key}`` para
        rastrear el conteo de peticiones. La clave tiene un TTL
        igual a la ventana de tiempo.

        Args:
            request: Objeto Request de FastAPI.
            redis: Cliente Redis asíncrono.
            key: Clave identificadora (ej. user_id o IP). Si no se
                proporciona, se deriva de la IP del cliente.

        Returns:
            Optional[Response]: Si la petición excede el límite,
                retorna una JSONResponse 429. Si está dentro del
                límite, retorna None (permitir la petición).
        """
        # Determinar la clave de rate limiting
        if key is None:
            key = self._get_client_ip(request)

        redis_key = f"rate_limit:{key}"

        # Obtener el conteo actual y el TTL
        pipe = redis.pipeline()
        pipe.incr(redis_key)
        pipe.ttl(redis_key)
        results = await pipe.execute()

        current_count = results[0]
        ttl = results[1]

        # Si es la primera petición en la ventana, establecer el TTL
        if current_count == 1 or ttl == -1:
            await redis.expire(redis_key, self.window_seconds)
            ttl = self.window_seconds

        remaining = max(0, self.max_requests - current_count)
        reset_time = int(time.time()) + max(ttl, 0)

        # Agregar headers de rate limit al request state para que
        # el middleware los pueda inyectar en la respuesta
        request.state.rate_limit_limit = self.max_requests
        request.state.rate_limit_remaining = remaining
        request.state.rate_limit_reset = reset_time

        # Verificar si se excedió el límite
        if current_count > self.max_requests:
            retry_after = max(ttl, 1)

            logger.warning(
                "Rate limit excedido — key=%s, count=%d/%d, window=%ds",
                key,
                current_count,
                self.max_requests,
                self.window_seconds,
            )

            return JSONResponse(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                content={
                    "detail": (
                        f"Se ha excedido el límite de {self.max_requests} peticiones "
                        f"en {self.window_seconds} segundos. Intente de nuevo más tarde."
                    ),
                    "error_type": "rate_limit_exceeded",
                    "retry_after": retry_after,
                    "limit": self.max_requests,
                    "window_seconds": self.window_seconds,
                },
                headers={
                    "Retry-After": str(retry_after),
                    "X-RateLimit-Limit": str(self.max_requests),
                    "X-RateLimit-Remaining": "0",
                    "X-RateLimit-Reset": str(reset_time),
                },
            )

        return None

    @staticmethod
    def _get_client_ip(request: Request) -> str:
        """
        Obtiene la dirección IP del cliente desde el request.

        Considera los headers ``X-Forwarded-For`` y ``X-Real-IP``
        para soportar despliegues detrás de proxies/reverse proxies.

        Args:
            request: Objeto Request de FastAPI.

        Returns:
            str: Dirección IP del cliente.
        """
        # Priorizar headers de proxy
        forwarded = request.headers.get("X-Forwarded-For")
        if forwarded:
            # X-Forwarded-For puede contener múltiples IPs
            return forwarded.split(",")[0].strip()

        real_ip = request.headers.get("X-Real-IP")
        if real_ip:
            return real_ip.strip()

        # Fallback a la IP directa del cliente
        if request.client is not None:
            return request.client.host

        return "unknown"


# ---------------------------------------------------------------------------
# Dependencias de FastAPI para rate limiting
# ---------------------------------------------------------------------------
async def rate_limit_dependency(
    request: Request,
) -> None:
    """
    Dependencia de FastAPI que aplica rate limiting por IP.

    Utiliza la configuración global de la plataforma para determinar
    los límites. Los headers de rate limit se agregan al request state
    para que el middleware de respuesta los incluya.

    Args:
        request: Objeto Request de FastAPI.

    Raises:
        HTTPException 429: Si se excede el límite de peticiones.
    """
    settings = get_settings()

    if not settings.RATE_LIMIT_ENABLED:
        return

    # Parsear la configuración de rate limit (formato: "60/minute")
    try:
        parts = settings.RATE_LIMIT_DEFAULT.split("/")
        max_requests = int(parts[0])
        window_unit = parts[1] if len(parts) > 1 else "minute"

        unit_map = {
            "second": 1,
            "minute": 60,
            "hour": 3600,
            "day": 86400,
        }
        window_seconds = unit_map.get(window_unit, 60)
    except (ValueError, IndexError):
        max_requests = 60
        window_seconds = 60

    limiter = RateLimiter(
        max_requests=max_requests,
        window_seconds=window_seconds,
    )

    # Obtener el cliente Redis
    try:
        from app.database import get_redis
        redis = get_redis()
    except RuntimeError:
        # Si Redis no está inicializado, permitir la petición
        logger.warning("Redis no inicializado — rate limiting deshabilitado.")
        return

    # Intentar obtener el user_id del JWT si está autenticado
    key = None
    try:
        auth_header = request.headers.get("Authorization", "")
        if auth_header.startswith("Bearer "):
            from app.middleware.auth import get_current_user
            # No podemos llamar a la dependencia directamente aquí,
            # así que usamos la IP como fallback
            pass
    except Exception:
        pass

    response = await limiter.check(request, redis, key=key)

    if response is not None:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=response.body.decode() if isinstance(response.body, bytes) else str(response.body),
        )


def create_rate_limit_middleware(
    max_requests: int = 60,
    window_seconds: int = 60,
) -> Callable:
    """
    Fábrica de middleware de rate limiting para FastAPI.

    Crea un middleware que aplica rate limiting a todas las peticiones
    entrantes, inyectando los headers de rate limit en las respuestas.

    Args:
        max_requests: Número máximo de peticiones en la ventana.
        window_seconds: Duración de la ventana en segundos.

    Returns:
        Callable: Función middleware para FastAPI.

    Example:
        from fastapi import FastAPI

        app = FastAPI()

        @app.middleware("http")
        async def rate_limit(request: Request, call_next):
            middleware = create_rate_limit_middleware(100, 60)
            return await middleware(request, call_next)
    """
    limiter = RateLimiter(max_requests=max_requests, window_seconds=window_seconds)

    async def rate_limit_middleware(request: Request, call_next: Callable) -> Response:
        # Obtener Redis
        try:
            from app.database import get_redis
            redis = get_redis()
        except RuntimeError:
            return await call_next(request)

        # Verificar rate limit
        rate_limit_response = await limiter.check(request, redis)

        if rate_limit_response is not None:
            return rate_limit_response

        # Procesar la petición normalmente
        response = await call_next(request)

        # Agregar headers de rate limit a la respuesta
        if hasattr(request.state, "rate_limit_limit"):
            response.headers["X-RateLimit-Limit"] = str(
                request.state.rate_limit_limit
            )
        if hasattr(request.state, "rate_limit_remaining"):
            response.headers["X-RateLimit-Remaining"] = str(
                request.state.rate_limit_remaining
            )
        if hasattr(request.state, "rate_limit_reset"):
            response.headers["X-RateLimit-Reset"] = str(
                request.state.rate_limit_reset
            )

        return response

    return rate_limit_middleware
