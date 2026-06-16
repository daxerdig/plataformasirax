"""
Esquemas Pydantic para el módulo de verificación de identidad.

Define los modelos de entrada y salida para la API de verificación,
incluyendo validación automática de tipos y documentación OpenAPI.

Esquemas de entrada:
- ``VerifyRequest``: Solicitud de verificación (CURP, RFC, nombre, etc.)

Esquemas de salida:
- ``CurpValidationResult``: Resultado de validación de CURP
- ``RfcValidationResult``: Resultado de validación de RFC
- ``VerificationResponse``: Respuesta combinada de verificación

Todos los esquemas usan ``model_config`` con ``from_attributes=True``
para compatibilidad con modelos SQLAlchemy.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field, field_validator, model_validator


# ---------------------------------------------------------------------------
# Esquemas de entrada
# ---------------------------------------------------------------------------
class VerifyRequest(BaseModel):
    """
    Solicitud de verificación de identidad.

    Al menos uno de los siguientes campos debe ser proporcionado:
    CURP, RFC o nombre completo. Se recomienda proporcionar la mayor
    cantidad de datos posible para una verificación más completa.

    Attributes:
        curp: Clave Única de Registro de Población (18 caracteres).
        rfc: Registro Federal de Contribuyentes (12-13 caracteres).
        name: Nombre completo de la persona.
        birth_date: Fecha de nacimiento en formato ISO (YYYY-MM-DD).
        gender: Sexo de la persona ('H' o 'M').
    """

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

    name: Optional[str] = Field(
        default=None,
        max_length=255,
        description="Nombre completo de la persona.",
        examples=["JUAN GOMEZ RODRIGUEZ"],
    )

    birth_date: Optional[date] = Field(
        default=None,
        description="Fecha de nacimiento en formato ISO (YYYY-MM-DD).",
        examples=["1985-01-01"],
    )

    gender: Optional[str] = Field(
        default=None,
        pattern=r"^[HM]$",
        description="Sexo de la persona: 'H' (hombre) o 'M' (mujer).",
        examples=["H"],
    )

    @model_validator(mode="after")
    def validate_at_least_one_field(self) -> "VerifyRequest":
        """Valida que al menos un campo de identificación sea proporcionado."""
        if not any([self.curp, self.rfc, self.name]):
            raise ValueError(
                "Debe proporcionar al menos uno de los siguientes campos: "
                "curp, rfc o nombre."
            )
        return self

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "curp": "GOME850101HDFRRN09",
                    "rfc": "GOME850101ABC",
                    "name": "JUAN GOMEZ RODRIGUEZ",
                    "birth_date": "1985-01-01",
                    "gender": "H",
                }
            ]
        }
    }


class CurpValidateRequest(BaseModel):
    """
    Solicitud de validación de CURP.

    Attributes:
        curp: La CURP a validar (18 caracteres).
        check_renapo: Si se debe consultar la base de datos RENAPO.
    """

    curp: str = Field(
        ...,
        min_length=18,
        max_length=18,
        description="Clave Única de Registro de Población a validar.",
        examples=["GOME850101HDFRRN09"],
    )

    check_renapo: bool = Field(
        default=False,
        description="Consultar la base de datos RENAPO para validación adicional.",
    )


class CurpSearchRequest(BaseModel):
    """
    Solicitud de búsqueda de CURP en RENAPO.

    Attributes:
        name: Nombre(s) de pila.
        paternal: Apellido paterno.
        maternal: Apellido materno.
        birth_date: Fecha de nacimiento.
        gender: Sexo ('H' o 'M').
        state: Clave de la entidad federativa (2 letras).
    """

    name: str = Field(..., description="Nombre(s) de pila.")
    paternal: str = Field(..., description="Apellido paterno.")
    maternal: str = Field(..., description="Apellido materno.")
    birth_date: date = Field(..., description="Fecha de nacimiento.")
    gender: str = Field(..., pattern=r"^[HM]$", description="Sexo: 'H' o 'M'.")
    state: Optional[str] = Field(
        default=None,
        max_length=2,
        description="Clave de la entidad federativa (2 letras).",
    )


class RfcValidateRequest(BaseModel):
    """
    Solicitud de validación de RFC.

    Attributes:
        rfc: El RFC a validar (12-13 caracteres).
        check_sat: Si se debe consultar el SAT para validación adicional.
    """

    rfc: str = Field(
        ...,
        min_length=12,
        max_length=13,
        description="Registro Federal de Contribuyentes a validar.",
        examples=["GOME850101ABC"],
    )

    check_sat: bool = Field(
        default=False,
        description="Consultar el SAT para validación adicional.",
    )


class RfcVerifySatRequest(BaseModel):
    """
    Solicitud de verificación de RFC contra el SAT.

    Attributes:
        rfc: El RFC a verificar.
    """

    rfc: str = Field(
        ...,
        min_length=12,
        max_length=13,
        description="RFC a verificar contra el SAT.",
    )


# ---------------------------------------------------------------------------
# Esquemas de salida — Información extraída
# ---------------------------------------------------------------------------
class CurpExtractedInfo(BaseModel):
    """
    Información extraída de una CURP válida.

    Attributes:
        name_initials: Las 4 letras iniciales del nombre.
        birth_date: Fecha de nacimiento.
        gender: Sexo (H/M).
        state_code: Clave de la entidad federativa.
        state_name: Nombre de la entidad federativa.
        internal_consonants: Las 3 consonantes internas.
        century_digit: Carácter identificador del siglo.
        birth_year: Año de nacimiento completo (4 dígitos).
    """

    name_initials: str = Field(description="Las 4 letras iniciales del nombre.")
    birth_date: str = Field(description="Fecha de nacimiento en formato ISO.")
    gender: str = Field(description="Sexo: 'H' (hombre) o 'M' (mujer).")
    state_code: str = Field(description="Clave de la entidad federativa (2 letras).")
    state_name: str = Field(description="Nombre completo de la entidad federativa.")
    internal_consonants: str = Field(description="Las 3 consonantes internas de la CURP.")
    century_digit: str = Field(description="Carácter identificador del siglo.")
    birth_year: int = Field(description="Año de nacimiento completo (4 dígitos).")


class RfcExtractedInfo(BaseModel):
    """
    Información extraída de un RFC válido.

    Attributes:
        person_type: Tipo de persona ('fisica' o 'moral').
        name_initials: Las letras iniciales del nombre o razón social.
        birth_date: Fecha de inicio de operaciones o nacimiento.
        homoclave: Los 3 caracteres de la homoclave.
        birth_year: Año completo (4 dígitos).
    """

    person_type: str = Field(description="Tipo de persona: 'fisica' o 'moral'.")
    name_initials: str = Field(description="Las letras iniciales del nombre o razón social.")
    birth_date: str = Field(description="Fecha en formato ISO.")
    homoclave: str = Field(description="Los 3 caracteres de la homoclave.")
    birth_year: int = Field(description="Año completo (4 dígitos).")


# ---------------------------------------------------------------------------
# Esquemas de salida — Resultados de validación
# ---------------------------------------------------------------------------
class CurpValidationResult(BaseModel):
    """
    Resultado completo de la validación de una CURP.

    Attributes:
        is_valid: Si la CURP pasó todas las validaciones.
        format_valid: Si el formato de la CURP es correcto.
        check_digit_valid: Si el dígito verificador es correcto.
        renapo_match: Si la CURP fue encontrada en RENAPO.
        extracted_info: Información extraída de la CURP (si el formato es válido).
        errors: Lista de errores encontrados durante la validación.
        validated_at: Fecha y hora de la validación.
    """

    is_valid: bool = Field(description="Si la CURP pasó todas las validaciones.")
    format_valid: bool = Field(description="Si el formato de la CURP es correcto.")
    check_digit_valid: bool = Field(description="Si el dígito verificador es correcto.")
    renapo_match: Optional[bool] = Field(
        default=None,
        description="Si la CURP fue encontrada en RENAPO (None si no se consultó).",
    )
    extracted_info: Optional[CurpExtractedInfo] = Field(
        default=None,
        description="Información extraída de la CURP (si el formato es válido).",
    )
    errors: List[str] = Field(
        default_factory=list,
        description="Lista de errores encontrados durante la validación.",
    )
    validated_at: datetime = Field(
        default_factory=datetime.now,
        description="Fecha y hora en que se realizó la validación.",
    )


class RfcValidationResult(BaseModel):
    """
    Resultado completo de la validación de un RFC.

    Attributes:
        is_valid: Si el RFC pasó todas las validaciones.
        format_valid: Si el formato del RFC es correcto.
        check_digit_valid: Si el dígito verificador es correcto.
        person_type: Tipo de persona ('fisica', 'moral' o 'desconocido').
        sat_active: Si el RFC está activo en el SAT.
        sat_data: Datos retornados por el SAT (si se consultó).
        extracted_info: Información extraída del RFC (si el formato es válido).
        errors: Lista de errores encontrados durante la validación.
        validated_at: Fecha y hora de la validación.
    """

    is_valid: bool = Field(description="Si el RFC pasó todas las validaciones.")
    format_valid: bool = Field(description="Si el formato del RFC es correcto.")
    check_digit_valid: bool = Field(description="Si el dígito verificador es correcto.")
    person_type: str = Field(
        default="desconocido",
        description="Tipo de persona: 'fisica', 'moral' o 'desconocido'.",
    )
    sat_active: Optional[bool] = Field(
        default=None,
        description="Si el RFC está activo en el SAT (None si no se consultó).",
    )
    sat_data: Optional[Dict[str, Any]] = Field(
        default=None,
        description="Datos retornados por el SAT en formato JSON.",
    )
    extracted_info: Optional[RfcExtractedInfo] = Field(
        default=None,
        description="Información extraída del RFC (si el formato es válido).",
    )
    errors: List[str] = Field(
        default_factory=list,
        description="Lista de errores encontrados durante la validación.",
    )
    validated_at: datetime = Field(
        default_factory=datetime.now,
        description="Fecha y hora en que se realizó la validación.",
    )


class ConsistencyResult(BaseModel):
    """
    Resultado de la verificación de consistencia entre CURP y RFC.

    Compara los datos extraídos de ambos documentos para verificar
    que sean coherentes entre sí.

    Attributes:
        is_consistent: Si los datos de CURP y RFC son consistentes.
        birth_date_match: Si las fechas de nacimiento coinciden.
        name_initials_match: Si las iniciales del nombre coinciden.
        inconsistencies: Lista de inconsistencias encontradas.
    """

    is_consistent: bool = Field(description="Si los datos de CURP y RFC son consistentes.")
    birth_date_match: Optional[bool] = Field(
        default=None,
        description="Si las fechas de nacimiento de CURP y RFC coinciden.",
    )
    name_initials_match: Optional[bool] = Field(
        default=None,
        description="Si las iniciales del nombre de CURP y RFC coinciden.",
    )
    inconsistencies: List[str] = Field(
        default_factory=list,
        description="Lista de inconsistencias encontradas entre CURP y RFC.",
    )


class CurpCandidate(BaseModel):
    """
    Candidato de CURP encontrado en la búsqueda RENAPO.

    Attributes:
        curp: CURP encontrada.
        name: Nombre completo.
        birth_date: Fecha de nacimiento.
        gender: Sexo.
        state: Entidad federativa.
        match_score: Puntuación de coincidencia (0-1).
    """

    curp: str = Field(description="CURP encontrada.")
    name: Optional[str] = Field(default=None, description="Nombre completo del candidato.")
    birth_date: Optional[str] = Field(default=None, description="Fecha de nacimiento.")
    gender: Optional[str] = Field(default=None, description="Sexo.")
    state: Optional[str] = Field(default=None, description="Entidad federativa.")
    match_score: float = Field(default=1.0, description="Puntuación de coincidencia (0-1).")


class SatStatus(BaseModel):
    """
    Estado de un RFC en el SAT.

    Attributes:
        rfc: RFC consultado.
        is_active: Si el RFC está activo.
        status: Estado del RFC ('activo', 'suspendido', 'cancelado').
        status_description: Descripción del estado en español.
        last_checked: Fecha y hora de la última consulta.
    """

    rfc: str = Field(description="RFC consultado.")
    is_active: bool = Field(description="Si el RFC está activo.")
    status: str = Field(
        description="Estado del RFC: 'activo', 'suspendido' o 'cancelado'.",
    )
    status_description: str = Field(description="Descripción del estado en español.")
    last_checked: datetime = Field(
        default_factory=datetime.now,
        description="Fecha y hora de la última consulta al SAT.",
    )


# ---------------------------------------------------------------------------
# Esquema de salida — Respuesta combinada
# ---------------------------------------------------------------------------
class VerificationResponse(BaseModel):
    """
    Respuesta completa de la verificación de identidad.

    Combina los resultados de todas las validaciones realizadas
    (CURP, RFC, consistencia) en una sola respuesta.

    Attributes:
        request_id: Identificador único de la solicitud.
        curp_result: Resultado de la validación de CURP (si se proporcionó).
        rfc_result: Resultado de la validación de RFC (si se proporcionó).
        consistency_result: Resultado de la consistencia entre CURP y RFC.
        overall_valid: Si la verificación general es positiva.
        name_similarity: Similitud fonética del nombre (0-1), si se proporcionó.
        verified_at: Fecha y hora de la verificación.
    """

    request_id: str = Field(description="Identificador único de la solicitud.")
    curp_result: Optional[CurpValidationResult] = Field(
        default=None,
        description="Resultado de la validación de CURP.",
    )
    rfc_result: Optional[RfcValidationResult] = Field(
        default=None,
        description="Resultado de la validación de RFC.",
    )
    consistency_result: Optional[ConsistencyResult] = Field(
        default=None,
        description="Resultado de la consistencia entre CURP y RFC.",
    )
    overall_valid: bool = Field(
        description="Si la verificación general de identidad es positiva.",
    )
    name_similarity: Optional[float] = Field(
        default=None,
        ge=0.0,
        le=1.0,
        description="Similitud fonética del nombre proporcionado vs. documentos (0-1).",
    )
    verified_at: datetime = Field(
        default_factory=datetime.now,
        description="Fecha y hora en que se realizó la verificación.",
    )
