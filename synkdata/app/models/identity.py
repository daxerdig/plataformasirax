"""
Modelos SQLAlchemy para el módulo de inteligencia de identidad.

Define los modelos ORM para persistir las evaluaciones de
correlación de identidad y evaluación de riesgo, incluyendo:

- ``IdentityCorrelation``: Resultado de la correlación de identidad
- ``RiskAssessment``: Resultado de la evaluación de riesgo

Ambos modelos heredan de ``Base`` y ``TimestampMixin`` para
auditoría y trazabilidad, siguiendo los patrones del proyecto.
"""

from __future__ import annotations

import enum
import uuid
from typing import Any, Dict, List, Optional

from sqlalchemy import JSON, Float, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin


# ---------------------------------------------------------------------------
# Enumeraciones
# ---------------------------------------------------------------------------
class RecommendationType(str, enum.Enum):
    """
    Recomendación resultante de la evaluación de riesgo.

    Attributes:
        APPROVE: Identidad aprobada, riesgo bajo.
        REVIEW: Requiere revisión manual, riesgo medio.
        REJECT: Identidad rechazada, riesgo alto o crítico.
    """

    APPROVE = "APPROVE"
    REVIEW = "REVIEW"
    REJECT = "REJECT"


# ---------------------------------------------------------------------------
# Modelo: Correlación de identidad
# ---------------------------------------------------------------------------
class IdentityCorrelation(TimestampMixin, Base):
    """
    Resultado de la correlación de identidad.

    Almacena los datos de entrada y los resultados de la evaluación
    de consistencia entre todas las señales de identidad proporcionadas:
    nombre, CURP, RFC, correo, teléfono, redes sociales, etc.

    Attributes:
        id: Identificador único del registro (UUID).
        name: Nombre completo evaluado.
        curp: CURP evaluada.
        rfc: RFC evaluado.
        email: Correo electrónico evaluado.
        phone: Número telefónico evaluado.
        username: Nombre de usuario evaluado.
        company: Empresa declarada.
        domain: Dominio declarado.
        identity_confidence: Puntuación de confianza de identidad (0-100).
        signals: Señales de correlación evaluadas (JSON).
        warnings: Advertencias detectadas (JSON).
        flags: Indicadores de alerta (JSON).
    """

    __tablename__ = "identity_correlations"

    id: Mapped[str] = mapped_column(
        String(36),
        primary_key=True,
        default=lambda: str(uuid.uuid4()),
        comment="Identificador único del registro (UUID v4).",
    )

    name: Mapped[Optional[str]] = mapped_column(
        String(500),
        nullable=True,
        index=True,
        comment="Nombre completo evaluado.",
    )

    curp: Mapped[Optional[str]] = mapped_column(
        String(18),
        nullable=True,
        index=True,
        comment="CURP evaluada.",
    )

    rfc: Mapped[Optional[str]] = mapped_column(
        String(13),
        nullable=True,
        index=True,
        comment="RFC evaluado.",
    )

    email: Mapped[Optional[str]] = mapped_column(
        String(320),
        nullable=True,
        index=True,
        comment="Correo electrónico evaluado.",
    )

    phone: Mapped[Optional[str]] = mapped_column(
        String(20),
        nullable=True,
        comment="Número telefónico evaluado (formato E.164).",
    )

    username: Mapped[Optional[str]] = mapped_column(
        String(100),
        nullable=True,
        comment="Nombre de usuario evaluado.",
    )

    company: Mapped[Optional[str]] = mapped_column(
        String(500),
        nullable=True,
        comment="Empresa declarada.",
    )

    domain: Mapped[Optional[str]] = mapped_column(
        String(255),
        nullable=True,
        comment="Dominio declarado.",
    )

    identity_confidence: Mapped[float] = mapped_column(
        Float,
        nullable=False,
        default=0.0,
        comment="Puntuación de confianza de identidad (0-100).",
    )

    signals: Mapped[Optional[List[Dict[str, Any]]]] = mapped_column(
        JSON,
        nullable=True,
        default=list,
        comment="Señales de correlación evaluadas en formato JSON.",
    )

    warnings: Mapped[Optional[List[str]]] = mapped_column(
        JSON,
        nullable=True,
        default=list,
        comment="Advertencias detectadas durante la correlación.",
    )

    flags: Mapped[Optional[List[str]]] = mapped_column(
        JSON,
        nullable=True,
        default=list,
        comment="Indicadores de alerta activados durante la correlación.",
    )

    # ── Relaciones ───────────────────────────────────────────────────────
    risk_assessment: Mapped[Optional["RiskAssessment"]] = relationship(
        "RiskAssessment",
        back_populates="correlation",
        uselist=False,
        lazy="selectin",
        cascade="all, delete-orphan",
    )

    def __repr__(self) -> str:
        return (
            f"<IdentityCorrelation(id={self.id!r}, "
            f"name={self.name!r}, "
            f"identity_confidence={self.identity_confidence!r})>"
        )


# ---------------------------------------------------------------------------
# Modelo: Evaluación de riesgo
# ---------------------------------------------------------------------------
class RiskAssessment(TimestampMixin, Base):
    """
    Resultado de la evaluación de riesgo de identidad.

    Almacena la puntuación de riesgo, confianza, recomendación
    y los factores de riesgo y mitigantes identificados.

    Attributes:
        id: Identificador único del registro (UUID).
        correlation_id: FK hacia la correlación de identidad.
        trust_score: Puntuación de confianza (0-100).
        risk_score: Puntuación de riesgo (0-100).
        recommendation: Recomendación (APPROVE/REVIEW/REJECT).
        risk_factors: Factores de riesgo identificados (JSON).
        mitigating_factors: Factores mitigantes identificados (JSON).
    """

    __tablename__ = "risk_assessments"

    id: Mapped[str] = mapped_column(
        String(36),
        primary_key=True,
        default=lambda: str(uuid.uuid4()),
        comment="Identificador único del registro (UUID v4).",
    )

    correlation_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("identity_correlations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        comment="FK hacia la correlación de identidad.",
    )

    trust_score: Mapped[float] = mapped_column(
        Float,
        nullable=False,
        default=0.0,
        comment="Puntuación de confianza derivada del trust score (0-100).",
    )

    risk_score: Mapped[float] = mapped_column(
        Float,
        nullable=False,
        default=0.0,
        comment="Puntuación de riesgo (0-100, señales negativas).",
    )

    recommendation: Mapped[str] = mapped_column(
        String(10),
        nullable=False,
        default=RecommendationType.REVIEW.value,
        comment="Recomendación: APPROVE, REVIEW o REJECT.",
    )

    risk_factors: Mapped[Optional[List[Dict[str, Any]]]] = mapped_column(
        JSON,
        nullable=True,
        default=list,
        comment="Factores de riesgo identificados en formato JSON.",
    )

    mitigating_factors: Mapped[Optional[List[Dict[str, Any]]]] = mapped_column(
        JSON,
        nullable=True,
        default=list,
        comment="Factores mitigantes identificados en formato JSON.",
    )

    # ── Relaciones ───────────────────────────────────────────────────────
    correlation: Mapped["IdentityCorrelation"] = relationship(
        "IdentityCorrelation",
        back_populates="risk_assessment",
    )

    def __repr__(self) -> str:
        return (
            f"<RiskAssessment(id={self.id!r}, "
            f"risk_score={self.risk_score!r}, "
            f"recommendation={self.recommendation!r})>"
        )
