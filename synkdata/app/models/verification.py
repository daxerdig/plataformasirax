"""
Modelos SQLAlchemy para el módulo de verificación de identidad.

Define los modelos ORM para persistir las solicitudes de verificación
y sus resultados individuales (CURP y RFC), incluyendo:

- ``VerificationRequest``: Solicitud de verificación de identidad
- ``CurpValidation``: Resultado de la validación de CURP
- ``RfcValidation``: Resultado de la validación de RFC

Todos los modelos heredan de ``Base`` y ``TimestampMixin`` para
auditoría y trazabilidad.
"""

from __future__ import annotations

import enum
import uuid
from datetime import datetime
from typing import Any, Dict, Optional

from sqlalchemy import JSON, DateTime, Enum, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin


# ---------------------------------------------------------------------------
# Enumeraciones
# ---------------------------------------------------------------------------
class VerificationStatus(str, enum.Enum):
    """
    Estado de una solicitud de verificación.

    Attributes:
        PENDING: Verificación en proceso.
        COMPLETED: Verificación completada exitosamente.
        FAILED: La verificación falló (error técnico).
        PARTIAL: Verificación parcialmente completada (algunas fuentes no respondieron).
    """

    PENDING = "pending"
    COMPLETED = "completed"
    FAILED = "failed"
    PARTIAL = "partial"


class Gender(str, enum.Enum):
    """
    Sexo del individuo conforme al estándar RENAPO/SAT.

    Attributes:
        H: Hombre.
        M: Mujer.
        X: No especificado / no binario.
    """

    H = "H"
    M = "M"
    X = "X"


# ---------------------------------------------------------------------------
# Modelo principal: Solicitud de verificación
# ---------------------------------------------------------------------------
class VerificationRequest(TimestampMixin, Base):
    """
    Solicitud de verificación de identidad.

    Representa una solicitud completa de verificación que puede incluir
    validación de CURP, RFC y coincidencia de nombres. Almacena los
    datos de entrada y los resultados agregados.

    Attributes:
        id: Identificador único de la solicitud (UUID).
        curp: CURP proporcionada para verificación (opcional).
        rfc: RFC proporcionado para verificación (opcional).
        name: Nombre completo de la persona.
        birth_date: Fecha de nacimiento.
        gender: Sexo de la persona.
        status: Estado actual de la verificación.
        results: Resultados de la verificación en formato JSON.
        created_at: Fecha y hora de creación del registro.
        updated_at: Fecha y hora de última actualización.
    """

    __tablename__ = "verification_requests"

    id: Mapped[str] = mapped_column(
        String(36),
        primary_key=True,
        default=lambda: str(uuid.uuid4()),
        comment="Identificador único de la solicitud (UUID v4).",
    )

    curp: Mapped[Optional[str]] = mapped_column(
        String(18),
        nullable=True,
        index=True,
        comment="CURP proporcionada para verificación.",
    )

    rfc: Mapped[Optional[str]] = mapped_column(
        String(13),
        nullable=True,
        index=True,
        comment="RFC proporcionado para verificación.",
    )

    name: Mapped[Optional[str]] = mapped_column(
        String(255),
        nullable=True,
        comment="Nombre completo de la persona.",
    )

    birth_date: Mapped[Optional[str]] = mapped_column(
        String(10),
        nullable=True,
        comment="Fecha de nacimiento en formato ISO (YYYY-MM-DD).",
    )

    gender: Mapped[Optional[Gender]] = mapped_column(
        Enum(Gender),
        nullable=True,
        comment="Sexo de la persona (H/M/X).",
    )

    status: Mapped[VerificationStatus] = mapped_column(
        Enum(VerificationStatus),
        default=VerificationStatus.PENDING,
        nullable=False,
        index=True,
        comment="Estado actual de la verificación.",
    )

    results: Mapped[Optional[Dict[str, Any]]] = mapped_column(
        JSON,
        nullable=True,
        comment="Resultados agregados de la verificación en formato JSON.",
    )

    # ── Relaciones ───────────────────────────────────────────────────────
    curp_validation: Mapped[Optional["CurpValidation"]] = relationship(
        "CurpValidation",
        back_populates="request",
        uselist=False,
        lazy="selectin",
        cascade="all, delete-orphan",
    )

    rfc_validation: Mapped[Optional["RfcValidation"]] = relationship(
        "RfcValidation",
        back_populates="request",
        uselist=False,
        lazy="selectin",
        cascade="all, delete-orphan",
    )

    def __repr__(self) -> str:
        return (
            f"<VerificationRequest(id={self.id!r}, "
            f"curp={self.curp!r}, rfc={self.rfc!r}, "
            f"status={self.status.value!r})>"
        )


# ---------------------------------------------------------------------------
# Modelo: Validación de CURP
# ---------------------------------------------------------------------------
class CurpValidation(TimestampMixin, Base):
    """
    Resultado de la validación de una CURP.

    Almacena los resultados detallados de la validación de formato,
    dígito verificador y consulta contra RENAPO.

    Attributes:
        id: Identificador único del registro.
        request_id: FK hacia la solicitud de verificación.
        curp: CURP validada (normalizada a mayúsculas).
        is_valid: Si la CURP pasó todas las validaciones.
        check_digit_valid: Si el dígito verificador es correcto.
        format_valid: Si el formato de la CURP es válido.
        renapo_match: Si la CURP fue encontrada en RENAPO.
        renapo_data: Datos retornados por RENAPO (JSON).
        extracted_info: Información extraída de la CURP (JSON).
        errors: Lista de errores encontrados (JSON).
        created_at: Fecha y hora de creación del registro.
        updated_at: Fecha y hora de última actualización.
    """

    __tablename__ = "curp_validations"

    id: Mapped[str] = mapped_column(
        String(36),
        primary_key=True,
        default=lambda: str(uuid.uuid4()),
        comment="Identificador único del registro (UUID v4).",
    )

    request_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("verification_requests.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        comment="FK hacia la solicitud de verificación.",
    )

    curp: Mapped[str] = mapped_column(
        String(18),
        nullable=False,
        index=True,
        comment="CURP validada (normalizada a mayúsculas).",
    )

    is_valid: Mapped[bool] = mapped_column(
        default=False,
        nullable=False,
        comment="Si la CURP pasó todas las validaciones.",
    )

    check_digit_valid: Mapped[bool] = mapped_column(
        default=False,
        nullable=False,
        comment="Si el dígito verificador es correcto.",
    )

    format_valid: Mapped[bool] = mapped_column(
        default=False,
        nullable=False,
        comment="Si el formato de la CURP es válido.",
    )

    renapo_match: Mapped[Optional[bool]] = mapped_column(
        nullable=True,
        default=None,
        comment="Si la CURP fue encontrada en RENAPO.",
    )

    renapo_data: Mapped[Optional[Dict[str, Any]]] = mapped_column(
        JSON,
        nullable=True,
        comment="Datos retornados por RENAPO en formato JSON.",
    )

    extracted_info: Mapped[Optional[Dict[str, Any]]] = mapped_column(
        JSON,
        nullable=True,
        comment="Información extraída de la CURP en formato JSON.",
    )

    errors: Mapped[Optional[list[str]]] = mapped_column(
        JSON,
        nullable=True,
        default=list,
        comment="Lista de errores encontrados durante la validación.",
    )

    # ── Relaciones ───────────────────────────────────────────────────────
    request: Mapped["VerificationRequest"] = relationship(
        "VerificationRequest",
        back_populates="curp_validation",
    )

    def __repr__(self) -> str:
        return (
            f"<CurpValidation(id={self.id!r}, curp={self.curp!r}, "
            f"is_valid={self.is_valid!r})>"
        )


# ---------------------------------------------------------------------------
# Modelo: Validación de RFC
# ---------------------------------------------------------------------------
class RfcValidation(TimestampMixin, Base):
    """
    Resultado de la validación de un RFC.

    Almacena los resultados detallados de la validación de formato,
    dígito verificador y consulta contra el SAT.

    Attributes:
        id: Identificador único del registro.
        request_id: FK hacia la solicitud de verificación.
        rfc: RFC validado (normalizado a mayúsculas).
        is_valid: Si el RFC pasó todas las validaciones.
        person_type: Tipo de persona ('fisica' o 'moral').
        check_digit_valid: Si el dígito verificador es correcto.
        format_valid: Si el formato del RFC es válido.
        sat_active: Si el RFC está activo en el SAT.
        sat_data: Datos retornados por el SAT (JSON).
        extracted_info: Información extraída del RFC (JSON).
        errors: Lista de errores encontrados (JSON).
        created_at: Fecha y hora de creación del registro.
        updated_at: Fecha y hora de última actualización.
    """

    __tablename__ = "rfc_validations"

    id: Mapped[str] = mapped_column(
        String(36),
        primary_key=True,
        default=lambda: str(uuid.uuid4()),
        comment="Identificador único del registro (UUID v4).",
    )

    request_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("verification_requests.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        comment="FK hacia la solicitud de verificación.",
    )

    rfc: Mapped[str] = mapped_column(
        String(13),
        nullable=False,
        index=True,
        comment="RFC validado (normalizado a mayúsculas).",
    )

    is_valid: Mapped[bool] = mapped_column(
        default=False,
        nullable=False,
        comment="Si el RFC pasó todas las validaciones.",
    )

    person_type: Mapped[Optional[str]] = mapped_column(
        String(10),
        nullable=True,
        comment="Tipo de persona: 'fisica' o 'moral'.",
    )

    check_digit_valid: Mapped[bool] = mapped_column(
        default=False,
        nullable=False,
        comment="Si el dígito verificador es correcto.",
    )

    format_valid: Mapped[bool] = mapped_column(
        default=False,
        nullable=False,
        comment="Si el formato del RFC es válido.",
    )

    sat_active: Mapped[Optional[bool]] = mapped_column(
        nullable=True,
        default=None,
        comment="Si el RFC está activo en el SAT.",
    )

    sat_data: Mapped[Optional[Dict[str, Any]]] = mapped_column(
        JSON,
        nullable=True,
        comment="Datos retornados por el SAT en formato JSON.",
    )

    extracted_info: Mapped[Optional[Dict[str, Any]]] = mapped_column(
        JSON,
        nullable=True,
        comment="Información extraída del RFC en formato JSON.",
    )

    errors: Mapped[Optional[list[str]]] = mapped_column(
        JSON,
        nullable=True,
        default=list,
        comment="Lista de errores encontrados durante la validación.",
    )

    # ── Relaciones ───────────────────────────────────────────────────────
    request: Mapped["VerificationRequest"] = relationship(
        "VerificationRequest",
        back_populates="rfc_validation",
    )

    def __repr__(self) -> str:
        return (
            f"<RfcValidation(id={self.id!r}, rfc={self.rfc!r}, "
            f"is_valid={self.is_valid!r})>"
        )
