"""
Modelos de datos de SynkData Identity Intelligence Platform.

Este paquete centraliza la importación de todos los modelos ORM
para facilitar su uso en migraciones (Alembic) y en la aplicación.

Importar todos los modelos aquí garantiza que Alembic pueda
detectar los cambios en el esquema al ejecutar
``alembic revision --autogenerate``.
"""

from app.models.base import Base, SoftDeleteMixin, TimestampMixin

# ---------------------------------------------------------------------------
# Importar modelos concretos para que Alembic los detecte.
# Descomentar a medida que se implementen los modelos.
# ---------------------------------------------------------------------------

# from app.models.user import User
from app.models.verification import CurpValidation, RfcValidation, VerificationRequest
from app.models.screening import (
    ScreeningMatch,
    ScreeningRequest,
    WatchlistEntry,
)
from app.models.digital_intelligence import (
    AnalysisStatus,
    DigitalIntelligenceRequest,
    DomainReputation,
    EmailAnalysis,
    LineType,
    PhoneAnalysis,
    UsernameAnalysis,
)
from app.models.identity import (
    IdentityCorrelation,
    RecommendationType,
    RiskAssessment,
)
from app.models.analytics import (
    Alert,
    AlertSeverity,
    AlertType,
    VerificationEvent,
)

# from app.models.identity_entity import IdentityEntity
# from app.models.audit_log import AuditLog
# from app.models.document import Document

__all__ = [
    "Base",
    "TimestampMixin",
    "SoftDeleteMixin",
    "CurpValidation",
    "RfcValidation",
    "VerificationRequest",
    "ScreeningMatch",
    "ScreeningRequest",
    "WatchlistEntry",
    "AnalysisStatus",
    "DigitalIntelligenceRequest",
    "DomainReputation",
    "EmailAnalysis",
    "LineType",
    "PhoneAnalysis",
    "UsernameAnalysis",
    "IdentityCorrelation",
    "RecommendationType",
    "RiskAssessment",
    "Alert",
    "AlertSeverity",
    "AlertType",
    "VerificationEvent",
]
