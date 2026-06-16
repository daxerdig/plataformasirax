"""
Orquestador principal de screening en listas restrictivas.

Coordina la consulta simultánea a todas las fuentes de datos de
compliance: OFAC, ONU, OpenSanctions, Interpol, PEP, SAT 69-B,
Diario Oficial de la Federación (DOF) y Suprema Corte de Justicia
de la Nación (SCJN).

Características principales:
- Ejecución paralela de todas las fuentes mediante asyncio.gather
- Aplicación de comparación difusa/fonética a cada resultado
- Agregación y deduplicación de coincidencias
- Clasificación automática del nivel de riesgo
- Manejo graceful de fallos en fuentes individuales
- Soporte para personas físicas y morales

Los mensajes dirigidos al usuario están en español conforme a los
estándares de la plataforma SynkData.
"""

from __future__ import annotations

import asyncio
import json
import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Optional

from app.config import get_settings
from app.database import get_redis
from app.integrations.interpol import InterpolClient, InterpolMatch
from app.integrations.ofac import OfacClient, OfacMatch
from app.integrations.open_sanctions import OpenSanctionsClient, SanctionsMatch
from app.integrations.un_sanctions import UnSanctionsClient, UnSanctionsMatch
from app.services.fuzzy_matcher import FuzzyMatcherService, MatchType

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Enumeraciones
# ---------------------------------------------------------------------------
class RiskLevel(str, Enum):
    """Nivel de riesgo resultante del screening."""

    NONE = "none"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class EntityType(str, Enum):
    """Tipo de entidad a screening."""

    PERSON = "person"
    ENTITY = "entity"


# ---------------------------------------------------------------------------
# Modelos de resultado
# ---------------------------------------------------------------------------
@dataclass(frozen=True, slots=True)
class MatchDetail:
    """
    Detalle de una coincidencia individual de screening.

    Attributes:
        source: Fuente donde se encontró la coincidencia.
        score: Puntuación de similitud (0.0 a 1.0).
        match_type: Tipo de coincidencia (exact/fuzzy/phonetic/alias).
        entity_name: Nombre de la entidad coincidente.
        entity_data: Datos adicionales de la entidad.
        is_confirmed: Si la coincidencia fue confirmada manualmente.
    """

    source: str
    score: float
    match_type: str
    entity_name: str
    entity_data: dict[str, Any] = field(default_factory=dict)
    is_confirmed: bool = False


@dataclass
class ScreeningResult:
    """
    Resultado completo del screening en listas restrictivas.

    Attributes:
        matches: Lista de coincidencias encontradas.
        total_hits: Número total de coincidencias.
        max_score: Puntuación máxima de todas las coincidencias.
        risk_level: Nivel de riesgo calculado.
        sources_checked: Lista de fuentes consultadas.
        sources_failed: Lista de fuentes que fallaron.
        timestamp: Fecha y hora del screening.
        request_id: Identificador único de la solicitud.
    """

    matches: list[MatchDetail] = field(default_factory=list)
    total_hits: int = 0
    max_score: float = 0.0
    risk_level: RiskLevel = RiskLevel.NONE
    sources_checked: list[str] = field(default_factory=list)
    sources_failed: list[str] = field(default_factory=list)
    timestamp: str = ""
    request_id: str = ""

    def __post_init__(self) -> None:
        if not self.timestamp:
            self.timestamp = datetime.now(timezone.utc).isoformat()
        if not self.request_id:
            self.request_id = str(uuid.uuid4())


@dataclass
class Sat69bResult:
    """
    Resultado de la verificación en la lista SAT 69-B.

    El artículo 69-B del CFF establece la presunción de operaciones
    simuladas para contribuyentes que emiten comprobantes fiscales
    sin contar con los activos, personal o infraestructura necesarios.

    Attributes:
        is_listed: Si el RFC/nombre aparece en la lista 69-B.
        rfc: RFC verificado.
        company_name: Nombre de la empresa/contr ibuyente.
        status: Estado en la lista (presunto/desvirtuado/definitivo).
        publication_date: Fecha de publicación en el DOF.
        docket_number: Número de oficio.
        observations: Observaciones adicionales.
    """

    is_listed: bool = False
    rfc: str = ""
    company_name: str = ""
    status: str = ""
    publication_date: str = ""
    docket_number: str = ""
    observations: str = ""


@dataclass
class PepResult:
    """
    Resultado de la verificación de Personas Políticamente Expuestas (PEP).

    Attributes:
        is_pep: Si la persona está identificada como PEP.
        positions: Lista de cargos políticos desempeñados.
        country: País donde ejerce/ejerció el cargo.
        level: Nivel del cargo (national/state/municipal).
        source: Fuente de la información PEP.
    """

    is_pep: bool = False
    positions: list[str] = field(default_factory=list)
    country: str = ""
    level: str = ""
    source: str = ""


@dataclass
class DofResult:
    """
    Resultado de la verificación en el Diario Oficial de la Federación.

    Attributes:
        has_results: Si se encontraron publicaciones relevantes.
        publications: Lista de publicaciones encontradas.
        source: Fuente de la información.
    """

    has_results: bool = False
    publications: list[dict[str, Any]] = field(default_factory=list)
    source: str = "DOF"


@dataclass
class ScjnResult:
    """
    Resultado de la verificación en la Suprema Corte de Justicia de la Nación.

    Attributes:
        has_results: Si se encontraron amparos o resoluciones relevantes.
        cases: Lista de casos/amparos encontrados.
        source: Fuente de la información.
    """

    has_results: bool = False
    cases: list[dict[str, Any]] = field(default_factory=list)
    source: str = "SCJN"


# ---------------------------------------------------------------------------
# Umbrales de riesgo
# ---------------------------------------------------------------------------
_RISK_THRESHOLDS: dict[RiskLevel, tuple[float, float]] = {
    # (max_score mínimo, total_hits mínimo) para cada nivel
    RiskLevel.CRITICAL: (0.95, 1),
    RiskLevel.HIGH: (0.90, 1),
    RiskLevel.MEDIUM: (0.80, 2),
    RiskLevel.LOW: (0.70, 1),
    RiskLevel.NONE: (0.0, 0),
}

# Nivel de riesgo según tipo de fuente
_SOURCE_RISK_WEIGHTS: dict[str, float] = {
    "ofac": 1.0,
    "un_sanctions": 1.0,
    "interpol": 0.95,
    "open_sanctions": 0.85,
    "pep": 0.70,
    "sat_69b": 0.90,
    "dof": 0.60,
    "scjn": 0.50,
}


# ---------------------------------------------------------------------------
# Servicio principal de screening
# ---------------------------------------------------------------------------
class ComplianceScreeningService:
    """
    Orquestador principal del servicio de screening en listas restrictivas.

    Coordina la consulta paralela a todas las fuentes de compliance
    y consolida los resultados con clasificación automática de riesgo.

    Fuentes soportadas:
    - OFAC SDN (Specially Designated Nationals)
    - UN Security Council (sanciones del Consejo de Seguridad)
    - OpenSanctions (agregador global de sanciones y PEP)
    - Interpol Red Notices (avisos rojos)
    - SAT 69-B (presunción de operaciones simuladas - México)
    - DOF (Diario Oficial de la Federación - México)
    - SCJN (Suprema Corte de Justicia de la Nación - México)
    - PEP (Personas Políticamente Expuestas)

    Example:
        >>> service = ComplianceScreeningService()
        >>> result = await service.screen_person("Juan Pérez López", nationality="MX")
        >>> print(f"Nivel de riesgo: {result.risk_level.value}")
        >>> print(f"Coincidencias: {result.total_hits}")
    """

    def __init__(self) -> None:
        """Inicializa el servicio de screening con todos los clientes."""
        self._matcher = FuzzyMatcherService()
        self._ofac = OfacClient(matcher=self._matcher)
        self._un_sanctions = UnSanctionsClient(matcher=self._matcher)
        self._open_sanctions = OpenSanctionsClient(matcher=self._matcher)
        self._interpol = InterpolClient(matcher=self._matcher)
        self._settings = get_settings()

    # ── Screening de persona física ─────────────────────────────────────

    async def screen_person(
        self,
        name: str,
        curp: str | None = None,
        rfc: str | None = None,
        nationality: str = "MX",
        threshold: float | None = None,
    ) -> ScreeningResult:
        """
        Realiza screening completo de una persona física.

        Ejecuta todas las consultas en paralelo usando asyncio.gather
        y consolida los resultados con deduplicación.

        Args:
            name: Nombre completo de la persona.
            curp: CURP de la persona (opcional, para fuentes mexicanas).
            rfc: RFC de la persona (opcional, para SAT 69-B).
            nationality: Nacionalidad (código ISO, por defecto MX).
            threshold: Umbral de similitud personalizado.

        Returns:
            ScreeningResult con coincidencias y nivel de riesgo.
        """
        if not name:
            return ScreeningResult(
                risk_level=RiskLevel.NONE,
                sources_failed=[
                    "ofac", "un_sanctions", "open_sanctions",
                    "interpol", "pep", "sat_69b", "dof", "scjn",
                ],
            )

        if threshold is None:
            threshold = self._settings.NAME_SIMILARITY_THRESHOLD

        # Ejecutar todas las fuentes en paralelo
        results = await self._run_parallel_screening(
            name=name,
            curp=curp,
            rfc=rfc,
            nationality=nationality,
            threshold=threshold,
        )

        # Consolidar resultados
        return self._consolidate_results(results)

    # ── Screening de persona moral / entidad ────────────────────────────

    async def screen_entity(
        self,
        name: str,
        country: str = "MX",
        threshold: float | None = None,
    ) -> ScreeningResult:
        """
        Realiza screening de una persona moral o entidad corporativa.

        Similar al screening de persona física pero adaptado para
        entidades corporativas (sin CURP, sin PEP, etc.).

        Args:
            name: Nombre de la entidad corporativa.
            country: País de registro (código ISO).
            threshold: Umbral de similitud personalizado.

        Returns:
            ScreeningResult con coincidencias y nivel de riesgo.
        """
        if not name:
            return ScreeningResult(
                risk_level=RiskLevel.NONE,
                sources_failed=["ofac", "un_sanctions", "open_sanctions"],
            )

        if threshold is None:
            threshold = self._settings.NAME_SIMILARITY_THRESHOLD

        # Ejecutar fuentes relevantes para entidades en paralelo
        ofac_task = self._screen_ofac(name, threshold)
        un_task = self._screen_un_sanctions(name, threshold)
        opensanctions_task = self._screen_open_sanctions(name, country, threshold)
        sat69b_task = self._screen_sat_69b(name, "")
        dof_task = self._screen_dof(name)

        ofac_matches, un_matches, os_matches, sat_result, dof_result = (
            await asyncio.gather(
                ofac_task, un_task, opensanctions_task,
                sat69b_task, dof_task,
                return_exceptions=True,
            )
        )

        # Consolidar
        all_matches: list[MatchDetail] = []
        sources_checked: list[str] = []
        sources_failed: list[str] = []

        # Procesar resultados OFAC
        self._process_ofac_result(ofac_matches, all_matches, sources_checked, sources_failed)

        # Procesar resultados ONU
        self._process_un_result(un_matches, all_matches, sources_checked, sources_failed)

        # Procesar resultados OpenSanctions
        self._process_opensanctions_result(os_matches, all_matches, sources_checked, sources_failed)

        # Procesar resultado SAT 69-B
        if isinstance(sat_result, Sat69bResult) and sat_result.is_listed:
            sources_checked.append("sat_69b")
            all_matches.append(
                MatchDetail(
                    source="sat_69b",
                    score=1.0 if sat_result.status == "definitivo" else 0.85,
                    match_type="exact",
                    entity_name=sat_result.company_name,
                    entity_data={
                        "rfc": sat_result.rfc,
                        "status": sat_result.status,
                        "publication_date": sat_result.publication_date,
                        "docket_number": sat_result.docket_number,
                        "observations": sat_result.observations,
                    },
                )
            )
        elif isinstance(sat_result, Exception):
            sources_failed.append("sat_69b")
        else:
            sources_checked.append("sat_69b")

        # Procesar resultado DOF
        if isinstance(dof_result, DofResult):
            sources_checked.append("dof")
            if dof_result.has_results:
                for pub in dof_result.publications:
                    all_matches.append(
                        MatchDetail(
                            source="dof",
                            score=0.70,
                            match_type="fuzzy",
                            entity_name=pub.get("title", ""),
                            entity_data=pub,
                        )
                    )
        elif isinstance(dof_result, Exception):
            sources_failed.append("dof")

        return self._build_screening_result(all_matches, sources_checked, sources_failed)

    # ── Screening SAT 69-B ──────────────────────────────────────────────

    async def screen_sat_69b(
        self,
        name: str,
        rfc: str,
    ) -> Sat69bResult:
        """
        Verifica si un contribuyente está en la lista SAT 69-B.

        El artículo 69-B del Código Fiscal de la Federación establece
        la presunción de operaciones simuladas. Los contribuyentes
        listados pueden estar en estado:
        - "presunto": Presunción de operaciones simuladas
        - "desvirtuado": Desvirtuó la presunción
        - "definitivo": Operaciones simuladas definitivas

        Args:
            name: Nombre del contribuyente.
            rfc: RFC del contribuyente.

        Returns:
            Sat69bResult con el resultado de la verificación.
        """
        return await self._screen_sat_69b(name, rfc)

    # ── Screening DOF ──────────────────────────────────────────────────

    async def screen_dof(self, name: str) -> DofResult:
        """
        Verifica publicaciones relevantes en el Diario Oficial de la Federación.

        Busca en el DOF publicaciones relacionadas con sanciones,
        inhabilitaciones, decomisos u otras disposiciones oficiales
        relacionadas con el nombre proporcionado.

        Args:
            name: Nombre a buscar en el DOF.

        Returns:
            DofResult con las publicaciones encontradas.
        """
        return await self._screen_dof(name)

    # ── Screening SCJN ─────────────────────────────────────────────────

    async def screen_scjn(self, name: str) -> ScjnResult:
        """
        Verifica amparos y resoluciones relevantes en la SCJN.

        Busca en los registros de la Suprema Corte de Justicia de la
        Nación amparos, revisiones y resoluciones relacionadas con
        el nombre proporcionado.

        Args:
            name: Nombre a buscar en la SCJN.

        Returns:
            ScjnResult con los casos encontrados.
        """
        return await self._screen_scjn(name)

    # ── Screening PEP ──────────────────────────────────────────────────

    async def screen_pep(
        self,
        name: str,
        country: str = "MX",
    ) -> PepResult:
        """
        Verifica si una persona es una Persona Políticamente Expuesta (PEP).

        Las PEP son individuos que desempeñan o han desempeñado
        funciones públicas destacadas, incluyendo:
        - Jefes de Estado o de Gobierno
        - Políticos de alto nivel
        - Funcionarios gubernamentales de alto nivel
        - Oficiales de alto nivel de las fuerzas armadas
        - Directivos de empresas estatales
        - Funcionarios de partidos políticos

        Args:
            name: Nombre de la persona a verificar.
            country: País para contextualizar la búsqueda.

        Returns:
            PepResult con el resultado de la verificación.
        """
        return await self._screen_pep(name, country)

    # ── Ejecución paralela ─────────────────────────────────────────────

    async def _run_parallel_screening(
        self,
        name: str,
        curp: str | None,
        rfc: str | None,
        nationality: str,
        threshold: float,
    ) -> dict[str, Any]:
        """
        Ejecuta todas las fuentes de screening en paralelo.

        Usa asyncio.gather con return_exceptions=True para que
        un fallo en una fuente no afecte a las demás.

        Args:
            name: Nombre a buscar.
            curp: CURP (opcional).
            rfc: RFC (opcional).
            nationality: Nacionalidad.
            threshold: Umbral de similitud.

        Returns:
            Diccionario con los resultados de cada fuente.
        """
        # Crear tareas para cada fuente
        tasks = {
            "ofac": self._screen_ofac(name, threshold),
            "un_sanctions": self._screen_un_sanctions(name, threshold),
            "open_sanctions": self._screen_open_sanctions(name, nationality, threshold),
            "interpol": self._screen_interpol(name, nationality),
            "pep": self._screen_pep(name, nationality),
            "sat_69b": self._screen_sat_69b(name, rfc or ""),
            "dof": self._screen_dof(name),
            "scjn": self._screen_scjn(name),
        }

        # Ejecutar todas las tareas en paralelo
        task_names = list(tasks.keys())
        task_coros = list(tasks.values())

        results_list = await asyncio.gather(*task_coros, return_exceptions=True)

        # Mapear resultados por nombre de fuente
        results: dict[str, Any] = {}
        for name_key, result in zip(task_names, results_list):
            results[name_key] = result

        return results

    # ── Métodos de screening por fuente ─────────────────────────────────

    async def _screen_ofac(
        self,
        name: str,
        threshold: float,
    ) -> list[OfacMatch]:
        """Screening contra la lista OFAC SDN."""
        try:
            return await self._ofac.search(name, threshold=threshold)
        except Exception as exc:
            logger.error("Error en screening OFAC: %s", exc)
            raise

    async def _screen_un_sanctions(
        self,
        name: str,
        threshold: float,
    ) -> list[UnSanctionsMatch]:
        """Screening contra la lista de sanciones de la ONU."""
        try:
            return await self._un_sanctions.search(name, threshold=threshold)
        except Exception as exc:
            logger.error("Error en screening ONU: %s", exc)
            raise

    async def _screen_open_sanctions(
        self,
        name: str,
        country: str,
        threshold: float,
    ) -> list[SanctionsMatch]:
        """Screening contra OpenSanctions."""
        try:
            return await self._open_sanctions.search(name, country=country, threshold=threshold)
        except Exception as exc:
            logger.error("Error en screening OpenSanctions: %s", exc)
            raise

    async def _screen_interpol(
        self,
        name: str,
        nationality: str,
    ) -> list[InterpolMatch]:
        """Screening contra avisos rojos de Interpol."""
        try:
            return await self._interpol.search(name, nationality=nationality)
        except Exception as exc:
            logger.error("Error en screening Interpol: %s", exc)
            raise

    async def _screen_pep(
        self,
        name: str,
        country: str,
    ) -> PepResult:
        """
        Screening de Personas Políticamente Expuestas.

        Consulta OpenSanctions para la verificación PEP, filtrando
        específicamente por datasets de tipo PEP.
        """
        try:
            pep_datasets = [
                "pep",
                "everypolitician",
                "wikidata_pep",
                "mex_pep",
            ]
            matches = await self._open_sanctions.search(
                name,
                country=country.lower(),
                threshold=0.80,
                datasets=pep_datasets,
            )

            if not matches:
                return PepResult(is_pep=False, country=country)

            # Analizar los resultados para determinar cargos y nivel
            positions: list[str] = []
            highest_level = "municipal"

            for match in matches:
                props = match.entity.properties
                position = props.get("position", props.get("title", ""))
                if position:
                    positions.append(str(position))

                # Determinar nivel del cargo
                description = str(position).upper()
                if any(kw in description for kw in (
                    "PRESIDENTE", "PRESIDENTA", "GOBERNADOR", "GOBERNADORA",
                    "SENADOR", "SENADORA", "SECRETARIO", "SECRETARIA DE ESTADO",
                    "MINISTRO", "MINISTRA", "PROCURADOR", "FISCAL GENERAL",
                    "PRESIDENT", "GOVERNOR", "SENATOR", "MINISTER",
                )):
                    highest_level = "national"
                elif any(kw in description for kw in (
                    "DIPUTADO", "DIPUTADA", "ALCALDE", "ALCALDESA",
                    "PRESIDENTE MUNICIPAL", "REGIDOR",
                    "DEPUTY", "MAYOR",
                )):
                    if highest_level != "national":
                        highest_level = "state"

            return PepResult(
                is_pep=True,
                positions=positions,
                country=country,
                level=highest_level,
                source="opensanctions_pep",
            )

        except Exception as exc:
            logger.error("Error en screening PEP: %s", exc)
            raise

    async def _screen_sat_69b(
        self,
        name: str,
        rfc: str,
    ) -> Sat69bResult:
        """
        Screening contra la lista SAT 69-B.

        Consulta la API del SAT para verificar si el contribuyente
        está listado en el artículo 69-B del CFF.
        """
        try:
            settings = get_settings()
            import httpx

            params: dict[str, str] = {}
            if rfc:
                params["rfc"] = rfc
            elif name:
                params["nombre"] = name
            else:
                return Sat69bResult()

            headers: dict[str, str] = {}
            if settings.SAT_API_KEY:
                headers["Authorization"] = f"Bearer {settings.SAT_API_KEY}"

            async with httpx.AsyncClient(timeout=15.0) as client:
                response = await client.get(
                    f"{settings.SAT_API_URL}/articulo-69-b",
                    params=params,
                    headers=headers,
                )

                if response.status_code == 404:
                    return Sat69bResult(rfc=rfc)

                response.raise_for_status()
                data = response.json()

                # Parsear la respuesta del SAT
                results = data.get("results", data if isinstance(data, list) else [data])

                if not results:
                    return Sat69bResult(rfc=rfc)

                first_result = results[0] if isinstance(results, list) else results

                # Verificar coincidencia difusa del nombre si no se usó RFC
                if not rfc and name:
                    sat_name = first_result.get("nombre", first_result.get("name", ""))
                    if sat_name:
                        match_results = self._matcher.match(name, [sat_name], threshold=0.75)
                        if not match_results:
                            return Sat69bResult(rfc=rfc)

                return Sat69bResult(
                    is_listed=True,
                    rfc=first_result.get("rfc", rfc),
                    company_name=first_result.get("nombre", first_result.get("name", "")),
                    status=first_result.get("situacion", first_result.get("status", "presunto")),
                    publication_date=first_result.get("fecha_publicacion", ""),
                    docket_number=first_result.get("oficio", first_result.get("docket_number", "")),
                    observations=first_result.get("observaciones", ""),
                )

        except Exception as exc:
            logger.error("Error en screening SAT 69-B: %s", exc)
            raise

    async def _screen_dof(self, name: str) -> DofResult:
        """
        Screening en el Diario Oficial de la Federación.

        Busca publicaciones relevantes en el DOF relacionadas con
        sanciones, inhabilitaciones y disposiciones oficiales.
        """
        try:
            import httpx

            # API del DOF (datos.gob.mx)
            async with httpx.AsyncClient(timeout=15.0) as client:
                params = {
                    "q": name,
                    "limit": 10,
                    "sort": "fecha-desc",
                }

                response = await client.get(
                    "https://www.dof.gob.mx/v2/api/busqueda",
                    params=params,
                    headers={"Accept": "application/json"},
                )

                if response.status_code != 200:
                    return DofResult()

                data = response.json()
                publications: list[dict[str, Any]] = []

                for item in data.get("results", data.get("items", [])):
                    title = item.get("titulo", item.get("title", ""))
                    summary = item.get("resumen", item.get("summary", ""))

                    # Filtrar solo publicaciones relevantes para compliance
                    relevance_keywords = (
                        "sanción", "sancionar", "inhabilit", "multa",
                        "decomiso", "proceso penal", "orden de aprensión",
                        "averiguación previa", "carpeta de investigación",
                        "lista negra", "operación simulada",
                    )

                    combined_text = f"{title} {summary}".lower()
                    is_relevant = any(kw in combined_text for kw in relevance_keywords)

                    if is_relevant:
                        publications.append({
                            "title": title,
                            "summary": summary,
                            "date": item.get("fecha", item.get("date", "")),
                            "url": item.get("url", ""),
                            "section": item.get("seccion", item.get("section", "")),
                        })

                return DofResult(
                    has_results=len(publications) > 0,
                    publications=publications,
                )

        except Exception as exc:
            logger.error("Error en screening DOF: %s", exc)
            raise

    async def _screen_scjn(self, name: str) -> ScjnResult:
        """
        Screening en la Suprema Corte de Justicia de la Nación.

        Busca amparos, revisiones y resoluciones relevantes en los
        registros públicos de la SCJN.
        """
        try:
            import httpx

            # API de la SCJN (buscador de precedentes)
            async with httpx.AsyncClient(timeout=15.0) as client:
                params = {
                    "q": name,
                    "limit": 10,
                    "tipo": "amparo",
                }

                response = await client.get(
                    "https://www.scjn.gob.mx/api/busqueda",
                    params=params,
                    headers={"Accept": "application/json"},
                )

                if response.status_code != 200:
                    return ScjnResult()

                data = response.json()
                cases: list[dict[str, Any]] = []

                for item in data.get("results", data.get("items", [])):
                    rubro = item.get("rubro", item.get("title", ""))
                    caso_tipo = item.get("tipo", item.get("type", ""))

                    cases.append({
                        "title": rubro,
                        "type": caso_tipo,
                        "date": item.get("fecha", item.get("date", "")),
                        "docket": item.get("expediente", item.get("docket", "")),
                        "url": item.get("url", ""),
                        "court": item.get("organo", item.get("court", "")),
                    })

                return ScjnResult(
                    has_results=len(cases) > 0,
                    cases=cases,
                )

        except Exception as exc:
            logger.error("Error en screening SCJN: %s", exc)
            raise

    # ── Consolidación de resultados ─────────────────────────────────────

    def _consolidate_results(
        self,
        results: dict[str, Any],
    ) -> ScreeningResult:
        """
        Consolida los resultados de todas las fuentes de screening.

        Aplica deduplicación y clasificación de riesgo.

        Args:
            results: Diccionario con los resultados de cada fuente.

        Returns:
            ScreeningResult consolidado.
        """
        all_matches: list[MatchDetail] = []
        sources_checked: list[str] = []
        sources_failed: list[str] = []

        # Procesar OFAC
        ofac_result = results.get("ofac")
        self._process_ofac_result(ofac_result, all_matches, sources_checked, sources_failed)

        # Procesar ONU
        un_result = results.get("un_sanctions")
        self._process_un_result(un_result, all_matches, sources_checked, sources_failed)

        # Procesar OpenSanctions
        os_result = results.get("open_sanctions")
        self._process_opensanctions_result(os_result, all_matches, sources_checked, sources_failed)

        # Procesar Interpol
        interpol_result = results.get("interpol")
        self._process_interpol_result(interpol_result, all_matches, sources_checked, sources_failed)

        # Procesar PEP
        pep_result = results.get("pep")
        if isinstance(pep_result, PepResult):
            sources_checked.append("pep")
            if pep_result.is_pep:
                all_matches.append(
                    MatchDetail(
                        source="pep",
                        score=0.70,
                        match_type="exact",
                        entity_name="PEP",
                        entity_data={
                            "positions": pep_result.positions,
                            "country": pep_result.country,
                            "level": pep_result.level,
                            "source": pep_result.source,
                        },
                    )
                )
        elif isinstance(pep_result, Exception):
            sources_failed.append("pep")

        # Procesar SAT 69-B
        sat_result = results.get("sat_69b")
        if isinstance(sat_result, Sat69bResult) and sat_result.is_listed:
            sources_checked.append("sat_69b")
            score = 1.0 if sat_result.status == "definitivo" else 0.85
            all_matches.append(
                MatchDetail(
                    source="sat_69b",
                    score=score,
                    match_type="exact",
                    entity_name=sat_result.company_name,
                    entity_data={
                        "rfc": sat_result.rfc,
                        "status": sat_result.status,
                        "publication_date": sat_result.publication_date,
                        "docket_number": sat_result.docket_number,
                        "observations": sat_result.observations,
                    },
                )
            )
        elif isinstance(sat_result, Exception):
            sources_failed.append("sat_69b")
        else:
            sources_checked.append("sat_69b")

        # Procesar DOF
        dof_result = results.get("dof")
        if isinstance(dof_result, DofResult):
            sources_checked.append("dof")
            if dof_result.has_results:
                for pub in dof_result.publications:
                    all_matches.append(
                        MatchDetail(
                            source="dof",
                            score=0.60,
                            match_type="fuzzy",
                            entity_name=pub.get("title", ""),
                            entity_data=pub,
                        )
                    )
        elif isinstance(dof_result, Exception):
            sources_failed.append("dof")

        # Procesar SCJN
        scjn_result = results.get("scjn")
        if isinstance(scjn_result, ScjnResult):
            sources_checked.append("scjn")
            if scjn_result.has_results:
                for case in scjn_result.cases:
                    all_matches.append(
                        MatchDetail(
                            source="scjn",
                            score=0.50,
                            match_type="fuzzy",
                            entity_name=case.get("title", ""),
                            entity_data=case,
                        )
                    )
        elif isinstance(scjn_result, Exception):
            sources_failed.append("scjn")

        return self._build_screening_result(all_matches, sources_checked, sources_failed)

    # ── Procesamiento de resultados por fuente ──────────────────────────

    def _process_ofac_result(
        self,
        result: Any,
        matches: list[MatchDetail],
        sources_checked: list[str],
        sources_failed: list[str],
    ) -> None:
        """Procesa el resultado de OFAC y agrega coincidencias."""
        if isinstance(result, list):
            sources_checked.append("ofac")
            for match in result:
                if isinstance(match, OfacMatch):
                    matches.append(
                        MatchDetail(
                            source="ofac",
                            score=match.match_score,
                            match_type=match.match_type,
                            entity_name=match.record.name,
                            entity_data={
                                "sdn_id": match.record.id,
                                "type": match.record.type,
                                "program": match.record.program,
                                "title": match.record.title,
                                "remarks": match.record.remarks,
                                "aliases": match.record.aliases,
                                "addresses": match.record.addresses,
                            },
                        )
                    )
        elif isinstance(result, Exception):
            sources_failed.append("ofac")

    def _process_un_result(
        self,
        result: Any,
        matches: list[MatchDetail],
        sources_checked: list[str],
        sources_failed: list[str],
    ) -> None:
        """Procesa el resultado de la ONU y agrega coincidencias."""
        if isinstance(result, list):
            sources_checked.append("un_sanctions")
            for match in result:
                if isinstance(match, UnSanctionsMatch):
                    matches.append(
                        MatchDetail(
                            source="un_sanctions",
                            score=match.match_score,
                            match_type=match.match_type,
                            entity_name=match.entity.name,
                            entity_data={
                                "entity_id": match.entity.id,
                                "entity_type": match.entity.entity_type,
                                "committee": match.entity.committee,
                                "nationality": match.entity.nationality,
                                "aliases": match.entity.aliases,
                                "designation_date": match.entity.designation_date,
                            },
                        )
                    )
        elif isinstance(result, Exception):
            sources_failed.append("un_sanctions")

    def _process_opensanctions_result(
        self,
        result: Any,
        matches: list[MatchDetail],
        sources_checked: list[str],
        sources_failed: list[str],
    ) -> None:
        """Procesa el resultado de OpenSanctions y agrega coincidencias."""
        if isinstance(result, list):
            sources_checked.append("open_sanctions")
            for match in result:
                if isinstance(match, SanctionsMatch):
                    matches.append(
                        MatchDetail(
                            source="open_sanctions",
                            score=match.score,
                            match_type=match.match_type,
                            entity_name=match.entity.name,
                            entity_data={
                                "entity_id": match.entity.id,
                                "schema": match.entity.schema,
                                "datasets": match.datasets,
                                "aliases": match.entity.aliases,
                                "countries": match.entity.countries,
                                "properties": match.properties,
                            },
                        )
                    )
        elif isinstance(result, Exception):
            sources_failed.append("open_sanctions")

    def _process_interpol_result(
        self,
        result: Any,
        matches: list[MatchDetail],
        sources_checked: list[str],
        sources_failed: list[str],
    ) -> None:
        """Procesa el resultado de Interpol y agrega coincidencias."""
        if isinstance(result, list):
            sources_checked.append("interpol")
            for match in result:
                if isinstance(match, InterpolMatch):
                    matches.append(
                        MatchDetail(
                            source="interpol",
                            score=match.match_score,
                            match_type=match.match_type,
                            entity_name=match.notice.name,
                            entity_data={
                                "notice_id": match.notice.notice_id,
                                "notice_type": match.notice.notice_type,
                                "nationalities": match.notice.nationalities,
                                "charges": match.notice.charges,
                                "arresting_country": match.notice.arresting_country,
                                "date_of_birth": match.notice.date_of_birth,
                                "sex": match.notice.sex,
                            },
                        )
                    )
        elif isinstance(result, Exception):
            sources_failed.append("interpol")

    # ── Construcción del resultado final ────────────────────────────────

    def _build_screening_result(
        self,
        matches: list[MatchDetail],
        sources_checked: list[str],
        sources_failed: list[str],
    ) -> ScreeningResult:
        """
        Construye el resultado final de screening con deduplicación
        y clasificación de riesgo.

        Args:
            matches: Lista de coincidencias encontradas.
            sources_checked: Fuentes consultadas exitosamente.
            sources_failed: Fuentes que fallaron.

        Returns:
            ScreeningResult con deduplicación y nivel de riesgo.
        """
        # Deduplicar coincidencias (mismo nombre + fuente)
        seen: set[str] = set()
        unique_matches: list[MatchDetail] = []
        for match in matches:
            key = f"{match.source}:{match.entity_name}:{match.match_type}"
            if key not in seen:
                seen.add(key)
                unique_matches.append(match)

        # Calcular métricas
        total_hits = len(unique_matches)
        max_score = max((m.score for m in unique_matches), default=0.0)

        # Calcular score ponderado por fuente
        weighted_score = 0.0
        for match in unique_matches:
            weight = _SOURCE_RISK_WEIGHTS.get(match.source, 0.5)
            weighted_score = max(weighted_score, match.score * weight)

        # Clasificar nivel de riesgo
        risk_level = self._classify_risk(max_score, weighted_score, total_hits)

        return ScreeningResult(
            matches=unique_matches,
            total_hits=total_hits,
            max_score=round(max_score, 4),
            risk_level=risk_level,
            sources_checked=sources_checked,
            sources_failed=sources_failed,
        )

    def _classify_risk(
        self,
        max_score: float,
        weighted_score: float,
        total_hits: int,
    ) -> RiskLevel:
        """
        Clasifica el nivel de riesgo basado en coincidencias.

        La clasificación considera:
        - Puntuación máxima de coincidencia
        - Score ponderado por criticidad de la fuente
        - Número total de coincidencias
        - Presencia en fuentes de alta criticidad (OFAC, ONU)

        Args:
            max_score: Puntuación máxima de coincidencia.
            weighted_score: Puntuación ponderada por fuente.
            total_hits: Número total de coincidencias.

        Returns:
            RiskLevel clasificado.
        """
        # Criterios de clasificación (de más a menos estricto)
        if weighted_score >= 0.95 or (max_score >= 0.95 and total_hits >= 1):
            return RiskLevel.CRITICAL

        if weighted_score >= 0.85 or (max_score >= 0.90 and total_hits >= 1):
            return RiskLevel.HIGH

        if weighted_score >= 0.70 or (max_score >= 0.80 and total_hits >= 2):
            return RiskLevel.MEDIUM

        if weighted_score >= 0.55 or (max_score >= 0.70 and total_hits >= 1):
            return RiskLevel.LOW

        return RiskLevel.NONE
