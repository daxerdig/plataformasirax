"""
Cliente de integración con OpenSanctions API.

OpenSanctions proporciona acceso consolidado a múltiples listas de
sanciones, PEP (Politically Exposed Persons) y datasets de crimen
organizado a nivel mundial.

Incluye:
- Búsqueda por nombre con filtrado por país
- Obtención de entidades individuales por ID
- Mapeo de esquemas, datasets y propiedades
- Manejo graceful de errores de API

OpenSanctions aggregate datasets from OFAC, EU, UN, UK HMT, and many
other sanctions and PEP sources worldwide.
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
_OPENSANCTIONS_CACHE_PREFIX = "opensanctions:search:"
_OPENSANCTIONS_ENTITY_CACHE_PREFIX = "opensanctions:entity:"
_OPENSANCTIONS_CACHE_TTL = 3600  # 1 hora
_HTTP_TIMEOUT = 30.0


# ---------------------------------------------------------------------------
# Modelos de datos
# ---------------------------------------------------------------------------
@dataclass(frozen=True, slots=True)
class SanctionsEntity:
    """
    Entidad de OpenSanctions con sus propiedades completas.

    Attributes:
        id: Identificador único de la entidad en OpenSanctions.
        schema: Tipo de esquema (Person, Company, Organization, etc.).
        name: Nombre principal de la entidad.
        aliases: Nombres alternativos conocidos.
        datasets: Lista de datasets/fuentes donde aparece la entidad.
        properties: Propiedades adicionales (fechas, nacionalidades, etc.).
        countries: Países asociados a la entidad.
    """

    id: str
    schema: str
    name: str
    aliases: list[str] = field(default_factory=list)
    datasets: list[str] = field(default_factory=list)
    properties: dict[str, Any] = field(default_factory=dict)
    countries: list[str] = field(default_factory=list)


@dataclass(frozen=True, slots=True)
class SanctionsMatch:
    """
    Resultado de una búsqueda en OpenSanctions.

    Attributes:
        entity: Entidad que coincidió.
        score: Puntuación de similitud del match.
        match_type: Tipo de coincidencia (exact/fuzzy/phonetic/alias).
        confidence: Nivel de confianza de la coincidencia.
        datasets: Datasets donde aparece la entidad.
        properties: Propiedades relevantes de la entidad.
    """

    entity: SanctionsEntity
    score: float
    match_type: str
    confidence: float
    datasets: list[str] = field(default_factory=list)
    properties: dict[str, Any] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Cliente OpenSanctions
# ---------------------------------------------------------------------------
class OpenSanctionsClient:
    """
    Cliente asíncrono para la API de OpenSanctions.

    OpenSanctions proporciona acceso consolidado a múltiples fuentes
    de datos de sanciones, PEP y crimen organizado, incluyendo
    OFAC, UE, ONU, UK HMT y muchas otras.

    Example:
        >>> client = OpenSanctionsClient()
        >>> matches = await client.search("Juan Pérez", country="mx")
        >>> for m in matches:
        ...     print(f"{m.entity.name} - {m.score} - {m.datasets}")
    """

    def __init__(self, *, matcher: FuzzyMatcherService | None = None) -> None:
        """
        Inicializa el cliente de OpenSanctions.

        Args:
            matcher: Servicio de comparación difusa. Si no se
                proporciona, se crea uno por defecto.
        """
        self._settings = get_settings()
        self._matcher = matcher or FuzzyMatcherService()
        self._base_url = self._settings.OPENSANCTIONS_API_URL
        self._api_key = self._settings.OPENSANCTIONS_API_KEY

    # ── Búsqueda principal ──────────────────────────────────────────────

    async def search(
        self,
        name: str,
        country: str = "mx",
        threshold: float = 0.80,
        datasets: list[str] | None = None,
    ) -> list[SanctionsMatch]:
        """
        Busca un nombre en OpenSanctions con comparación difusa.

        Realiza la búsqueda contra la API de OpenSanctions y aplica
        comparación difusa adicional para mejorar la cobertura.

        Args:
            name: Nombre a buscar.
            country: Código ISO del país para filtrar resultados.
                Por defecto "mx" (México).
            threshold: Umbral mínimo de similitud.
            datasets: Lista de datasets específicos a consultar.
                None para buscar en todos.

        Returns:
            Lista de SanctionsMatch ordenada por score descendente.
        """
        if not name:
            return []

        cache_key = (
            f"{_OPENSANCTIONS_CACHE_PREFIX}"
            f"{name.lower()}:{country}:{datasets or 'all'}"
        )

        # Verificar caché
        try:
            redis = get_redis()
            cached = await redis.get(cache_key)
            if cached:
                logger.debug("Resultado OpenSanctions desde caché: %s", name)
                return self._deserialize_matches(cached)
        except Exception as exc:
            logger.warning("Error accediendo caché Redis para OpenSanctions: %s", exc)

        # Consultar la API
        try:
            api_results = await self._search_api(name, country, datasets)
        except Exception as exc:
            logger.error("Error consultando API de OpenSanctions: %s", exc)
            return []

        # Aplicar comparación difusa para refinar resultados
        results = self._refine_results(name, api_results, threshold)

        # Cachear resultados
        try:
            redis = get_redis()
            await redis.setex(
                cache_key,
                _OPENSANCTIONS_CACHE_TTL,
                self._serialize_matches(results),
            )
        except Exception as exc:
            logger.warning("Error cacheando resultados OpenSanctions: %s", exc)

        return results

    # ── Obtener entidad por ID ──────────────────────────────────────────

    async def get_entity(self, entity_id: str) -> SanctionsEntity | None:
        """
        Obtiene una entidad específica por su identificador.

        Args:
            entity_id: Identificador único de la entidad en OpenSanctions.

        Returns:
            SanctionsEntity si se encuentra, None si no existe.
        """
        if not entity_id:
            return None

        cache_key = f"{_OPENSANCTIONS_ENTITY_CACHE_PREFIX}{entity_id}"

        # Verificar caché
        try:
            redis = get_redis()
            cached = await redis.get(cache_key)
            if cached:
                return self._deserialize_entity(cached)
        except Exception:
            pass

        # Consultar API
        try:
            headers = self._build_headers()
            async with httpx.AsyncClient(timeout=_HTTP_TIMEOUT) as client:
                response = await client.get(
                    f"{self._base_url}/entities/{entity_id}",
                    headers=headers,
                )
                response.raise_for_status()

                data = response.json()
                entity = self._parse_entity(data.get("data", data))

                # Cachear
                try:
                    redis = get_redis()
                    await redis.setex(
                        cache_key,
                        _OPENSANCTIONS_CACHE_TTL,
                        json.dumps(self._entity_to_dict(entity), ensure_ascii=False),
                    )
                except Exception:
                    pass

                return entity

        except httpx.TimeoutException:
            logger.error("Timeout obteniendo entidad %s de OpenSanctions", entity_id)
        except httpx.HTTPStatusError as exc:
            logger.error(
                "Error HTTP obteniendo entidad %s: %d",
                entity_id,
                exc.response.status_code,
            )
        except Exception as exc:
            logger.error("Error obteniendo entidad %s: %s", entity_id, exc)

        return None

    # ── Métodos internos ────────────────────────────────────────────────

    async def _search_api(
        self,
        name: str,
        country: str,
        datasets: list[str] | None = None,
    ) -> list[dict[str, Any]]:
        """
        Realiza la búsqueda contra la API de OpenSanctions.

        Args:
            name: Nombre a buscar.
            country: Código ISO del país.
            datasets: Datasets específicos a consultar.

        Returns:
            Lista de resultados crudos de la API.
        """
        headers = self._build_headers()

        params: dict[str, Any] = {
            "q": name,
            "limit": 50,
        }

        if country:
            params["countries"] = country

        if datasets:
            params["datasets"] = ",".join(datasets)

        async with httpx.AsyncClient(timeout=_HTTP_TIMEOUT) as client:
            response = await client.get(
                f"{self._base_url}/search",
                params=params,
                headers=headers,
            )
            response.raise_for_status()

            data = response.json()
            return data.get("results", data.get("responses", []))

    def _refine_results(
        self,
        query_name: str,
        api_results: list[dict[str, Any]],
        threshold: float,
    ) -> list[SanctionsMatch]:
        """
        Refina los resultados de la API con comparación difusa local.

        Args:
            query_name: Nombre original de la búsqueda.
            api_results: Resultados crudos de la API.
            threshold: Umbral mínimo de similitud.

        Returns:
            Lista de SanctionsMatch refinada.
        """
        matches: list[SanctionsMatch] = []

        for result in api_results:
            entity = self._parse_entity(result)
            if not entity or not entity.name:
                continue

            # Comparación difusa con el nombre principal
            name_results = self._matcher.match(
                query_name, [entity.name], threshold=0.6  # Umbral más bajo para la API
            )

            # Comparación con alias
            alias_results = self._matcher.match_with_aliases(
                query_name, entity.aliases, threshold=0.6
            )

            # Determinar el mejor score
            best_score = 0.0
            best_match_type = "fuzzy"
            best_confidence = 0.0

            if name_results:
                best_name = max(name_results, key=lambda r: r.score)
                if best_name.score > best_score:
                    best_score = best_name.score
                    best_match_type = best_name.match_type.value
                    best_confidence = best_name.confidence

            if alias_results:
                best_alias = max(alias_results, key=lambda r: r.score)
                if best_alias.score > best_score:
                    best_score = best_alias.score
                    best_match_type = "alias"
                    best_confidence = best_alias.confidence

            # Si la API ya incluyó un score, considerar el máximo
            api_score = result.get("score", 0.0)
            if isinstance(api_score, (int, float)):
                api_score = float(api_score)
                if api_score > best_score:
                    best_score = api_score
                    best_confidence = api_score * 0.90

            if best_score >= threshold:
                matches.append(
                    SanctionsMatch(
                        entity=entity,
                        score=round(best_score, 4),
                        match_type=best_match_type,
                        confidence=round(best_confidence, 4),
                        datasets=entity.datasets,
                        properties=entity.properties,
                    )
                )

        return sorted(matches, key=lambda m: m.score, reverse=True)

    def _parse_entity(self, data: dict[str, Any]) -> SanctionsEntity:
        """
        Parsea una entidad desde la respuesta de la API.

        Args:
            data: Diccionario con los datos de la entidad.

        Returns:
            SanctionsEntity parseada.
        """
        entity_id = data.get("id", data.get("entity_id", ""))
        schema_type = data.get("schema", data.get("type", "Person"))
        name = data.get("caption", data.get("name", ""))

        # Extraer alias
        aliases: list[str] = []
        for prop in data.get("properties", {}).get("alias", []):
            if isinstance(prop, dict):
                alias_name = prop.get("string", prop.get("name", ""))
            else:
                alias_name = str(prop)
            if alias_name:
                aliases.append(alias_name)

        # Extraer datasets
        dataset_list = data.get("datasets", data.get("dataset", []))
        if isinstance(dataset_list, str):
            dataset_list = [dataset_list]

        # Extraer países
        countries: list[str] = []
        for country in data.get("properties", {}).get("country", []):
            if isinstance(country, dict):
                code = country.get("code", country.get("name", ""))
            else:
                code = str(country)
            if code:
                countries.append(code)

        # Propiedades adicionales
        properties = data.get("properties", {})

        return SanctionsEntity(
            id=entity_id,
            schema=schema_type,
            name=name,
            aliases=aliases,
            datasets=dataset_list,
            properties=properties,
            countries=countries,
        )

    def _build_headers(self) -> dict[str, str]:
        """Construye los headers HTTP para las peticiones a la API."""
        headers: dict[str, str] = {
            "Accept": "application/json",
            "Content-Type": "application/json",
        }
        if self._api_key:
            headers["Authorization"] = f"ApiKey {self._api_key}"
        return headers

    # ── Serialización ───────────────────────────────────────────────────

    def _entity_to_dict(self, entity: SanctionsEntity) -> dict[str, Any]:
        """Convierte una SanctionsEntity a diccionario."""
        return {
            "id": entity.id,
            "schema": entity.schema,
            "name": entity.name,
            "aliases": entity.aliases,
            "datasets": entity.datasets,
            "properties": entity.properties,
            "countries": entity.countries,
        }

    def _deserialize_entity(self, cached: str) -> SanctionsEntity:
        """Deserializa una SanctionsEntity desde JSON."""
        data = json.loads(cached)
        return self._parse_entity(data)

    def _serialize_matches(self, matches: list[SanctionsMatch]) -> str:
        """Serializa una lista de SanctionsMatch a JSON."""
        data = [
            {
                "entity": self._entity_to_dict(m.entity),
                "score": m.score,
                "match_type": m.match_type,
                "confidence": m.confidence,
                "datasets": m.datasets,
                "properties": m.properties,
            }
            for m in matches
        ]
        return json.dumps(data, ensure_ascii=False)

    def _deserialize_matches(self, cached: str) -> list[SanctionsMatch]:
        """Deserializa una lista de SanctionsMatch desde JSON."""
        data = json.loads(cached)
        return [
            SanctionsMatch(
                entity=self._parse_entity(m["entity"]),
                score=m["score"],
                match_type=m["match_type"],
                confidence=m["confidence"],
                datasets=m.get("datasets", []),
                properties=m.get("properties", {}),
            )
            for m in data
        ]
