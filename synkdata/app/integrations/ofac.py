"""
Cliente de integración con la lista OFAC SDN (Specially Designated Nationals).

Gestiona la consulta y caché de la lista de personas y entidades bloqueadas
por la Office of Foreign Assets Control del Departamento del Tesoro de EE.UU.

Incluye:
- Búsqueda por nombre con filtrado por tipo de entidad
- Búsqueda por ID de registro SDN
- Descarga y caché de la lista completa SDN en Redis (TTL 24h)
- Manejo graceful de errores de conectividad

La lista SDN contiene nombres de personas y entidades sujetas a sanciones
económicas por parte del gobierno de los Estados Unidos.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Optional

import httpx

from app.config import get_settings
from app.database import get_redis
from app.services.fuzzy_matcher import FuzzyMatcherService

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constantes
# ---------------------------------------------------------------------------
_OFAC_SDN_CACHE_KEY = "ofac:sdn_list"
_OFAC_SDN_CACHE_TTL = 86400  # 24 horas en segundos
_OFAC_SEARCH_CACHE_PREFIX = "ofac:search:"
_OFAC_SEARCH_CACHE_TTL = 3600  # 1 hora en segundos
_HTTP_TIMEOUT = 30.0


# ---------------------------------------------------------------------------
# Modelos de datos
# ---------------------------------------------------------------------------
@dataclass(frozen=True, slots=True)
class OfacRecord:
    """
    Registro individual de la lista SDN de OFAC.

    Attributes:
        id: Identificador único del registro SDN.
        name: Nombre completo de la persona o entidad.
        type: Tipo de entidad (individual, entity, vessel, aircraft).
        program: Programa de sanciones bajo el cual está listado.
        title: Cargo o título de la persona (si aplica).
        remarks: Observaciones adicionales del registro.
        aliases: Lista de nombres alternativos o alias conocidos.
        addresses: Lista de direcciones asociadas al registro.
    """

    id: str
    name: str
    type: str
    program: str = ""
    title: str = ""
    remarks: str = ""
    aliases: list[str] = field(default_factory=list)
    addresses: list[str] = field(default_factory=list)


@dataclass(frozen=True, slots=True)
class OfacMatch:
    """
    Resultado de una búsqueda en la lista OFAC SDN.

    Attributes:
        record: Registro OFAC que coincidió.
        match_score: Puntuación de similitud (0.0 a 1.0).
        match_type: Tipo de coincidencia detectada (exact/fuzzy/phonetic/alias).
    """

    record: OfacRecord
    match_score: float
    match_type: str


# ---------------------------------------------------------------------------
# Cliente OFAC
# ---------------------------------------------------------------------------
class OfacClient:
    """
    Cliente asíncrono para la consulta de la lista OFAC SDN.

    Gestiona la descarga, caché y búsqueda en la lista de personas
    y entidades sancionadas por el Departamento del Tesoro de EE.UU.

    La lista SDN se cachea en Redis con un TTL de 24 horas. Las
    búsquedas individuales se cachean con un TTL de 1 hora.

    Example:
        >>> client = OfacClient()
        >>> matches = await client.search("Juan Pérez López")
        >>> for m in matches:
        ...     print(f"{m.record.name} - score: {m.match_score}")
    """

    def __init__(self, *, matcher: FuzzyMatcherService | None = None) -> None:
        """
        Inicializa el cliente OFAC.

        Args:
            matcher: Servicio de comparación difusa a utilizar.
                Si no se proporciona, se crea uno por defecto.
        """
        self._settings = get_settings()
        self._matcher = matcher or FuzzyMatcherService()
        self._base_url = self._settings.OFAC_API_URL
        self._api_key = self._settings.OFAC_API_KEY

    # ── Búsqueda principal ──────────────────────────────────────────────

    async def search(
        self,
        name: str,
        entity_type: str | None = None,
        threshold: float = 0.85,
    ) -> list[OfacMatch]:
        """
        Busca un nombre en la lista OFAC SDN con comparación difusa.

        Realiza la búsqueda en los siguientes pasos:
        1. Verifica caché de búsqueda previa
        2. Obtiene la lista SDN (desde caché o descarga)
        3. Filtra por tipo de entidad si se especifica
        4. Aplica comparación difusa y fonética
        5. Cachea los resultados

        Args:
            name: Nombre a buscar en la lista SDN.
            entity_type: Tipo de entidad a filtrar (individual, entity,
                vessel, aircraft). None para buscar en todos.
            threshold: Umbral mínimo de similitud.

        Returns:
            Lista de OfacMatch ordenada por score descendente.
        """
        if not name:
            return []

        cache_key = f"{_OFAC_SEARCH_CACHE_PREFIX}{name.lower()}:{entity_type or 'all'}"

        try:
            redis = get_redis()
            cached = await redis.get(cache_key)
            if cached:
                logger.debug("Resultado OFAC desde caché: %s", name)
                return self._deserialize_matches(cached)
        except Exception as exc:
            logger.warning("Error accediendo caché Redis para OFAC: %s", exc)

        # Obtener la lista SDN
        try:
            sdn_records = await self._get_sdn_list()
        except Exception as exc:
            logger.error("Error obteniendo lista SDN de OFAC: %s", exc)
            return []

        # Filtrar por tipo de entidad si se especifica
        if entity_type:
            sdn_records = [
                r for r in sdn_records
                if r.type.lower() == entity_type.lower()
            ]

        # Construir lista de nombres objetivos
        targets = [r.name for r in sdn_records]

        # Comparación difusa contra nombres principales
        name_matches = self._matcher.match(name, targets, threshold=threshold)

        # Comparación contra alias
        alias_matches = self._search_aliases(name, sdn_records, threshold)

        # Consolidar resultados
        results = self._merge_results(name_matches, alias_matches, sdn_records)

        # Cachear resultados
        try:
            redis = get_redis()
            await redis.setex(
                cache_key,
                _OFAC_SEARCH_CACHE_TTL,
                self._serialize_matches(results),
            )
        except Exception as exc:
            logger.warning("Error cacheando resultados OFAC: %s", exc)

        return results

    # ── Búsqueda por ID ─────────────────────────────────────────────────

    async def search_by_id(self, sdn_id: str) -> OfacRecord | None:
        """
        Busca un registro SDN específico por su identificador.

        Args:
            sdn_id: Identificador único del registro SDN.

        Returns:
            OfacRecord si se encuentra, None si no existe.
        """
        if not sdn_id:
            return None

        try:
            sdn_records = await self._get_sdn_list()
            for record in sdn_records:
                if record.id == sdn_id:
                    return record
        except Exception as exc:
            logger.error("Error buscando SDN por ID %s: %s", sdn_id, exc)

        return None

    # ── Descarga y caché de la lista SDN ────────────────────────────────

    async def download_sdn_list(self) -> None:
        """
        Descarga la lista SDN completa y la cachea en Redis.

        La lista se obtiene desde la API del Departamento del Tesoro
        y se almacena en Redis con un TTL de 24 horas.

        Raises:
            httpx.HTTPError: Si la descarga falla después de los reintentos.
        """
        logger.info("Descargando lista SDN de OFAC...")

        try:
            records = await self._fetch_sdn_from_api()

            redis = get_redis()
            serialized = json.dumps(
                [self._record_to_dict(r) for r in records],
                ensure_ascii=False,
            )
            await redis.setex(_OFAC_SDN_CACHE_KEY, _OFAC_SDN_CACHE_TTL, serialized)

            logger.info(
                "Lista SDN de OFAC descargada y cacheada: %d registros",
                len(records),
            )
        except Exception as exc:
            logger.error("Error descargando lista SDN de OFAC: %s", exc)
            raise

    # ── Métodos internos ────────────────────────────────────────────────

    async def _get_sdn_list(self) -> list[OfacRecord]:
        """
        Obtiene la lista SDN desde caché o la descarga si no existe.

        Returns:
            Lista de registros SDN.
        """
        try:
            redis = get_redis()
            cached = await redis.get(_OFAC_SDN_CACHE_KEY)
            if cached:
                logger.debug("Lista SDN obtenida desde caché Redis")
                return self._deserialize_records(cached)
        except Exception as exc:
            logger.warning("Error leyendo caché SDN: %s", exc)

        # Si no está en caché, descargar
        await self.download_sdn_list()

        # Intentar leer de caché nuevamente
        try:
            redis = get_redis()
            cached = await redis.get(_OFAC_SDN_CACHE_KEY)
            if cached:
                return self._deserialize_records(cached)
        except Exception:
            pass

        return []

    async def _fetch_sdn_from_api(self) -> list[OfacRecord]:
        """
        Obtiene la lista SDN desde la API del Departamento del Tesoro.

        Returns:
            Lista de registros SDN parseados.
        """
        records: list[OfacRecord] = []

        try:
            async with httpx.AsyncClient(timeout=_HTTP_TIMEOUT) as client:
                # Consultar la API de OFAC
                headers: dict[str, str] = {}
                if self._api_key:
                    headers["Authorization"] = f"Bearer {self._api_key}"

                params = {
                    "format": "json",
                    "type": "SDN",
                }

                response = await client.get(
                    f"{self._base_url}/sdn",
                    params=params,
                    headers=headers,
                )
                response.raise_for_status()

                data = response.json()

                # Parsear la respuesta de la API
                sdn_entries = data.get("sdnEntries", data.get("results", []))

                for entry in sdn_entries:
                    record = self._parse_sdn_entry(entry)
                    if record:
                        records.append(record)

        except httpx.TimeoutException:
            logger.error("Timeout descargando lista SDN de OFAC")
            raise
        except httpx.HTTPStatusError as exc:
            logger.error(
                "Error HTTP descargando lista SDN: %d - %s",
                exc.response.status_code,
                exc.response.text[:200],
            )
            raise
        except Exception as exc:
            logger.error("Error inesperado descargando lista SDN: %s", exc)
            raise

        return records

    def _parse_sdn_entry(self, entry: dict[str, Any]) -> OfacRecord | None:
        """
        Parsea una entrada individual de la respuesta SDN.

        Args:
            entry: Diccionario con los datos de la entrada SDN.

        Returns:
            OfacRecord parseado, o None si los datos son inválidos.
        """
        try:
            sdn_id = str(entry.get("entNumber", entry.get("id", "")))
            name = entry.get("sdnName", entry.get("name", ""))
            entity_type = entry.get("sdnType", entry.get("type", "individual"))

            if not sdn_id or not name:
                return None

            # Extraer alias
            aliases: list[str] = []
            for aka in entry.get("akaList", entry.get("aliases", [])):
                aka_name = aka.get("lastName", aka.get("name", ""))
                if aka_name:
                    first = aka.get("firstName", "")
                    full_aka = f"{first} {aka_name}".strip() if first else aka_name
                    aliases.append(full_aka)

            # Extraer direcciones
            addresses: list[str] = []
            for addr in entry.get("addressList", entry.get("addresses", [])):
                address_parts = [
                    addr.get("address1", ""),
                    addr.get("city", ""),
                    addr.get("stateOrProvince", ""),
                    addr.get("country", ""),
                ]
                full_addr = ", ".join(p for p in address_parts if p)
                if full_addr:
                    addresses.append(full_addr)

            return OfacRecord(
                id=sdn_id,
                name=name,
                type=entity_type,
                program=entry.get("programs", entry.get("program", "")),
                title=entry.get("title", ""),
                remarks=entry.get("remarks", ""),
                aliases=aliases,
                addresses=addresses,
            )
        except Exception as exc:
            logger.warning("Error parseando entrada SDN: %s", exc)
            return None

    def _search_aliases(
        self,
        name: str,
        records: list[OfacRecord],
        threshold: float,
    ) -> list[tuple[OfacRecord, MatchResult]]:
        """
        Busca coincidencias contra los alias de los registros SDN.

        Args:
            name: Nombre a buscar.
            records: Lista de registros SDN.
            threshold: Umbral mínimo de similitud.

        Returns:
            Lista de tuplas (registro, resultado_match) para alias coincidentes.
        """
        results: list[tuple[OfacRecord, MatchResult]] = []

        for record in records:
            if not record.aliases:
                continue

            alias_matches = self._matcher.match_with_aliases(
                name, record.aliases, threshold=threshold
            )
            for match in alias_matches:
                results.append((record, match))

        return results

    def _merge_results(
        self,
        name_matches: list[MatchResult],
        alias_matches: list[tuple[OfacRecord, MatchResult]],
        records: list[OfacRecord],
    ) -> list[OfacMatch]:
        """
        Consolida los resultados de búsqueda por nombre y alias.

        Elimina duplicados (mismo registro) conservando el mejor score.

        Args:
            name_matches: Resultados de búsqueda por nombre principal.
            alias_matches: Resultados de búsqueda por alias.
            records: Lista completa de registros SDN.

        Returns:
            Lista deduplicada de OfacMatch ordenada por score.
        """
        # Mapear nombre -> registro para lookup rápido
        name_to_record: dict[str, OfacRecord] = {r.name: r for r in records}

        # Diccionario para deduplicar: SDN ID -> mejor match
        best_matches: dict[str, OfacMatch] = {}

        # Procesar matches por nombre
        for match in name_matches:
            record = name_to_record.get(match.target)
            if record is None:
                continue
            self._upsert_ofac_match(best_matches, record, match.score, match.match_type.value)

        # Procesar matches por alias
        for record, match in alias_matches:
            self._upsert_ofac_match(best_matches, record, match.score, match.match_type.value)

        return sorted(best_matches.values(), key=lambda m: m.match_score, reverse=True)

    def _upsert_ofac_match(
        self,
        best_matches: dict[str, OfacMatch],
        record: OfacRecord,
        score: float,
        match_type: str,
    ) -> None:
        """
        Inserta o actualiza un match, conservando el mejor score por registro.

        Args:
            best_matches: Diccionario de mejores matches por ID de registro.
            record: Registro SDN.
            score: Puntuación de la coincidencia.
            match_type: Tipo de coincidencia.
        """
        existing = best_matches.get(record.id)
        if existing is None or score > existing.match_score:
            best_matches[record.id] = OfacMatch(
                record=record,
                match_score=score,
                match_type=match_type,
            )

    # ── Serialización ───────────────────────────────────────────────────

    def _record_to_dict(self, record: OfacRecord) -> dict[str, Any]:
        """Convierte un OfacRecord a diccionario para serialización."""
        return {
            "id": record.id,
            "name": record.name,
            "type": record.type,
            "program": record.program,
            "title": record.title,
            "remarks": record.remarks,
            "aliases": record.aliases,
            "addresses": record.addresses,
        }

    def _dict_to_record(self, data: dict[str, Any]) -> OfacRecord:
        """Convierte un diccionario a OfacRecord."""
        return OfacRecord(
            id=data.get("id", ""),
            name=data.get("name", ""),
            type=data.get("type", "individual"),
            program=data.get("program", ""),
            title=data.get("title", ""),
            remarks=data.get("remarks", ""),
            aliases=data.get("aliases", []),
            addresses=data.get("addresses", []),
        )

    def _serialize_matches(self, matches: list[OfacMatch]) -> str:
        """Serializa una lista de OfacMatch a JSON."""
        data = [
            {
                "record": self._record_to_dict(m.record),
                "match_score": m.match_score,
                "match_type": m.match_type,
            }
            for m in matches
        ]
        return json.dumps(data, ensure_ascii=False)

    def _deserialize_matches(self, cached: str) -> list[OfacMatch]:
        """Deserializa una lista de OfacMatch desde JSON."""
        data = json.loads(cached)
        return [
            OfacMatch(
                record=self._dict_to_record(m["record"]),
                match_score=m["match_score"],
                match_type=m["match_type"],
            )
            for m in data
        ]

    def _deserialize_records(self, cached: str) -> list[OfacRecord]:
        """Deserializa una lista de OfacRecord desde JSON."""
        data = json.loads(cached)
        return [self._dict_to_record(r) for r in data]
