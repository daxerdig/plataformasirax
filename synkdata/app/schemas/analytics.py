"""
Esquemas Pydantic para el módulo de analítica y monitoreo.

Define los modelos de validación y serialización para:
- Solicitudes de dashboard (DashboardRequest)
- Dashboard ejecutivo (ExecutiveDashboard)
- Distribución de riesgo (RiskDistribution)
- Tendencias temporales (TrendData)
- Respuestas de alertas (AlertResponse)
- Métricas regionales (RegionalMetrics)
- Métricas por industria (IndustryMetrics)

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
class AlertSeveritySchema(str, Enum):
    """Severidad de una alerta."""

    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    INFO = "info"


class AlertTypeSchema(str, Enum):
    """Tipo de alerta del sistema."""

    SCREENING_HIT = "screening_hit"
    RISK_THRESHOLD = "risk_threshold"
    IDENTITY_ANOMALY = "identity_anomaly"
    VERIFICATION_FAILED = "verification_failed"
    SYSTEM_ERROR = "system_error"
    COMPLIANCE_REMINDER = "compliance_reminder"
    PATTERN_DETECTED = "pattern_detected"


class MetricType(str, Enum):
    """Métricas disponibles para tendencias."""

    VERIFICATIONS = "verifications"
    RISK_SCORE = "risk_score"
    TRUST_SCORE = "trust_score"
    APPROVAL_RATE = "approval_rate"
    PROCESSING_TIME = "processing_time"
    SCREENING_HITS = "screening_hits"


# ---------------------------------------------------------------------------
# Esquemas de entrada (request)
# ---------------------------------------------------------------------------
class DashboardRequest(BaseModel):
    """
    Solicitud de datos del dashboard ejecutivo.

    Attributes:
        days: Número de días hacia atrás para calcular las métricas.
        region: Filtrar por región específica (opcional).
        industry: Filtrar por industria específica (opcional).
    """

    days: int = Field(
        default=30,
        ge=1,
        le=365,
        description="Número de días hacia atrás para calcular las métricas.",
    )
    region: Optional[str] = Field(
        default=None,
        max_length=100,
        description="Filtrar por región específica (estado de México).",
    )
    industry: Optional[str] = Field(
        default=None,
        max_length=100,
        description="Filtrar por industria específica.",
    )


class TrendsRequest(BaseModel):
    """
    Solicitud de datos de tendencias temporales.

    Attributes:
        metric: Métrica a consultar.
        days: Número de días hacia atrás.
        granularity: Granularidad de los datos (daily/weekly/monthly).
    """

    metric: MetricType = Field(
        description="Métrica a consultar para la tendencia.",
    )
    days: int = Field(
        default=90,
        ge=1,
        le=365,
        description="Número de días hacia atrás para la tendencia.",
    )
    granularity: str = Field(
        default="daily",
        pattern="^(daily|weekly|monthly)$",
        description="Granularidad de los datos: daily, weekly o monthly.",
    )


# ---------------------------------------------------------------------------
# Esquemas de salida (response)
# ---------------------------------------------------------------------------
class RiskDistributionByLevel(BaseModel):
    """
    Distribución de verificaciones por nivel de riesgo.

    Attributes:
        very_high: Cantidad de verificaciones con riesgo muy alto (>75).
        high: Cantidad de verificaciones con riesgo alto (50-75).
        medium: Cantidad de verificaciones con riesgo medio (25-50).
        low: Cantidad de verificaciones con riesgo bajo (0-25).
    """

    very_high: int = Field(
        default=0,
        description="Verificaciones con riesgo muy alto (>75).",
    )
    high: int = Field(
        default=0,
        description="Verificaciones con riesgo alto (50-75).",
    )
    medium: int = Field(
        default=0,
        description="Verificaciones con riesgo medio (25-50).",
    )
    low: int = Field(
        default=0,
        description="Verificaciones con riesgo bajo (0-25).",
    )


class RiskDistribution(BaseModel):
    """
    Distribución de riesgo de las verificaciones.

    Attributes:
        approve_count: Cantidad de verificaciones aprobadas.
        review_count: Cantidad de verificaciones en revisión.
        reject_count: Cantidad de verificaciones rechazadas.
        by_risk_level: Distribución detallada por nivel de riesgo.
    """

    approve_count: int = Field(
        default=0,
        description="Cantidad de verificaciones con recomendación APPROVE.",
    )
    review_count: int = Field(
        default=0,
        description="Cantidad de verificaciones con recomendación REVIEW.",
    )
    reject_count: int = Field(
        default=0,
        description="Cantidad de verificaciones con recomendación REJECT.",
    )
    by_risk_level: RiskDistributionByLevel = Field(
        default_factory=RiskDistributionByLevel,
        description="Distribución detallada por nivel de riesgo.",
    )


class TopRiskFactor(BaseModel):
    """
    Factor de riesgo más frecuente.

    Attributes:
        name: Nombre del factor de riesgo.
        count: Número de veces que se activó.
        percentage: Porcentaje del total de verificaciones.
    """

    name: str = Field(description="Nombre del factor de riesgo.")
    count: int = Field(description="Número de veces que se activó.")
    percentage: float = Field(
        description="Porcentaje del total de verificaciones."
    )


class ScreeningCoverage(BaseModel):
    """
    Cobertura del screening en listas restrictivas.

    Attributes:
        total_screened: Total de verificaciones con screening completo.
        ofac_coverage: Cobertura de la lista OFAC (0-100%).
        un_coverage: Cobertura de la lista de la ONU (0-100%).
        interpol_coverage: Cobertura de avisos de Interpol (0-100%).
        sat_69b_coverage: Cobertura del artículo 69-B del SAT (0-100%).
    """

    total_screened: int = Field(
        default=0,
        description="Total de verificaciones con screening completo.",
    )
    ofac_coverage: float = Field(
        default=0.0,
        description="Cobertura de la lista OFAC (0-100%).",
    )
    un_coverage: float = Field(
        default=0.0,
        description="Cobertura de la lista de la ONU (0-100%).",
    )
    interpol_coverage: float = Field(
        default=0.0,
        description="Cobertura de avisos de Interpol (0-100%).",
    )
    sat_69b_coverage: float = Field(
        default=0.0,
        description="Cobertura del artículo 69-B del SAT (0-100%).",
    )


class ExecutiveDashboard(BaseModel):
    """
    Dashboard ejecutivo con métricas clave de la plataforma.

    Attributes:
        total_verifications: Total de verificaciones en el período.
        approval_rate: Tasa de aprobación (0-100%).
        risk_distribution: Distribución de riesgo de las verificaciones.
        top_risk_factors: Factores de riesgo más frecuentes.
        screening_coverage: Cobertura del screening en listas restrictivas.
        avg_processing_time: Tiempo promedio de procesamiento en ms.
    """

    total_verifications: int = Field(
        default=0,
        description="Total de verificaciones realizadas en el período.",
    )
    approval_rate: float = Field(
        default=0.0,
        description="Tasa de aprobación como porcentaje (0-100%).",
    )
    risk_distribution: RiskDistribution = Field(
        default_factory=RiskDistribution,
        description="Distribución de riesgo de las verificaciones.",
    )
    top_risk_factors: List[TopRiskFactor] = Field(
        default_factory=list,
        description="Factores de riesgo más frecuentes.",
    )
    screening_coverage: ScreeningCoverage = Field(
        default_factory=ScreeningCoverage,
        description="Cobertura del screening en listas restrictivas.",
    )
    avg_processing_time: float = Field(
        default=0.0,
        description="Tiempo promedio de procesamiento en milisegundos.",
    )


class TrendDataPoint(BaseModel):
    """
    Punto de datos de una tendencia temporal.

    Attributes:
        date: Fecha del punto de datos.
        value: Valor de la métrica en esa fecha.
    """

    date: str = Field(description="Fecha del punto de datos (YYYY-MM-DD).")
    value: float = Field(description="Valor de la métrica en esa fecha.")


class TrendData(BaseModel):
    """
    Datos de tendencia temporal de una métrica.

    Attributes:
        metric: Nombre de la métrica.
        dates: Lista de fechas.
        values: Lista de valores correspondientes.
        change_percentage: Cambio porcentual respecto al período anterior.
        granularity: Granularidad de los datos (daily/weekly/monthly).
    """

    metric: str = Field(description="Nombre de la métrica consultada.")
    dates: List[str] = Field(
        default_factory=list,
        description="Lista de fechas en formato YYYY-MM-DD.",
    )
    values: List[float] = Field(
        default_factory=list,
        description="Lista de valores correspondientes a cada fecha.",
    )
    change_percentage: float = Field(
        default=0.0,
        description="Cambio porcentual respecto al período anterior.",
    )
    granularity: str = Field(
        default="daily",
        description="Granularidad de los datos: daily, weekly o monthly.",
    )


class AlertResponse(BaseModel):
    """
    Respuesta de una alerta del sistema.

    Attributes:
        id: Identificador único de la alerta.
        severity: Severidad de la alerta.
        type: Tipo de alerta.
        message: Mensaje descriptivo en español.
        entity_id: ID de la entidad asociada.
        created_at: Fecha y hora de creación.
        is_read: Si la alerta ha sido leída.
    """

    id: str = Field(description="Identificador único de la alerta.")
    severity: str = Field(description="Severidad de la alerta.")
    type: str = Field(description="Tipo de alerta.")
    message: str = Field(description="Mensaje descriptivo en español.")
    entity_id: Optional[str] = Field(
        default=None,
        description="ID de la entidad asociada a la alerta.",
    )
    created_at: str = Field(
        description="Fecha y hora de creación (ISO 8601)."
    )
    is_read: bool = Field(
        default=False,
        description="Si la alerta ha sido leída por un analista.",
    )


class RegionData(BaseModel):
    """
    Datos de una región específica.

    Attributes:
        name: Nombre de la región (estado de México).
        verification_count: Número de verificaciones.
        risk_rate: Tasa de riesgo (0-100%).
        top_issues: Principales problemas detectados.
    """

    name: str = Field(description="Nombre de la región (estado de México).")
    verification_count: int = Field(
        default=0,
        description="Número de verificaciones en la región.",
    )
    risk_rate: float = Field(
        default=0.0,
        description="Tasa de riesgo en la región (0-100%).",
    )
    top_issues: List[str] = Field(
        default_factory=list,
        description="Principales problemas detectados en la región.",
    )


class RegionalMetrics(BaseModel):
    """
    Métricas desglosadas por región geográfica.

    Attributes:
        regions: Lista de datos por región.
    """

    regions: List[RegionData] = Field(
        default_factory=list,
        description="Lista de datos por región.",
    )


class IndustryData(BaseModel):
    """
    Datos de una industria específica.

    Attributes:
        name: Nombre de la industria o sector.
        volume: Volumen de verificaciones.
        risk_rate: Tasa de riesgo (0-100%).
        common_issues: Problemas comunes detectados.
    """

    name: str = Field(description="Nombre de la industria o sector.")
    volume: int = Field(
        default=0,
        description="Volumen de verificaciones en la industria.",
    )
    risk_rate: float = Field(
        default=0.0,
        description="Tasa de riesgo en la industria (0-100%).",
    )
    common_issues: List[str] = Field(
        default_factory=list,
        description="Problemas comunes detectados en la industria.",
    )


class IndustryMetrics(BaseModel):
    """
    Métricas desglosadas por industria o sector.

    Attributes:
        industries: Lista de datos por industria.
    """

    industries: List[IndustryData] = Field(
        default_factory=list,
        description="Lista de datos por industria.",
    )
