"""
Router de verificación de identidad — validación combinada de CURP, RFC y nombres.

Endpoints disponibles:
- ``POST /verify`` — Verificación completa de identidad

Este endpoint combina la validación de CURP, RFC, consistencia entre
ambos documentos y coincidencia fonética de nombres para proporcionar
una evaluación integral de la identidad del individuo.
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status
from redis.asyncio import Redis

from app.dependencies import redis_client
from app.schemas.verification import (
    ConsistencyResult,
    CurpValidationResult,
    RfcValidationResult,
    VerificationResponse,
    VerifyRequest,
)
from app.services.curp_validator import CurpValidatorService
from app.services.rfc_validator import RfcValidatorService
from app.utils.phonetic import phonetic_match
from app.utils.text_normalizer import normalize_for_comparison

logger = logging.getLogger(__name__)

router = APIRouter()


# ---------------------------------------------------------------------------
# Dependencias para los servicios
# ---------------------------------------------------------------------------
async def get_curp_validator(
    redis: Redis = Depends(redis_client),
) -> CurpValidatorService:
    """Proveedor del servicio de validación de CURP."""
    return CurpValidatorService(redis=redis)


async def get_rfc_validator(
    redis: Redis = Depends(redis_client),
) -> RfcValidatorService:
    """Proveedor del servicio de validación de RFC."""
    return RfcValidatorService(redis=redis)


# ---------------------------------------------------------------------------
# Endpoint principal
# ---------------------------------------------------------------------------
@router.post(
    "/",
    response_model=VerificationResponse,
    summary="Verificación completa de identidad",
    description=(
        "Realiza la verificación integral de identidad combinando: "
        "validación de CURP, validación de RFC, verificación de "
        "consistencia entre ambos documentos y coincidencia fonética "
        "del nombre proporcionado."
    ),
    responses={
        200: {"description": "Resultado de la verificación de identidad."},
        400: {"description": "Los datos proporcionados son insuficientes."},
        500: {"description": "Error interno durante la verificación."},
    },
)
async def verify_identity(
    request: VerifyRequest,
    curp_validator: CurpValidatorService = Depends(get_curp_validator),
    rfc_validator: RfcValidatorService = Depends(get_rfc_validator),
) -> VerificationResponse:
    """
    Verificación completa de identidad.

    Proceso de verificación:
    1. Si se proporciona CURP, validar formato + dígito verificador
    2. Si se proporciona RFC, validar formato + dígito verificador
    3. Si se proporcionan ambos, verificar consistencia entre CURP y RFC
    4. Si se proporciona nombre, calcular similitud fonética
    5. Determinar validez general de la verificación

    Al menos uno de los siguientes campos es obligatorio:
    CURP, RFC o nombre completo.

    Args:
        request: Solicitud de verificación con los datos del individuo.
        curp_validator: Servicio de validación de CURP inyectado.
        rfc_validator: Servicio de validación de RFC inyectado.

    Returns:
        VerificationResponse: Resultado completo de la verificación.
    """
    request_id = str(uuid.uuid4())
    logger.info(
        "Iniciando verificación de identidad [request_id=%s]: "
        "curp=%s, rfc=%s, nombre=%s",
        request_id,
        bool(request.curp),
        bool(request.rfc),
        bool(request.name),
    )

    curp_result: Optional[CurpValidationResult] = None
    rfc_result: Optional[RfcValidationResult] = None
    consistency_result: Optional[ConsistencyResult] = None
    name_similarity: Optional[float] = None

    try:
        # ── Paso 1: Validación de CURP ───────────────────────────────────
        if request.curp:
            try:
                curp_result = await curp_validator.validate(request.curp)
            except Exception as exc:
                logger.error(
                    "Error validando CURP en verificación [request_id=%s]: %s",
                    request_id,
                    exc,
                )
                curp_result = CurpValidationResult(
                    is_valid=False,
                    format_valid=False,
                    check_digit_valid=False,
                    errors=[
                        f"Error al validar la CURP: {exc}. "
                        f"Intente de nuevo más tarde."
                    ],
                    validated_at=datetime.now(),
                )

        # ── Paso 2: Validación de RFC ────────────────────────────────────
        if request.rfc:
            try:
                rfc_result = await rfc_validator.validate(request.rfc)
            except Exception as exc:
                logger.error(
                    "Error validando RFC en verificación [request_id=%s]: %s",
                    request_id,
                    exc,
                )
                rfc_result = RfcValidationResult(
                    is_valid=False,
                    format_valid=False,
                    check_digit_valid=False,
                    errors=[
                        f"Error al validar el RFC: {exc}. "
                        f"Intente de nuevo más tarde."
                    ],
                    validated_at=datetime.now(),
                )

        # ── Paso 3: Consistencia CURP-RFC ───────────────────────────────
        if request.curp and request.rfc:
            try:
                consistency_result = await rfc_validator.verify_rfc_curp_consistency(
                    rfc=request.rfc,
                    curp=request.curp,
                )
            except Exception as exc:
                logger.error(
                    "Error verificando consistencia CURP-RFC [request_id=%s]: %s",
                    request_id,
                    exc,
                )
                consistency_result = ConsistencyResult(
                    is_consistent=False,
                    inconsistencies=[
                        f"Error al verificar la consistencia entre CURP y RFC: {exc}."
                    ],
                )

        # ── Paso 4: Similitud fonética del nombre ───────────────────────
        if request.name:
            name_similarity = _calculate_name_similarity(
                name=request.name,
                curp_result=curp_result,
                rfc_result=rfc_result,
            )

        # ── Paso 5: Determinar validez general ──────────────────────────
        overall_valid = _determine_overall_validity(
            curp_result=curp_result,
            rfc_result=rfc_result,
            consistency_result=consistency_result,
            name_similarity=name_similarity,
        )

        response = VerificationResponse(
            request_id=request_id,
            curp_result=curp_result,
            rfc_result=rfc_result,
            consistency_result=consistency_result,
            overall_valid=overall_valid,
            name_similarity=name_similarity,
            verified_at=datetime.now(),
        )

        logger.info(
            "Verificación de identidad completada [request_id=%s]: "
            "válida=%s, curp_válida=%s, rfc_válido=%s, consistencia=%s",
            request_id,
            overall_valid,
            curp_result.is_valid if curp_result else None,
            rfc_result.is_valid if rfc_result else None,
            consistency_result.is_consistent if consistency_result else None,
        )

        return response

    except Exception as exc:
        logger.error(
            "Error inesperado en verificación de identidad [request_id=%s]: %s",
            request_id,
            exc,
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=(
                "Error interno durante la verificación de identidad. "
                "Intente de nuevo más tarde."
            ),
        ) from exc

    finally:
        await curp_validator.close()
        await rfc_validator.close()


# ---------------------------------------------------------------------------
# Funciones auxiliares
# ---------------------------------------------------------------------------

def _calculate_name_similarity(
    name: str,
    curp_result: Optional[CurpValidationResult],
    rfc_result: Optional[RfcValidationResult],
) -> Optional[float]:
    """
    Calcula la similitud fonética entre el nombre proporcionado y los
    datos extraídos de los documentos de identidad.

    Compara el nombre con las iniciales extraídas de la CURP y/o RFC
    para determinar la coincidencia fonética.

    Args:
        name: Nombre proporcionado por el usuario.
        curp_result: Resultado de la validación de CURP (puede ser None).
        rfc_result: Resultado de la validación de RFC (puede ser None).

    Returns:
        Optional[float]: Similitud fonética (0-1) o None si no se puede calcular.
    """
    if not name:
        return None

    name_normalized = normalize_for_comparison(name)
    similarities: list[float] = []

    # Comparar con datos de CURP si están disponibles
    if curp_result and curp_result.extracted_info:
        # Reconstruir un nombre aproximado a partir de las iniciales de la CURP
        curp_initials = curp_result.extracted_info.name_initials
        if curp_initials:
            # La similitud fonética entre las iniciales y el nombre
            name_initials_from_curp = curp_initials
            provided_initials = ""
            words = name_normalized.split()
            for word in words[:4]:  # Máximo 4 palabras para las iniciales
                if word:
                    provided_initials += word[0]
            sim = _compare_initials(provided_initials, name_initials_from_curp)
            similarities.append(sim)

    # Comparar con datos de RFC si están disponibles
    if rfc_result and rfc_result.extracted_info:
        rfc_initials = rfc_result.extracted_info.name_initials
        if rfc_initials:
            provided_initials = ""
            words = name_normalized.split()
            for word in words[:4]:
                if word:
                    provided_initials += word[0]
            sim = _compare_initials(provided_initials, rfc_initials)
            similarities.append(sim)

    if not similarities:
        return None

    # Retornar la similitud máxima encontrada
    return max(similarities)


def _compare_initials(provided: str, expected: str) -> float:
    """
    Compara dos conjuntos de iniciales de nombre.

    Args:
        provided: Iniciales extraídas del nombre proporcionado.
        expected: Iniciales esperadas (de CURP o RFC).

    Returns:
        float: Similitud entre 0 y 1.
    """
    if not provided or not expected:
        return 0.0

    if provided == expected:
        return 1.0

    # Contar caracteres coincidentes en la misma posición
    matches = 0
    min_len = min(len(provided), len(expected))

    for i in range(min_len):
        if provided[i] == expected[i]:
            matches += 1

    return matches / max(len(provided), len(expected))


def _determine_overall_validity(
    curp_result: Optional[CurpValidationResult],
    rfc_result: Optional[RfcValidationResult],
    consistency_result: Optional[ConsistencyResult],
    name_similarity: Optional[float],
) -> bool:
    """
    Determina la validez general de la verificación de identidad.

    Criterios:
    - Si se validó CURP y no es válida → inválida
    - Si se validó RFC y no es válido → inválida
    - Si se verificó consistencia y no es consistente → inválida
    - Si la similitud del nombre es muy baja (< 0.5) → inválida
    - En caso contrario → válida

    Args:
        curp_result: Resultado de la validación de CURP.
        rfc_result: Resultado de la validación de RFC.
        consistency_result: Resultado de la consistencia.
        name_similarity: Similitud fonética del nombre.

    Returns:
        bool: True si la verificación general es positiva.
    """
    # CURP inválida
    if curp_result is not None and not curp_result.is_valid:
        return False

    # RFC inválido
    if rfc_result is not None and not rfc_result.is_valid:
        return False

    # Inconsistencia entre CURP y RFC
    if consistency_result is not None and not consistency_result.is_consistent:
        return False

    # Similitud del nombre muy baja
    if name_similarity is not None and name_similarity < 0.5:
        return False

    return True
