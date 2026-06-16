"""
Router de identidad — Correlación, trust score y evaluación de riesgo.

Endpoints para la evaluación integral de identidad que combina:
- Correlación cruzada de señales de identidad
- Cálculo del puntaje de confianza (trust score)
- Evaluación de riesgo y recomendación de decisión

Todos los mensajes de error y descripciones están en español.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Optional
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, status
from redis.asyncio import Redis
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.dependencies import db_session, get_current_active_user, redis_client
from app.models.identity import IdentityCorrelation, RecommendationType, RiskAssessment
from app.schemas.identity import (
    CorrelationResult,
    FullIdentityResponse,
    IdentityCorrelationDetail,
    IdentityData,
    RiskAssessmentResult,
    RiskContext,
    TrustContext,
    TrustScoreResult,
)
from app.services.identity_correlation import IdentityCorrelationService
from app.services.risk_engine import RiskEngineService
from app.services.trust_score import TrustScoreService

logger = logging.getLogger(__name__)

router = APIRouter()


# ---------------------------------------------------------------------------
# Helpers de conversión
# ---------------------------------------------------------------------------
def _calculate_trust_context_from_correlation(
    identity_data: IdentityData,
    correlation: CorrelationResult,
) -> TrustContext:
    """
    Deriva un TrustContext a partir de los datos de identidad y
    los resultados de la correlación.

    Nota: En un flujo de producción completo, el TrustContext se construiría
    con los resultados reales de RENAPO, SAT, etc. Aquí usamos heurísticas
    basadas en la correlación como aproximación razonable.
    """
    # Determinar RENAPO válido: si la CURP tiene formato válido
    renapo_valid = False
    if identity_data.curp:
        from app.utils.curp_algorithm import validate_curp_format
        renapo_valid = validate_curp_format(identity_data.curp)

    # Determinar RFC válido
    rfc_valid = False
    if identity_data.rfc:
        from app.utils.rfc_algorithm import validate_rfc_format
        is_valid, _ = validate_rfc_format(identity_data.rfc)
        rfc_valid = is_valid

    # Determinar screening limpio (asumido si no hay flags de screening)
    screening_clean = "ALERTA_CONSISTENCIA_CURP_RFC" not in correlation.flags

    # Presencia profesional: si hay perfiles sociales o dominio corporativo
    professional_presence = (
        len(identity_data.social_profiles) > 0
        or (identity_data.company is not None and identity_data.domain is not None)
    )

    # GitHub activo
    github_active = any(
        p.platform.lower() == "github" for p in identity_data.social_profiles
    )

    # LinkedIn encontrado
    linkedin_found = any(
        p.platform.lower() == "linkedin" for p in identity_data.social_profiles
    )

    # Correo verificable (heuristic: no es desechable)
    email_verifiable = False
    if identity_data.email:
        from app.services.identity_correlation import _is_disposable_email
        email_verifiable = not _is_disposable_email(identity_data.email)

    # Teléfono válido (heuristic: tiene formato E.164)
    phone_valid = False
    if identity_data.phone:
        phone_valid = identity_data.phone.startswith("+") and len(identity_data.phone) >= 10

    return TrustContext(
        renapo_valid=renapo_valid,
        rfc_valid=rfc_valid,
        sat_active=False,  # Requiere consulta real al SAT
        screening_clean=screening_clean,
        professional_presence=professional_presence,
        github_active=github_active,
        linkedin_found=linkedin_found,
        email_verifiable=email_verifiable,
        phone_valid=phone_valid,
        verification_details={
            "correlation_confidence": correlation.identity_confidence,
            "correlation_flags": correlation.flags,
        },
    )


def _calculate_risk_context_from_results(
    identity_data: IdentityData,
    correlation: CorrelationResult,
    trust_result: TrustScoreResult,
) -> RiskContext:
    """
    Deriva un RiskContext a partir de los resultados de correlación y trust score.

    Nota: En un flujo de producción completo, el RiskContext se construiría
    con los resultados reales del screening. Aquí usamos heurísticas.
    """
    # Identidad inconsistente si la confianza es baja
    identity_inconsistent = correlation.identity_confidence < 50

    # Correo desechable
    email_disposable = False
    if identity_data.email:
        from app.services.identity_correlation import _is_disposable_email
        email_disposable = _is_disposable_email(identity_data.email)

    # Sin presencia digital
    no_digital_presence = (
        not identity_data.social_profiles
        and not identity_data.email
        and not identity_data.phone
        and not identity_data.username
    )

    # Teléfono VoIP/sospechoso (heurística simple)
    phone_voip_suspicious = False
    if identity_data.phone and not identity_data.phone.startswith("+52"):
        phone_voip_suspicious = True

    return RiskContext(
        identity_inconsistent=identity_inconsistent,
        email_disposable=email_disposable,
        no_digital_presence=no_digital_presence,
        phone_voip_suspicious=phone_voip_suspicious,
        correlation_confidence=correlation.identity_confidence,
    )


# ---------------------------------------------------------------------------
# Endpoint: Correlación de identidad
# ---------------------------------------------------------------------------
@router.post(
    "/correlate",
    response_model=CorrelationResult,
    summary="Correlación de identidad",
    description=(
        "Ejecuta la correlación cruzada de todas las señales de identidad "
        "proporcionadas (nombre, CURP, RFC, correo, teléfono, redes sociales) "
        "para determinar la consistencia y confianza de la identidad declarada. "
        "Produce un puntaje identity_confidence (0-100)."
    ),
    responses={
        200: {"description": "Correlación completada exitosamente."},
        400: {"description": "Datos de entrada inválidos."},
        500: {"description": "Error interno del servidor."},
    },
)
async def correlate_identity(
    identity_data: IdentityData,
    # current_user: dict = Depends(get_current_active_user),
) -> CorrelationResult:
    """
    Ejecuta la correlación cruzada de señales de identidad.

    Evalúa 6 señales de correlación: consistencia del nombre,
    consistencia CURP-RFC, correlación correo-teléfono, coincidencia
    en redes sociales, verificación empresa/dominio y consistencia
    de nombre de usuario.
    """
    service = IdentityCorrelationService()

    try:
        result = await service.correlate(identity_data)
        return result

    except Exception as exc:
        logger.error("Error en correlación de identidad: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=(
                "Error interno al realizar la correlación de identidad. "
                "Intente de nuevo más tarde."
            ),
        ) from exc


# ---------------------------------------------------------------------------
# Endpoint: Trust Score
# ---------------------------------------------------------------------------
@router.post(
    "/trust-score",
    response_model=TrustScoreResult,
    summary="Cálculo del puntaje de confianza (Trust Score)",
    description=(
        "Calcula el puntaje de confianza de una identidad basándose en "
        "señales positivas: RENAPO válido (+20), RFC válido (+15), "
        "SAT activo (+15), screening limpio (+20), presencia profesional (+10), "
        "GitHub activo (+5), LinkedIn (+5), correo verificable (+5), "
        "teléfono válido (+5). Máximo: 100 puntos."
    ),
    responses={
        200: {"description": "Cálculo completado exitosamente."},
        400: {"description": "Datos de entrada inválidos."},
        500: {"description": "Error interno del servidor."},
    },
)
async def calculate_trust_score(
    context: TrustContext,
    # current_user: dict = Depends(get_current_active_user),
) -> TrustScoreResult:
    """
    Calcula el puntaje de confianza de una identidad.

    Evalúa 9 factores contribuyentes basados en los resultados
    de verificaciones previas y produce un trust score con nivel
    categorizado (very_high/high/medium/low/very_low).
    """
    service = TrustScoreService()

    try:
        result = await service.calculate(context)
        return result

    except Exception as exc:
        logger.error("Error en cálculo de trust score: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=(
                "Error interno al calcular el puntaje de confianza. "
                "Intente de nuevo más tarde."
            ),
        ) from exc


# ---------------------------------------------------------------------------
# Endpoint: Evaluación completa de identidad
# ---------------------------------------------------------------------------
@router.post(
    "/assess",
    response_model=FullIdentityResponse,
    summary="Evaluación completa de identidad",
    description=(
        "Realiza la evaluación integral de identidad combinando: "
        "1) Correlación cruzada de señales, 2) Cálculo del trust score, "
        "3) Evaluación de riesgo con recomendación de decisión "
        "(APPROVE/REVIEW/REJECT). Persiste los resultados para consulta posterior."
    ),
    responses={
        200: {"description": "Evaluación completada exitosamente."},
        400: {"description": "Datos de entrada inválidos."},
        500: {"description": "Error interno del servidor."},
    },
)
async def assess_identity(
    identity_data: IdentityData,
    session: AsyncSession = Depends(db_session),
    redis: Redis = Depends(redis_client),
    # current_user: dict = Depends(get_current_active_user),
) -> FullIdentityResponse:
    """
    Realiza la evaluación integral de identidad.

    Ejecuta en secuencia:
    1. Correlación cruzada de señales de identidad
    2. Cálculo del puntaje de confianza (trust score)
    3. Evaluación de riesgo y recomendación de decisión

    Los resultados se persisten en la base de datos y se
    almacenan en caché para consultas posteriores.
    """
    try:
        # ── 1. Correlación de identidad ──────────────────────────────────
        correlation_service = IdentityCorrelationService()
        correlation_result = await correlation_service.correlate(identity_data)

        # ── 2. Cálculo de trust score ───────────────────────────────────
        trust_context = _calculate_trust_context_from_correlation(
            identity_data, correlation_result
        )
        trust_service = TrustScoreService()
        trust_result = await trust_service.calculate(trust_context)

        # ── 3. Evaluación de riesgo ─────────────────────────────────────
        risk_context = _calculate_risk_context_from_results(
            identity_data, correlation_result, trust_result
        )
        risk_service = RiskEngineService()
        risk_result = await risk_service.assess(
            risk_context, trust_score=trust_result.score
        )

        # ── 4. Persistir resultados ─────────────────────────────────────
        evaluation_id = str(uuid4())

        correlation_record = IdentityCorrelation(
            id=evaluation_id,
            name=identity_data.name,
            curp=identity_data.curp,
            rfc=identity_data.rfc,
            email=identity_data.email,
            phone=identity_data.phone,
            username=identity_data.username,
            company=identity_data.company,
            domain=identity_data.domain,
            identity_confidence=correlation_result.identity_confidence,
            signals=[s.model_dump() for s in correlation_result.signals],
            warnings=correlation_result.warnings,
            flags=correlation_result.flags,
        )
        session.add(correlation_record)

        risk_record = RiskAssessment(
            correlation_id=evaluation_id,
            trust_score=risk_result.trust_score,
            risk_score=risk_result.risk_score,
            recommendation=risk_result.recommendation.value,
            risk_factors=[rf.model_dump() for rf in risk_result.risk_factors],
            mitigating_factors=[mf.model_dump() for mf in risk_result.mitigating_factors],
        )
        session.add(risk_record)

        await session.flush()

        # ── 5. Cachear resultado ────────────────────────────────────────
        try:
            cache_key = f"identity_assessment:{evaluation_id}"
            await redis.setex(
                cache_key,
                3600,  # 1 hora
                FullIdentityResponse(
                    id=evaluation_id,
                    identity_data=identity_data,
                    correlation=correlation_result,
                    trust_score=trust_result,
                    risk_assessment=risk_result,
                    evaluated_at=datetime.now(timezone.utc),
                ).model_dump_json(),
            )
        except Exception as cache_exc:
            logger.warning("Error al cachear resultado de evaluación: %s", cache_exc)

        return FullIdentityResponse(
            id=evaluation_id,
            identity_data=identity_data,
            correlation=correlation_result,
            trust_score=trust_result,
            risk_assessment=risk_result,
            evaluated_at=datetime.now(timezone.utc),
        )

    except HTTPException:
        raise
    except Exception as exc:
        logger.error("Error en evaluación completa de identidad: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=(
                "Error interno al realizar la evaluación de identidad. "
                "Intente de nuevo más tarde."
            ),
        ) from exc


# ---------------------------------------------------------------------------
# Endpoint: Consulta de evaluación previa
# ---------------------------------------------------------------------------
@router.get(
    "/{assessment_id}",
    response_model=IdentityCorrelationDetail,
    summary="Consultar evaluación de identidad previa",
    description=(
        "Recupera los resultados de una evaluación de identidad previa "
        "usando su identificador único."
    ),
    responses={
        200: {"description": "Evaluación encontrada."},
        404: {"description": "Evaluación no encontrada."},
    },
)
async def get_identity_assessment(
    assessment_id: str,
    session: AsyncSession = Depends(db_session),
    # current_user: dict = Depends(get_current_active_user),
) -> IdentityCorrelationDetail:
    """
    Recupera el resultado de una evaluación de identidad previa.

    Args:
        assessment_id: Identificador único de la evaluación.
    """
    try:
        # Intentar recuperar de caché primero
        redis = None
        try:
            from app.database import get_redis
            redis = get_redis()
            cache_key = f"identity_assessment:{assessment_id}"
            cached = await redis.get(cache_key)
            if cached:
                import json
                cached_data = json.loads(cached)
                return IdentityCorrelationDetail(
                    id=cached_data.get("id", assessment_id),
                    name=cached_data.get("identity_data", {}).get("name"),
                    curp=cached_data.get("identity_data", {}).get("curp"),
                    rfc=cached_data.get("identity_data", {}).get("rfc"),
                    email=cached_data.get("identity_data", {}).get("email"),
                    phone=cached_data.get("identity_data", {}).get("phone"),
                    identity_confidence=cached_data.get("correlation", {}).get(
                        "identity_confidence", 0.0
                    ),
                    signals=cached_data.get("correlation", {}).get("signals"),
                    warnings=cached_data.get("correlation", {}).get("warnings"),
                    flags=cached_data.get("correlation", {}).get("flags"),
                    created_at=cached_data.get("evaluated_at"),
                )
        except Exception:
            pass  # Si falla el caché, ir a la base de datos

        # Consultar en la base de datos
        stmt = select(IdentityCorrelation).where(
            IdentityCorrelation.id == assessment_id
        )
        db_result = await session.execute(stmt)
        correlation = db_result.scalar_one_or_none()

        if correlation is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=(
                    f"Evaluación de identidad con ID '{assessment_id}' "
                    f"no encontrada."
                ),
            )

        return IdentityCorrelationDetail(
            id=correlation.id,
            name=correlation.name,
            curp=correlation.curp,
            rfc=correlation.rfc,
            email=correlation.email,
            phone=correlation.phone,
            identity_confidence=correlation.identity_confidence,
            signals=correlation.signals,
            warnings=correlation.warnings,
            flags=correlation.flags,
            created_at=(
                correlation.created_at.isoformat()
                if correlation.created_at
                else None
            ),
        )

    except HTTPException:
        raise
    except Exception as exc:
        logger.error(
            "Error consultando evaluación de identidad %s: %s",
            assessment_id,
            exc,
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error interno al consultar la evaluación de identidad.",
        ) from exc


# ---------------------------------------------------------------------------
# Endpoint: Estado del servicio
# ---------------------------------------------------------------------------
@router.get(
    "/",
    summary="Estado del servicio de identidad",
    description="Retorna el estado del servicio de inteligencia de identidad.",
)
async def identity_root():
    """Retorna el estado del servicio de inteligencia de identidad."""
    return {
        "service": "identity",
        "status": "active",
        "capabilities": [
            "correlate",
            "trust-score",
            "assess",
        ],
        "version": "2.0.0",
    }
