"""
Servicio de validación de RFC contra el SAT.

Este módulo implementa el servicio de validación del Registro Federal
de Contribuyentes (RFC), incluyendo:

- Validación de formato y dígito verificador (local)
- Verificación del estado del RFC en el SAT (LFTP)
- Verificación de consistencia entre RFC y CURP
- Caché de resultados en Redis para optimizar consultas repetidas

El servicio utiliza inyección de dependencias para recibir los clientes
de base de datos y Redis, facilitando las pruebas unitarias.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime
from typing import Any, Dict, List, Optional

import httpx
from redis.asyncio import Redis

from app.config import get_settings
from app.schemas.verification import (
    ConsistencyResult,
    RfcExtractedInfo,
    RfcValidationResult,
    SatStatus,
)
from app.utils.curp_algorithm import extract_curp_info, validate_curp_format
from app.utils.rfc_algorithm import (
    calculate_rfc_check_digit,
    extract_rfc_info,
    validate_rfc_format,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Prefijos de claves para Redis
# ---------------------------------------------------------------------------
_RFC_CACHE_PREFIX = "rfc:validate:"
_RFC_SAT_CACHE_PREFIX = "rfc:sat:"
_RFC_STATUS_CACHE_PREFIX = "rfc:status:"


class RfcValidatorService:
    """
    Servicio de validación de RFC con soporte para verificación SAT.

    Proporciona validación local (formato + dígito verificador) y
    verificación remota contra los servicios del SAT. Los resultados
    se almacenan en caché Redis para evitar consultas repetidas.

    Attributes:
        redis: Cliente Redis asíncrono para caché.
        http_client: Cliente HTTP asíncrono para llamadas al SAT.
    """

    def __init__(self, redis: Redis) -> None:
        """
        Inicializa el servicio de validación de RFC.

        Args:
            redis: Cliente Redis asíncrono para almacenar en caché
                   los resultados de validación.
        """
        self._redis = redis
        self._http_client: Optional[httpx.AsyncClient] = None
        self._settings = get_settings()

    async def _get_http_client(self) -> httpx.AsyncClient:
        """
        Obtiene o crea el cliente HTTP para llamadas al SAT.

        Returns:
            httpx.AsyncClient: Cliente HTTP configurado.
        """
        if self._http_client is None or self._http_client.is_closed:
            self._http_client = httpx.AsyncClient(
                base_url=self._settings.SAT_API_URL,
                timeout=self._settings.SAT_TIMEOUT,
                headers={
                    "Authorization": f"Bearer {self._settings.SAT_API_KEY}",
                    "Content-Type": "application/json",
                    "Accept": "application/json",
                },
            )
        return self._http_client

    async def close(self) -> None:
        """Cierra el cliente HTTP y libera recursos."""
        if self._http_client is not None and not self._http_client.is_closed:
            await self._http_client.aclose()
            self._http_client = None

    # -----------------------------------------------------------------------
    # Validación principal
    # -----------------------------------------------------------------------

    async def validate(self, rfc: str) -> RfcValidationResult:
        """
        Realiza la validación completa de un RFC.

        Ejecuta las siguientes validaciones en orden:
        1. Validación de formato y tipo de persona
        2. Validación del dígito verificador
        3. Extracción de información (si el formato es válido)

        Args:
            rfc: El RFC a validar (12-13 caracteres).

        Returns:
            RfcValidationResult: Resultado detallado de la validación.
        """
        rfc_upper = rfc.strip().upper()
        cache_key = f"{_RFC_CACHE_PREFIX}{rfc_upper}"

        # Verificar caché
        cached = await self._get_cached_result(cache_key)
        if cached is not None:
            logger.info("Resultado de RFC obtenido desde caché: %s", rfc_upper)
            return cached

        errors: list[str] = []
        format_valid = False
        check_digit_valid = False
        person_type = "desconocido"
        extracted_info: Optional[RfcExtractedInfo] = None

        # Paso 1: Validación de formato
        format_valid, person_type = validate_rfc_format(rfc_upper)
        if not format_valid:
            errors.append(
                "El formato del RFC no es válido. Verifique que cumpla "
                "con la estructura oficial (persona física: 4 letras + "
                "6 dígitos + 3 alfanuméricos; persona moral: 3 letras + "
                "6 dígitos + 3 alfanuméricos)."
            )

        # Paso 2: Validación del dígito verificador
        if format_valid:
            try:
                expected_digit = calculate_rfc_check_digit(rfc_upper)
                actual_digit = rfc_upper[-1]
                check_digit_valid = expected_digit == actual_digit

                if not check_digit_valid:
                    errors.append(
                        f"El dígito verificador del RFC no coincide. "
                        f"Esperado: '{expected_digit}', Actual: '{actual_digit}'."
                    )
            except ValueError as exc:
                errors.append(f"Error al calcular el dígito verificador: {exc}")

        # Paso 3: Extracción de información
        if format_valid:
            try:
                info = extract_rfc_info(rfc_upper)
                extracted_info = RfcExtractedInfo(
                    person_type=info.person_type,
                    name_initials=info.name_initials,
                    birth_date=info.birth_date.isoformat(),
                    homoclave=info.homoclave,
                    birth_year=info.birth_year,
                )
            except ValueError as exc:
                errors.append(f"Error al extraer información del RFC: {exc}")

        # Determinar validez general
        is_valid = format_valid and check_digit_valid

        result = RfcValidationResult(
            is_valid=is_valid,
            format_valid=format_valid,
            check_digit_valid=check_digit_valid,
            person_type=person_type if format_valid else "desconocido",
            sat_active=None,
            extracted_info=extracted_info,
            errors=errors,
            validated_at=datetime.now(),
        )

        # Almacenar en caché
        await self._cache_result(cache_key, result)

        logger.info(
            "Validación de RFC completada: %s — válida=%s, tipo=%s, dígito=%s",
            rfc_upper,
            is_valid,
            person_type,
            check_digit_valid,
        )

        return result

    async def validate_with_sat(self, rfc: str) -> RfcValidationResult:
        """
        Valida un RFC y verifica su estado en el SAT.

        Realiza primero la validación local (formato + dígito verificador)
        y luego consulta los servicios del SAT para verificar el estado
        del RFC en la Lista de Facilitadores de Contribuyentes (LFTP).

        Args:
            rfc: El RFC a validar y verificar.

        Returns:
            RfcValidationResult: Resultado detallado incluyendo datos SAT.
        """
        # Realizar validación local primero
        result = await self.validate(rfc)

        rfc_upper = rfc.strip().upper()
        cache_key = f"{_RFC_SAT_CACHE_PREFIX}{rfc_upper}"

        # Verificar caché de SAT
        cached_sat = await self._redis.get(cache_key)
        if cached_sat is not None:
            try:
                sat_data = json.loads(cached_sat)
                result.sat_active = sat_data.get("active", False)
                result.sat_data = sat_data.get("data")
                logger.info(
                    "Resultado SAT obtenido desde caché: %s", rfc_upper
                )
                return result
            except json.JSONDecodeError:
                pass

        # Consultar SAT
        if not result.format_valid:
            result.sat_active = False
            result.errors.append(
                "No se puede consultar el SAT: el formato del RFC no es válido."
            )
            return result

        try:
            sat_response = await self._call_sat_api(rfc_upper)

            if sat_response:
                result.sat_active = sat_response.get("activo", False)
                result.sat_data = sat_response

                # Almacenar en caché
                await self._redis.set(
                    cache_key,
                    json.dumps({
                        "active": result.sat_active,
                        "data": sat_response,
                    }),
                    ex=self._settings.REDIS_CACHE_TTL,
                )
            else:
                result.sat_active = False
                await self._redis.set(
                    cache_key,
                    json.dumps({"active": False, "data": None}),
                    ex=self._settings.REDIS_CACHE_TTL,
                )

        except Exception as exc:
            logger.error("Error consultando SAT para RFC %s: %s", rfc_upper, exc)
            result.sat_active = None
            result.errors.append(
                f"Error al consultar el servicio SAT: {exc}. "
                f"Intente de nuevo más tarde."
            )

        return result

    async def get_sat_status(self, rfc: str) -> SatStatus:
        """
        Obtiene el estado actual de un RFC en el SAT.

        Verifica si el RFC está activo, suspendido o cancelado
        en los registros del Servicio de Administración Tributaria.

        Args:
            rfc: El RFC a consultar.

        Returns:
            SatStatus: Estado del RFC en el SAT.
        """
        rfc_upper = rfc.strip().upper()
        cache_key = f"{_RFC_STATUS_CACHE_PREFIX}{rfc_upper}"

        # Verificar caché
        cached = await self._redis.get(cache_key)
        if cached is not None:
            try:
                return SatStatus(**json.loads(cached))
            except (json.JSONDecodeError, TypeError):
                pass

        # Consultar SAT
        try:
            sat_data = await self._call_sat_api(rfc_upper)

            if sat_data:
                status_value = sat_data.get("estado", "desconocido")
                is_active = status_value.lower() == "activo"

                status_descriptions = {
                    "activo": "El RFC se encuentra activo y vigente ante el SAT.",
                    "suspendido": "El RFC se encuentra suspendido temporalmente.",
                    "cancelado": "El RFC ha sido cancelado definitivamente.",
                    "desconocido": "No se pudo determinar el estado del RFC.",
                }

                result = SatStatus(
                    rfc=rfc_upper,
                    is_active=is_active,
                    status=status_value.lower(),
                    status_description=status_descriptions.get(
                        status_value.lower(),
                        "Estado no reconocido por el sistema.",
                    ),
                    last_checked=datetime.now(),
                )
            else:
                result = SatStatus(
                    rfc=rfc_upper,
                    is_active=False,
                    status="no_encontrado",
                    status_description=(
                        "El RFC no fue encontrado en los registros del SAT. "
                        "Verifique que el RFC sea correcto."
                    ),
                    last_checked=datetime.now(),
                )

            # Almacenar en caché
            await self._redis.set(
                cache_key,
                result.model_dump_json(),
                ex=self._settings.REDIS_CACHE_TTL,
            )

            return result

        except Exception as exc:
            logger.error("Error obteniendo estado SAT para RFC %s: %s", rfc_upper, exc)
            return SatStatus(
                rfc=rfc_upper,
                is_active=False,
                status="error",
                status_description=(
                    f"Error al consultar el estado del RFC: {exc}. "
                    f"Intente de nuevo más tarde."
                ),
                last_checked=datetime.now(),
            )

    async def verify_rfc_curp_consistency(
        self, rfc: str, curp: str
    ) -> ConsistencyResult:
        """
        Verifica la consistencia entre un RFC y una CURP.

        Compara los datos extraídos de ambos documentos para verificar
        que sean coherentes entre sí:
        - Fecha de nacimiento
        - Iniciales del nombre

        Args:
            rfc: El RFC a comparar.
            curp: La CURP a comparar.

        Returns:
            ConsistencyResult: Resultado de la verificación de consistencia.
        """
        inconsistencies: list[str] = []
        birth_date_match: Optional[bool] = None
        name_initials_match: Optional[bool] = None

        # Extraer información de la CURP
        curp_info = None
        if validate_curp_format(curp):
            try:
                curp_info = extract_curp_info(curp)
            except ValueError as exc:
                inconsistencies.append(
                    f"Error al extraer información de la CURP: {exc}"
                )

        # Extraer información del RFC
        rfc_info = None
        is_rfc_valid, _ = validate_rfc_format(rfc)
        if is_rfc_valid:
            try:
                rfc_info = extract_rfc_info(rfc)
            except ValueError as exc:
                inconsistencies.append(
                    f"Error al extraer información del RFC: {exc}"
                )

        # Comparar fechas de nacimiento
        if curp_info and rfc_info:
            birth_date_match = curp_info.birth_date == rfc_info.birth_date
            if not birth_date_match:
                inconsistencies.append(
                    f"La fecha de nacimiento no coincide entre CURP y RFC. "
                    f"CURP: {curp_info.birth_date.isoformat()}, "
                    f"RFC: {rfc_info.birth_date.isoformat()}."
                )

            # Comparar iniciales del nombre
            # La CURP tiene 4 letras y el RFC (persona física) también tiene 4
            if rfc_info.person_type == "fisica":
                name_initials_match = (
                    curp_info.name_initials == rfc_info.name_initials
                )
                if not name_initials_match:
                    inconsistencies.append(
                        f"Las iniciales del nombre no coinciden entre CURP y RFC. "
                        f"CURP: {curp_info.name_initials}, "
                        f"RFC: {rfc_info.name_initials}."
                    )
            else:
                # Para personas morales, solo comparar los primeros 3 caracteres
                # del RFC con los primeros 3 de la CURP (si aplica)
                name_initials_match = None

        elif not curp_info:
            inconsistencies.append(
                "No se pudo extraer información de la CURP para comparar."
            )
        elif not rfc_info:
            inconsistencies.append(
                "No se pudo extraer información del RFC para comparar."
            )

        is_consistent = len(inconsistencies) == 0

        return ConsistencyResult(
            is_consistent=is_consistent,
            birth_date_match=birth_date_match,
            name_initials_match=name_initials_match,
            inconsistencies=inconsistencies,
        )

    # -----------------------------------------------------------------------
    # Métodos de caché
    # -----------------------------------------------------------------------

    async def _get_cached_result(self, cache_key: str) -> Optional[RfcValidationResult]:
        """
        Obtiene un resultado de validación desde el caché Redis.

        Args:
            cache_key: Clave de caché a buscar.

        Returns:
            Optional[RfcValidationResult]: Resultado cacheado o None.
        """
        try:
            cached = await self._redis.get(cache_key)
            if cached:
                data = json.loads(cached)
                return RfcValidationResult(**data)
        except (json.JSONDecodeError, TypeError) as exc:
            logger.warning("Error leyendo caché de RFC: %s", exc)
        return None

    async def _cache_result(
        self, cache_key: str, result: RfcValidationResult
    ) -> None:
        """
        Almacena un resultado de validación en el caché Redis.

        Args:
            cache_key: Clave de caché.
            result: Resultado a almacenar.
        """
        try:
            await self._redis.set(
                cache_key,
                result.model_dump_json(),
                ex=self._settings.REDIS_CACHE_TTL,
            )
        except Exception as exc:
            logger.warning("Error almacenando en caché RFC: %s", exc)

    # -----------------------------------------------------------------------
    # Métodos de integración con el SAT
    # -----------------------------------------------------------------------

    async def _call_sat_api(self, rfc: str) -> Optional[Dict[str, Any]]:
        """
        Realiza la consulta a la API del SAT para verificar un RFC.

        Args:
            rfc: RFC a consultar.

        Returns:
            Optional[Dict]: Datos del SAT o None si no se encontró.

        Raises:
            httpx.HTTPError: Si la llamada a la API falla.
        """
        client = await self._get_http_client()

        try:
            response = await client.get(f"/rfc/{rfc}")
            if response.status_code == 200:
                return response.json()
            elif response.status_code == 404:
                return None
            else:
                logger.warning(
                    "SAT respondió con código %d para RFC %s",
                    response.status_code,
                    rfc,
                )
                return None
        except httpx.HTTPError as exc:
            logger.error("Error HTTP consultando SAT: %s", exc)
            raise

    async def get_cached_validation(self, rfc: str) -> Optional[RfcValidationResult]:
        """
        Obtiene el resultado de validación cacheado para un RFC.

        Busca en Redis si existe un resultado de validación previo
        para el RFC especificado, sin realizar nuevas validaciones.

        Args:
            rfc: RFC a buscar en caché.

        Returns:
            Optional[RfcValidationResult]: Resultado cacheado o None.
        """
        rfc_upper = rfc.strip().upper()
        cache_key = f"{_RFC_CACHE_PREFIX}{rfc_upper}"
        return await self._get_cached_result(cache_key)
