"""
Modelos SQLAlchemy para el módulo de screening en listas restrictivas.

Define los modelos ORM para persistir las solicitudes de screening,
coincidencias individuales y entradas de listas restrictivas, incluyendo:

- ``ScreeningRequest``: Solicitud de screening completa
- ``ScreeningMatch``: Coincidencia individual de una fuente
- ``WatchlistEntry``: Entrada cacheada de una lista restrictiva

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
class ScreeningStatus(str, enum.Enum):
    """
    Estado de una solicitud de screening.

    Attributes:
        PENDING: Screening en proceso.
        COMPLETED: Screening completado exitosamente.
        FAILED: El screening falló (error técnico).
        PARTIAL: Screening parcialmente completado (algunas fuentes no respondieron).
    """

    PENDING = "pending"
    COMPLETED = "completed"
    FAILED = "failed"
    PARTIAL = "partial"


class ScreeningEntityType(str, enum.Enum):
    """
    Tipo de entidad sometida a screening.

    Attributes:
        PERSON: Persona física.
        ENTITY: Persona moral / entidad corporativa.
    """

    PERSON = "person"
    ENTITY = "entity"


class RiskLevel(str, enum.Enum):
    """
    Nivel de riesgo resultante del screening.

    Attributes:
        NONE: Sin riesgo identificado.
        LOW: Riesgo bajo.
        MEDIUM: Riesgo medio.
        HIGH: Riesgo alto.
        CRITICAL: Riesgo crítico.
    """

    NONE = "none"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class MatchType(str, enum.Enum):
    """
    Tipo de coincidencia detectada.

    Attributes:
        EXACT: Coincidencia exacta (normalizada).
        FUZZY: Coincidencia difusa (Levenshtein).
        PHONETIC: Coincidencia fonética (español).
        ALIAS: Coincidencia con alias/nombre alternativo.
    """

    EXACT = "exact"
    FUZZY = "fuzzy"
    PHONETIC = "phonetic"
    ALIAS = "alias"


class WatchlistSource(str, enum.Enum):
    """
    Fuentes de listas restrictivas soportadas.

    Attributes:
        OFAC: Office of Foreign Assets Control (SDN List).
        UN_SANCTIONS: UN Security Council Consolidated List.
        INTERPOL: Interpol Red Notices.
        OPEN_SANCTIONS: OpenSanctions aggregator.
        SAT_69B: SAT Artículo 69-B (México).
        DOF: Diario Oficial de la Federación (México).
        SCJN: Suprema Corte de Justicia de la Nación (México).
        PEP: Politically Exposed Persons.
    """

    OFAC = "ofac"
    UN_SANCTIONS = "un_sanctions"
    INTERPOL = "interpol"
    OPEN_SANCTIONS = "open_sanctions"
    SAT_69B = "sat_69b"
    DOF = "dof"
    SCJN = "scjn"
    PEP = "pep"


# ---------------------------------------------------------------------------
# Modelo principal: Solicitud de screening
# ---------------------------------------------------------------------------
class ScreeningRequest(TimestampMixin, Base):
    """
    Solicitud de screening en listas restrictivas.

    Representa una solicitud completa de screening que puede incluir
    verificación en múltiples fuentes (OFAC, ONU, Interpol, SAT, etc.).

    Attributes:
        id: Identificador único de la solicitud (UUID).
        name: Nombre de la persona o entidad a screening.
        curp: CURP de la persona (si aplica).
        rfc: RFC del contribuyente (si aplica).
        entity_type: Tipo de entidad (persona/entidad).
        status: Estado actual del screening.
        results: Resultados agregados del screening en formato JSON.
    """

    __tablename__ = "screening_requests"

    id: Mapped[str] = mapped_column(
        String(36),
        primary_key=True,
        default=lambda: str(uuid.uuid4()),
        comment="Identificador único de la solicitud (UUID v4).",
    )

    name: Mapped[str] = mapped_column(
        String(500),
        nullable=False,
        index=True,
        comment="Nombre de la persona o entidad sometida a screening.",
    )

    curp: Mapped[Optional[str]] = mapped_column(
        String(18),
        nullable=True,
        index=True,
        comment="CURP de la persona (si aplica).",
    )

    rfc: Mapped[Optional[str]] = mapped_column(
        String(13),
        nullable=True,
        index=True,
        comment="RFC del contribuyente (si aplica).",
    )

    entity_type: Mapped[ScreeningEntityType] = mapped_column(
        Enum(ScreeningEntityType),
        default=ScreeningEntityType.PERSON,
        nullable=False,
        comment="Tipo de entidad: persona física o moral.",
    )

    status: Mapped[ScreeningStatus] = mapped_column(
        Enum(ScreeningStatus),
        default=ScreeningStatus.PENDING,
        nullable=False,
        index=True,
        comment="Estado actual del screening.",
    )

    results: Mapped[Optional[Dict[str, Any]]] = mapped_column(
        JSON,
        nullable=True,
        comment="Resultados agregados del screening en formato JSON.",
    )

    # ── Relaciones ───────────────────────────────────────────────────────
    matches: Mapped[List["ScreeningMatch"]] = relationship(
        "ScreeningMatch",
        back_populates="request",
        lazy="selectin",
        cascade="all, delete-orphan",
    )

    def __repr__(self) -> str:
        return (
            f"<ScreeningRequest(id={self.id!r}, "
            f"name={self.name!r}, "
            f"status={self.status.value!r})>"
        )


# ---------------------------------------------------------------------------
# Modelo: Coincidencia individual de screening
# ---------------------------------------------------------------------------
class ScreeningMatch(TimestampMixin, Base):
    """
    Coincidencia individual encontrada durante el screening.

    Cada registro representa una coincidencia en una fuente específica,
    con su puntuación, tipo de coincidencia y datos de la entidad.

    Attributes:
        id: Identificador único del registro (UUID).
        request_id: FK hacia la solicitud de screening.
        source: Fuente donde se encontró la coincidencia.
        match_score: Puntuación de similitud (0.0 a 1.0).
        match_type: Tipo de coincidencia (exact/fuzzy/phonetic/alias).
        entity_name: Nombre de la entidad coincidente en la fuente.
        entity_data: Datos adicionales de la entidad en formato JSON.
        is_confirmed: Si la coincidencia fue confirmada manualmente.
    """

    __tablename__ = "screening_matches"

    id: Mapped[str] = mapped_column(
        String(36),
        primary_key=True,
        default=lambda: str(uuid.uuid4()),
        comment="Identificador único del registro (UUID v4).",
    )

    request_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("screening_requests.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        comment="FK hacia la solicitud de screening.",
    )

    source: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        index=True,
        comment="Fuente donde se encontró la coincidencia (ofac, un_sanctions, etc.).",
    )

    match_score: Mapped[float] = mapped_column(
        Float,
        nullable=False,
        comment="Puntuación de similitud (0.0 a 1.0).",
    )

    match_type: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        comment="Tipo de coincidencia: exact, fuzzy, phonetic, alias.",
    )

    entity_name: Mapped[str] = mapped_column(
        String(500),
        nullable=False,
        comment="Nombre de la entidad coincidente en la fuente.",
    )

    entity_data: Mapped[Optional[Dict[str, Any]]] = mapped_column(
        JSON,
        nullable=True,
        comment="Datos adicionales de la entidad en formato JSON.",
    )

    is_confirmed: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        nullable=False,
        comment="Si la coincidencia fue confirmada manualmente por un analista.",
    )

    # ── Relaciones ───────────────────────────────────────────────────────
    request: Mapped["ScreeningRequest"] = relationship(
        "ScreeningRequest",
        back_populates="matches",
    )

    def __repr__(self) -> str:
        return (
            f"<ScreeningMatch(id={self.id!r}, "
            f"source={self.source!r}, "
            f"score={self.match_score!r}, "
            f"entity_name={self.entity_name!r})>"
        )


# ---------------------------------------------------------------------------
# Modelo: Entrada de lista restrictiva (cache local)
# ---------------------------------------------------------------------------
class WatchlistEntry(TimestampMixin, Base):
    """
    Entrada de una lista restrictiva cacheada localmente.

    Almacena los datos de las listas restrictivas descargadas para
    consultas rápidas sin necesidad de acceder a las APIs externas
    en cada solicitud.

    Attributes:
        id: Identificador único del registro (UUID).
        source: Fuente de la lista restrictiva.
        entity_name: Nombre de la persona o entidad.
        entity_type: Tipo de entidad (individual, entity, vessel, etc.).
        aliases: Nombres alternativos o alias (JSON).
        country: País asociado a la entidad.
        data: Datos completos de la entidad en formato JSON.
        last_updated: Fecha de última actualización desde la fuente.
    """

    __tablename__ = "watchlist_entries"

    id: Mapped[str] = mapped_column(
        String(36),
        primary_key=True,
        default=lambda: str(uuid.uuid4()),
        comment="Identificador único del registro (UUID v4).",
    )

    source: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        index=True,
        comment="Fuente de la lista restrictiva (ofac, un_sanctions, etc.).",
    )

    entity_name: Mapped[str] = mapped_column(
        String(500),
        nullable=False,
        index=True,
        comment="Nombre de la persona o entidad en la lista.",
    )

    entity_type: Mapped[str] = mapped_column(
        String(50),
        nullable=True,
        comment="Tipo de entidad: individual, entity, vessel, aircraft.",
    )

    aliases: Mapped[Optional[List[str]]] = mapped_column(
        JSON,
        nullable=True,
        default=list,
        comment="Lista de nombres alternativos o alias en formato JSON.",
    )

    country: Mapped[Optional[str]] = mapped_column(
        String(5),
        nullable=True,
        index=True,
        comment="Código ISO del país asociado a la entidad.",
    )

    data: Mapped[Optional[Dict[str, Any]]] = mapped_column(
        JSON,
        nullable=True,
        comment="Datos completos de la entidad en formato JSON.",
    )

    last_updated: Mapped[Optional[str]] = mapped_column(
        String(30),
        nullable=True,
        comment="Fecha de última actualización desde la fuente original.",
    )

    def __repr__(self) -> str:
        return (
            f"<WatchlistEntry(id={self.id!r}, "
            f"source={self.source!r}, "
            f"entity_name={self.entity_name!r})>"
        )
