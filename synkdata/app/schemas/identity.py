"""
Esquemas Pydantic para el módulo de inteligencia de identidad.

Define los modelos de validación y serialización para:
- Correlación de identidad (entrada y salida)
- Puntuación de confianza (trust score)
- Evaluación de riesgo (risk assessment)
- Respuesta completa de evaluación de identidad

Todos los esquemas incluyen documentación en español para la
generación automática de la documentación OpenAPI.
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field, field_validator, model_validator


# ---------------------------------------------------------------------------
# Enumeraciones compartidas
# ---------------------------------------------------------------------------
class TrustLevel(str, Enum):
    """Nivel de confianza de una identidad."""

    VERY_HIGH = "very_high"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    VERY_LOW = "very_low"


class Recommendation(str, Enum):
    """Recomendación resultante de la evaluación de riesgo."""

    APPROVE = "APPROVE"
    REVIEW = "REVIEW"
    REJECT = "REJECT"


class Severity(str, Enum):
    """Severidad de un factor de riesgo."""

    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


# ---------------------------------------------------------------------------
# Esquemas de entrada (request)
# ---------------------------------------------------------------------------
class SocialProfileInput(BaseModel):
    """
    Perfil social de una persona en una plataforma específica.

    Attributes:
        platform: Nombre de la plataforma (ej. linkedin, github, twitter).
        username: Nombre de usuario en la plataforma.
        display_name: Nombre visible en el perfil.
        url: URL del perfil.
        verified: Si el perfil está verificado.
    """

    platform: str = Field(
        ...,
        description="Nombre de la plataforma (ej. 'linkedin', 'github', 'twitter').",
    )
    username: Optional[str] = Field(
        default=None,
        description="Nombre de usuario en la plataforma.",
    )
    display_name: Optional[str] = Field(
        default=None,
        description="Nombre visible en el perfil.",
    )
    url: Optional[str] = Field(
        default=None,
        description="URL del perfil.",
    )
    verified: bool = Field(
        default=False,
        description="Si el perfil está verificado en la plataforma.",
    )


class IdentityData(BaseModel):
    """
    Datos de identidad para correlación cruzada.

    Al menos uno de los campos de identificación debe ser proporcionado.
    Se recomienda proporcionar la mayor cantidad de datos posible
    para una correlación más precisa.

    Attributes:
        name: Nombre completo de la persona.
        curp: Clave Única de Registro de Población (18 caracteres).
        rfc: Registro Federal de Contribuyentes (12-13 caracteres).
        email: Correo electrónico.
        phone: Número telefónico (formato E.164).
        username: Nombre de usuario genérico.
        company: Nombre de la empresa declarada.
        domain: Dominio declarado (ej. empresa.com.mx).
        social_profiles: Lista de perfiles en redes sociales y plataformas.
    """

    name: Optional[str] = Field(
        default=None,
        max_length=500,
        description="Nombre completo de la persona.",
        examples=["JUAN GOMEZ RODRIGUEZ"],
    )
    curp: Optional[str] = Field(
        default=None,
        min_length=18,
        max_length=18,
        description="Clave Única de Registro de Población (18 caracteres).",
        examples=["GOME850101HDFRRN09"],
    )
    rfc: Optional[str] = Field(
        default=None,
        min_length=12,
        max_length=13,
        description="Registro Federal de Contribuyentes (12-13 caracteres).",
        examples=["GOME850101ABC"],
    )
    email: Optional[str] = Field(
        default=None,
        max_length=320,
        description="Correo electrónico de la persona.",
        examples=["juan.gomez@empresa.com.mx"],
    )
    phone: Optional[str] = Field(
        default=None,
        max_length=20,
        description="Número telefónico en formato E.164.",
        examples=["+525512345678"],
    )
    username: Optional[str] = Field(
        default=None,
        max_length=100,
        description="Nombre de usuario genérico.",
        examples=["juangomez"],
    )
    company: Optional[str] = Field(
        default=None,
        max_length=500,
        description="Nombre de la empresa declarada.",
        examples=["Empresa S.A. de C.V."],
    )
    domain: Optional[str] = Field(
        default=None,
        max_length=255,
        description="Dominio declarado (ej. empresa.com.mx).",
        examples=["empresa.com.mx"],
    )
    social_profiles: List[SocialProfileInput] = Field(
        default_factory=list,
        description="Lista de perfiles en redes sociales y plataformas.",
    )

    @model_validator(mode="after")
    def validate_at_least_one_field(self) -> "IdentityData":
        """Valida que al menos un campo de identificación sea proporcionado."""
        if not any([self.name, self.curp, self.rfc, self.email, self.phone, self.username]):
            raise ValueError(
                "Debe proporcionar al menos uno de los siguientes campos: "
                "name, curp, rfc, email, phone o username."
            )
        return self

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "name": "JUAN GOMEZ RODRIGUEZ",
                    "curp": "GOME850101HDFRRN09",
                    "rfc": "GOME850101ABC",
                    "email": "juan.gomez@empresa.com.mx",
                    "phone": "+525512345678",
                    "username": "juangomez",
                    "company": "Empresa S.A. de C.V.",
                    "domain": "empresa.com.mx",
                    "social_profiles": [
                        {
                            "platform": "linkedin",
                            "username": "juangomez",
                            "display_name": "Juan Gomez Rodriguez",
                        },
                        {
                            "platform": "github",
                            "username": "juangomez",
                            "display_name": "Juan Gomez",
                        },
                    ],
                }
            ]
        }
    }


class TrustContext(BaseModel):
    """
    Contexto completo para el cálculo del puntaje de confianza (trust score).

    Incluye los resultados de todas las verificaciones, screening
    e inteligencia digital realizadas previamente.

    Attributes:
        renapo_valid: Si la CURP fue validada exitosamente por RENAPO.
        rfc_valid: Si el RFC pasó la validación de formato y dígito verificador.
        sat_active: Si el RFC está activo en el SAT.
        screening_clean: Si el screening en listas restrictivas no arrojó coincidencias.
        professional_presence: Si se detectó presencia profesional (LinkedIn, etc.).
        github_active: Si se encontró un perfil activo en GitHub.
        linkedin_found: Si se encontró un perfil en LinkedIn.
        email_verifiable: Si el correo electrónico es verificable (MX + entregable).
        phone_valid: Si el número telefónico es válido.
        verification_details: Detalles adicionales de cada verificación.
    """

    renapo_valid: bool = Field(
        default=False,
        description="Si la CURP fue validada exitosamente por RENAPO.",
    )
    rfc_valid: bool = Field(
        default=False,
        description="Si el RFC pasó la validación de formato y dígito verificador.",
    )
    sat_active: bool = Field(
        default=False,
        description="Si el RFC está activo en el SAT.",
    )
    screening_clean: bool = Field(
        default=False,
        description="Si el screening en listas restrictivas no arrojó coincidencias.",
    )
    professional_presence: bool = Field(
        default=False,
        description="Si se detectó presencia profesional (LinkedIn, sitio web, etc.).",
    )
    github_active: bool = Field(
        default=False,
        description="Si se encontró un perfil activo en GitHub.",
    )
    linkedin_found: bool = Field(
        default=False,
        description="Si se encontró un perfil en LinkedIn.",
    )
    email_verifiable: bool = Field(
        default=False,
        description="Si el correo electrónico es verificable (MX + entregable).",
    )
    phone_valid: bool = Field(
        default=False,
        description="Si el número telefónico es válido.",
    )
    verification_details: Dict[str, Any] = Field(
        default_factory=dict,
        description="Detalles adicionales de cada verificación realizada.",
    )


class RiskContext(BaseModel):
    """
    Contexto completo para la evaluación de riesgo.

    Incluye los resultados de screening, verificaciones fallidas,
    inteligencia digital y resultados de correlación.

    Attributes:
        rnd_positive: Si la persona aparece en el Registro Nacional de Detenciones.
        ofac_match: Si hay coincidencia en la lista OFAC SDN.
        un_match: Si hay coincidencia en la lista de sanciones de la ONU.
        interpol_match: Si hay coincidencia en avisos de Interpol.
        open_sanctions_match: Si hay coincidencia en OpenSanctions.
        pep_identified: Si la persona está identificada como PEP.
        sat_69b_listed: Si el RFC está listado en el artículo 69-B del SAT.
        identity_inconsistent: Si la correlación de identidad reveló inconsistencias.
        email_disposable: Si el correo electrónico usa un dominio desechable.
        multiple_identities: Si se detectaron múltiples identidades asociadas.
        no_digital_presence: Si no se encontró presencia digital alguna.
        phone_voip_suspicious: Si el teléfono es VoIP o sospechoso.
        screening_details: Detalles del screening en listas restrictivas.
        correlation_result: Resultados de la correlación de identidad.
        digital_intel_details: Detalles de la inteligencia digital.
    """

    rnd_positive: bool = Field(
        default=False,
        description="Si la persona aparece en el Registro Nacional de Detenciones.",
    )
    ofac_match: bool = Field(
        default=False,
        description="Si hay coincidencia en la lista OFAC SDN.",
    )
    un_match: bool = Field(
        default=False,
        description="Si hay coincidencia en la lista de sanciones de la ONU.",
    )
    interpol_match: bool = Field(
        default=False,
        description="Si hay coincidencia en avisos de Interpol.",
    )
    open_sanctions_match: bool = Field(
        default=False,
        description="Si hay coincidencia en OpenSanctions.",
    )
    pep_identified: bool = Field(
        default=False,
        description="Si la persona está identificada como PEP.",
    )
    sat_69b_listed: bool = Field(
        default=False,
        description="Si el RFC está listado en el artículo 69-B del SAT.",
    )
    identity_inconsistent: bool = Field(
        default=False,
        description="Si la correlación de identidad reveló inconsistencias significativas.",
    )
    email_disposable: bool = Field(
        default=False,
        description="Si el correo electrónico usa un dominio desechable.",
    )
    multiple_identities: bool = Field(
        default=False,
        description="Si se detectaron múltiples identidades asociadas a los mismos datos.",
    )
    no_digital_presence: bool = Field(
        default=False,
        description="Si no se encontró presencia digital alguna.",
    )
    phone_voip_suspicious: bool = Field(
        default=False,
        description="Si el teléfono es VoIP o sospechoso.",
    )
    screening_details: Dict[str, Any] = Field(
        default_factory=dict,
        description="Detalles del screening en listas restrictivas.",
    )
    correlation_confidence: Optional[float] = Field(
        default=None,
        ge=0.0,
        le=100.0,
        description="Puntuación de confianza de la correlación de identidad (0-100).",
    )
    digital_intel_details: Dict[str, Any] = Field(
        default_factory=dict,
        description="Detalles de la inteligencia digital.",
    )


# ---------------------------------------------------------------------------
# Esquemas de salida — Correlación
# ---------------------------------------------------------------------------
class CorrelationSignal(BaseModel):
    """
    Señal individual de correlación de identidad.

    Cada señal representa una verificación específica de consistencia
    entre los diferentes datos de identidad proporcionados.

    Attributes:
        name: Nombre descriptivo de la señal de correlación.
        passed: Si la verificación pasó exitosamente.
        score: Puntuación asignada (0-100) según el resultado.
        weight: Peso relativo de esta señal en el cálculo global.
        details: Descripción detallada del resultado.
    """

    name: str = Field(
        ...,
        description="Nombre descriptivo de la señal de correlación.",
        examples=["Consistencia CURP-RFC"],
    )
    passed: bool = Field(
        ...,
        description="Si la verificación de correlación pasó exitosamente.",
    )
    score: float = Field(
        ...,
        ge=0.0,
        le=100.0,
        description="Puntuación asignada según el resultado (0-100).",
    )
    weight: float = Field(
        ...,
        ge=0.0,
        le=1.0,
        description="Peso relativo de esta señal en el cálculo global (0-1).",
    )
    details: str = Field(
        default="",
        description="Descripción detallada del resultado de la correlación.",
    )

    model_config = {"from_attributes": True}


class CorrelationResult(BaseModel):
    """
    Resultado completo de la correlación de identidad.

    Combina todas las señales de correlación para producir una
    puntuación de confianza de identidad global.

    Attributes:
        identity_confidence: Puntuación de confianza de identidad (0-100).
        signals: Lista de señales de correlación evaluadas.
        warnings: Advertencias detectadas durante la correlación.
        flags: Indicadores de alerta activados.
    """

    identity_confidence: float = Field(
        ...,
        ge=0.0,
        le=100.0,
        description=(
            "Puntuación de confianza de identidad (0-100). "
            "95-100: todas las señales consistentes. "
            "70-94: inconsistencias menores. "
            "30-69: inconsistencias mayores. "
            "0-29: señales contradictorias."
        ),
    )
    signals: List[CorrelationSignal] = Field(
        default_factory=list,
        description="Lista de señales de correlación evaluadas.",
    )
    warnings: List[str] = Field(
        default_factory=list,
        description="Advertencias detectadas durante la correlación de identidad.",
    )
    flags: List[str] = Field(
        default_factory=list,
        description="Indicadores de alerta activados durante la correlación.",
    )

    model_config = {"from_attributes": True}


# ---------------------------------------------------------------------------
# Esquemas de salida — Trust Score
# ---------------------------------------------------------------------------
class ScoreContributor(BaseModel):
    """
    Contribuyente individual al puntaje de confianza (trust score).

    Attributes:
        name: Nombre descriptivo del factor contribuyente.
        points: Puntos obtenidos por este factor.
        max_points: Puntos máximos posibles para este factor.
        passed: Si el factor se cumplió exitosamente.
        details: Descripción del resultado.
    """

    name: str = Field(
        ...,
        description="Nombre descriptivo del factor contribuyente al trust score.",
        examples=["RENAPO válido"],
    )
    points: float = Field(
        ...,
        ge=0.0,
        description="Puntos obtenidos por este factor.",
    )
    max_points: float = Field(
        ...,
        gt=0.0,
        description="Puntos máximos posibles para este factor.",
    )
    passed: bool = Field(
        ...,
        description="Si el factor contribuyente se cumplió exitosamente.",
    )
    details: str = Field(
        default="",
        description="Descripción del resultado de este factor.",
    )

    model_config = {"from_attributes": True}


class TrustScoreResult(BaseModel):
    """
    Resultado completo del cálculo del puntaje de confianza.

    Attributes:
        score: Puntuación de confianza obtenida (0-100).
        max_possible: Puntuación máxima posible.
        contributors: Lista de factores contribuyentes con su detalle.
        level: Nivel de confianza categorizado.
    """

    score: float = Field(
        ...,
        ge=0.0,
        le=100.0,
        description="Puntuación de confianza obtenida (0-100).",
    )
    max_possible: float = Field(
        default=100.0,
        description="Puntuación máxima posible del trust score.",
    )
    contributors: List[ScoreContributor] = Field(
        default_factory=list,
        description="Lista de factores contribuyentes al trust score.",
    )
    level: TrustLevel = Field(
        ...,
        description=(
            "Nivel de confianza categorizado: "
            "very_high (90+), high (70-89), medium (50-69), low (30-49), very_low (0-29)."
        ),
    )

    model_config = {"from_attributes": True}


# ---------------------------------------------------------------------------
# Esquemas de salida — Risk Assessment
# ---------------------------------------------------------------------------
class RiskFactor(BaseModel):
    """
    Factor de riesgo individual identificado en la evaluación.

    Attributes:
        name: Nombre descriptivo del factor de riesgo.
        score: Puntuación de riesgo asignada (contribución al risk_score).
        severity: Severidad del factor (critical, high, medium, low).
        details: Descripción detallada del factor de riesgo.
    """

    name: str = Field(
        ...,
        description="Nombre descriptivo del factor de riesgo.",
        examples=["Coincidencia en lista OFAC SDN"],
    )
    score: float = Field(
        ...,
        ge=0.0,
        description="Puntuación de riesgo asignada por este factor.",
    )
    severity: Severity = Field(
        ...,
        description="Severidad del factor de riesgo: critical, high, medium, low.",
    )
    details: str = Field(
        default="",
        description="Descripción detallada del factor de riesgo.",
    )

    model_config = {"from_attributes": True}


class MitigatingFactor(BaseModel):
    """
    Factor mitigante que reduce la puntuación de riesgo.

    Attributes:
        name: Nombre descriptivo del factor mitigante.
        points_reduced: Puntos de riesgo reducidos por este factor.
        details: Descripción del factor mitigante.
    """

    name: str = Field(
        ...,
        description="Nombre descriptivo del factor mitigante.",
        examples=["Identidad verificada por RENAPO"],
    )
    points_reduced: float = Field(
        ...,
        ge=0.0,
        description="Puntos de riesgo reducidos por este factor mitigante.",
    )
    details: str = Field(
        default="",
        description="Descripción del factor mitigante.",
    )

    model_config = {"from_attributes": True}


class RiskAssessmentResult(BaseModel):
    """
    Resultado completo de la evaluación de riesgo.

    Attributes:
        risk_score: Puntuación de riesgo (0-100, señales negativas).
        trust_score: Puntuación de confianza (señales positivas).
        recommendation: Recomendación de decisión (APPROVE, REVIEW, REJECT).
        risk_factors: Lista de factores de riesgo identificados.
        mitigating_factors: Lista de factores mitigantes identificados.
    """

    risk_score: float = Field(
        ...,
        ge=0.0,
        le=100.0,
        description=(
            "Puntuación de riesgo (0-100, señales negativas). "
            "0-15: aprobado, 16-40: revisión, >40: rechazo."
        ),
    )
    trust_score: float = Field(
        ...,
        ge=0.0,
        le=100.0,
        description="Puntuación de confianza derivada del trust score (señales positivas).",
    )
    recommendation: Recommendation = Field(
        ...,
        description=(
            "Recomendación de decisión: "
            "APPROVE (riesgo ≤ 15), REVIEW (riesgo 16-40), REJECT (riesgo > 40). "
            "Cualquier coincidencia crítica (OFAC, RND) resulta en REJECT automático."
        ),
    )
    risk_factors: List[RiskFactor] = Field(
        default_factory=list,
        description="Lista de factores de riesgo identificados.",
    )
    mitigating_factors: List[MitigatingFactor] = Field(
        default_factory=list,
        description="Lista de factores mitigantes identificados.",
    )

    model_config = {"from_attributes": True}


# ---------------------------------------------------------------------------
# Esquema de respuesta completa
# ---------------------------------------------------------------------------
class FullIdentityResponse(BaseModel):
    """
    Respuesta completa de la evaluación de identidad.

    Combina los resultados de correlación, trust score y evaluación
    de riesgo en una sola respuesta consolidada.

    Attributes:
        id: Identificador único de la evaluación.
        identity_data: Datos de identidad proporcionados como entrada.
        correlation: Resultado de la correlación de identidad.
        trust_score: Resultado del cálculo de confianza.
        risk_assessment: Resultado de la evaluación de riesgo.
        evaluated_at: Fecha y hora de la evaluación.
    """

    id: str = Field(
        ...,
        description="Identificador único de la evaluación de identidad.",
    )
    identity_data: IdentityData = Field(
        ...,
        description="Datos de identidad proporcionados como entrada.",
    )
    correlation: CorrelationResult = Field(
        ...,
        description="Resultado de la correlación de identidad.",
    )
    trust_score: TrustScoreResult = Field(
        ...,
        description="Resultado del cálculo del puntaje de confianza.",
    )
    risk_assessment: RiskAssessmentResult = Field(
        ...,
        description="Resultado de la evaluación de riesgo.",
    )
    evaluated_at: datetime = Field(
        default_factory=datetime.now,
        description="Fecha y hora en que se realizó la evaluación.",
    )

    model_config = {"from_attributes": True}


# ---------------------------------------------------------------------------
# Esquemas para consulta de resultados previos
# ---------------------------------------------------------------------------
class IdentityCorrelationDetail(BaseModel):
    """
    Detalle de una evaluación de identidad previa almacenada.

    Attributes:
        id: Identificador único.
        name: Nombre evaluado.
        curp: CURP evaluada.
        rfc: RFC evaluado.
        identity_confidence: Puntuación de confianza de identidad.
        signals: Señales de correlación evaluadas (JSON).
        warnings: Advertencias detectadas.
        flags: Indicadores de alerta.
        created_at: Fecha de creación.
    """

    id: str = Field(..., description="Identificador único del registro.")
    name: Optional[str] = Field(default=None, description="Nombre evaluado.")
    curp: Optional[str] = Field(default=None, description="CURP evaluada.")
    rfc: Optional[str] = Field(default=None, description="RFC evaluado.")
    email: Optional[str] = Field(default=None, description="Correo evaluado.")
    phone: Optional[str] = Field(default=None, description="Teléfono evaluado.")
    identity_confidence: float = Field(
        ..., description="Puntuación de confianza de identidad."
    )
    signals: Optional[List[Dict[str, Any]]] = Field(
        default=None, description="Señales de correlación evaluadas."
    )
    warnings: Optional[List[str]] = Field(
        default=None, description="Advertencias detectadas."
    )
    flags: Optional[List[str]] = Field(
        default=None, description="Indicadores de alerta."
    )
    created_at: Optional[str] = Field(
        default=None, description="Fecha de creación."
    )

    model_config = {"from_attributes": True}


class RiskAssessmentDetail(BaseModel):
    """
    Detalle de una evaluación de riesgo previa almacenada.

    Attributes:
        id: Identificador único.
        correlation_id: ID de la correlación asociada.
        trust_score: Puntuación de confianza.
        risk_score: Puntuación de riesgo.
        recommendation: Recomendación (APPROVE/REVIEW/REJECT).
        risk_factors: Factores de riesgo identificados.
        mitigating_factors: Factores mitigantes identificados.
        created_at: Fecha de creación.
    """

    id: str = Field(..., description="Identificador único del registro.")
    correlation_id: str = Field(
        ..., description="ID de la correlación de identidad asociada."
    )
    trust_score: float = Field(..., description="Puntuación de confianza.")
    risk_score: float = Field(..., description="Puntuación de riesgo.")
    recommendation: str = Field(
        ..., description="Recomendación: APPROVE, REVIEW o REJECT."
    )
    risk_factors: Optional[List[Dict[str, Any]]] = Field(
        default=None, description="Factores de riesgo identificados."
    )
    mitigating_factors: Optional[List[Dict[str, Any]]] = Field(
        default=None, description="Factores mitigantes identificados."
    )
    created_at: Optional[str] = Field(
        default=None, description="Fecha de creación."
    )

    model_config = {"from_attributes": True}
