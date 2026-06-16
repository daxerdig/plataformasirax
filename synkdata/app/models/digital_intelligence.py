"""
Modelos SQLAlchemy para el módulo de inteligencia digital.

Define los modelos ORM para persistir las solicitudes de análisis
de inteligencia digital y sus resultados individuales, incluyendo:

- ``DigitalIntelligenceRequest``: Solicitud completa de análisis digital
- ``EmailAnalysis``: Resultado del análisis de inteligencia de correo electrónico
- ``PhoneAnalysis``: Resultado del análisis de inteligencia telefónica
- ``UsernameAnalysis``: Resultado del análisis de inteligencia de nombre de usuario

Todos los modelos heredan de ``Base`` y ``TimestampMixin`` para
auditoría y trazabilidad, siguiendo los patrones del proyecto.
"""

from __future__ import annotations

import enum
import uuid
from typing import Any, Dict, List, Optional

from sqlalchemy import JSON, Boolean, DateTime, Enum, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin


# ---------------------------------------------------------------------------
# Enumeraciones
# ---------------------------------------------------------------------------
class AnalysisStatus(str, enum.Enum):
    """
    Estado de una solicitud de análisis de inteligencia digital.

    Attributes:
        PENDING: Análisis en proceso.
        COMPLETED: Análisis completado exitosamente.
        FAILED: El análisis falló (error técnico).
        PARTIAL: Análisis parcialmente completado (algunas fuentes no respondieron).
    """

    PENDING = "pending"
    COMPLETED = "completed"
    FAILED = "failed"
    PARTIAL = "partial"


class LineType(str, enum.Enum):
    """
    Tipo de línea telefónica detectada.

    Attributes:
        MOBILE: Teléfono móvil / celular.
        FIXED: Línea fija.
        VOIP: Voz sobre IP.
        TOLL_FREE: Línea gratuita.
        PREMIUM: Línea premium / de pago.
        PAGER: Buscapersonas / pager.
        PERSONAL: Número personal.
        UNKNOWN: Tipo desconocido.
    """

    MOBILE = "mobile"
    FIXED = "fixed"
    VOIP = "voip"
    TOLL_FREE = "toll_free"
    PREMIUM = "premium"
    PAGER = "pager"
    PERSONAL = "personal"
    UNKNOWN = "unknown"


class DomainReputation(str, enum.Enum):
    """
    Reputación del dominio de correo electrónico.

    Attributes:
        HIGH: Dominio de alta reputación (ej. gmail.com, outlook.com).
        MEDIUM: Dominio de reputación media (ej. dominios corporativos).
        LOW: Dominio de baja reputación.
        DISPOSABLE: Dominio de correo desechable.
        SUSPICIOUS: Dominio sospechoso.
        UNKNOWN: Reputación desconocida.
    """

    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    DISPOSABLE = "disposable"
    SUSPICIOUS = "suspicious"
    UNKNOWN = "unknown"


# ---------------------------------------------------------------------------
# Modelo principal: Solicitud de inteligencia digital
# ---------------------------------------------------------------------------
class DigitalIntelligenceRequest(TimestampMixin, Base):
    """
    Solicitud de análisis de inteligencia digital.

    Representa una solicitud completa que puede incluir análisis de
    correo electrónico, teléfono, nombre de usuario y descubrimiento
    social. Almacena los datos de entrada y los resultados agregados.

    Attributes:
        id: Identificador único de la solicitud (UUID).
        email: Correo electrónico a analizar (opcional).
        phone: Número telefónico a analizar (opcional).
        username: Nombre de usuario a analizar (opcional).
        name: Nombre completo de la persona (opcional).
        status: Estado actual del análisis.
        results: Resultados agregados del análisis en formato JSON.
    """

    __tablename__ = "digital_intelligence_requests"

    id: Mapped[str] = mapped_column(
        String(36),
        primary_key=True,
        default=lambda: str(uuid.uuid4()),
        comment="Identificador único de la solicitud (UUID v4).",
    )

    email: Mapped[Optional[str]] = mapped_column(
        String(320),
        nullable=True,
        index=True,
        comment="Correo electrónico a analizar.",
    )

    phone: Mapped[Optional[str]] = mapped_column(
        String(20),
        nullable=True,
        index=True,
        comment="Número telefónico a analizar (formato E.164).",
    )

    username: Mapped[Optional[str]] = mapped_column(
        String(100),
        nullable=True,
        index=True,
        comment="Nombre de usuario a analizar.",
    )

    name: Mapped[Optional[str]] = mapped_column(
        String(500),
        nullable=True,
        index=True,
        comment="Nombre completo de la persona para descubrimiento social.",
    )

    status: Mapped[AnalysisStatus] = mapped_column(
        Enum(AnalysisStatus),
        default=AnalysisStatus.PENDING,
        nullable=False,
        index=True,
        comment="Estado actual del análisis de inteligencia digital.",
    )

    results: Mapped[Optional[Dict[str, Any]]] = mapped_column(
        JSON,
        nullable=True,
        comment="Resultados agregados del análisis en formato JSON.",
    )

    # ── Relaciones ───────────────────────────────────────────────────────
    email_analysis: Mapped[Optional["EmailAnalysis"]] = relationship(
        "EmailAnalysis",
        back_populates="request",
        uselist=False,
        lazy="selectin",
        cascade="all, delete-orphan",
    )

    phone_analysis: Mapped[Optional["PhoneAnalysis"]] = relationship(
        "PhoneAnalysis",
        back_populates="request",
        uselist=False,
        lazy="selectin",
        cascade="all, delete-orphan",
    )

    username_analysis: Mapped[Optional["UsernameAnalysis"]] = relationship(
        "UsernameAnalysis",
        back_populates="request",
        uselist=False,
        lazy="selectin",
        cascade="all, delete-orphan",
    )

    def __repr__(self) -> str:
        return (
            f"<DigitalIntelligenceRequest(id={self.id!r}, "
            f"email={self.email!r}, phone={self.phone!r}, "
            f"username={self.username!r}, status={self.status.value!r})>"
        )


# ---------------------------------------------------------------------------
# Modelo: Análisis de correo electrónico
# ---------------------------------------------------------------------------
class EmailAnalysis(TimestampMixin, Base):
    """
    Resultado del análisis de inteligencia de correo electrónico.

    Almacena los resultados de la verificación de formato, detección
    de dominios desechables, verificación de breaches (HIBP),
    entregabilidad y reputación del dominio.

    Attributes:
        id: Identificador único del registro.
        request_id: FK hacia la solicitud de inteligencia digital.
        email: Correo electrónico analizado (normalizado a minúsculas).
        is_valid_format: Si el formato del correo es válido.
        is_disposable: Si el dominio es de un proveedor desechable.
        breach_count: Número de breaches donde aparece el correo.
        deliverable: Si el correo es entregable (MX válido + SMTP).
        mx_records: Registros MX del dominio (JSON).
        domain_reputation: Reputación del dominio.
        risk_flags: Indicadores de riesgo identificados (JSON).
        breaches: Lista de breaches encontrados (JSON).
        related_accounts: Cuentas relacionadas encontradas (JSON).
    """

    __tablename__ = "email_analyses"

    id: Mapped[str] = mapped_column(
        String(36),
        primary_key=True,
        default=lambda: str(uuid.uuid4()),
        comment="Identificador único del registro (UUID v4).",
    )

    request_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("digital_intelligence_requests.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        comment="FK hacia la solicitud de inteligencia digital.",
    )

    email: Mapped[str] = mapped_column(
        String(320),
        nullable=False,
        index=True,
        comment="Correo electrónico analizado (normalizado a minúsculas).",
    )

    is_valid_format: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        nullable=False,
        comment="Si el formato del correo electrónico es válido.",
    )

    is_disposable: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        nullable=False,
        comment="Si el dominio pertenece a un proveedor de correo desechable.",
    )

    breach_count: Mapped[int] = mapped_column(
        Integer,
        default=0,
        nullable=False,
        comment="Número de breaches donde aparece el correo.",
    )

    deliverable: Mapped[Optional[bool]] = mapped_column(
        Boolean,
        nullable=True,
        default=None,
        comment="Si el correo es entregable (MX válido + verificación SMTP).",
    )

    mx_records: Mapped[Optional[List[str]]] = mapped_column(
        JSON,
        nullable=True,
        default=list,
        comment="Registros MX del dominio en formato JSON.",
    )

    domain_reputation: Mapped[str] = mapped_column(
        String(20),
        default=DomainReputation.UNKNOWN.value,
        nullable=False,
        comment="Reputación del dominio: high, medium, low, disposable, suspicious, unknown.",
    )

    risk_flags: Mapped[Optional[List[str]]] = mapped_column(
        JSON,
        nullable=True,
        default=list,
        comment="Lista de indicadores de riesgo identificados.",
    )

    breaches: Mapped[Optional[List[Dict[str, Any]]]] = mapped_column(
        JSON,
        nullable=True,
        default=list,
        comment="Lista de breaches encontrados con nombre, fecha y datos comprometidos.",
    )

    related_accounts: Mapped[Optional[List[Dict[str, Any]]]] = mapped_column(
        JSON,
        nullable=True,
        default=list,
        comment="Cuentas relacionadas encontradas vía Hunter.io u otras fuentes.",
    )

    # ── Relaciones ───────────────────────────────────────────────────────
    request: Mapped["DigitalIntelligenceRequest"] = relationship(
        "DigitalIntelligenceRequest",
        back_populates="email_analysis",
    )

    def __repr__(self) -> str:
        return (
            f"<EmailAnalysis(id={self.id!r}, email={self.email!r}, "
            f"is_valid={self.is_valid_format!r}, "
            f"breach_count={self.breach_count!r})>"
        )


# ---------------------------------------------------------------------------
# Modelo: Análisis telefónico
# ---------------------------------------------------------------------------
class PhoneAnalysis(TimestampMixin, Base):
    """
    Resultado del análisis de inteligencia telefónica.

    Almacena los resultados de la validación de formato, información
    del carrier, tipo de línea, detección de spam y geolocalización.

    Attributes:
        id: Identificador único del registro.
        request_id: FK hacia la solicitud de inteligencia digital.
        phone: Número telefónico analizado (formato E.164).
        is_valid: Si el número telefónico es válido.
        country_code: Código de país (ISO 3166-1 alpha-2).
        carrier: Nombre del operador/carrier.
        line_type: Tipo de línea (mobile, fixed, voip, etc.).
        is_spam: Si el número ha sido reportado como spam.
        spam_reports: Número de reportes de spam.
        region: Región/geográfica asociada al número.
        number_type: Tipo de número según la librería phonenumbers.
        risk_flags: Indicadores de riesgo identificados (JSON).
    """

    __tablename__ = "phone_analyses"

    id: Mapped[str] = mapped_column(
        String(36),
        primary_key=True,
        default=lambda: str(uuid.uuid4()),
        comment="Identificador único del registro (UUID v4).",
    )

    request_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("digital_intelligence_requests.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        comment="FK hacia la solicitud de inteligencia digital.",
    )

    phone: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        index=True,
        comment="Número telefónico analizado (formato E.164).",
    )

    is_valid: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        nullable=False,
        comment="Si el número telefónico es válido según la librería phonenumbers.",
    )

    country_code: Mapped[Optional[str]] = mapped_column(
        String(5),
        nullable=True,
        comment="Código de país ISO 3166-1 alpha-2 (ej. MX, US, ES).",
    )

    carrier: Mapped[Optional[str]] = mapped_column(
        String(200),
        nullable=True,
        comment="Nombre del operador/carrier del número.",
    )

    line_type: Mapped[str] = mapped_column(
        String(20),
        default=LineType.UNKNOWN.value,
        nullable=False,
        comment="Tipo de línea: mobile, fixed, voip, toll_free, premium, pager, personal, unknown.",
    )

    is_spam: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        nullable=False,
        comment="Si el número ha sido reportado como spam o estafa.",
    )

    spam_reports: Mapped[int] = mapped_column(
        Integer,
        default=0,
        nullable=False,
        comment="Número de reportes de spam/estafa recibidos.",
    )

    region: Mapped[Optional[str]] = mapped_column(
        String(200),
        nullable=True,
        comment="Región geográfica asociada al número telefónico.",
    )

    number_type: Mapped[Optional[str]] = mapped_column(
        String(30),
        nullable=True,
        comment="Tipo de número según la clasificación de phonenumbers.",
    )

    risk_flags: Mapped[Optional[List[str]]] = mapped_column(
        JSON,
        nullable=True,
        default=list,
        comment="Lista de indicadores de riesgo identificados.",
    )

    # ── Relaciones ───────────────────────────────────────────────────────
    request: Mapped["DigitalIntelligenceRequest"] = relationship(
        "DigitalIntelligenceRequest",
        back_populates="phone_analysis",
    )

    def __repr__(self) -> str:
        return (
            f"<PhoneAnalysis(id={self.id!r}, phone={self.phone!r}, "
            f"is_valid={self.is_valid!r}, line_type={self.line_type!r})>"
        )


# ---------------------------------------------------------------------------
# Modelo: Análisis de nombre de usuario
# ---------------------------------------------------------------------------
class UsernameAnalysis(TimestampMixin, Base):
    """
    Resultado del análisis de inteligencia de nombre de usuario.

    Almacena los resultados de la búsqueda de perfiles en múltiples
    plataformas, puntuación de presencia digital y categorías
    de actividad identificadas.

    Attributes:
        id: Identificador único del registro.
        request_id: FK hacia la solicitud de inteligencia digital.
        username: Nombre de usuario analizado.
        total_profiles: Número total de perfiles encontrados.
        platforms_found: Lista de plataformas donde se encontró el usuario (JSON).
        presence_score: Puntuación de presencia digital (0-100).
        profiles: Detalle de los perfiles encontrados (JSON).
        categories: Categorías de actividad identificadas (JSON).
        risk_flags: Indicadores de riesgo identificados (JSON).
    """

    __tablename__ = "username_analyses"

    id: Mapped[str] = mapped_column(
        String(36),
        primary_key=True,
        default=lambda: str(uuid.uuid4()),
        comment="Identificador único del registro (UUID v4).",
    )

    request_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("digital_intelligence_requests.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        comment="FK hacia la solicitud de inteligencia digital.",
    )

    username: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        index=True,
        comment="Nombre de usuario analizado.",
    )

    total_profiles: Mapped[int] = mapped_column(
        Integer,
        default=0,
        nullable=False,
        comment="Número total de perfiles encontrados en todas las plataformas.",
    )

    platforms_found: Mapped[Optional[List[str]]] = mapped_column(
        JSON,
        nullable=True,
        default=list,
        comment="Lista de nombres de plataformas donde se encontró el usuario.",
    )

    presence_score: Mapped[float] = mapped_column(
        Float,
        default=0.0,
        nullable=False,
        comment="Puntuación de presencia digital (0.0 a 100.0).",
    )

    profiles: Mapped[Optional[List[Dict[str, Any]]]] = mapped_column(
        JSON,
        nullable=True,
        default=list,
        comment="Detalle de los perfiles encontrados en cada plataforma.",
    )

    categories: Mapped[Optional[List[str]]] = mapped_column(
        JSON,
        nullable=True,
        default=list,
        comment="Categorías de actividad identificadas (developer, social, professional, etc.).",
    )

    risk_flags: Mapped[Optional[List[str]]] = mapped_column(
        JSON,
        nullable=True,
        default=list,
        comment="Lista de indicadores de riesgo identificados.",
    )

    # ── Relaciones ───────────────────────────────────────────────────────
    request: Mapped["DigitalIntelligenceRequest"] = relationship(
        "DigitalIntelligenceRequest",
        back_populates="username_analysis",
    )

    def __repr__(self) -> str:
        return (
            f"<UsernameAnalysis(id={self.id!r}, username={self.username!r}, "
            f"total_profiles={self.total_profiles!r}, "
            f"presence_score={self.presence_score!r})>"
        )
