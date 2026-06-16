"""
Router de CURP — validación y consulta contra RENAPO.

Endpoints disponibles:
- ``POST /curp/validate`` — Valida una CURP (formato + dígito verificador + RENAPO)
- ``POST /curp/search`` — Busca una CURP en RENAPO por datos personales
- ``GET /curp/{curp}`` — Obtiene un resultado de validación cacheado

Todos los endpoints retornan respuestas en español con mensajes
descriptivos para el usuario final.
"""

from __future__ import annotations

import logging
from typing import List

from fastapi import APIRouter, Depends, HTTPException, Query, status
from redis.asyncio import Redis

from app.dependencies import redis_client
from app.schemas.verification import (
    CurpCandidate,
    CurpSearchRequest,
    CurpValidateRequest,
    CurpValidationResult,
)
from app.services.curp_validator import CurpValidatorService

logger = logging.getLogger(__name__)

router = APIRouter()


# ---------------------------------------------------------------------------
# Dependencia para el servicio de validación de CURP
# ---------------------------------------------------------------------------
async def get_curp_validator(
    redis: Redis = Depends(redis_client),
) -> CurpValidatorService:
    """
    Proveedor del servicio de validación de CURP por inyección de dependencias.

    Crea una instancia del servicio con el cliente Redis inyectado.

    Args:
        redis: Cliente Redis proporcionado por la dependencia.

    Returns:
        CurpValidatorService: Instancia del servicio configurada.
    """
    return CurpValidatorService(redis=redis)


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------
@router.post(
    "/validate",
    response_model=CurpValidationResult,
    summary="Validar una CURP",
    description=(
        "Realiza la validación completa de una CURP: formato, dígito verificador "
        "y opcionalmente consulta contra la base de datos de RENAPO."
    ),
    responses={
        200: {"description": "Resultado de la validación de la CURP."},
        400: {"description": "La CURP proporcionada no tiene el formato correcto."},
    },
)
async def validate_curp(
    request: CurpValidateRequest,
    validator: CurpValidatorService = Depends(get_curp_validator),
) -> CurpValidationResult:
    """
    Valida una CURP con opción de consulta RENAPO.

    Realiza las siguientes validaciones:
    1. Formato de la CURP (18 posiciones, caracteres válidos, entidad federativa)
    2. Dígito verificador (algoritmo de suma ponderada)
    3. Extracción de información personal
    4. Consulta RENAPO (si ``check_renapo`` es True)

    Args:
        request: Solicitud con la CURP y opciones de validación.
        validator: Servicio de validación inyectado.

    Returns:
        CurpValidationResult: Resultado detallado de la validación.
    """
    logger.info("Solicitud de validación de CURP: %s", request.curp)

    try:
        if request.check_renapo:
            result = await validator.validate_with_renapo(request.curp)
        else:
            result = await validator.validate(request.curp)

        return result

    except Exception as exc:
        logger.error("Error inesperado validando CURP %s: %s", request.curp, exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error interno al validar la CURP. Intente de nuevo más tarde.",
        ) from exc
    finally:
        await validator.close()


@router.post(
    "/search",
    response_model=List[CurpCandidate],
    summary="Buscar CURP en RENAPO",
    description=(
        "Busca una CURP en la base de datos de RENAPO proporcionando "
        "los datos personales del individuo."
    ),
    responses={
        200: {"description": "Lista de candidatos CURP encontrados."},
        400: {"description": "Los datos proporcionados son insuficientes."},
    },
)
async def search_curp(
    request: CurpSearchRequest,
    validator: CurpValidatorService = Depends(get_curp_validator),
) -> List[CurpCandidate]:
    """
    Busca una CURP en RENAPO por datos personales.

    Genera la CURP probable a partir de los datos proporcionados y
    la consulta contra la base de datos de RENAPO para encontrar
    coincidencias.

    Args:
        request: Solicitud con los datos personales del individuo.
        validator: Servicio de validación inyectado.

    Returns:
        list[CurpCandidate]: Lista de candidatos encontrados.
    """
    logger.info(
        "Solicitud de búsqueda de CURP: nombre=%s, fecha=%s, sexo=%s",
        request.name,
        request.birth_date,
        request.gender,
    )

    try:
        candidates = await validator.search(
            name=request.name,
            birth_date=request.birth_date,
            gender=request.gender,
            state=request.state,
        )
        return candidates

    except Exception as exc:
        logger.error("Error inesperado buscando CURP: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error interno al buscar la CURP. Intente de nuevo más tarde.",
        ) from exc
    finally:
        await validator.close()


@router.get(
    "/{curp}",
    response_model=CurpValidationResult,
    summary="Obtener validación cacheada de CURP",
    description=(
        "Obtiene el resultado de una validación previa de CURP almacenada "
        "en el caché. Si no existe una validación previa, retorna 404."
    ),
    responses={
        200: {"description": "Resultado de validación cacheado."},
        404: {"description": "No se encontró una validación previa para esta CURP."},
    },
)
async def get_cached_curp_validation(
    curp: str = Query(
        ...,
        min_length=18,
        max_length=18,
        description="CURP a buscar en el caché.",
    ),
    validator: CurpValidatorService = Depends(get_curp_validator),
) -> CurpValidationResult:
    """
    Obtiene el resultado de validación cacheado para una CURP.

    Busca en el caché Redis si existe un resultado de validación previo
    para la CURP especificada. No realiza nuevas validaciones.

    Args:
        curp: CURP a buscar en el caché.
        validator: Servicio de validación inyectado.

    Returns:
        CurpValidationResult: Resultado cacheado de la validación.

    Raises:
        HTTPException 404: Si no se encontró validación previa.
    """
    result = await validator.get_cached_validation(curp)

    if result is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=(
                f"No se encontró una validación previa para la CURP '{curp}'. "
                f"Utilice el endpoint POST /curp/validate para realizar una "
                f"validación nueva."
            ),
        )

    return result
