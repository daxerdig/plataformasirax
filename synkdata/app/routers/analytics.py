"""
Router de analítica — Métricas, dashboards y monitoreo.

Endpoints para la consulta de métricas de la plataforma de inteligencia
de identidad, incluyendo:
- Dashboard ejecutivo con KPIs principales
- Distribución de riesgo de las verificaciones
- Tendencias temporales de métricas
- Gestión de alertas del sistema
- Métricas regionales y por industria

Todos los mensajes de error y descripciones están en español.
"""

from __future__ import annotations

import logging
from typing import Optional

from fastapi import APIRouter, HTTPException, Query, status

from app.schemas.analytics import (
    AlertResponse,
    ExecutiveDashboard,
    IndustryMetrics,
    RegionalMetrics,
    RiskDistribution,
    TrendData,
)
from app.services.analytics_service import AnalyticsService

logger = logging.getLogger(__name__)

router = APIRouter()


# ---------------------------------------------------------------------------
# Instancia del servicio
# ---------------------------------------------------------------------------
_analytics_service = AnalyticsService()


# ---------------------------------------------------------------------------
# Endpoint: Dashboard ejecutivo
# ---------------------------------------------------------------------------
@router.get(
    "/dashboard",
    response_model=ExecutiveDashboard,
    summary="Dashboard ejecutivo",
    description=(
        "Obtiene las métricas clave de la plataforma para el período "
        "especificado: total de verificaciones, tasa de aprobación, "
        "distribución de riesgo, factores de riesgo principales, "
        "cobertura de screening y tiempo promedio de procesamiento."
    ),
    responses={
        200: {"description": "Dashboard obtenido exitosamente."},
        500: {"description": "Error interno del servidor."},
    },
)
async def get_executive_dashboard(
    days: int = Query(
        default=30,
        ge=1,
        le=365,
        description="Número de días hacia atrás para calcular las métricas.",
    ),
) -> ExecutiveDashboard:
    """
    Retorna el dashboard ejecutivo con métricas clave.

    Incluye:
    - Total de verificaciones en el período
    - Tasa de aprobación (%)
    - Distribución de riesgo (APPROVE/REVIEW/REJECT + niveles)
    - Top 5 factores de riesgo más frecuentes
    - Cobertura de screening en listas restrictivas
    - Tiempo promedio de procesamiento (ms)
    """
    try:
        return await _analytics_service.get_executive_dashboard(days=days)
    except Exception as exc:
        logger.error("Error obteniendo dashboard ejecutivo: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=(
                "Error al obtener el dashboard ejecutivo. "
                "Intente de nuevo más tarde."
            ),
        ) from exc


# ---------------------------------------------------------------------------
# Endpoint: Distribución de riesgo
# ---------------------------------------------------------------------------
@router.get(
    "/risk-distribution",
    response_model=RiskDistribution,
    summary="Distribución de riesgo",
    description=(
        "Obtiene la distribución de riesgo de las verificaciones "
        "realizadas en el período especificado, incluyendo el conteo "
        "por recomendación (APPROVE/REVIEW/REJECT) y por nivel de "
        "riesgo (muy alto/alto/medio/bajo)."
    ),
    responses={
        200: {"description": "Distribución obtenida exitosamente."},
        500: {"description": "Error interno del servidor."},
    },
)
async def get_risk_distribution(
    days: int = Query(
        default=30,
        ge=1,
        le=365,
        description="Número de días hacia atrás.",
    ),
) -> RiskDistribution:
    """
    Retorna la distribución de riesgo de las verificaciones.

    Desglosa las verificaciones por:
    - Recomendación: APPROVE, REVIEW, REJECT
    - Nivel de riesgo: muy alto (>75), alto (50-75), medio (25-50), bajo (0-25)
    """
    try:
        return await _analytics_service.get_risk_distribution(days=days)
    except Exception as exc:
        logger.error("Error obteniendo distribución de riesgo: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=(
                "Error al obtener la distribución de riesgo. "
                "Intente de nuevo más tarde."
            ),
        ) from exc


# ---------------------------------------------------------------------------
# Endpoint: Tendencias
# ---------------------------------------------------------------------------
@router.get(
    "/trends/{metric}",
    response_model=TrendData,
    summary="Tendencias temporales",
    description=(
        "Obtiene la serie temporal de una métrica específica para el "
        "período indicado. Métricas disponibles: verifications, "
        "risk_score, trust_score, approval_rate, processing_time."
    ),
    responses={
        200: {"description": "Tendencias obtenidas exitosamente."},
        400: {"description": "Métrica no válida."},
        500: {"description": "Error interno del servidor."},
    },
)
async def get_trends(
    metric: str,
    days: int = Query(
        default=90,
        ge=1,
        le=365,
        description="Número de días hacia atrás.",
    ),
) -> TrendData:
    """
    Retorna los datos de tendencia de una métrica específica.

    Métricas disponibles:
    - **verifications**: Cantidad de verificaciones por día
    - **risk_score**: Promedio de puntaje de riesgo por día
    - **trust_score**: Promedio de puntaje de confianza por día
    - **approval_rate**: Tasa de aprobación por día (%)
    - **processing_time**: Tiempo promedio de procesamiento por día (ms)

    También incluye el cambio porcentual respecto al período anterior.
    """
    valid_metrics = {
        "verifications",
        "risk_score",
        "trust_score",
        "approval_rate",
        "processing_time",
        "screening_hits",
    }

    if metric not in valid_metrics:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                f"Métrica '{metric}' no válida. "
                f"Métricas disponibles: {', '.join(sorted(valid_metrics))}."
            ),
        )

    try:
        return await _analytics_service.get_trends(
            metric=metric, days=days
        )
    except Exception as exc:
        logger.error(
            "Error obteniendo tendencias para métrica %s: %s", metric, exc
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=(
                "Error al obtener las tendencias. "
                "Intente de nuevo más tarde."
            ),
        ) from exc


# ---------------------------------------------------------------------------
# Endpoint: Alertas
# ---------------------------------------------------------------------------
@router.get(
    "/alerts",
    response_model=list[AlertResponse],
    summary="Lista de alertas",
    description=(
        "Obtiene la lista de alertas del sistema de monitoreo, "
        "ordenadas por fecha de creación descendente. Opcionalmente "
        "se puede filtrar por severidad."
    ),
    responses={
        200: {"description": "Alertas obtenidas exitosamente."},
        500: {"description": "Error interno del servidor."},
    },
)
async def get_alerts(
    severity: Optional[str] = Query(
        default=None,
        description="Filtrar por severidad: critical, high, medium, low, info.",
    ),
    limit: int = Query(
        default=50,
        ge=1,
        le=100,
        description="Número máximo de alertas a retornar.",
    ),
) -> list[AlertResponse]:
    """
    Retorna la lista de alertas del sistema.

    Las alertas se generan automáticamente cuando:
    - Se detecta una coincidencia en listas restrictivas
    - Se supera un umbral de riesgo
    - Se detecta una anomalía en la identidad
    - Falla una verificación
    - Se detecta un patrón sospechoso
    """
    try:
        return await _analytics_service.get_alerts(
            severity=severity, limit=limit
        )
    except Exception as exc:
        logger.error("Error obteniendo alertas: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=(
                "Error al obtener las alertas. "
                "Intente de nuevo más tarde."
            ),
        ) from exc


# ---------------------------------------------------------------------------
# Endpoint: Marcar alerta como leída
# ---------------------------------------------------------------------------
@router.patch(
    "/alerts/{alert_id}/read",
    summary="Marcar alerta como leída",
    description=(
        "Marca una alerta específica como leída por un analista."
    ),
    responses={
        200: {"description": "Alerta marcada como leída."},
        404: {"description": "Alerta no encontrada."},
        500: {"description": "Error interno del servidor."},
    },
)
async def mark_alert_as_read(alert_id: str) -> dict:
    """
    Marca una alerta como leída.

    Args:
        alert_id: Identificador único de la alerta.
    """
    try:
        success = await _analytics_service.mark_alert_as_read(alert_id)

        if not success:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Alerta con ID '{alert_id}' no encontrada.",
            )

        return {
            "message": "Alerta marcada como leída exitosamente.",
            "alert_id": alert_id,
        }

    except HTTPException:
        raise
    except Exception as exc:
        logger.error(
            "Error marcando alerta %s como leída: %s", alert_id, exc
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error al marcar la alerta como leída.",
        ) from exc


# ---------------------------------------------------------------------------
# Endpoint: Métricas regionales
# ---------------------------------------------------------------------------
@router.get(
    "/regional",
    response_model=RegionalMetrics,
    summary="Métricas regionales",
    description=(
        "Obtiene las métricas desglosadas por región geográfica "
        "(estados de México), incluyendo volumen de verificaciones, "
        "tasa de riesgo y principales problemas detectados."
    ),
    responses={
        200: {"description": "Métricas regionales obtenidas exitosamente."},
        500: {"description": "Error interno del servidor."},
    },
)
async def get_regional_metrics(
    days: int = Query(
        default=30,
        ge=1,
        le=365,
        description="Número de días hacia atrás.",
    ),
) -> RegionalMetrics:
    """
    Retorna las métricas desglosadas por región.

    Cada región incluye:
    - Nombre del estado
    - Número de verificaciones
    - Tasa de riesgo promedio
    - Principales problemas detectados
    """
    try:
        return await _analytics_service.get_regional_metrics(days=days)
    except Exception as exc:
        logger.error("Error obteniendo métricas regionales: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=(
                "Error al obtener las métricas regionales. "
                "Intente de nuevo más tarde."
            ),
        ) from exc


# ---------------------------------------------------------------------------
# Endpoint: Métricas por industria
# ---------------------------------------------------------------------------
@router.get(
    "/industry",
    response_model=IndustryMetrics,
    summary="Métricas por industria",
    description=(
        "Obtiene las métricas desglosadas por industria o sector, "
        "incluyendo volumen de verificaciones, tasa de riesgo y "
        "problemas comunes detectados."
    ),
    responses={
        200: {"description": "Métricas por industria obtenidas exitosamente."},
        500: {"description": "Error interno del servidor."},
    },
)
async def get_industry_metrics(
    days: int = Query(
        default=30,
        ge=1,
        le=365,
        description="Número de días hacia atrás.",
    ),
) -> IndustryMetrics:
    """
    Retorna las métricas desglosadas por industria.

    Cada industria incluye:
    - Nombre del sector
    - Volumen de verificaciones
    - Tasa de riesgo promedio
    - Problemas comunes detectados
    """
    try:
        return await _analytics_service.get_industry_metrics(days=days)
    except Exception as exc:
        logger.error("Error obteniendo métricas por industria: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=(
                "Error al obtener las métricas por industria. "
                "Intente de nuevo más tarde."
            ),
        ) from exc
