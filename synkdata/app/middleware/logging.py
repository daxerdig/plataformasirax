"""
Middleware de logging estructurado para la plataforma SynkData.

Proporciona:
- Logging de todas las peticiones y respuestas HTTP
- Tracking por request ID (UUID único por petición)
- Medición del tiempo de procesamiento
- Logging estructurado en formato JSON
- Exclusión de endpoints de health check del logging

El middleware genera entradas de log en formato JSON para facilitar
el procesamiento por herramientas de observabilidad (ELK, Datadog, etc.).

Formato de log JSON:
    {
        "request_id": "uuid-v4",
        "method": "POST",
        "path": "/api/v1/curp/validate",
        "status_code": 200,
        "duration_ms": 45.3,
        "client_ip": "192.168.1.1",
        "user_agent": "Mozilla/5.0...",
        "timestamp": "2025-01-15T10:30:00.000Z",
        "level": "INFO"
    }
"""

from __future__ import annotations

import json
import logging
import time
import uuid
from typing import Callable, Set

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint

logger = logging.getLogger("synkdata.requests")

# ---------------------------------------------------------------------------
# Endpoints excluidos del logging (health checks, readiness, etc.)
# ---------------------------------------------------------------------------
EXCLUDED_PATHS: Set[str] = {
    "/health",
    "/ready",
    "/",
    "/favicon.ico",
}


# ---------------------------------------------------------------------------
# Middleware de Logging
# ---------------------------------------------------------------------------
class LoggingMiddleware(BaseHTTPMiddleware):
    """
    Middleware de FastAPI para logging estructurado de peticiones HTTP.

    Registra cada petición y respuesta con:
    - Request ID único (UUID v4)
    - Método HTTP y ruta
    - Código de estado de la respuesta
    - Duración en milisegundos
    - IP del cliente
    - User-Agent
    - Timestamp en formato ISO 8601

    Los endpoints de health check (``/health``, ``/ready``, ``/``)
    se excluyen automáticamente del logging para reducir ruido.

    Los logs se emiten en formato JSON estructurado para facilitar
    la integración con sistemas de observabilidad.

    Example:
        from fastapi import FastAPI
        from app.middleware.logging import LoggingMiddleware

        app = FastAPI()
        app.add_middleware(LoggingMiddleware)
    """

    async def dispatch(
        self,
        request: Request,
        call_next: RequestResponseEndpoint,
    ) -> Response:
        """
        Procesa la petición, registra el log y retorna la respuesta.

        Flujo:
        1. Genera o recupera el request ID
        2. Registra la petición entrante
        3. Mide el tiempo de procesamiento
        4. Registra la respuesta con el código de estado
        5. Agrega headers de trazabilidad a la respuesta

        Args:
            request: Objeto Request de FastAPI/Starlette.
            call_next: Función para invocar el siguiente middleware/endpoint.

        Returns:
            Response: Respuesta HTTP con headers de trazabilidad agregados.
        """
        # Determinar el request ID
        request_id = request.headers.get(
            "X-Request-ID", str(uuid.uuid4())
        )

        # Extraer información de la petición
        method = request.method
        path = request.url.path
        client_ip = self._get_client_ip(request)
        user_agent = request.headers.get("User-Agent", "")

        # Verificar si la ruta debe ser excluida del logging
        should_skip = self._should_skip_logging(path)

        # Almacenar el request_id en el estado para uso posterior
        request.state.request_id = request_id

        # Registrar petición entrante (excepto health checks)
        if not should_skip:
            self._log_request(
                request_id=request_id,
                method=method,
                path=path,
                client_ip=client_ip,
                user_agent=user_agent,
            )

        # Medir el tiempo de procesamiento
        start_time = time.perf_counter()

        try:
            response = await call_next(request)
        except Exception as exc:
            # Registrar errores no manejados
            duration_ms = (time.perf_counter() - start_time) * 1000

            if not should_skip:
                self._log_response(
                    request_id=request_id,
                    method=method,
                    path=path,
                    status_code=500,
                    duration_ms=duration_ms,
                    client_ip=client_ip,
                    user_agent=user_agent,
                    error=str(exc),
                )

            raise

        # Calcular duración
        duration_ms = (time.perf_counter() - start_time) * 1000
        status_code = response.status_code

        # Registrar respuesta (excepto health checks)
        if not should_skip:
            self._log_response(
                request_id=request_id,
                method=method,
                path=path,
                status_code=status_code,
                duration_ms=duration_ms,
                client_ip=client_ip,
                user_agent=user_agent,
            )

        # Agregar headers de trazabilidad a la respuesta
        response.headers["X-Request-ID"] = request_id
        response.headers["X-Response-Time-ms"] = f"{duration_ms:.1f}"

        return response

    @staticmethod
    def _should_skip_logging(path: str) -> bool:
        """
        Determina si una ruta debe ser excluida del logging.

        Se excluyen los endpoints de health check y readiness
        para reducir el ruido en los logs.

        Args:
            path: Ruta de la petición.

        Returns:
            bool: True si la ruta debe ser excluida.
        """
        return path in EXCLUDED_PATHS

    @staticmethod
    def _get_client_ip(request: Request) -> str:
        """
        Obtiene la dirección IP del cliente.

        Considera headers de proxy (X-Forwarded-For, X-Real-IP).

        Args:
            request: Objeto Request.

        Returns:
            str: Dirección IP del cliente.
        """
        forwarded = request.headers.get("X-Forwarded-For")
        if forwarded:
            return forwarded.split(",")[0].strip()

        real_ip = request.headers.get("X-Real-IP")
        if real_ip:
            return real_ip.strip()

        if request.client is not None:
            return request.client.host

        return "unknown"

    @staticmethod
    def _log_request(
        request_id: str,
        method: str,
        path: str,
        client_ip: str,
        user_agent: str,
    ) -> None:
        """
        Registra una petición entrante en formato JSON estructurado.

        Args:
            request_id: Identificador único de la petición.
            method: Método HTTP (GET, POST, etc.).
            path: Ruta de la petición.
            client_ip: Dirección IP del cliente.
            user_agent: Header User-Agent del cliente.
        """
        log_entry = {
            "direction": "incoming",
            "request_id": request_id,
            "method": method,
            "path": path,
            "client_ip": client_ip,
            "user_agent": user_agent[:200] if user_agent else "",
            "message": f"→ {method} {path}",
        }

        logger.info(json.dumps(log_entry, ensure_ascii=False))

    @staticmethod
    def _log_response(
        request_id: str,
        method: str,
        path: str,
        status_code: int,
        duration_ms: float,
        client_ip: str,
        user_agent: str,
        error: str = "",
    ) -> None:
        """
        Registra una respuesta en formato JSON estructurado.

        El nivel de log se determina por el código de estado:
        - 2xx, 3xx: INFO
        - 4xx: WARNING
        - 5xx: ERROR

        Args:
            request_id: Identificador único de la petición.
            method: Método HTTP.
            path: Ruta de la petición.
            status_code: Código de estado de la respuesta.
            duration_ms: Duración de la petición en milisegundos.
            client_ip: Dirección IP del cliente.
            user_agent: Header User-Agent del cliente.
            error: Mensaje de error (si aplica).
        """
        log_entry = {
            "direction": "outgoing",
            "request_id": request_id,
            "method": method,
            "path": path,
            "status_code": status_code,
            "duration_ms": round(duration_ms, 2),
            "client_ip": client_ip,
            "error": error,
            "message": f"← {method} {path} → {status_code} ({duration_ms:.1f}ms)",
        }

        # Determinar nivel de log según el código de estado
        if status_code >= 500:
            log_level = logging.ERROR
        elif status_code >= 400:
            log_level = logging.WARNING
        else:
            log_level = logging.INFO

        logger.log(log_level, json.dumps(log_entry, ensure_ascii=False))
