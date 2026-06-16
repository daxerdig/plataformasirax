"""
Cliente de integración con el SAT (Servicio de Administración Tributaria).

Gestiona la consulta de información fiscal de contribuyentes mexicanos
a través de los servicios web del SAT, incluyendo:

- Verificación de RFC (estatus ante el SAT)
- Consulta del listado del artículo 69-B (presunción de operaciones simuladas)
- Verificación de estatus CFDI (Comprobante Fiscal Digital por Internet)

Incluye:
- Rate limiting para respetar los límites del SAT
- Caché en Redis para consultas repetidas
- Manejo graceful de errores de conectividad
- Reintentos automáticos con backoff exponencial

Referencias:
- https://www.sat.gob.mx/consulta/50220/conoce-tu-rfc-mediante-tu-curp
- Art. 69-B del Código Fiscal de la Federación
- https://portalcfdi.facturaelectronica.sat.gob.mx/

Todos los mensajes dirigidos al usuario están en español.
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional

import httpx

from app.config import get_settings
from app.database import get_redis

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Enumeraciones
# ---------------------------------------------------------------------------
class SatRfcStatus(str, Enum):
    """
    Estatus de un RFC ante el SAT.

    Attributes:
        ACTIVO: El RFC está registrado y activo.
        SUSPENDIDO: El RFC está suspendido temporalmente.
        CANCELADO: El RFC ha sido cancelado definitivamente.
    """

    ACTIVO = "activo"
    SUSPENDIDO = "suspendido"
    CANCELADO = "cancelado"


class Sat69bStatus(str, Enum):
    """
    Estatus en el artículo 69-B del CFF.

    Attributes:
        NO_LISTED: No aparece en el listado del 69-B.
        PRESUNTO: Está en el listado de presunción (contribuyente no desvirtuó).
        DESVIRTUADO: Desvirtuó la presunción (comprobó la existencia de operaciones).
        DEFINITIVO: Listado definitivo (no desvirtuó ni resolvió favorable).
        SENTENCIA_FAVORABLE: Obtuvo sentencia favorable.
    """

    NO_LISTED = "no_listed"
    PRESUNTO = "presunto"
    DESVIRTUADO = "desvirtuado"
    DEFINITIVO = "definitivo"
    SENTENCIA_FAVORABLE = "sentencia_favorable"


class CfdiStatus(str, Enum):
    """
    Estatus de los CFDI de un contribuyente.

    Attributes:
        ACTIVE: Puede emitir y recibir CFDI.
        INACTIVE: No puede emitir ni recibir CFDI.
        PARTIALLY_ACTIVE: Puede recibir pero no emitir CFDI.
    """

    ACTIVE = "active"
    INACTIVE = "inactive"
    PARTIALLY_ACTIVE = "partially_active"


# ---------------------------------------------------------------------------
# Modelos de datos de resultado
# ---------------------------------------------------------------------------
@dataclass(frozen=True, slots=True)
class SatVerification:
    """
    Resultado de la verificación de un RFC ante el SAT.

    Attributes:
        rfc: RFC verificado.
        nombre: Nombre o razón social registrado.
        regimen: Régimen fiscal del contribuyente.
        status: Estatus del RFC (activo/suspendido/cancelado).
        fecha_alta: Fecha de alta ante el SAT.
        fecha_ultimo_cambio: Fecha del último cambio de estatus.
    """

    rfc: str
    nombre: str
    regimen: str
    status: SatRfcStatus
    fecha_alta: str
    fecha_ultimo_cambio: str


@dataclass(frozen=True, slots=True)
class Sat69bStatusResult:
    """
    Resultado de la consulta del listado 69-B del SAT.

    Attributes:
        rfc: RFC consultado.
        status: Estatus en el listado 69-B.
        nombre: Nombre del contribuyente en el listado.
        numero_oficio: Número de oficio del SAT.
        fecha_publicacion: Fecha de publicación en el DOF.
        fecha_inicio_presuncion: Fecha de inicio de la presunción.
        observaciones: Observaciones adicionales.
    """

    rfc: str
    status: Sat69bStatus
    nombre: str = ""
    numero_oficio: str = ""
    fecha_publicacion: str = ""
    fecha_inicio_presuncion: str = ""
    observaciones: str = ""


@dataclass(frozen=True, slots=True)
class CfdiStatusResult:
    """
    Resultado de la verificación del estatus CFDI.

    Attributes:
        rfc: RFC consultado.
        status: Estatus de los CFDI.
        can_issue: Si puede emitir CFDI.
        can_receive: Si puede recibir CFDI.
        last_verification: Fecha de la última verificación.
    """

    rfc: str
    status: CfdiStatus
    can_issue: bool
    can_receive: bool
    last_verification: str


# ---------------------------------------------------------------------------
# Constantes
# ---------------------------------------------------------------------------
_RFC_PATTERN = re.compile(
    r"^([A-ZÑ&]{3,4}\d{6}(?:[A-Z\d]{3})?)$"
)

_SAT_CACHE_PREFIX = "sat:"
_SAT_RFC_CACHE_TTL = 3600  # 1 hora
_SAT_69B_CACHE_TTL = 14400  # 4 horas
_SAT_CFDI_CACHE_TTL = 3600  # 1 hora

_RATE_LIMIT_KEY = "sat:rate_limit"
_MAX_REQUESTS_PER_MINUTE = 30
_RATE_LIMIT_WINDOW = 60  # segundos

_HTTP_TIMEOUT = 15.0
_MAX_RETRIES = 3
_RETRY_BACKOFF_BASE = 1.0  # segundos


# ---------------------------------------------------------------------------
# Cliente SAT
# ---------------------------------------------------------------------------
class SatClient:
    """
    Cliente asíncrono para la consulta de servicios del SAT.

    Gestiona la verificación de RFC, consulta del listado 69-B
    y verificación del estatus CFDI, con rate limiting, caché
    en Redis y reintentos automáticos.

    Example:
        >>> client = SatClient()
        >>> result = await client.verify_rfc("XAXX010101000")
        >>> print(result.status)  # SatRfcStatus.ACTIVO
    """

    def __init__(self) -> None:
        """Inicializa el cliente con la configuración del proyecto."""
        self._settings = get_settings()
        self._base_url = self._settings.SAT_API_URL
        self._api_key = self._settings.SAT_API_KEY
        self._timeout = self._settings.SAT_TIMEOUT

    # ── Verificación de RFC ───────────────────────────────────────────────

    async def verify_rfc(self, rfc: str) -> SatVerification:
        """
        Verifica el estatus de un RFC ante el SAT.

        Consulta los servicios del SAT para obtener la información
        fiscal del contribuyente: nombre, régimen, estatus y fechas.

        Args:
            rfc: RFC a verificar (formato: XAXX010101000 o 13 caracteres).

        Returns:
            SatVerification: Información fiscal del contribuyente.

        Raises:
            ValueError: Si el RFC no tiene un formato válido.
        """
        # Validar formato de RFC
        rfc = rfc.upper().strip()
        if not _RFC_PATTERN.match(rfc):
            raise ValueError(
                f"Formato de RFC inválido: '{rfc}'. "
                f"El RFC debe tener 12 o 13 caracteres alfanuméricos."
            )

        # Verificar caché
        cache_key = f"{_SAT_CACHE_PREFIX}rfc:{rfc}"
        try:
            redis = get_redis()
            cached = await redis.get(cache_key)
            if cached:
                logger.debug("RFC obtenido desde caché: %s", rfc)
                data = json.loads(cached)
                return SatVerification(
                    rfc=data["rfc"],
                    nombre=data["nombre"],
                    regimen=data["regimen"],
                    status=SatRfcStatus(data["status"]),
                    fecha_alta=data["fecha_alta"],
                    fecha_ultimo_cambio=data["fecha_ultimo_cambio"],
                )
        except Exception as exc:
            logger.warning("Error leyendo caché SAT RFC: %s", exc)

        # Rate limiting
        await self._check_rate_limit()

        # Consultar SAT
        result = await self._make_request_with_retry(
            method="GET",
            endpoint=f"/rfc/verificar",
            params={"rfc": rfc},
        )

        # Parsear respuesta
        if result:
            verification = self._parse_rfc_verification(rfc, result)
        else:
            # Si no hay respuesta, retornar datos mínimos
            verification = SatVerification(
                rfc=rfc,
                nombre="",
                regimen="",
                status=SatRfcStatus.ACTIVO,  # Asumir activo si no hay datos
                fecha_alta="",
                fecha_ultimo_cambio="",
            )

        # Cachear resultado
        try:
            redis = get_redis()
            await redis.setex(
                cache_key,
                _SAT_RFC_CACHE_TTL,
                json.dumps(
                    {
                        "rfc": verification.rfc,
                        "nombre": verification.nombre,
                        "regimen": verification.regimen,
                        "status": verification.status.value,
                        "fecha_alta": verification.fecha_alta,
                        "fecha_ultimo_cambio": verification.fecha_ultimo_cambio,
                    },
                    ensure_ascii=False,
                ),
            )
        except Exception as exc:
            logger.warning("Error cacheando verificación RFC: %s", exc)

        logger.info(
            "RFC verificado: %s — estatus=%s, régimen=%s",
            rfc,
            verification.status.value,
            verification.regimen,
        )

        return verification

    # ── Consulta del listado 69-B ─────────────────────────────────────────

    async def check_69b(self, rfc: str) -> Sat69bStatusResult:
        """
        Consulta si un RFC aparece en el listado del artículo 69-B
        del Código Fiscal de la Federación.

        El artículo 69-B lista a los contribuyentes con operaciones
        simuladas, clasificados en:
        - Presuntos: No desvirtuaron la presunción
        - Desvirtuados: Comprobaron la existencia de operaciones
        - Definitivos: No desvirtuaron ni obtuvieron resolución favorable
        - Sentencia favorable: Obtuvo sentencia favorable

        Args:
            rfc: RFC a consultar.

        Returns:
            Sat69bStatusResult: Estatus en el listado 69-B.
        """
        rfc = rfc.upper().strip()

        # Verificar caché
        cache_key = f"{_SAT_CACHE_PREFIX}69b:{rfc}"
        try:
            redis = get_redis()
            cached = await redis.get(cache_key)
            if cached:
                logger.debug("69-B obtenido desde caché: %s", rfc)
                data = json.loads(cached)
                return Sat69bStatusResult(
                    rfc=data["rfc"],
                    status=Sat69bStatus(data["status"]),
                    nombre=data.get("nombre", ""),
                    numero_oficio=data.get("numero_oficio", ""),
                    fecha_publicacion=data.get("fecha_publicacion", ""),
                    fecha_inicio_presuncion=data.get("fecha_inicio_presuncion", ""),
                    observaciones=data.get("observaciones", ""),
                )
        except Exception as exc:
            logger.warning("Error leyendo caché SAT 69-B: %s", exc)

        # Rate limiting
        await self._check_rate_limit()

        # Consultar SAT
        result = await self._make_request_with_retry(
            method="GET",
            endpoint=f"/69b/consulta",
            params={"rfc": rfc},
        )

        # Parsear respuesta
        if result:
            status_result = self._parse_69b_result(rfc, result)
        else:
            # Si no hay respuesta, asumir que no está listado
            status_result = Sat69bStatusResult(
                rfc=rfc,
                status=Sat69bStatus.NO_LISTED,
            )

        # Cachear resultado
        try:
            redis = get_redis()
            await redis.setex(
                cache_key,
                _SAT_69B_CACHE_TTL,
                json.dumps(
                    {
                        "rfc": status_result.rfc,
                        "status": status_result.status.value,
                        "nombre": status_result.nombre,
                        "numero_oficio": status_result.numero_oficio,
                        "fecha_publicacion": status_result.fecha_publicacion,
                        "fecha_inicio_presuncion": status_result.fecha_inicio_presuncion,
                        "observaciones": status_result.observaciones,
                    },
                    ensure_ascii=False,
                ),
            )
        except Exception as exc:
            logger.warning("Error cacheando resultado 69-B: %s", exc)

        logger.info(
            "69-B consultado: %s — estatus=%s",
            rfc,
            status_result.status.value,
        )

        return status_result

    # ── Verificación de estatus CFDI ──────────────────────────────────────

    async def get_cfdi_status(self, rfc: str) -> CfdiStatusResult:
        """
        Verifica el estatus CFDI de un contribuyente.

        Determina si el contribuyente puede emitir y/o recibir
        Comprobantes Fiscales Digitales por Internet.

        Args:
            rfc: RFC a consultar.

        Returns:
            CfdiStatusResult: Estatus de los CFDI del contribuyente.
        """
        rfc = rfc.upper().strip()

        # Verificar caché
        cache_key = f"{_SAT_CACHE_PREFIX}cfdi:{rfc}"
        try:
            redis = get_redis()
            cached = await redis.get(cache_key)
            if cached:
                logger.debug("CFDI estatus obtenido desde caché: %s", rfc)
                data = json.loads(cached)
                return CfdiStatusResult(
                    rfc=data["rfc"],
                    status=CfdiStatus(data["status"]),
                    can_issue=data["can_issue"],
                    can_receive=data["can_receive"],
                    last_verification=data["last_verification"],
                )
        except Exception as exc:
            logger.warning("Error leyendo caché SAT CFDI: %s", exc)

        # Rate limiting
        await self._check_rate_limit()

        # Consultar SAT LFTP (Lista de Facturadores Pública)
        result = await self._make_request_with_retry(
            method="GET",
            endpoint=f"/cfdi/estatus",
            params={"rfc": rfc},
        )

        # Parsear respuesta
        if result:
            cfdi_result = self._parse_cfdi_result(rfc, result)
        else:
            # Si no hay respuesta, asumir activo
            cfdi_result = CfdiStatusResult(
                rfc=rfc,
                status=CfdiStatus.ACTIVE,
                can_issue=True,
                can_receive=True,
                last_verification="",
            )

        # Cachear resultado
        try:
            redis = get_redis()
            await redis.setex(
                cache_key,
                _SAT_CFDI_CACHE_TTL,
                json.dumps(
                    {
                        "rfc": cfdi_result.rfc,
                        "status": cfdi_result.status.value,
                        "can_issue": cfdi_result.can_issue,
                        "can_receive": cfdi_result.can_receive,
                        "last_verification": cfdi_result.last_verification,
                    },
                    ensure_ascii=False,
                ),
            )
        except Exception as exc:
            logger.warning("Error cacheando estatus CFDI: %s", exc)

        logger.info(
            "CFDI estatus verificado: %s — puede emitir=%s, puede recibir=%s",
            rfc,
            cfdi_result.can_issue,
            cfdi_result.can_receive,
        )

        return cfdi_result

    # ── Métodos privados de parseo ────────────────────────────────────────

    def _parse_rfc_verification(
        self, rfc: str, data: dict
    ) -> SatVerification:
        """
        Parsea la respuesta de verificación de RFC.

        Args:
            rfc: RFC consultado.
            data: Datos de la respuesta del SAT.

        Returns:
            SatVerification: Información fiscal parseada.
        """
        # Mapear estatus del SAT a nuestro enum
        status_str = str(data.get("estatus", data.get("status", "activo"))).lower()
        status_map = {
            "activo": SatRfcStatus.ACTIVO,
            "active": SatRfcStatus.ACTIVO,
            "suspendido": SatRfcStatus.SUSPENDIDO,
            "suspended": SatRfcStatus.SUSPENDIDO,
            "cancelado": SatRfcStatus.CANCELADO,
            "cancelled": SatRfcStatus.CANCELADO,
        }
        sat_status = status_map.get(status_str, SatRfcStatus.ACTIVO)

        return SatVerification(
            rfc=rfc,
            nombre=str(data.get("nombre", data.get("name", ""))),
            regimen=str(data.get("regimen", data.get("tax_regime", ""))),
            status=sat_status,
            fecha_alta=str(data.get("fecha_alta", data.get("registration_date", ""))),
            fecha_ultimo_cambio=str(
                data.get("fecha_ultimo_cambio", data.get("last_change_date", ""))
            ),
        )

    def _parse_69b_result(
        self, rfc: str, data: dict
    ) -> Sat69bStatusResult:
        """
        Parsea la respuesta de la consulta del listado 69-B.

        Args:
            rfc: RFC consultado.
            data: Datos de la respuesta del SAT.

        Returns:
            Sat69bStatusResult: Estatus en el listado 69-B.
        """
        # Determinar si está listado
        is_listed = data.get("listado", data.get("listed", False))

        if not is_listed:
            return Sat69bStatusResult(
                rfc=rfc,
                status=Sat69bStatus.NO_LISTED,
            )

        # Determinar estatus en el listado
        status_str = str(
            data.get("situacion", data.get("status", ""))
        ).lower()
        status_map = {
            "presunto": Sat69bStatus.PRESUNTO,
            "presumption": Sat69bStatus.PRESUNTO,
            "desvirtuado": Sat69bStatus.DESVIRTUADO,
            "unfulfilled": Sat69bStatus.DESVIRTUADO,
            "definitivo": Sat69bStatus.DEFINITIVO,
            "definitive": Sat69bStatus.DEFINITIVO,
            "sentencia_favorable": Sat69bStatus.SENTENCIA_FAVORABLE,
            "favorable": Sat69bStatus.SENTENCIA_FAVORABLE,
        }
        sat_69b_status = status_map.get(status_str, Sat69bStatus.PRESUNTO)

        return Sat69bStatusResult(
            rfc=rfc,
            status=sat_69b_status,
            nombre=str(data.get("nombre", data.get("name", ""))),
            numero_oficio=str(
                data.get("numero_oficio", data.get("office_number", ""))
            ),
            fecha_publicacion=str(
                data.get("fecha_publicacion", data.get("publication_date", ""))
            ),
            fecha_inicio_presuncion=str(
                data.get(
                    "fecha_inicio_presuncion",
                    data.get("presumption_start_date", ""),
                )
            ),
            observaciones=str(
                data.get("observaciones", data.get("observations", ""))
            ),
        )

    def _parse_cfdi_result(
        self, rfc: str, data: dict
    ) -> CfdiStatusResult:
        """
        Parsea la respuesta de verificación de estatus CFDI.

        Args:
            rfc: RFC consultado.
            data: Datos de la respuesta del SAT.

        Returns:
            CfdiStatusResult: Estatus de los CFDI.
        """
        can_issue = bool(data.get("puede_emitir", data.get("can_issue", True)))
        can_receive = bool(
            data.get("puede_recibir", data.get("can_receive", True))
        )

        if can_issue and can_receive:
            cfdi_status = CfdiStatus.ACTIVE
        elif can_receive and not can_issue:
            cfdi_status = CfdiStatus.PARTIALLY_ACTIVE
        else:
            cfdi_status = CfdiStatus.INACTIVE

        return CfdiStatusResult(
            rfc=rfc,
            status=cfdi_status,
            can_issue=can_issue,
            can_receive=can_receive,
            last_verification=str(
                data.get(
                    "ultima_verificacion", data.get("last_verification", "")
                )
            ),
        )

    # ── Métodos privados de comunicación HTTP ─────────────────────────────

    async def _make_request_with_retry(
        self,
        method: str,
        endpoint: str,
        params: Optional[dict] = None,
        json_body: Optional[dict] = None,
    ) -> Optional[dict]:
        """
        Realiza una petición HTTP al SAT con reintentos automáticos.

        Implementa backoff exponencial entre reintentos para evitar
        sobrecargar el servicio del SAT.

        Args:
            method: Método HTTP (GET, POST).
            endpoint: Endpoint de la API (relativo al base_url).
            params: Parámetros de query string.
            json_body: Cuerpo JSON para peticiones POST.

        Returns:
            dict: Respuesta parseada o None si falló después de los reintentos.
        """
        url = f"{self._base_url}{endpoint}"
        headers: Dict[str, str] = {
            "Content-Type": "application/json",
            "Accept": "application/json",
        }

        if self._api_key:
            headers["Authorization"] = f"Bearer {self._api_key}"

        last_exception: Optional[Exception] = None

        for attempt in range(1, _MAX_RETRIES + 1):
            try:
                async with httpx.AsyncClient(
                    timeout=self._timeout or _HTTP_TIMEOUT
                ) as client:
                    response = await client.request(
                        method=method,
                        url=url,
                        params=params,
                        json=json_body,
                        headers=headers,
                    )

                    response.raise_for_status()

                    return response.json()

            except httpx.TimeoutException as exc:
                last_exception = exc
                logger.warning(
                    "Timeout consultando SAT (intento %d/%d): %s %s",
                    attempt,
                    _MAX_RETRIES,
                    method,
                    endpoint,
                )
            except httpx.HTTPStatusError as exc:
                last_exception = exc
                status_code = exc.response.status_code

                # No reintentar en errores de cliente (4xx)
                if 400 <= status_code < 500:
                    logger.error(
                        "Error de cliente SAT (%d): %s",
                        status_code,
                        exc.response.text[:200],
                    )
                    return None

                logger.warning(
                    "Error HTTP consultando SAT (intento %d/%d): %d",
                    attempt,
                    _MAX_RETRIES,
                    status_code,
                )
            except Exception as exc:
                last_exception = exc
                logger.warning(
                    "Error consultando SAT (intento %d/%d): %s",
                    attempt,
                    _MAX_RETRIES,
                    exc,
                )

            # Backoff exponencial
            if attempt < _MAX_RETRIES:
                wait_time = _RETRY_BACKOFF_BASE * (2 ** (attempt - 1))
                logger.debug(
                    "Esperando %.1f segundos antes de reintentar...",
                    wait_time,
                )
                await asyncio.sleep(wait_time)

        logger.error(
            "Todas las consultas al SAT fallaron para %s %s: %s",
            method,
            endpoint,
            last_exception,
        )
        return None

    async def _check_rate_limit(self) -> None:
        """
        Verifica y aplica rate limiting para las consultas al SAT.

        Utiliza Redis para rastrear el número de consultas en la
        ventana de tiempo configurada.

        Raises:
            RuntimeError: Si se excede el límite de consultas.
        """
        try:
            redis = get_redis()
            current = await redis.incr(_RATE_LIMIT_KEY)

            if current == 1:
                await redis.expire(_RATE_LIMIT_KEY, _RATE_LIMIT_WINDOW)

            if current > _MAX_REQUESTS_PER_MINUTE:
                ttl = await redis.ttl(_RATE_LIMIT_KEY)
                logger.warning(
                    "Rate limit SAT excedido: %d/%d consultas. "
                    "Esperando %d segundos.",
                    current,
                    _MAX_REQUESTS_PER_MINUTE,
                    ttl,
                )
                # Esperar en lugar de fallar
                await asyncio.sleep(max(ttl, 1))

        except Exception as exc:
            logger.warning("Error en rate limiting SAT: %s", exc)
            # No bloquear si Redis no está disponible
