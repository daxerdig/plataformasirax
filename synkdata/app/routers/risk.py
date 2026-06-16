"""
Router de riesgo — Análisis de riesgo y scoring de identidad.

Endpoints para la evaluación de riesgo de identidad que incluye:
- Evaluación completa de riesgo con contexto
- Verificación rápida de screening
- Consulta de evaluaciones previas

Todos los mensajes de error y descripciones están en español.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from redis.asyncio import Redis
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.dependencies import db_session, get_current_active_user, redis_client
from app.models.identity import IdentityCorrelation, RiskAssessment
from app.schemas.identity import (
    Recommendation,
    RiskAssessmentDetail,
    RiskAssessmentResult,
    RiskContext,
)
from app.services.risk_engine import RiskEngineService

logger = logging.getLogger(__name__)

router = APIRouter()


# ---------------------------------------------------------------------------
# Endpoint: Evaluación de riesgo
# ---------------------------------------------------------------------------
@router.post(
    "/assess",
    response_model=RiskAssessmentResult,
    summary="Evaluación de riesgo de identidad",
    description=(
        "Evalúa el nivel de riesgo de una identidad basándose en señales "
        "negativas del screening, verificaciones fallidas, inteligencia "
        "digital y resultados de correlación. Produce un risk_score (0-100), "
        "trust_score y una recomendación de decisión (APPROVE/REVIEW/REJECT). "
        "Cualquier coincidencia crítica (OFAC, RND, OpenSanctions) resulta "
        "en REJECT automático."
    ),
    responses={
        200: {"description": "Evaluación completada exitosamente."},
        400: {"description": "Datos de entrada inválidos."},
        500: {"description": "Error interno del servidor."},
    },
)
async def assess_risk(
    context: RiskContext,
    # current_user: dict = Depends(get_current_active_user),
) -> RiskAssessmentResult:
    """
    Ejecuta la evaluación de riesgo de identidad.

    Analiza 11 factores de riesgo:
    - Críticos: RND (+100), OFAC (+100), OpenSanctions (+100)
    - Altos: ONU (+90), Interpol (+90), SAT 69-B (+50), Identidad inconsistente (+50)
    - Medios: Múltiples identidades (+40), Correo desechable (+20), Sin presencia digital (+15)
    - Bajos: Teléfono VoIP (+10)

    También evalúa factores mitigantes que reducen el riesgo.
    """
    service = RiskEngineService()

    try:
        result = await service.assess(context)
        return result

    except Exception as exc:
        logger.error("Error en evaluación de riesgo: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=(
                "Error interno al realizar la evaluación de riesgo. "
                "Intente de nuevo más tarde."
            ),
        ) from exc


# ---------------------------------------------------------------------------
# Endpoint: Verificación rápida de screening
# ---------------------------------------------------------------------------
@router.post(
    "/quick",
    response_model=RiskAssessmentResult,
    summary="Verificación rápida de riesgo (solo screening)",
    description=(
        "Realiza una verificación rápida de riesgo basada únicamente en "
        "los resultados del screening en listas restrictivas. Útil para "
        "una evaluación inicial antes de realizar el análisis completo. "
        "Parámetros booleanos para cada lista: ofac, open_sanctions, "
        "un_sanctions, interpol, rnd."
    ),
    responses={
        200: {"description": "Verificación completada."},
        400: {"description": "Datos de entrada inválidos."},
        500: {"description": "Error interno del servidor."},
    },
)
async def quick_risk_check(
    ofac: bool = False,
    open_sanctions: bool = False,
    un_sanctions: bool = False,
    interpol: bool = False,
    rnd: bool = False,
    # current_user: dict = Depends(get_current_active_user),
) -> RiskAssessmentResult:
    """
    Realiza una verificación rápida de riesgo basada en screening.

    Evalúa solo las coincidencias en listas restrictivas sin
    realizar el análisis completo de identidad. Ideal para un
    primer filtro antes de una evaluación más profunda.

    Args:
        ofac: Si hay coincidencia en OFAC SDN.
        open_sanctions: Si hay coincidencia en OpenSanctions.
        un_sanctions: Si hay coincidencia en la ONU.
        interpol: Si hay coincidencia en Interpol.
        rnd: Si aparece en el RND.
    """
    service = RiskEngineService()

    try:
        result = await service.quick_screening_check(
            ofac_match=ofac,
            open_sanctions_match=open_sanctions,
            un_match=un_sanctions,
            interpol_match=interpol,
            rnd_positive=rnd,
        )
        return result

    except Exception as exc:
        logger.error("Error en verificación rápida de riesgo: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=(
                "Error interno al realizar la verificación rápida. "
                "Intente de nuevo más tarde."
            ),
        ) from exc


# ---------------------------------------------------------------------------
# Endpoint: Consulta de evaluación previa
# ---------------------------------------------------------------------------
@router.get(
    "/{assessment_id}",
    response_model=RiskAssessmentDetail,
    summary="Consultar evaluación de riesgo previa",
    description=(
        "Recupera los resultados de una evaluación de riesgo previa "
        "usando su identificador único."
    ),
    responses={
        200: {"description": "Evaluación encontrada."},
        404: {"description": "Evaluación no encontrada."},
    },
)
async def get_risk_assessment(
    assessment_id: str,
    session: AsyncSession = Depends(db_session),
    # current_user: dict = Depends(get_current_active_user),
) -> RiskAssessmentDetail:
    """
    Recupera el resultado de una evaluación de riesgo previa.

    Args:
        assessment_id: Identificador único de la evaluación.
    """
    try:
        stmt = select(RiskAssessment).where(
            RiskAssessment.id == assessment_id
        )
        db_result = await session.execute(stmt)
        risk_record = db_result.scalar_one_or_none()

        if risk_record is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=(
                    f"Evaluación de riesgo con ID '{assessment_id}' "
                    f"no encontrada."
                ),
            )

        return RiskAssessmentDetail(
            id=risk_record.id,
            correlation_id=risk_record.correlation_id,
            trust_score=risk_record.trust_score,
            risk_score=risk_record.risk_score,
            recommendation=risk_record.recommendation,
            risk_factors=risk_record.risk_factors,
            mitigating_factors=risk_record.mitigating_factors,
            created_at=(
                risk_record.created_at.isoformat()
                if risk_record.created_at
                else None
            ),
        )

    except HTTPException:
        raise
    except Exception as exc:
        logger.error(
            "Error consultando evaluación de riesgo %s: %s",
            assessment_id,
            exc,
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error interno al consultar la evaluación de riesgo.",
        ) from exc


# ---------------------------------------------------------------------------
# Endpoint: Estado del servicio
# ---------------------------------------------------------------------------
@router.get(
    "/",
    summary="Estado del servicio de riesgo",
    description="Retorna el estado del servicio de análisis de riesgo.",
)
async def risk_root():
    """Retorna el estado del servicio de análisis de riesgo y scoring."""
    return {
        "service": "risk",
        "status": "active",
        "capabilities": [
            "assess",
            "quick",
        ],
        "risk_thresholds": {
            "approve": "0-15",
            "review": "16-40",
            "reject": ">40",
            "auto_reject": "OFAC, RND, OpenSanctions",
        },
        "version": "2.0.0",
    }
