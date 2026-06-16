"""
Cliente de integración con Interpol Red Notices API.

Gestiona la consulta de avisos rojos (Red Notices) y avisos difusos
(Diffusion Notices) publicados por la Organización Internacional de
Policía Criminal (INTERPOL).

Incluye:
- Búsqueda por nombre con filtrado por nacionalidad
- Obtención de avisos individuales por ID
- Parseo de datos de cargos y países requirentes
- Caché de resultados en Redis
- Manejo graceful de errores y rate limiting de Interpol

Note:
    La API pública de Interpol tiene límites de tasa estrictos.
    Los resultados se cachean agresivamente para minimizar peticiones.
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
_INTERPOL_CACHE_PREFIX = "interpol:search:"
_INTERPOL_NOTICE_CACHE_PREFIX = "interpol:notice:"
_INTERPOL_CACHE_TTL = 7200  # 2 horas (más largo por rate limiting estricto)
_HTTP_TIMEOUT = 20.0
_MAX_RESULTS = 50


# ---------------------------------------------------------------------------
# Modelos de datos
# ---------------------------------------------------------------------------
@dataclass(frozen=True, slots=True)
class InterpolNotice:
    """
    Aviso individual de Interpol (Red Notice / Yellow Notice).

    Attributes:
        notice_id: Identificador único del aviso (ej. 2023/12345).
        name: Nombre de la persona buscada.
        nationalities: Lista de nacionalidades de la persona.
        charges: Cargos o delitos imputados.
        arresting_country: País requirente (solicitante de la captura).
        notice_type: Tipo de aviso (red, yellow, diffusion).
        date_of_birth: Fecha de nacimiento si está disponible.
        sex: Sexo de la persona (M/F).
        thumbnail_url: URL de la fotografía si está disponible.
    """

    notice_id: str
    name: str
    nationalities: list[str] = field(default_factory=list)
    charges: list[str] = field(default_factory=list)
    arresting_country: str = ""
    notice_type: str = "red"
    date_of_birth: str = ""
    sex: str = ""
    thumbnail_url: str = ""


@dataclass(frozen=True, slots=True)
class InterpolMatch:
    """
    Resultado de una búsqueda en avisos de Interpol.

    Attributes:
        notice: Aviso de Interpol que coincidió.
        match_score: Puntuación de similitud (0.0 a 1.0).
        match_type: Tipo de coincidencia detectada.
    """

    notice: InterpolNotice
    match_score: float
    match_type: str


# ---------------------------------------------------------------------------
# Cliente Interpol
# ---------------------------------------------------------------------------
class InterpolClient:
    """
    Cliente asíncrono para la API pública de Interpol.

    Consulta avisos rojos (Red Notices) y otros tipos de avisos
    publicados por Interpol. La API pública tiene rate limiting
    estricto, por lo que los resultados se cachean agresivamente.

    Example:
        >>> client = InterpolClient()
        >>> matches = await client.search("Juan Pérez", nationality="MX")
        >>> for m in matches:
        ...     print(f"{m.notice.name} - {m.notice.charges}")
    """

    def __init__(self, *, matcher: FuzzyMatcherService | None = None) -> None:
        """
        Inicializa el cliente de Interpol.

        Args:
            matcher: Servicio de comparación difusa. Si no se
                proporciona, se crea uno por defecto.
        """
        self._settings = get_settings()
        self._matcher = matcher or FuzzyMatcherService()
        self._base_url = self._settings.INTERPOL_API_URL
        self._api_key = self._settings.INTERPOL_API_KEY

    # ── Búsqueda principal ──────────────────────────────────────────────

    async def search(
        self,
        name: str,
        nationality: str | None = None,
        threshold: float = 0.80,
    ) -> list[InterpolMatch]:
        """
        Busca un nombre en los avisos de Interpol.

        Realiza la búsqueda en la API pública de Interpol y aplica
        comparación difusa para refinar los resultados.

        Args:
            name: Nombre de la persona a buscar.
            nationality: Código ISO de nacionalidad para filtrar.
                None para buscar en todas las nacionalidades.
            threshold: Umbral mínimo de similitud.

        Returns:
            Lista de InterpolMatch ordenada por score descendente.
        """
        if not name:
            return []

        cache_key = (
            f"{_INTERPOL_CACHE_PREFIX}"
            f"{name.lower()}:{nationality or 'all'}"
        )

        # Verificar caché
        try:
            redis = get_redis()
            cached = await redis.get(cache_key)
            if cached:
                logger.debug("Resultado Interpol desde caché: %s", name)
                return self._deserialize_matches(cached)
        except Exception as exc:
            logger.warning("Error accediendo caché Redis para Interpol: %s", exc)

        # Consultar la API de Interpol
        try:
            api_notices = await self._search_api(name, nationality)
        except Exception as exc:
            logger.error("Error consultando API de Interpol: %s", exc)
            return []

        # Aplicar comparación difusa
        results = self._apply_fuzzy_matching(name, api_notices, threshold)

        # Cachear resultados
        try:
            redis = get_redis()
            await redis.setex(
                cache_key,
                _INTERPOL_CACHE_TTL,
                self._serialize_matches(results),
            )
        except Exception as exc:
            logger.warning("Error cacheando resultados Interpol: %s", exc)

        return results

    # ── Obtener aviso por ID ────────────────────────────────────────────

    async def get_notice(self, notice_id: str) -> InterpolNotice | None:
        """
        Obtiene un aviso específico por su identificador.

        Args:
            notice_id: Identificador único del aviso.

        Returns:
            InterpolNotice si se encuentra, None si no existe.
        """
        if not notice_id:
            return None

        cache_key = f"{_INTERPOL_NOTICE_CACHE_PREFIX}{notice_id}"

        # Verificar caché
        try:
            redis = get_redis()
            cached = await redis.get(cache_key)
            if cached:
                return self._deserialize_notice(cached)
        except Exception:
            pass

        # Consultar API
        try:
            headers = self._build_headers()
            async with httpx.AsyncClient(timeout=_HTTP_TIMEOUT) as client:
                response = await client.get(
                    f"{self._base_url}/red/{notice_id}",
                    headers=headers,
                )
                response.raise_for_status()

                data = response.json()
                notice_data = data.get("_embedded", {}).get("notice", data)
                notice = self._parse_notice(notice_data)

                # Cachear
                try:
                    redis = get_redis()
                    await redis.setex(
                        cache_key,
                        _INTERPOL_CACHE_TTL,
                        json.dumps(
                            self._notice_to_dict(notice), ensure_ascii=False
                        ),
                    )
                except Exception:
                    pass

                return notice

        except httpx.TimeoutException:
            logger.error("Timeout obteniendo aviso %s de Interpol", notice_id)
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code == 404:
                logger.debug("Aviso %s no encontrado en Interpol", notice_id)
            else:
                logger.error(
                    "Error HTTP obteniendo aviso %s: %d",
                    notice_id,
                    exc.response.status_code,
                )
        except Exception as exc:
            logger.error("Error obteniendo aviso %s: %s", notice_id, exc)

        return None

    # ── Métodos internos ────────────────────────────────────────────────

    async def _search_api(
        self,
        name: str,
        nationality: str | None = None,
    ) -> list[InterpolNotice]:
        """
        Realiza la búsqueda contra la API pública de Interpol.

        Args:
            name: Nombre a buscar.
            nationality: Nacionalidad para filtrar.

        Returns:
            Lista de avisos parseados.
        """
        notices: list[InterpolNotice] = []

        # Dividir el nombre para búsqueda por nombre y apellido
        name_parts = name.strip().split()
        forename = name_parts[0] if name_parts else ""
        surname = " ".join(name_parts[1:]) if len(name_parts) > 1 else name_parts[0]

        params: dict[str, Any] = {
            "forename": forename,
            "name": surname,
            "resultPerPage": _MAX_RESULTS,
        }

        if nationality:
            params["nationality"] = nationality.upper()

        headers = self._build_headers()

        try:
            async with httpx.AsyncClient(timeout=_HTTP_TIMEOUT) as client:
                # Buscar en Red Notices
                response = await client.get(
                    f"{self._base_url}/red",
                    params=params,
                    headers=headers,
                )
                response.raise_for_status()

                data = response.json()
                notice_list = data.get("_embedded", {}).get("notices", [])

                for notice_data in notice_list:
                    notice = self._parse_notice(notice_data)
                    if notice and notice.name:
                        notices.append(notice)

                # También buscar si hay más páginas
                total = data.get("total", 0)
                if total > _MAX_RESULTS:
                    logger.info(
                        "Interpol: %d resultados totales, mostrando primeros %d",
                        total,
                        _MAX_RESULTS,
                    )

        except httpx.TimeoutException:
            logger.error("Timeout buscando en API de Interpol: %s", name)
        except httpx.HTTPStatusError as exc:
            logger.error(
                "Error HTTP en búsqueda Interpol: %d - %s",
                exc.response.status_code,
                str(exc.response.text)[:200],
            )
        except Exception as exc:
            logger.error("Error buscando en Interpol: %s", exc)

        return notices

    def _parse_notice(self, data: dict[str, Any]) -> InterpolNotice | None:
        """
        Parsea un aviso individual desde la respuesta de la API.

        Args:
            data: Diccionario con los datos del aviso.

        Returns:
            InterpolNotice parseado, o None si los datos son inválidos.
        """
        try:
            notice_id = data.get("entity_id", data.get("id", ""))

            # Construir nombre completo
            forename = data.get("forename", "")
            name = data.get("name", "")
            full_name = f"{forename} {name}".strip() if forename else name

            if not full_name:
                return None

            # Nacionalidades
            nationalities_raw = data.get("nationalities", "")
            if isinstance(nationalities_raw, str):
                nationalities = [
                    n.strip()
                    for n in nationalities_raw.split("/")
                    if n.strip()
                ]
            elif isinstance(nationalities_raw, list):
                nationalities = nationalities_raw
            else:
                nationalities = []

            # Cargos
            charges_raw = data.get("arrest_warrants", [])
            charges: list[str] = []
            if isinstance(charges_raw, list):
                for warrant in charges_raw:
                    if isinstance(warrant, dict):
                        charge = warrant.get("charge", "")
                        if charge:
                            charges.append(charge)
                    elif isinstance(warrant, str):
                        charges.append(warrant)

            # País requirente
            arresting_country = ""
            if charges_raw and isinstance(charges_raw, list):
                for warrant in charges_raw:
                    if isinstance(warrant, dict):
                        country = warrant.get("issuing_country", "")
                        if country:
                            arresting_country = country
                            break

            # Tipo de aviso
            notice_type = data.get("_links", {}).get("self", {}).get("href", "")
            if "red" in notice_type:
                notice_type = "red"
            elif "yellow" in notice_type:
                notice_type = "yellow"
            else:
                notice_type = data.get("notice_type", "red")

            # Thumbnail
            thumbnail_url = data.get("thumbnail_url", "")
            if not thumbnail_url:
                images = data.get("_embedded", {}).get("images", [])
                if images and isinstance(images, list):
                    thumbnail_url = images[0].get("_links", {}).get(
                        "self", {}
                    ).get("href", "")

            return InterpolNotice(
                notice_id=notice_id,
                name=full_name,
                nationalities=nationalities,
                charges=charges,
                arresting_country=arresting_country,
                notice_type=notice_type,
                date_of_birth=data.get("date_of_birth", ""),
                sex=data.get("sex", ""),
                thumbnail_url=thumbnail_url,
            )

        except Exception as exc:
            logger.warning("Error parseando aviso de Interpol: %s", exc)
            return None

    def _apply_fuzzy_matching(
        self,
        query_name: str,
        notices: list[InterpolNotice],
        threshold: float,
    ) -> list[InterpolMatch]:
        """
        Aplica comparación difusa a los resultados de la API de Interpol.

        Args:
            query_name: Nombre original de la búsqueda.
            notices: Lista de avisos de Interpol.
            threshold: Umbral mínimo de similitud.

        Returns:
            Lista de InterpolMatch con coincidencias significativas.
        """
        matches: list[InterpolMatch] = []

        for notice in notices:
            # Comparación difusa con el nombre del aviso
            name_results = self._matcher.match(
                query_name, [notice.name], threshold=0.6
            )

            best_score = 0.0
            best_match_type = "fuzzy"

            if name_results:
                best = max(name_results, key=lambda r: r.score)
                best_score = best.score
                best_match_type = best.match_type.value

            if best_score >= threshold:
                matches.append(
                    InterpolMatch(
                        notice=notice,
                        match_score=round(best_score, 4),
                        match_type=best_match_type,
                    )
                )

        return sorted(matches, key=lambda m: m.match_score, reverse=True)

    def _build_headers(self) -> dict[str, str]:
        """Construye los headers HTTP para las peticiones a la API."""
        headers: dict[str, str] = {
            "Accept": "application/json",
        }
        if self._api_key:
            headers["Authorization"] = f"Bearer {self._api_key}"
        return headers

    # ── Serialización ───────────────────────────────────────────────────

    def _notice_to_dict(self, notice: InterpolNotice) -> dict[str, Any]:
        """Convierte un InterpolNotice a diccionario."""
        return {
            "notice_id": notice.notice_id,
            "name": notice.name,
            "nationalities": notice.nationalities,
            "charges": notice.charges,
            "arresting_country": notice.arresting_country,
            "notice_type": notice.notice_type,
            "date_of_birth": notice.date_of_birth,
            "sex": notice.sex,
            "thumbnail_url": notice.thumbnail_url,
        }

    def _deserialize_notice(self, cached: str) -> InterpolNotice:
        """Deserializa un InterpolNotice desde JSON."""
        data = json.loads(cached)
        return InterpolNotice(
            notice_id=data.get("notice_id", ""),
            name=data.get("name", ""),
            nationalities=data.get("nationalities", []),
            charges=data.get("charges", []),
            arresting_country=data.get("arresting_country", ""),
            notice_type=data.get("notice_type", "red"),
            date_of_birth=data.get("date_of_birth", ""),
            sex=data.get("sex", ""),
            thumbnail_url=data.get("thumbnail_url", ""),
        )

    def _serialize_matches(self, matches: list[InterpolMatch]) -> str:
        """Serializa una lista de InterpolMatch a JSON."""
        data = [
            {
                "notice": self._notice_to_dict(m.notice),
                "match_score": m.match_score,
                "match_type": m.match_type,
            }
            for m in matches
        ]
        return json.dumps(data, ensure_ascii=False)

    def _deserialize_matches(self, cached: str) -> list[InterpolMatch]:
        """Deserializa una lista de InterpolMatch desde JSON."""
        data = json.loads(cached)
        return [
            InterpolMatch(
                notice=InterpolNotice(
                    notice_id=m["notice"].get("notice_id", ""),
                    name=m["notice"].get("name", ""),
                    nationalities=m["notice"].get("nationalities", []),
                    charges=m["notice"].get("charges", []),
                    arresting_country=m["notice"].get("arresting_country", ""),
                    notice_type=m["notice"].get("notice_type", "red"),
                    date_of_birth=m["notice"].get("date_of_birth", ""),
                    sex=m["notice"].get("sex", ""),
                    thumbnail_url=m["notice"].get("thumbnail_url", ""),
                ),
                match_score=m["match_score"],
                match_type=m["match_type"],
            )
            for m in data
        ]
