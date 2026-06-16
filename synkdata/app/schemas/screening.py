"""
Esquemas Pydantic para el módulo de screening en listas restrictivas.

Define los modelos de validación y serialización para:
- Solicitudes de screening (entrada)
- Resultados de screening (salida)
- Resultados por fuente específica (SAT 69-B, PEP, DOF, SCJN)
- Detalles de coincidencias individuales

Todos los esquemas incluyen documentación en español para la
generación automática de la documentación OpenAPI.
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field, field_validator


# ---------------------------------------------------------------------------
# Enumeraciones compartidas
# ---------------------------------------------------------------------------
class RiskLevelSchema(str, Enum):
    """Nivel de riesgo resultante del screening."""

    NONE = "none"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class MatchTypeSchema(str, Enum):
    """Tipo de coincidencia detectada."""

    EXACT = "exact"
    FUZZY = "fuzzy"
    PHONETIC = "phonetic"
    ALIAS = "alias"


class ScreeningEntityTypeSchema(str, Enum):
    """Tipo de entidad sometida a screening."""

    PERSON = "person"
    ENTITY = "entity"


# ---------------------------------------------------------------------------
# Esquemas de entrada (request)
# ---------------------------------------------------------------------------
class ScreeningPersonRequest(BaseModel):
    """
    Solicitud de screening para una persona física.

    Attributes:
        name: Nombre completo de la persona.
        curp: CURP de la persona (opcional, mejora precisión en fuentes mexicanas).
        rfc: RFC de la persona (opcional, necesario para SAT 69-B).
        country: País de nacionalidad (código ISO, por defecto MX).
        threshold: Umbral de similitud personalizado (0.0 a 1.0).
    """

    name: str = Field(
        ...,
        min_length=2,
        max_length=500,
        description="Nombre completo de la persona a screening.",
        examples=["Juan Pérez López"],
    )
    curp: Optional[str] = Field(
        default=None,
        max_length=18,
        description="CURP de la persona (opcional, mejora precisión en fuentes mexicanas).",
        examples=["PELJ800101HDFRRN09"],
    )
    rfc: Optional[str] = Field(
        default=None,
        max_length=13,
        description="RFC de la persona (opcional, necesario para verificación SAT 69-B).",
        examples=["PELJ800101XYZ"],
    )
    country: str = Field(
        default="MX",
        max_length=5,
        description="País de nacionalidad (código ISO 3166-1 alpha-2).",
        examples=["MX"],
    )
    threshold: Optional[float] = Field(
        default=None,
        ge=0.5,
        le=1.0,
        description="Umbral de similitud personalizado (0.5 a 1.0).",
    )

    @field_validator("name")
    @classmethod
    def validate_name(cls, v: str) -> str:
        """Valida que el nombre no esté vacío después de normalizar."""
        if not v.strip():
            raise ValueError("El nombre no puede estar vacío.")
        return v.strip()


class ScreeningEntityRequest(BaseModel):
    """
    Solicitud de screening para una persona moral o entidad corporativa.

    Attributes:
        name: Nombre de la entidad corporativa.
        country: País de registro (código ISO).
        threshold: Umbral de similitud personalizado.
    """

    name: str = Field(
        ...,
        min_length=2,
        max_length=500,
        description="Nombre de la entidad corporativa a screening.",
        examples=["Corporativo Alfa S.A. de C.V."],
    )
    country: str = Field(
        default="MX",
        max_length=5,
        description="País de registro (código ISO 3166-1 alpha-2).",
        examples=["MX"],
    )
    threshold: Optional[float] = Field(
        default=None,
        ge=0.5,
        le=1.0,
        description="Umbral de similitud personalizado (0.5 a 1.0).",
    )

    @field_validator("name")
    @classmethod
    def validate_name(cls, v: str) -> str:
        """Valida que el nombre no esté vacío después de normalizar."""
        if not v.strip():
            raise ValueError("El nombre de la entidad no puede estar vacío.")
        return v.strip()


class Sat69bRequest(BaseModel):
    """
    Solicitud de verificación específica en la lista SAT 69-B.

    Attributes:
        name: Nombre del contribuyente.
        rfc: RFC del contribuyente.
    """

    name: str = Field(
        ...,
        min_length=2,
        max_length=500,
        description="Nombre del contribuyente a verificar.",
    )
    rfc: str = Field(
        ...,
        min_length=12,
        max_length=13,
        description="RFC del contribuyente a verificar en SAT 69-B.",
    )

    @field_validator("rfc")
    @classmethod
    def validate_rfc(cls, v: str) -> str:
        """Valida formato básico del RFC."""
        v = v.strip().upper()
        if len(v) < 12:
            raise ValueError("El RFC debe tener al menos 12 caracteres.")
        return v


class PepRequest(BaseModel):
    """
    Solicitud de verificación de Persona Políticamente Expuesta.

    Attributes:
        name: Nombre de la persona a verificar.
        country: País para contextualizar la búsqueda.
    """

    name: str = Field(
        ...,
        min_length=2,
        max_length=500,
        description="Nombre de la persona a verificar como PEP.",
    )
    country: str = Field(
        default="MX",
        max_length=5,
        description="País para contextualizar la búsqueda PEP.",
    )


# ---------------------------------------------------------------------------
# Esquemas de salida (response)
# ---------------------------------------------------------------------------
class MatchDetailSchema(BaseModel):
    """
    Detalle de una coincidencia individual de screening.

    Attributes:
        source: Fuente donde se encontró la coincidencia.
        score: Puntuación de similitud (0.0 a 1.0).
        match_type: Tipo de coincidencia.
        entity_name: Nombre de la entidad coincidente.
        entity_data: Datos adicionales de la entidad.
        is_confirmed: Si la coincidencia fue confirmada manualmente.
    """

    source: str = Field(
        ...,
        description="Fuente donde se encontró la coincidencia (ofac, interpol, etc.).",
    )
    score: float = Field(
        ...,
        ge=0.0,
        le=1.0,
        description="Puntuación de similitud (0.0 = sin similitud, 1.0 = coincidencia exacta).",
    )
    match_type: MatchTypeSchema = Field(
        ...,
        description="Tipo de coincidencia detectada.",
    )
    entity_name: str = Field(
        ...,
        description="Nombre de la entidad coincidente en la fuente.",
    )
    entity_data: Dict[str, Any] = Field(
        default_factory=dict,
        description="Datos adicionales de la entidad (varía según la fuente).",
    )
    is_confirmed: bool = Field(
        default=False,
        description="Si la coincidencia fue confirmada manualmente por un analista.",
    )

    model_config = {"from_attributes": True}


class ScreeningResultSchema(BaseModel):
    """
    Resultado completo del screening en listas restrictivas.

    Attributes:
        request_id: Identificador único de la solicitud.
        matches: Lista de coincidencias encontradas.
        total_hits: Número total de coincidencias.
        max_score: Puntuación máxima de todas las coincidencias.
        risk_level: Nivel de riesgo calculado.
        sources_checked: Lista de fuentes consultadas exitosamente.
        sources_failed: Lista de fuentes que fallaron.
        timestamp: Fecha y hora del screening (ISO 8601).
    """

    request_id: str = Field(
        ...,
        description="Identificador único de la solicitud de screening.",
    )
    matches: List[MatchDetailSchema] = Field(
        default_factory=list,
        description="Lista de coincidencias encontradas en todas las fuentes.",
    )
    total_hits: int = Field(
        default=0,
        ge=0,
        description="Número total de coincidencias encontradas.",
    )
    max_score: float = Field(
        default=0.0,
        ge=0.0,
        le=1.0,
        description="Puntuación máxima de todas las coincidencias.",
    )
    risk_level: RiskLevelSchema = Field(
        default=RiskLevelSchema.NONE,
        description="Nivel de riesgo calculado: none, low, medium, high, critical.",
    )
    sources_checked: List[str] = Field(
        default_factory=list,
        description="Lista de fuentes consultadas exitosamente.",
    )
    sources_failed: List[str] = Field(
        default_factory=list,
        description="Lista de fuentes que no pudieron ser consultadas.",
    )
    timestamp: str = Field(
        default="",
        description="Fecha y hora del screening en formato ISO 8601 (UTC).",
    )

    model_config = {"from_attributes": True}


class Sat69bResultSchema(BaseModel):
    """
    Resultado de la verificación en la lista SAT 69-B.

    El artículo 69-B del Código Fiscal de la Federación establece
    la presunción de operaciones simuladas.

    Attributes:
        is_listed: Si el RFC/nombre aparece en la lista 69-B.
        rfc: RFC verificado.
        company_name: Nombre de la empresa/contribuyente.
        status: Estado en la lista (presunto/desvirtuado/definitivo).
        publication_date: Fecha de publicación en el DOF.
        docket_number: Número de oficio.
        observations: Observaciones adicionales.
    """

    is_listed: bool = Field(
        default=False,
        description="Si el RFC/nombre aparece en la lista 69-B del SAT.",
    )
    rfc: str = Field(
        default="",
        description="RFC del contribuyente verificado.",
    )
    company_name: str = Field(
        default="",
        description="Nombre o razón social del contribuyente.",
    )
    status: str = Field(
        default="",
        description=(
            "Estado en la lista 69-B: "
            "'presunto' = presunción de operaciones simuladas, "
            "'desvirtuado' = desvirtuó la presunción, "
            "'definitivo' = operaciones simuladas definitivas."
        ),
    )
    publication_date: str = Field(
        default="",
        description="Fecha de publicación en el Diario Oficial de la Federación.",
    )
    docket_number: str = Field(
        default="",
        description="Número de oficio del procedimiento.",
    )
    observations: str = Field(
        default="",
        description="Observaciones adicionales del SAT.",
    )

    model_config = {"from_attributes": True}


class PepPositionSchema(BaseModel):
    """
    Cargo político desempeñado por una PEP.

    Attributes:
        title: Título del cargo.
        level: Nivel del cargo (national/state/municipal).
        country: País donde ejerce/ejerció el cargo.
        start_date: Fecha de inicio del cargo.
        end_date: Fecha de fin del cargo (si aplica).
    """

    title: str = Field(..., description="Título del cargo desempeñado.")
    level: str = Field(default="", description="Nivel del cargo: national, state, municipal.")
    country: str = Field(default="", description="País donde ejerce el cargo.")
    start_date: str = Field(default="", description="Fecha de inicio del cargo.")
    end_date: str = Field(default="", description="Fecha de fin del cargo.")


class PepResultSchema(BaseModel):
    """
    Resultado de la verificación de Persona Políticamente Expuesta.

    Attributes:
        is_pep: Si la persona está identificada como PEP.
        positions: Lista de cargos políticos desempeñados.
        country: País donde ejerce/ejerció el cargo.
        level: Nivel del cargo de mayor jerarquía.
        source: Fuente de la información PEP.
    """

    is_pep: bool = Field(
        default=False,
        description="Si la persona está identificada como PEP.",
    )
    positions: List[str] = Field(
        default_factory=list,
        description="Lista de cargos políticos desempeñados.",
    )
    country: str = Field(
        default="",
        description="País donde ejerce o ejerció el cargo.",
    )
    level: str = Field(
        default="",
        description=(
            "Nivel del cargo de mayor jerarquía: "
            "'national' = nivel federal/nacional, "
            "'state' = nivel estatal, "
            "'municipal' = nivel municipal."
        ),
    )
    source: str = Field(
        default="",
        description="Fuente de la información PEP.",
    )

    model_config = {"from_attributes": True}


class DofPublicationSchema(BaseModel):
    """
    Publicación encontrada en el Diario Oficial de la Federación.

    Attributes:
        title: Título de la publicación.
        summary: Resumen del contenido.
        date: Fecha de publicación.
        url: URL de la publicación.
        section: Sección del DOF.
    """

    title: str = Field(default="", description="Título de la publicación.")
    summary: str = Field(default="", description="Resumen del contenido.")
    date: str = Field(default="", description="Fecha de publicación.")
    url: str = Field(default="", description="URL de la publicación en el DOF.")
    section: str = Field(default="", description="Sección del DOF.")


class DofResultSchema(BaseModel):
    """
    Resultado de la verificación en el Diario Oficial de la Federación.

    Attributes:
        has_results: Si se encontraron publicaciones relevantes.
        publications: Lista de publicaciones encontradas.
        source: Fuente de la información.
    """

    has_results: bool = Field(
        default=False,
        description="Si se encontraron publicaciones relevantes en el DOF.",
    )
    publications: List[DofPublicationSchema] = Field(
        default_factory=list,
        description="Lista de publicaciones relevantes encontradas.",
    )
    source: str = Field(
        default="DOF",
        description="Fuente de la información.",
    )

    model_config = {"from_attributes": True}


class ScjnCaseSchema(BaseModel):
    """
    Caso/amparo encontrado en la SCJN.

    Attributes:
        title: Título/rubro del caso.
        type: Tipo de caso (amparo, revisión, etc.).
        date: Fecha del caso.
        docket: Número de expediente.
        url: URL del caso.
        court: Órgano jurisdiccional.
    """

    title: str = Field(default="", description="Título o rubro del caso.")
    type: str = Field(default="", description="Tipo de caso: amparo, revisión, etc.")
    date: str = Field(default="", description="Fecha del caso.")
    docket: str = Field(default="", description="Número de expediente.")
    url: str = Field(default="", description="URL del caso en la SCJN.")
    court: str = Field(default="", description="Órgano jurisdiccional.")


class ScjnResultSchema(BaseModel):
    """
    Resultado de la verificación en la Suprema Corte de Justicia de la Nación.

    Attributes:
        has_results: Si se encontraron amparos o resoluciones relevantes.
        cases: Lista de casos/amparos encontrados.
        source: Fuente de la información.
    """

    has_results: bool = Field(
        default=False,
        description="Si se encontraron amparos o resoluciones relevantes.",
    )
    cases: List[ScjnCaseSchema] = Field(
        default_factory=list,
        description="Lista de casos y amparos encontrados.",
    )
    source: str = Field(
        default="SCJN",
        description="Fuente de la información.",
    )

    model_config = {"from_attributes": True}


# ---------------------------------------------------------------------------
# Esquema de respuesta para consulta de solicitud previa
# ---------------------------------------------------------------------------
class ScreeningRequestDetail(BaseModel):
    """
    Detalle completo de una solicitud de screening previa.

    Attributes:
        id: Identificador único de la solicitud.
        name: Nombre de la persona o entidad.
        curp: CURP (si aplica).
        rfc: RFC (si aplica).
        entity_type: Tipo de entidad.
        status: Estado del screening.
        results: Resultados del screening.
        created_at: Fecha de creación.
        updated_at: Fecha de última actualización.
    """

    id: str = Field(..., description="Identificador único de la solicitud.")
    name: str = Field(..., description="Nombre de la persona o entidad.")
    curp: Optional[str] = Field(default=None, description="CURP de la persona.")
    rfc: Optional[str] = Field(default=None, description="RFC del contribuyente.")
    entity_type: str = Field(..., description="Tipo de entidad (person/entity).")
    status: str = Field(..., description="Estado del screening.")
    results: Optional[ScreeningResultSchema] = Field(
        default=None,
        description="Resultados del screening.",
    )
    created_at: Optional[str] = Field(default=None, description="Fecha de creación.")
    updated_at: Optional[str] = Field(default=None, description="Fecha de última actualización.")

    model_config = {"from_attributes": True}
