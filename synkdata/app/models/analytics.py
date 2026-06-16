"""
Modelos SQLAlchemy para el módulo de analítica y monitoreo.

Define los modelos ORM para persistir eventos de verificación y alertas
del sistema de inteligencia de identidad, incluyendo:

- ``VerificationEvent``: Evento de verificación de identidad registrado
- ``Alert``: Alerta del sistema de monitoreo

Ambos modelos heredan de ``Base`` y ``TimestampMixin`` para
auditoría y trazabilidad, siguiendo los patrones del proyecto.
Los índices están optimizados para consultas por rango de fechas.
"""

from __future__ import annotations

import enum
import uuid
from typing import Any, Dict, List, Optional

from sqlalchemy import (
    Boolean,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin


# ---------------------------------------------------------------------------
# Enumeraciones
# ---------------------------------------------------------------------------
class AlertSeverity(str, enum.Enum):
    """
    Severidad de una alerta del sistema.

    Attributes:
        CRITICAL: Alerta crítica que requiere atención inmediata.
        HIGH: Alerta de alta prioridad.
        MEDIUM: Alerta de prioridad media.
        LOW: Alerta de baja prioridad.
        INFO: Alerta informativa.
    """

    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    INFO = "info"


class AlertType(str, enum.Enum):
    """
    Tipo de alerta del sistema.

    Attributes:
        SCREENING_HIT: Coincidencia en lista restrictiva.
        RISK_THRESHOLD: Umbral de riesgo superado.
        IDENTITY_ANOMALY: Anomalía en la identidad detectada.
        VERIFICATION_FAILED: Verificación fallida.
        SYSTEM_ERROR: Error del sistema.
        COMPLIANCE_REMINDER: Recordatorio de cumplimiento.
        PATTERN_DETECTED: Patrón sospechoso detectado.
    """

    SCREENING_HIT = "screening_hit"
    RISK_THRESHOLD = "risk_threshold"
    IDENTITY_ANOMALY = "identity_anomaly"
    VERIFICATION_FAILED = "verification_failed"
    SYSTEM_ERROR = "system_error"
    COMPLIANCE_REMINDER = "compliance_reminder"
    PATTERN_DETECTED = "pattern_detected"


# ---------------------------------------------------------------------------
# Modelo: Evento de verificación
# ---------------------------------------------------------------------------
class VerificationEvent(TimestampMixin, Base):
    """
    Evento de verificación de identidad registrado en el sistema.

    Almacena cada verificación realizada con sus métricas clave para
    alimentar los dashboards de analítica y monitoreo.

    Attributes:
        id: Identificador único del evento (UUID).
        entity_type: Tipo de entidad verificada (person/company).
        entity_name: Nombre de la entidad verificada.
        curp: CURP de la persona verificada (si aplica).
        rfc: RFC del contribuyente verificado (si aplica).
        recommendation: Resultado de la verificación (APPROVE/REVIEW/REJECT).
        trust_score: Puntuación de confianza (0-100).
        risk_score: Puntuación de riesgo (0-100).
        processing_time_ms: Tiempo de procesamiento en milisegundos.
        region: Región geográfica de la entidad.
        industry: Industria o sector de la entidad.
    """

    __tablename__ = "verification_events"

    id: Mapped[str] = mapped_column(
        String(36),
        primary_key=True,
        default=lambda: str(uuid.uuid4()),
        comment="Identificador único del evento (UUID v4).",
    )

    entity_type: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="person",
        index=True,
        comment="Tipo de entidad verificada: person o company.",
    )

    entity_name: Mapped[str] = mapped_column(
        String(500),
        nullable=False,
        index=True,
        comment="Nombre de la entidad verificada.",
    )

    curp: Mapped[Optional[str]] = mapped_column(
        String(18),
        nullable=True,
        index=True,
        comment="CURP de la persona verificada (si aplica).",
    )

    rfc: Mapped[Optional[str]] = mapped_column(
        String(13),
        nullable=True,
        index=True,
        comment="RFC del contribuyente verificado (si aplica).",
    )

    recommendation: Mapped[str] = mapped_column(
        String(10),
        nullable=False,
        default="REVIEW",
        index=True,
        comment="Resultado de la verificación: APPROVE, REVIEW o REJECT.",
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
        comment="Puntuación de riesgo (0-100).",
    )

    processing_time_ms: Mapped[Optional[int]] = mapped_column(
        Integer,
        nullable=True,
        comment="Tiempo de procesamiento en milisegundos.",
    )

    region: Mapped[Optional[str]] = mapped_column(
        String(100),
        nullable=True,
        index=True,
        comment="Región geográfica de la entidad (estado de México).",
    )

    industry: Mapped[Optional[str]] = mapped_column(
        String(100),
        nullable=True,
        index=True,
        comment="Industria o sector de la entidad.",
    )

    # ── Índices compuestos para consultas eficientes ──────────────────────
    __table_args__ = (
        Index(
            "ix_verification_events_created_at",
            "created_at",
        ),
        Index(
            "ix_verification_events_recommendation_created",
            "recommendation",
            "created_at",
        ),
        Index(
            "ix_verification_events_region_created",
            "region",
            "created_at",
        ),
        Index(
            "ix_verification_events_industry_created",
            "industry",
            "created_at",
        ),
    )

    def __repr__(self) -> str:
        return (
            f"<VerificationEvent(id={self.id!r}, "
            f"entity_name={self.entity_name!r}, "
            f"recommendation={self.recommendation!r}, "
            f"risk_score={self.risk_score!r})>"
        )


# ---------------------------------------------------------------------------
# Modelo: Alerta del sistema
# ---------------------------------------------------------------------------
class Alert(TimestampMixin, Base):
    """
    Alerta generada por el sistema de monitoreo.

    Almacena las alertas producidas por el sistema cuando se detectan
    eventos que requieren atención, como coincidencias en listas
    restrictivas, umbrales de riesgo superados o anomalías.

    Attributes:
        id: Identificador único de la alerta (UUID).
        severity: Severidad de la alerta (critical/high/medium/low/info).
        alert_type: Tipo de alerta (screening_hit, risk_threshold, etc.).
        message: Mensaje descriptivo de la alerta en español.
        entity_id: ID de la entidad asociada a la alerta.
        is_read: Si la alerta ha sido leída por un analista.
        is_resolved: Si la alerta ha sido resuelta.
        resolved_by: ID del usuario que resolvió la alerta.
        resolved_at: Fecha y hora de resolución.
    """

    __tablename__ = "alerts"

    id: Mapped[str] = mapped_column(
        String(36),
        primary_key=True,
        default=lambda: str(uuid.uuid4()),
        comment="Identificador único de la alerta (UUID v4).",
    )

    severity: Mapped[AlertSeverity] = mapped_column(
        Enum(AlertSeverity),
        nullable=False,
        default=AlertSeverity.MEDIUM,
        index=True,
        comment="Severidad de la alerta: critical, high, medium, low, info.",
    )

    alert_type: Mapped[AlertType] = mapped_column(
        Enum(AlertType),
        nullable=False,
        index=True,
        comment="Tipo de alerta: screening_hit, risk_threshold, etc.",
    )

    message: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        comment="Mensaje descriptivo de la alerta en español.",
    )

    entity_id: Mapped[Optional[str]] = mapped_column(
        String(36),
        nullable=True,
        index=True,
        comment="ID de la entidad asociada a la alerta.",
    )

    is_read: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        index=True,
        comment="Si la alerta ha sido leída por un analista.",
    )

    is_resolved: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        index=True,
        comment="Si la alerta ha sido resuelta.",
    )

    resolved_by: Mapped[Optional[str]] = mapped_column(
        String(36),
        nullable=True,
        comment="ID del usuario que resolvió la alerta.",
    )

    resolved_at: Mapped[Optional[str]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        comment="Fecha y hora de resolución de la alerta.",
    )

    # ── Índices compuestos ───────────────────────────────────────────────
    __table_args__ = (
        Index(
            "ix_alerts_severity_created",
            "severity",
            "created_at",
        ),
        Index(
            "ix_alerts_type_created",
            "alert_type",
            "created_at",
        ),
        Index(
            "ix_alerts_unread",
            "is_read",
            "severity",
            "created_at",
        ),
    )

    def __repr__(self) -> str:
        return (
            f"<Alert(id={self.id!r}, "
            f"severity={self.severity.value!r}, "
            f"alert_type={self.alert_type.value!r}, "
            f"is_read={self.is_read!r})>"
        )
