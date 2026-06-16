"""
Modelo base y mixins reutilizables para SynkData.

Proporciona:
- ``Base``: Clase declarativa base de SQLAlchemy para todos los modelos.
- ``TimestampMixin``: Mixin que agrega columnas de timestamps automáticos
  (created_at, updated_at) con soporte para zonas horarias.
- ``SoftDeleteMixin``: Mixin para eliminación lógica (soft delete).

Todos los modelos del proyecto deben heredar de ``Base`` y pueden
combinar los mixins según sus necesidades.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import DateTime, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


# ---------------------------------------------------------------------------
# Base declarativa
# ---------------------------------------------------------------------------
class Base(DeclarativeBase):
    """
    Clase base declarativa para todos los modelos SQLAlchemy de SynkData.

    Heredar de esta clase garantiza que todos los modelos compartan
    los metadatos necesarios para las migraciones de Alembic.

    Note:
        No confundir con ``app.database.Base``. Este módulo es la fuente
        canónica de la base declarativa; ``app.database`` la re-exporta.
    """
    pass


# ---------------------------------------------------------------------------
# Mixins
# ---------------------------------------------------------------------------
class TimestampMixin:
    """
    Mixin que agrega columnas de timestamp automáticas a cualquier modelo.

    Attributes:
        created_at: Fecha y hora de creación del registro (UTC).
        updated_at: Fecha y hora de la última actualización (UTC).

    Example:
        class User(TimestampMixin, Base):
            __tablename__ = "users"
            id: Mapped[int] = mapped_column(primary_key=True)
            email: Mapped[str] = mapped_column(String(255))
    """

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
        comment="Fecha y hora de creación del registro (UTC).",
    )

    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
        comment="Fecha y hora de la última actualización (UTC).",
    )


class SoftDeleteMixin:
    """
    Mixin para eliminación lógica (soft delete) de registros.

    En lugar de eliminar físicamente un registro, se marca como
    eliminado estableciendo ``deleted_at`` a la fecha/hora actual.

    Attributes:
        deleted_at: Fecha y hora de eliminación lógica (None = activo).
        is_deleted: Propiedad que retorna True si el registro fue eliminado.

    Example:
        class Document(SoftDeleteMixin, TimestampMixin, Base):
            __tablename__ = "documents"
            id: Mapped[int] = mapped_column(primary_key=True)
    """

    deleted_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        default=None,
        comment="Fecha y hora de eliminación lógica (None = activo).",
    )

    @property
    def is_deleted(self) -> bool:
        """Retorna True si el registro fue eliminado lógicamente."""
        return self.deleted_at is not None

    def soft_delete(self) -> None:
        """Marca el registro como eliminado lógicamente."""
        self.deleted_at = datetime.now(timezone.utc)

    def restore(self) -> None:
        """Restaura un registro eliminado lógicamente."""
        self.deleted_at = None
