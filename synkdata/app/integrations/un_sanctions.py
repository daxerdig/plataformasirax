"""
Cliente de integración con la lista consolidada de sanciones del
Consejo de Seguridad de las Naciones Unidas.

Gestiona la consulta de la lista consolidada de individuos y entidades
asociados con Al-Qaida e ISIS (Comité 1267/1989/2253), así como
las listas de los comités 1518 (Iraq), 1533 (R.D. del Congo),
1591 (Sudán/Darfur), 1636 (Líbano), 1718 (R.P.D. de Corea),
1737 (Irán), 1970 (Libia), 2048 (Guinea-Bissau), 2127 (RCA),
2140 (Yemen), 2206 (Sudán del Sur), 2230 (Irán), 2374 (Malí),
2430 (Somalia) y 2664 (sanciones transversales de terrorismo).

Incluye:
- Búsqueda por nombre en la lista consolidada
- Obtención de entidades por ID
- Caché de resultados en Redis
- Manejo graceful de errores
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from typing import Any, Optional

import httpx

from app.config import get_settings
from app.database import get_redis
from app.services.fuzzy_matcher import FuzzyMatcherService, MatchType

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constantes
# ---------------------------------------------------------------------------
_UN_SANCTIONS_CACHE_PREFIX = "un_sanctions:search:"
_UN_SANCTIONS_ENTITY_CACHE_PREFIX = "un_sanctions:entity:"
_UN_SANCTIONS_CACHE_TTL = 7200  # 2 horas
_UN_SC_API_URL = "https://scsanctions.un.org/resources/xml/en/consolidated.xml"
_HTTP_TIMEOUT = 45.0  # La lista consolidada puede ser grande


# ---------------------------------------------------------------------------
# Modelos de datos
# ---------------------------------------------------------------------------
@dataclass(frozen=True, slots=True)
class UnSanctionsEntity:
    """
    Entidad de la lista de sanciones del Consejo de Seguridad de la ONU.

    Attributes:
        id: Identificador único de la entidad (ej. QI.A.1.03).
        name: Nombre completo de la persona o entidad.
        entity_type: Tipo de entidad (individual, entity).
        aliases: Nombres alternativos conocidos.
        designation_date: Fecha de designación en la lista.
        committee: Comité del CS que emitió la designación.
        nationality: Nacionalidad (para individuos).
        passport_numbers: Números de pasaporte conocidos.
        national_id_numbers: Números de identificación nacional.
        addresses: Direcciones conocidas.
        listed_on: Fecha de inclusión en la lista.
        other_information: Información adicional relevante.
    """

    id: str
    name: str
    entity_type: str = "individual"
    aliases: list[str] = field(default_factory=list)
    designation_date: str = ""
    committee: str = ""
    nationality: str = ""
    passport_numbers: list[str] = field(default_factory=list)
    national_id_numbers: list[str] = field(default_factory=list)
    addresses: list[str] = field(default_factory=list)
    listed_on: str = ""
    other_information: str = ""


@dataclass(frozen=True, slots=True)
class UnSanctionsMatch:
    """
    Resultado de una búsqueda en la lista de sanciones de la ONU.

    Attributes:
        entity: Entidad sancionada que coincidió.
        match_score: Puntuación de similitud (0.0 a 1.0).
        match_type: Tipo de coincidencia detectada.
    """

    entity: UnSanctionsEntity
    match_score: float
    match_type: str


# ---------------------------------------------------------------------------
# Cliente ONU - Sanciones del Consejo de Seguridad
# ---------------------------------------------------------------------------
class UnSanctionsClient:
    """
    Cliente asíncrono para la lista de sanciones del CS de la ONU.

    La lista consolidada del Consejo de Seguridad incluye individuos
    y entidades sujetos a sanciones bajo múltiples resoluciones.
    Los datos se obtienen del portal de sanciones de la ONU y
    se cachean en Redis para minimizar peticiones.

    Example:
        >>> client = UnSanctionsClient()
        >>> matches = await client.search("Ahmed Hassan")
        >>> for m in matches:
        ...     print(f"{m.entity.name} - {m.entity.committee}")
    """

    def __init__(self, *, matcher: FuzzyMatcherService | None = None) -> None:
        """
        Inicializa el cliente de sanciones de la ONU.

        Args:
            matcher: Servicio de comparación difusa. Si no se
                proporciona, se crea uno por defecto.
        """
        self._settings = get_settings()
        self._matcher = matcher or FuzzyMatcherService()

    # ── Búsqueda principal ──────────────────────────────────────────────

    async def search(
        self,
        name: str,
        threshold: float = 0.80,
    ) -> list[UnSanctionsMatch]:
        """
        Busca un nombre en la lista consolidada de sanciones de la ONU.

        Args:
            name: Nombre a buscar.
            threshold: Umbral mínimo de similitud.

        Returns:
            Lista de UnSanctionsMatch ordenada por score descendente.
        """
        if not name:
            return []

        cache_key = f"{_UN_SANCTIONS_CACHE_PREFIX}{name.lower()}"

        # Verificar caché
        try:
            redis = get_redis()
            cached = await redis.get(cache_key)
            if cached:
                logger.debug("Resultado ONU desde caché: %s", name)
                return self._deserialize_matches(cached)
        except Exception as exc:
            logger.warning("Error accediendo caché Redis para ONU: %s", exc)

        # Obtener la lista de sanciones
        try:
            entities = await self._get_sanctions_list()
        except Exception as exc:
            logger.error("Error obteniendo lista de sanciones ONU: %s", exc)
            return []

        # Aplicar comparación difusa
        results = self._apply_fuzzy_matching(name, entities, threshold)

        # Cachear resultados
        try:
            redis = get_redis()
            await redis.setex(
                cache_key,
                _UN_SANCTIONS_CACHE_TTL,
                self._serialize_matches(results),
            )
        except Exception as exc:
            logger.warning("Error cacheando resultados ONU: %s", exc)

        return results

    # ── Obtener entidad por ID ──────────────────────────────────────────

    async def get_entity(self, entity_id: str) -> UnSanctionsEntity | None:
        """
        Obtiene una entidad específica por su identificador.

        Args:
            entity_id: Identificador único de la entidad.

        Returns:
            UnSanctionsEntity si se encuentra, None si no existe.
        """
        if not entity_id:
            return None

        cache_key = f"{_UN_SANCTIONS_ENTITY_CACHE_PREFIX}{entity_id}"

        # Verificar caché
        try:
            redis = get_redis()
            cached = await redis.get(cache_key)
            if cached:
                return self._deserialize_entity(cached)
        except Exception:
            pass

        # Buscar en la lista completa
        try:
            entities = await self._get_sanctions_list()
            for entity in entities:
                if entity.id == entity_id:
                    # Cachear la entidad
                    try:
                        redis = get_redis()
                        await redis.setex(
                            cache_key,
                            _UN_SANCTIONS_CACHE_TTL,
                            json.dumps(
                                self._entity_to_dict(entity), ensure_ascii=False
                            ),
                        )
                    except Exception:
                        pass
                    return entity
        except Exception as exc:
            logger.error("Error buscando entidad ONU %s: %s", entity_id, exc)

        return None

    # ── Métodos internos ────────────────────────────────────────────────

    async def _get_sanctions_list(self) -> list[UnSanctionsEntity]:
        """
        Obtiene la lista de sanciones desde caché o la descarga.

        Returns:
            Lista de entidades sancionadas.
        """
        cache_key = "un_sanctions:consolidated_list"

        try:
            redis = get_redis()
            cached = await redis.get(cache_key)
            if cached:
                logger.debug("Lista ONU obtenida desde caché Redis")
                return self._deserialize_entities(cached)
        except Exception as exc:
            logger.warning("Error leyendo caché de lista ONU: %s", exc)

        # Descargar la lista
        entities = await self._fetch_sanctions_from_api()

        if entities:
            try:
                redis = get_redis()
                await redis.setex(
                    cache_key,
                    _UN_SANCTIONS_CACHE_TTL,
                    json.dumps(
                        [self._entity_to_dict(e) for e in entities],
                        ensure_ascii=False,
                    ),
                )
                logger.info(
                    "Lista de sanciones ONU cacheada: %d entidades",
                    len(entities),
                )
            except Exception as exc:
                logger.warning("Error cacheando lista ONU: %s", exc)

        return entities

    async def _fetch_sanctions_from_api(self) -> list[UnSanctionsEntity]:
        """
        Descarga la lista consolidada de sanciones desde la API de la ONU.

        La ONU proporciona los datos en formato XML. Este método
        realiza la descarga y el parseo inicial.

        Returns:
            Lista de entidades sancionadas.
        """
        entities: list[UnSanctionsEntity] = []

        try:
            async with httpx.AsyncClient(timeout=_HTTP_TIMEOUT) as client:
                # La ONU expone la lista consolidada en XML
                # Utilizamos también el endpoint JSON si está disponible
                response = await client.get(
                    "https://scsanctions.un.org/services/json/",
                    headers={"Accept": "application/json"},
                )
                response.raise_for_status()

                data = response.json()

                # La estructura varía según el comité
                # Intentar extraer las entidades de la respuesta
                all_entities = data.get("consolidatedList", data.get("entities", []))

                if isinstance(all_entities, dict):
                    # Formato por comités
                    for committee_key, committee_entities in all_entities.items():
                        if isinstance(committee_entities, list):
                            for entry in committee_entities:
                                entity = self._parse_entity(entry, committee_key)
                                if entity:
                                    entities.append(entity)
                elif isinstance(all_entities, list):
                    for entry in all_entities:
                        entity = self._parse_entity(entry)
                        if entity:
                            entities.append(entity)

        except httpx.TimeoutException:
            logger.error("Timeout descargando lista de sanciones ONU")
        except httpx.HTTPStatusError as exc:
            logger.error(
                "Error HTTP descargando lista ONU: %d",
                exc.response.status_code,
            )
        except Exception as exc:
            logger.error("Error descargando lista de sanciones ONU: %s", exc)

        return entities

    def _parse_entity(
        self,
        data: dict[str, Any],
        committee: str = "",
    ) -> UnSanctionsEntity | None:
        """
        Parsea una entidad desde la respuesta de la API de la ONU.

        Args:
            data: Diccionario con los datos de la entidad.
            committee: Comité del CS asociado.

        Returns:
            UnSanctionsEntity parseada, o None si los datos son inválidos.
        """
        try:
            entity_id = str(
                data.get("REFERENCE_NUMBER", data.get("id", ""))
            )
            name = data.get("FIRST_NAME", "")
            second_name = data.get("SECOND_NAME", "")
            third_name = data.get("THIRD_NAME", "")
            fourth_name = data.get("FOURTH_NAME", "")

            # Construir nombre completo
            name_parts = [n for n in [name, second_name, third_name, fourth_name] if n]
            full_name = data.get("NAME_ORIGINAL_SCRIPT", " ".join(name_parts))

            if not full_name:
                full_name = data.get("name", "")

            if not entity_id and not full_name:
                return None

            # Extraer alias
            aliases: list[str] = []
            alias_list = data.get("ALIAS", [])
            if isinstance(alias_list, list):
                for alias in alias_list:
                    if isinstance(alias, dict):
                        alias_name = alias.get("ALIAS_NAME", alias.get("name", ""))
                    else:
                        alias_name = str(alias)
                    if alias_name:
                        aliases.append(alias_name)
            elif isinstance(alias_list, str) and alias_list:
                aliases.append(alias_list)

            # Números de pasaporte
            passport_numbers: list[str] = []
            passport_data = data.get("PASSPORT", [])
            if isinstance(passport_data, list):
                for pp in passport_data:
                    if isinstance(pp, dict):
                        num = pp.get("NUMBER", pp.get("number", ""))
                    else:
                        num = str(pp)
                    if num:
                        passport_numbers.append(num)

            # Nacionalidad
            nationality = ""
            nationality_data = data.get("NATIONALITY", [])
            if isinstance(nationality_data, list) and nationality_data:
                nat = nationality_data[0]
                if isinstance(nat, dict):
                    nationality = nat.get("COUNTRY", nat.get("name", ""))
                else:
                    nationality = str(nat)

            # Direcciones
            addresses: list[str] = []
            address_data = data.get("ADDRESS", [])
            if isinstance(address_data, list):
                for addr in address_data:
                    if isinstance(addr, dict):
                        parts = [
                            addr.get("ADDRESS1", ""),
                            addr.get("CITY", ""),
                            addr.get("COUNTRY", ""),
                        ]
                        full_addr = ", ".join(p for p in parts if p)
                        if full_addr:
                            addresses.append(full_addr)
                    elif isinstance(addr, str):
                        addresses.append(addr)

            # Tipo de entidad
            entity_type = data.get("ENTITY_TYPE", data.get("type", "individual"))

            return UnSanctionsEntity(
                id=entity_id,
                name=full_name,
                entity_type=entity_type,
                aliases=aliases,
                designation_date=data.get("LISTED_ON", data.get("designation_date", "")),
                committee=committee,
                nationality=nationality,
                passport_numbers=passport_numbers,
                national_id_numbers=data.get("NATIONAL_ID", []),
                addresses=addresses,
                listed_on=data.get("LISTED_ON", ""),
                other_information=data.get("OTHER_INFORMATION", ""),
            )

        except Exception as exc:
            logger.warning("Error parseando entidad ONU: %s", exc)
            return None

    def _apply_fuzzy_matching(
        self,
        query_name: str,
        entities: list[UnSanctionsEntity],
        threshold: float,
    ) -> list[UnSanctionsMatch]:
        """
        Aplica comparación difusa a las entidades de la ONU.

        Args:
            query_name: Nombre a buscar.
            entities: Lista de entidades sancionadas.
            threshold: Umbral mínimo de similitud.

        Returns:
            Lista de coincidencias significativas.
        """
        matches: list[UnSanctionsMatch] = []

        # Construir listas de nombres y alias para comparación por lotes
        for entity in entities:
            if not entity.name:
                continue

            # Comparación con nombre principal
            name_results = self._matcher.match(
                query_name, [entity.name], threshold=0.6
            )

            best_score = 0.0
            best_match_type = "fuzzy"

            if name_results:
                best = max(name_results, key=lambda r: r.score)
                best_score = best.score
                best_match_type = best.match_type.value

            # Comparación con alias
            if entity.aliases:
                alias_results = self._matcher.match_with_aliases(
                    query_name, entity.aliases, threshold=0.6
                )
                if alias_results:
                    best_alias = max(alias_results, key=lambda r: r.score)
                    if best_alias.score > best_score:
                        best_score = best_alias.score
                        best_match_type = "alias"

            if best_score >= threshold:
                matches.append(
                    UnSanctionsMatch(
                        entity=entity,
                        match_score=round(best_score, 4),
                        match_type=best_match_type,
                    )
                )

        return sorted(matches, key=lambda m: m.match_score, reverse=True)

    # ── Serialización ───────────────────────────────────────────────────

    def _entity_to_dict(self, entity: UnSanctionsEntity) -> dict[str, Any]:
        """Convierte una UnSanctionsEntity a diccionario."""
        return {
            "id": entity.id,
            "name": entity.name,
            "entity_type": entity.entity_type,
            "aliases": entity.aliases,
            "designation_date": entity.designation_date,
            "committee": entity.committee,
            "nationality": entity.nationality,
            "passport_numbers": entity.passport_numbers,
            "national_id_numbers": entity.national_id_numbers,
            "addresses": entity.addresses,
            "listed_on": entity.listed_on,
            "other_information": entity.other_information,
        }

    def _deserialize_entity(self, cached: str) -> UnSanctionsEntity:
        """Deserializa una UnSanctionsEntity desde JSON."""
        data = json.loads(cached)
        return UnSanctionsEntity(
            id=data.get("id", ""),
            name=data.get("name", ""),
            entity_type=data.get("entity_type", "individual"),
            aliases=data.get("aliases", []),
            designation_date=data.get("designation_date", ""),
            committee=data.get("committee", ""),
            nationality=data.get("nationality", ""),
            passport_numbers=data.get("passport_numbers", []),
            national_id_numbers=data.get("national_id_numbers", []),
            addresses=data.get("addresses", []),
            listed_on=data.get("listed_on", ""),
            other_information=data.get("other_information", ""),
        )

    def _deserialize_entities(self, cached: str) -> list[UnSanctionsEntity]:
        """Deserializa una lista de UnSanctionsEntity desde JSON."""
        data = json.loads(cached)
        return [self._deserialize_entity(json.dumps(e, ensure_ascii=False)) for e in data]

    def _serialize_matches(self, matches: list[UnSanctionsMatch]) -> str:
        """Serializa una lista de UnSanctionsMatch a JSON."""
        data = [
            {
                "entity": self._entity_to_dict(m.entity),
                "match_score": m.match_score,
                "match_type": m.match_type,
            }
            for m in matches
        ]
        return json.dumps(data, ensure_ascii=False)

    def _deserialize_matches(self, cached: str) -> list[UnSanctionsMatch]:
        """Deserializa una lista de UnSanctionsMatch desde JSON."""
        data = json.loads(cached)
        return [
            UnSanctionsMatch(
                entity=UnSanctionsEntity(
                    id=m["entity"].get("id", ""),
                    name=m["entity"].get("name", ""),
                    entity_type=m["entity"].get("entity_type", "individual"),
                    aliases=m["entity"].get("aliases", []),
                    designation_date=m["entity"].get("designation_date", ""),
                    committee=m["entity"].get("committee", ""),
                    nationality=m["entity"].get("nationality", ""),
                    passport_numbers=m["entity"].get("passport_numbers", []),
                    national_id_numbers=m["entity"].get("national_id_numbers", []),
                    addresses=m["entity"].get("addresses", []),
                    listed_on=m["entity"].get("listed_on", ""),
                    other_information=m["entity"].get("other_information", ""),
                ),
                match_score=m["match_score"],
                match_type=m["match_type"],
            )
            for m in data
        ]
