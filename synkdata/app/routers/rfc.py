"""
Router de RFC — validación y verificación contra el SAT.

Endpoints disponibles:
- ``POST /rfc/validate`` — Valida un RFC (formato + dígito verificador + SAT)
- ``POST /rfc/verify-sat`` — Verifica un RFC contra el SAT (LFTP)
- ``GET /rfc/{rfc}`` — Obtiene un resultado de validación cacheado

Todos los endpoints retornan respuestas en español con mensajes
descriptivos para el usuario final.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException, Query, status
from redis.asyncio import Redis

from app.dependencies import redis_client
from app.schemas.verification import (
    RfcValidateRequest,
    RfcValidationResult,
    RfcVerifySatRequest,
    SatStatus,
)
from app.services.rfc_validator import RfcValidatorService

logger = logging.getLogger(__name__)

router = APIRouter()


# ---------------------------------------------------------------------------
# Dependencia para el servicio de validación de RFC
# ---------------------------------------------------------------------------
async def get_rfc_validator(
    redis: Redis = Depends(redis_client),
) -> RfcValidatorService:
    """
    Proveedor del servicio de validación de RFC por inyección de dependencias.

    Crea una instancia del servicio con el cliente Redis inyectado.

    Args:
        redis: Cliente Redis proporcionado por la dependencia.

    Returns:
        RfcValidatorService: Instancia del servicio configurada.
    """
    return RfcValidatorService(redis=redis)


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------
@router.post(
    "/validate",
    response_model=RfcValidationResult,
    summary="Validar un RFC",
    description=(
        "Realiza la validación completa de un RFC: formato, tipo de persona, "
        "dígito verificador y opcionalmente verifica el estado en el SAT."
    ),
    responses={
        200: {"description": "Resultado de la validación del RFC."},
        400: {"description": "El RFC proporcionado no tiene el formato correcto."},
    },
)
async def validate_rfc(
    request: RfcValidateRequest,
    validator: RfcValidatorService = Depends(get_rfc_validator),
) -> RfcValidationResult:
    """
    Valida un RFC con opción de verificación SAT.

    Realiza las siguientes validaciones:
    1. Formato del RFC y determinación del tipo de persona (física/moral)
    2. Dígito verificador (algoritmo de suma ponderada)
    3. Extracción de información del RFC
    4. Verificación SAT (si ``check_sat`` es True)

    Args:
        request: Solicitud con el RFC y opciones de validación.
        validator: Servicio de validación inyectado.

    Returns:
        RfcValidationResult: Resultado detallado de la validación.
    """
    logger.info("Solicitud de validación de RFC: %s", request.rfc)

    try:
        if request.check_sat:
            result = await validator.validate_with_sat(request.rfc)
        else:
            result = await validator.validate(request.rfc)

        return result

    except Exception as exc:
        logger.error("Error inesperado validando RFC %s: %s", request.rfc, exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error interno al validar el RFC. Intente de nuevo más tarde.",
        ) from exc
    finally:
        await validator.close()


@router.post(
    "/verify-sat",
    response_model=RfcValidationResult,
    summary="Verificar RFC contra el SAT",
    description=(
        "Verifica un RFC contra los servicios del SAT, incluyendo "
        "el estado en la Lista de Facilitadores de Contribuyentes (LFTP)."
    ),
    responses={
        200: {"description": "Resultado de la verificación SAT."},
        400: {"description": "El RFC proporcionado no tiene el formato correcto."},
    },
)
async def verify_rfc_sat(
    request: RfcVerifySatRequest,
    validator: RfcValidatorService = Depends(get_rfc_validator),
) -> RfcValidationResult:
    """
    Verifica un RFC contra el SAT.

    Realiza la validación local del RFC y luego consulta los servicios
    del SAT para verificar su estado (activo, suspendido, cancelado)
    y obtener información adicional.

    Args:
        request: Solicitud con el RFC a verificar.
        validator: Servicio de validación inyectado.

    Returns:
        RfcValidationResult: Resultado detallado incluyendo datos SAT.
    """
    logger.info("Solicitud de verificación SAT para RFC: %s", request.rfc)

    try:
        result = await validator.validate_with_sat(request.rfc)
        return result

    except Exception as exc:
        logger.error(
            "Error inesperado verificando RFC %s contra SAT: %s",
            request.rfc,
            exc,
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=(
                "Error interno al verificar el RFC contra el SAT. "
                "Intente de nuevo más tarde."
            ),
        ) from exc
    finally:
        await validator.close()


@router.get(
    "/{rfc}",
    response_model=RfcValidationResult,
    summary="Obtener validación cacheada de RFC",
    description=(
        "Obtiene el resultado de una validación previa de RFC almacenada "
        "en el caché. Si no existe una validación previa, retorna 404."
    ),
    responses={
        200: {"description": "Resultado de validación cacheado."},
        404: {"description": "No se encontró una validación previa para este RFC."},
    },
)
async def get_cached_rfc_validation(
    rfc: str = Query(
        ...,
        min_length=12,
        max_length=13,
        description="RFC a buscar en el caché.",
    ),
    validator: RfcValidatorService = Depends(get_rfc_validator),
) -> RfcValidationResult:
    """
    Obtiene el resultado de validación cacheado para un RFC.

    Busca en el caché Redis si existe un resultado de validación previo
    para el RFC especificado. No realiza nuevas validaciones.

    Args:
        rfc: RFC a buscar en el caché.
        validator: Servicio de validación inyectado.

    Returns:
        RfcValidationResult: Resultado cacheado de la validación.

    Raises:
        HTTPException 404: Si no se encontró validación previa.
    """
    result = await validator.get_cached_validation(rfc)

    if result is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=(
                f"No se encontró una validación previa para el RFC '{rfc}'. "
                f"Utilice el endpoint POST /rfc/validate para realizar una "
                f"validación nueva."
            ),
        )

    return result
