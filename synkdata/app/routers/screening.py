"""
Router de screening — Consulta en listas restrictivas y de compliance.

Endpoints para el screening de personas físicas y morales contra
múltiples listas restrictivas y de compliance normativo:

- OFAC SDN (Specially Designated Nationals)
- UN Security Council (sanciones del Consejo de Seguridad)
- OpenSanctions (agregador global de sanciones y PEP)
- Interpol Red Notices (avisos rojos)
- SAT 69-B (presunción de operaciones simuladas - México)
- DOF (Diario Oficial de la Federación - México)
- SCJN (Suprema Corte de Justicia de la Nación - México)
- PEP (Personas Políticamente Expuestas)

Todos los mensajes de error y descripciones están en español.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Optional
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.dependencies import db_session, get_current_active_user
from app.models.screening import (
    ScreeningEntityType,
    ScreeningMatch,
    ScreeningRequest,
    ScreeningStatus,
)
from app.schemas.screening import (
    DofResultSchema,
    MatchDetailSchema,
    MatchTypeSchema,
    PepRequest,
    PepResultSchema,
    RiskLevelSchema,
    Sat69bRequest,
    Sat69bResultSchema,
    ScreeningEntityRequest,
    ScreeningPersonRequest,
    ScreeningRequestDetail,
    ScreeningResultSchema,
    ScjnResultSchema,
)
from app.services.compliance_screening import (
    ComplianceScreeningService,
    DofResult,
    MatchDetail,
    PepResult,
    RiskLevel,
    Sat69bResult,
    ScreeningResult,
    ScjnResult,
)

logger = logging.getLogger(__name__)

router = APIRouter()


# ---------------------------------------------------------------------------
# Helpers de conversión interna → schema
# ---------------------------------------------------------------------------
def _to_match_detail_schema(match: MatchDetail) -> MatchDetailSchema:
    """Convierte un MatchDetail interno a MatchDetailSchema."""
    return MatchDetailSchema(
        source=match.source,
        score=match.score,
        match_type=MatchTypeSchema(match.match_type),
        entity_name=match.entity_name,
        entity_data=match.entity_data,
        is_confirmed=match.is_confirmed,
    )


def _to_risk_level_schema(level: RiskLevel) -> RiskLevelSchema:
    """Convierte RiskLevel interno a RiskLevelSchema."""
    mapping = {
        RiskLevel.NONE: RiskLevelSchema.NONE,
        RiskLevel.LOW: RiskLevelSchema.LOW,
        RiskLevel.MEDIUM: RiskLevelSchema.MEDIUM,
        RiskLevel.HIGH: RiskLevelSchema.HIGH,
        RiskLevel.CRITICAL: RiskLevelSchema.CRITICAL,
    }
    return mapping.get(level, RiskLevelSchema.NONE)


def _to_screening_result_schema(result: ScreeningResult) -> ScreeningResultSchema:
    """Convierte un ScreeningResult interno a ScreeningResultSchema."""
    return ScreeningResultSchema(
        request_id=result.request_id,
        matches=[_to_match_detail_schema(m) for m in result.matches],
        total_hits=result.total_hits,
        max_score=result.max_score,
        risk_level=_to_risk_level_schema(result.risk_level),
        sources_checked=result.sources_checked,
        sources_failed=result.sources_failed,
        timestamp=result.timestamp,
    )


def _to_sat69b_schema(result: Sat69bResult) -> Sat69bResultSchema:
    """Convierte un Sat69bResult interno a Sat69bResultSchema."""
    return Sat69bResultSchema(
        is_listed=result.is_listed,
        rfc=result.rfc,
        company_name=result.company_name,
        status=result.status,
        publication_date=result.publication_date,
        docket_number=result.docket_number,
        observations=result.observations,
    )


def _to_pep_schema(result: PepResult) -> PepResultSchema:
    """Convierte un PepResult interno a PepResultSchema."""
    return PepResultSchema(
        is_pep=result.is_pep,
        positions=result.positions,
        country=result.country,
        level=result.level,
        source=result.source,
    )


def _to_dof_schema(result: DofResult) -> DofResultSchema:
    """Convierte un DofResult interno a DofResultSchema."""
    from app.schemas.screening import DofPublicationSchema

    return DofResultSchema(
        has_results=result.has_results,
        publications=[
            DofPublicationSchema(**pub) for pub in result.publications
        ],
        source=result.source,
    )


def _to_scjn_schema(result: ScjnResult) -> ScjnResultSchema:
    """Convierte un ScjnResult interno a ScjnResultSchema."""
    from app.schemas.screening import ScjnCaseSchema

    return ScjnResultSchema(
        has_results=result.has_results,
        cases=[ScjnCaseSchema(**case) for case in result.cases],
        source=result.source,
    )


# ---------------------------------------------------------------------------
# Endpoint: Screening de persona física
# ---------------------------------------------------------------------------
@router.post(
    "/person",
    response_model=ScreeningResultSchema,
    summary="Screening de persona física contra listas restrictivas",
    description=(
        "Realiza el screening completo de una persona física contra todas "
        "las listas restrictivas y de compliance configuradas: OFAC, ONU, "
        "OpenSanctions, Interpol, SAT 69-B, DOF, SCJN y PEP. "
        "Las consultas se ejecutan en paralelo y los resultados se "
        "consolidan con clasificación automática de riesgo."
    ),
    responses={
        200: {"description": "Screening completado exitosamente."},
        400: {"description": "Datos de entrada inválidos."},
        500: {"description": "Error interno del servidor."},
    },
)
async def screen_person(
    request: ScreeningPersonRequest,
    # session: AsyncSession = Depends(db_session),
    # current_user: dict = Depends(get_current_active_user),
) -> ScreeningResultSchema:
    """
    Realiza screening de una persona física contra todas las listas restrictivas.

    Ejecuta consultas paralelas a OFAC, ONU, OpenSanctions, Interpol,
    SAT 69-B, DOF, SCJN y PEP. Aplica comparación difusa y fonética
    a cada fuente y consolida los resultados con deduplicación y
    clasificación automática de riesgo.
    """
    service = ComplianceScreeningService()

    try:
        result = await service.screen_person(
            name=request.name,
            curp=request.curp,
            rfc=request.rfc,
            nationality=request.country,
            threshold=request.threshold,
        )

        # Persistir la solicitud (mejor esfuerzo)
        # await _persist_screening_request(session, request, result, "person")

        return _to_screening_result_schema(result)

    except Exception as exc:
        logger.error("Error en screening de persona: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=(
                "Error interno al realizar el screening. "
                "Intente de nuevo más tarde."
            ),
        ) from exc


# ---------------------------------------------------------------------------
# Endpoint: Screening de persona moral / entidad
# ---------------------------------------------------------------------------
@router.post(
    "/entity",
    response_model=ScreeningResultSchema,
    summary="Screening de persona moral o entidad corporativa",
    description=(
        "Realiza el screening de una persona moral o entidad corporativa "
        "contra las listas restrictivas aplicables: OFAC, ONU, OpenSanctions, "
        "SAT 69-B y DOF."
    ),
    responses={
        200: {"description": "Screening completado exitosamente."},
        400: {"description": "Datos de entrada inválidos."},
        500: {"description": "Error interno del servidor."},
    },
)
async def screen_entity(
    request: ScreeningEntityRequest,
    # session: AsyncSession = Depends(db_session),
    # current_user: dict = Depends(get_current_active_user),
) -> ScreeningResultSchema:
    """
    Realiza screening de una persona moral o entidad corporativa.

    Similar al screening de persona física pero adaptado para
    entidades corporativas (sin PEP, sin SCJN).
    """
    service = ComplianceScreeningService()

    try:
        result = await service.screen_entity(
            name=request.name,
            country=request.country,
            threshold=request.threshold,
        )

        return _to_screening_result_schema(result)

    except Exception as exc:
        logger.error("Error en screening de entidad: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=(
                "Error interno al realizar el screening de la entidad. "
                "Intente de nuevo más tarde."
            ),
        ) from exc


# ---------------------------------------------------------------------------
# Endpoint: Verificación SAT 69-B
# ---------------------------------------------------------------------------
@router.post(
    "/sat-69b",
    response_model=Sat69bResultSchema,
    summary="Verificación en lista SAT 69-B",
    description=(
        "Verifica si un contribuyente está listado en el artículo 69-B "
        "del Código Fiscal de la Federación (presunción de operaciones "
        "simuladas). Los contribuyentes pueden estar en estado 'presunto', "
        "'desvirtuado' o 'definitivo'."
    ),
    responses={
        200: {"description": "Verificación completada."},
        400: {"description": "RFC inválido."},
        500: {"description": "Error interno del servidor."},
    },
)
async def screen_sat_69b(
    request: Sat69bRequest,
    # current_user: dict = Depends(get_current_active_user),
) -> Sat69bResultSchema:
    """
    Verifica si un contribuyente está en la lista SAT 69-B.

    El artículo 69-B del CFF establece la presunción de operaciones
    simuladas para contribuyentes que emiten comprobantes fiscales
    sin contar con los activos, personal o infraestructura necesarios.
    """
    service = ComplianceScreeningService()

    try:
        result = await service.screen_sat_69b(
            name=request.name,
            rfc=request.rfc,
        )
        return _to_sat69b_schema(result)

    except Exception as exc:
        logger.error("Error en verificación SAT 69-B: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=(
                "Error interno al verificar en la lista SAT 69-B. "
                "Intente de nuevo más tarde."
            ),
        ) from exc


# ---------------------------------------------------------------------------
# Endpoint: Verificación PEP
# ---------------------------------------------------------------------------
@router.post(
    "/pep",
    response_model=PepResultSchema,
    summary="Verificación de Persona Políticamente Expuesta (PEP)",
    description=(
        "Verifica si una persona está identificada como Persona "
        "Políticamente Expuesta (PEP). Las PEP incluyen jefes de Estado, "
        "funcionarios de alto nivel, directivos de empresas estatales, etc."
    ),
    responses={
        200: {"description": "Verificación completada."},
        400: {"description": "Datos de entrada inválidos."},
        500: {"description": "Error interno del servidor."},
    },
)
async def screen_pep(
    request: PepRequest,
    # current_user: dict = Depends(get_current_active_user),
) -> PepResultSchema:
    """
    Verifica si una persona es una Persona Políticamente Expuesta.

    Las PEP son individuos que desempeñan o han desempeñado funciones
    públicas destacadas, lo que implica un mayor riesgo de lavado
    de dinero y corrupción.
    """
    service = ComplianceScreeningService()

    try:
        result = await service.screen_pep(
            name=request.name,
            country=request.country,
        )
        return _to_pep_schema(result)

    except Exception as exc:
        logger.error("Error en verificación PEP: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=(
                "Error interno al verificar PEP. "
                "Intente de nuevo más tarde."
            ),
        ) from exc


# ---------------------------------------------------------------------------
# Endpoint: Consulta de resultado previo
# ---------------------------------------------------------------------------
@router.get(
    "/{request_id}",
    response_model=ScreeningRequestDetail,
    summary="Consultar resultado de screening previo",
    description=(
        "Recupera los resultados de una solicitud de screening previa "
        "usando su identificador único."
    ),
    responses={
        200: {"description": "Resultado encontrado."},
        404: {"description": "Solicitud no encontrada."},
    },
)
async def get_screening_result(
    request_id: str,
    session: AsyncSession = Depends(db_session),
    # current_user: dict = Depends(get_current_active_user),
) -> ScreeningRequestDetail:
    """
    Recupera el resultado de una solicitud de screening previa.

    Args:
        request_id: Identificador único de la solicitud.
    """
    try:
        stmt = select(ScreeningRequest).where(
            ScreeningRequest.id == request_id
        )
        db_result = await session.execute(stmt)
        screening_request = db_result.scalar_one_or_none()

        if screening_request is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=(
                    f"Solicitud de screening con ID '{request_id}' "
                    f"no encontrada."
                ),
            )

        # Convertir resultados almacenados
        screening_result = None
        if screening_request.results:
            stored = screening_request.results
            screening_result = ScreeningResultSchema(
                request_id=screening_request.id,
                matches=stored.get("matches", []),
                total_hits=stored.get("total_hits", 0),
                max_score=stored.get("max_score", 0.0),
                risk_level=RiskLevelSchema(stored.get("risk_level", "none")),
                sources_checked=stored.get("sources_checked", []),
                sources_failed=stored.get("sources_failed", []),
                timestamp=stored.get("timestamp", ""),
            )

        return ScreeningRequestDetail(
            id=screening_request.id,
            name=screening_request.name,
            curp=screening_request.curp,
            rfc=screening_request.rfc,
            entity_type=screening_request.entity_type.value,
            status=screening_request.status.value,
            results=screening_result,
            created_at=screening_request.created_at.isoformat() if screening_request.created_at else None,
            updated_at=screening_request.updated_at.isoformat() if screening_request.updated_at else None,
        )

    except HTTPException:
        raise
    except Exception as exc:
        logger.error(
            "Error consultando solicitud de screening %s: %s",
            request_id,
            exc,
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error interno al consultar la solicitud de screening.",
        ) from exc


# ---------------------------------------------------------------------------
# Endpoint: Estado del servicio (mantiene compatibilidad con router anterior)
# ---------------------------------------------------------------------------
@router.get(
    "/",
    summary="Estado del servicio de screening",
    description="Retorna el estado del servicio de screening en listas restrictivas.",
)
async def screening_root():
    """Retorna el estado del servicio de screening en listas restrictivas."""
    return {
        "service": "screening",
        "status": "active",
        "sources": [
            "OFAC SDN",
            "UN Security Council",
            "OpenSanctions",
            "Interpol Red Notices",
            "SAT 69-B",
            "DOF",
            "SCJN",
            "PEP",
        ],
        "version": "2.0.0",
    }


# ---------------------------------------------------------------------------
# Función auxiliar: Persistencia (mejor esfuerzo)
# ---------------------------------------------------------------------------
async def _persist_screening_request(
    session: AsyncSession,
    request: ScreeningPersonRequest | ScreeningEntityRequest,
    result: ScreeningResult,
    entity_type: str,
) -> None:
    """
    Persiste una solicitud de screening y sus coincidencias.

    Esta operación se realiza en modo "mejor esfuerzo": si falla
    la persistencia, no afecta la respuesta al usuario.

    Args:
        session: Sesión de base de datos.
        request: Solicitud original.
        result: Resultado del screening.
        entity_type: Tipo de entidad (person/entity).
    """
    try:
        # Crear la solicitud
        screening_request = ScreeningRequest(
            id=result.request_id,
            name=request.name,
            curp=getattr(request, "curp", None),
            rfc=getattr(request, "rfc", None),
            entity_type=ScreeningEntityType(entity_type),
            status=ScreeningStatus.COMPLETED if not result.sources_failed else ScreeningStatus.PARTIAL,
            results={
                "matches": [m.model_dump() for m in result.matches] if hasattr(result.matches[0], 'model_dump') else [],
                "total_hits": result.total_hits,
                "max_score": result.max_score,
                "risk_level": result.risk_level.value,
                "sources_checked": result.sources_checked,
                "sources_failed": result.sources_failed,
                "timestamp": result.timestamp,
            },
        )
        session.add(screening_request)

        # Crear las coincidencias
        for match in result.matches:
            screening_match = ScreeningMatch(
                request_id=result.request_id,
                source=match.source,
                match_score=match.score,
                match_type=match.match_type,
                entity_name=match.entity_name,
                entity_data=match.entity_data,
                is_confirmed=match.is_confirmed,
            )
            session.add(screening_match)

        await session.flush()

    except Exception as exc:
        logger.warning("Error persistiendo solicitud de screening: %s", exc)
        # No propagar el error — es mejor esfuerzo
