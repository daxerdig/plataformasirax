"""
Servicio de validación de CURP contra RENAPO.

Este módulo implementa el servicio de validación de la Clave Única de
Registro de Población (CURP), incluyendo:

- Validación de formato y dígito verificador (local)
- Consulta contra la API de RENAPO para validación oficial
- Búsqueda de CURP en la base de datos de RENAPO
- Caché de resultados en Redis para optimizar consultas repetidas

El servicio utiliza inyección de dependencias para recibir los clientes
de base de datos y Redis, facilitando las pruebas unitarias.
"""

from __future__ import annotations

import json
import logging
from datetime import date, datetime
from typing import Any, Dict, List, Optional

import httpx
from redis.asyncio import Redis

from app.config import get_settings
from app.schemas.verification import (
    CurpCandidate,
    CurpExtractedInfo,
    CurpValidationResult,
)
from app.utils.curp_algorithm import (
    calculate_curp_check_digit,
    extract_curp_info,
    generate_curp,
    validate_curp_format,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Prefijos de claves para Redis
# ---------------------------------------------------------------------------
_CURP_CACHE_PREFIX = "curp:validate:"
_CURP_RENAPO_CACHE_PREFIX = "curp:renapo:"
_CURP_SEARCH_CACHE_PREFIX = "curp:search:"


class CurpValidatorService:
    """
    Servicio de validación de CURP con soporte para consulta RENAPO.

    Proporciona validación local (formato + dígito verificador) y
    validación remota contra la API de RENAPO. Los resultados se
    almacenan en caché Redis para evitar consultas repetidas.

    Attributes:
        redis: Cliente Redis asíncrono para caché.
        http_client: Cliente HTTP asíncrono para llamadas a RENAPO.
    """

    def __init__(self, redis: Redis) -> None:
        """
        Inicializa el servicio de validación de CURP.

        Args:
            redis: Cliente Redis asíncrono para almacenar en caché
                   los resultados de validación.
        """
        self._redis = redis
        self._http_client: Optional[httpx.AsyncClient] = None
        self._settings = get_settings()

    async def _get_http_client(self) -> httpx.AsyncClient:
        """
        Obtiene o crea el cliente HTTP para llamadas a RENAPO.

        Returns:
            httpx.AsyncClient: Cliente HTTP configurado.
        """
        if self._http_client is None or self._http_client.is_closed:
            self._http_client = httpx.AsyncClient(
                base_url=self._settings.RENAPO_API_URL,
                timeout=self._settings.RENAPO_TIMEOUT,
                headers={
                    "Authorization": f"Bearer {self._settings.RENAPO_API_KEY}",
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

    async def validate(self, curp: str) -> CurpValidationResult:
        """
        Realiza la validación completa de una CURP.

        Ejecuta las siguientes validaciones en orden:
        1. Validación de formato (estructura y caracteres)
        2. Validación del dígito verificador
        3. Extracción de información (si el formato es válido)
        4. Consulta RENAPO (si está disponible)

        Los resultados se almacenan en caché Redis para consultas
        posteriores con la misma CURP.

        Args:
            curp: La CURP a validar (18 caracteres).

        Returns:
            CurpValidationResult: Resultado detallado de la validación.
        """
        curp_upper = curp.strip().upper()
        cache_key = f"{_CURP_CACHE_PREFIX}{curp_upper}"

        # Verificar caché
        cached = await self._get_cached_result(cache_key)
        if cached is not None:
            logger.info("Resultado de CURP obtenido desde caché: %s", curp_upper)
            return cached

        errors: list[str] = []
        format_valid = False
        check_digit_valid = False
        extracted_info: Optional[CurpExtractedInfo] = None

        # Paso 1: Validación de formato
        format_valid = validate_curp_format(curp_upper)
        if not format_valid:
            errors.append(
                "El formato de la CURP no es válido. Verifique que cumpla "
                "con la estructura oficial de 18 posiciones."
            )

        # Paso 2: Validación del dígito verificador
        if format_valid:
            try:
                expected_digit = calculate_curp_check_digit(curp_upper)
                actual_digit = curp_upper[-1]
                check_digit_valid = expected_digit == actual_digit

                if not check_digit_valid:
                    errors.append(
                        f"El dígito verificador no coincide. "
                        f"Esperado: '{expected_digit}', Actual: '{actual_digit}'."
                    )
            except ValueError as exc:
                errors.append(f"Error al calcular el dígito verificador: {exc}")

        # Paso 3: Extracción de información
        if format_valid:
            try:
                info = extract_curp_info(curp_upper)
                extracted_info = CurpExtractedInfo(
                    name_initials=info.name_initials,
                    birth_date=info.birth_date.isoformat(),
                    gender=info.gender,
                    state_code=info.state_code,
                    state_name=info.state_name,
                    internal_consonants=info.internal_consonants,
                    century_digit=info.century_digit,
                    birth_year=info.birth_year,
                )
            except ValueError as exc:
                errors.append(f"Error al extraer información de la CURP: {exc}")

        # Determinar validez general
        is_valid = format_valid and check_digit_valid

        result = CurpValidationResult(
            is_valid=is_valid,
            format_valid=format_valid,
            check_digit_valid=check_digit_valid,
            renapo_match=None,
            extracted_info=extracted_info,
            errors=errors,
            validated_at=datetime.now(),
        )

        # Almacenar en caché
        await self._cache_result(cache_key, result)

        logger.info(
            "Validación de CURP completada: %s — válida=%s, formato=%s, dígito=%s",
            curp_upper,
            is_valid,
            format_valid,
            check_digit_valid,
        )

        return result

    async def validate_with_renapo(self, curp: str) -> CurpValidationResult:
        """
        Valida una CURP contra la base de datos de RENAPO.

        Realiza primero la validación local (formato + dígito verificador)
        y luego consulta la API de RENAPO para verificar que la CURP
        exista en el registro oficial.

        Args:
            curp: La CURP a validar (18 caracteres).

        Returns:
            CurpValidationResult: Resultado detallado incluyendo datos RENAPO.
        """
        # Realizar validación local primero
        result = await self.validate(curp)

        curp_upper = curp.strip().upper()
        cache_key = f"{_CURP_RENAPO_CACHE_PREFIX}{curp_upper}"

        # Verificar caché de RENAPO
        cached_renapo = await self._redis.get(cache_key)
        if cached_renapo is not None:
            try:
                renapo_data = json.loads(cached_renapo)
                result.renapo_match = renapo_data.get("match", False)
                logger.info(
                    "Resultado RENAPO obtenido desde caché: %s", curp_upper
                )
                return result
            except json.JSONDecodeError:
                pass

        # Consultar RENAPO
        if not result.format_valid:
            result.renapo_match = False
            result.errors.append(
                "No se puede consultar RENAPO: el formato de la CURP no es válido."
            )
            return result

        try:
            renapo_data = await self._call_renapo_api(curp_upper)
            result.renapo_match = renapo_data is not None

            if renapo_data:
                # Almacenar en caché
                await self._redis.set(
                    cache_key,
                    json.dumps({"match": True, "data": renapo_data}),
                    ex=self._settings.REDIS_CACHE_TTL,
                )
            else:
                result.renapo_match = False
                await self._redis.set(
                    cache_key,
                    json.dumps({"match": False}),
                    ex=self._settings.REDIS_CACHE_TTL,
                )

        except Exception as exc:
            logger.error("Error consultando RENAPO para CURP %s: %s", curp_upper, exc)
            result.renapo_match = None
            result.errors.append(
                f"Error al consultar el servicio RENAPO: {exc}. "
                f"Intente de nuevo más tarde."
            )

        # Actualizar validez general
        result.is_valid = result.format_valid and result.check_digit_valid

        return result

    async def search(
        self,
        name: str,
        birth_date: date,
        gender: str,
        state: Optional[str] = None,
    ) -> List[CurpCandidate]:
        """
        Busca una CURP en la base de datos de RENAPO.

        Genera la CURP probable a partir de los datos proporcionados y
        la consulta contra RENAPO para encontrar coincidencias.

        Args:
            name: Nombre(s) de pila.
            birth_date: Fecha de nacimiento.
            gender: Sexo ('H' o 'M').
            state: Clave de la entidad federativa (opcional).

        Returns:
            list[CurpCandidate]: Lista de candidatos encontrados.
        """
        # Generar CURP probable
        try:
            from app.utils.text_normalizer import split_full_name

            name_parts = split_full_name(name)
            paternal = name_parts[1] if len(name_parts) > 1 else ""
            maternal = name_parts[2] if len(name_parts) > 2 else ""
            first_name = name_parts[0]

            state_code = state or "NE"
            probable_curp = generate_curp(
                first_name, paternal, maternal, birth_date, gender, state_code
            )
        except ValueError as exc:
            logger.warning("Error generando CURP probable: %s", exc)
            return []

        # Verificar caché
        cache_key = f"{_CURP_SEARCH_CACHE_PREFIX}{probable_curp}"
        cached = await self._redis.get(cache_key)
        if cached is not None:
            try:
                cached_data = json.loads(cached)
                return [CurpCandidate(**c) for c in cached_data]
            except (json.JSONDecodeError, TypeError):
                pass

        # Consultar RENAPO
        candidates: list[CurpCandidate] = []

        try:
            renapo_data = await self._call_renapo_search_api(
                name=name,
                birth_date=birth_date.isoformat(),
                gender=gender,
                state=state,
            )

            if renapo_data:
                for entry in renapo_data:
                    candidate = CurpCandidate(
                        curp=entry.get("curp", ""),
                        name=entry.get("nombreCompleto"),
                        birth_date=entry.get("fechaNacimiento"),
                        gender=entry.get("sexo"),
                        state=entry.get("entidadFederativa"),
                        match_score=entry.get("score", 0.85),
                    )
                    candidates.append(candidate)

        except Exception as exc:
            logger.error("Error buscando CURP en RENAPO: %s", exc)
            # Retornar al menos la CURP generada localmente
            candidates.append(
                CurpCandidate(
                    curp=probable_curp,
                    name=name,
                    birth_date=birth_date.isoformat(),
                    gender=gender,
                    state=state,
                    match_score=0.7,
                )
            )

        # Almacenar en caché
        await self._redis.set(
            cache_key,
            json.dumps([c.model_dump() for c in candidates]),
            ex=self._settings.REDIS_CACHE_TTL,
        )

        return candidates

    # -----------------------------------------------------------------------
    # Métodos de caché
    # -----------------------------------------------------------------------

    async def _get_cached_result(self, cache_key: str) -> Optional[CurpValidationResult]:
        """
        Obtiene un resultado de validación desde el caché Redis.

        Args:
            cache_key: Clave de caché a buscar.

        Returns:
            Optional[CurpValidationResult]: Resultado cacheado o None.
        """
        try:
            cached = await self._redis.get(cache_key)
            if cached:
                data = json.loads(cached)
                return CurpValidationResult(**data)
        except (json.JSONDecodeError, TypeError) as exc:
            logger.warning("Error leyendo caché de CURP: %s", exc)
        return None

    async def _cache_result(
        self, cache_key: str, result: CurpValidationResult
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
            logger.warning("Error almacenando en caché CURP: %s", exc)

    # -----------------------------------------------------------------------
    # Métodos de integración con RENAPO
    # -----------------------------------------------------------------------

    async def _call_renapo_api(self, curp: str) -> Optional[Dict[str, Any]]:
        """
        Realiza la consulta a la API de RENAPO para validar una CURP.

        Args:
            curp: CURP a consultar.

        Returns:
            Optional[Dict]: Datos de RENAPO o None si no se encontró.

        Raises:
            httpx.HTTPError: Si la llamada a la API falla.
        """
        client = await self._get_http_client()

        try:
            response = await client.get(f"/curp/{curp}")
            if response.status_code == 200:
                return response.json()
            elif response.status_code == 404:
                return None
            else:
                logger.warning(
                    "RENAPO respondió con código %d para CURP %s",
                    response.status_code,
                    curp,
                )
                return None
        except httpx.HTTPError as exc:
            logger.error("Error HTTP consultando RENAPO: %s", exc)
            raise

    async def _call_renapo_search_api(
        self,
        name: str,
        birth_date: str,
        gender: str,
        state: Optional[str] = None,
    ) -> Optional[List[Dict[str, Any]]]:
        """
        Realiza la búsqueda en la API de RENAPO.

        Args:
            name: Nombre completo a buscar.
            birth_date: Fecha de nacimiento en formato ISO.
            gender: Sexo.
            state: Clave de entidad federativa.

        Returns:
            Optional[List[Dict]]: Lista de resultados o None.

        Raises:
            httpx.HTTPError: Si la llamada a la API falla.
        """
        client = await self._get_http_client()

        payload: Dict[str, Any] = {
            "nombre": name,
            "fechaNacimiento": birth_date,
            "sexo": gender,
        }
        if state:
            payload["entidadFederativa"] = state

        try:
            response = await client.post("/curp/search", json=payload)
            if response.status_code == 200:
                return response.json().get("results", [])
            else:
                logger.warning(
                    "Búsqueda RENAPO respondió con código %d", response.status_code
                )
                return None
        except httpx.HTTPError as exc:
            logger.error("Error HTTP en búsqueda RENAPO: %s", exc)
            raise

    async def get_cached_validation(self, curp: str) -> Optional[CurpValidationResult]:
        """
        Obtiene el resultado de validación cacheado para una CURP.

        Busca en Redis si existe un resultado de validación previo
        para la CURP especificada, sin realizar nuevas validaciones.

        Args:
            curp: CURP a buscar en caché.

        Returns:
            Optional[CurpValidationResult]: Resultado cacheado o None.
        """
        curp_upper = curp.strip().upper()
        cache_key = f"{_CURP_CACHE_PREFIX}{curp_upper}"
        return await self._get_cached_result(cache_key)
