"""
Servicios de la plataforma SynkData.

Provee los servicios de validación de identidad para CURP y RFC,
incluyendo validación local y consultas a APIs gubernamentales.
Incluye el servicio de screening en listas restrictivas con
comparación difusa y fonética, los servicios de inteligencia
digital (email, phone, username, social discovery), los
servicios de inteligencia de identidad (correlación, trust score,
motor de riesgo), el grafo de conocimiento, OCR, investigación
con IA y analítica.
"""

from app.services.curp_validator import CurpValidatorService
from app.services.rfc_validator import RfcValidatorService
from app.services.fuzzy_matcher import FuzzyMatcherService, MatchResult, MatchType


def __getattr__(name: str):
    """Importación diferida de servicios para evitar imports circulares."""
    _lazy_imports = {
        "ComplianceScreeningService": "app.services.compliance_screening",
        "EmailIntelligenceService": "app.services.email_intelligence",
        "PhoneIntelligenceService": "app.services.phone_intelligence",
        "UsernameIntelligenceService": "app.services.username_intelligence",
        "SocialDiscoveryService": "app.services.social_discovery",
        "IdentityCorrelationService": "app.services.identity_correlation",
        "TrustScoreService": "app.services.trust_score",
        "RiskEngineService": "app.services.risk_engine",
        "KnowledgeGraphService": "app.services.knowledge_graph",
        "OcrService": "app.services.ocr_service",
        "AiInvestigationService": "app.services.ai_investigation",
        "AnalyticsService": "app.services.analytics_service",
    }
    if name in _lazy_imports:
        import importlib
        module = importlib.import_module(_lazy_imports[name])
        return getattr(module, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


__all__ = [
    "CurpValidatorService",
    "RfcValidatorService",
    "FuzzyMatcherService",
    "MatchResult",
    "MatchType",
    "ComplianceScreeningService",
    "EmailIntelligenceService",
    "PhoneIntelligenceService",
    "UsernameIntelligenceService",
    "SocialDiscoveryService",
    "IdentityCorrelationService",
    "TrustScoreService",
    "RiskEngineService",
    "KnowledgeGraphService",
    "OcrService",
    "AiInvestigationService",
    "AnalyticsService",
]
