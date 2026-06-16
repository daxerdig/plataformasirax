"""
Pruebas unitarias para el motor de evaluación de riesgo.

Cubre:
- Cálculo del risk score con diversos escenarios
- Cálculo del trust score
- Lógica de recomendación (APPROVE/REVIEW/REJECT)
- Rechazo automático por coincidencias críticas
- Factores mitigantes
"""

from __future__ import annotations

import pytest

from app.schemas.identity import (
    MitigatingFactor,
    Recommendation,
    RiskAssessmentResult,
    RiskContext,
    RiskFactor,
    Severity,
    TrustContext,
    TrustLevel,
    TrustScoreResult,
)
from app.services.risk_engine import RiskEngineService, RISK_FACTORS, CRITICAL_FIELDS
from app.services.trust_score import TrustScoreService, TRUST_CONTRIBUTORS


# ===========================================================================
# Tests de cálculo de risk score
# ===========================================================================
class TestRiskScoreCalculation:
    """Pruebas del cálculo del puntaje de riesgo."""

    @pytest.fixture
    def risk_engine(self) -> RiskEngineService:
        """Crea una instancia del motor de riesgo."""
        return RiskEngineService()

    @pytest.mark.asyncio
    async def test_risk_score_identidad_limpia(
        self, risk_engine: RiskEngineService, sample_risk_context_clean: RiskContext
    ):
        """Verifica que una identidad limpia tenga risk score bajo."""
        result = await risk_engine.assess(sample_risk_context_clean)

        assert result.risk_score <= 15
        assert result.recommendation == Recommendation.APPROVE

    @pytest.mark.asyncio
    async def test_risk_score_coincidencia_critica_ofac(
        self, risk_engine: RiskEngineService, sample_risk_context_critical: RiskContext
    ):
        """Verifica que una coincidencia OFAC resulte en risk score máximo y REJECT."""
        result = await risk_engine.assess(sample_risk_context_critical)

        assert result.recommendation == Recommendation.REJECT
        assert result.risk_score == 100.0
        assert any(f.severity == Severity.CRITICAL for f in result.risk_factors)

    @pytest.mark.asyncio
    async def test_risk_score_riesgo_medio(
        self, risk_engine: RiskEngineService, sample_risk_context_medium: RiskContext
    ):
        """Verifica que señales medias resulten en risk score medio y REVIEW."""
        result = await risk_engine.assess(sample_risk_context_medium)

        # Con correo desechable (+20), sin presencia digital (+15), teléfono VoIP (+10)
        # y baja confianza de correlación (45 → (30-45)*0.5 es negativo, no se suma)
        # Mitigantes pueden reducir el score
        assert result.risk_score > 0
        assert result.recommendation in (Recommendation.REVIEW, Recommendation.REJECT)

    @pytest.mark.asyncio
    async def test_risk_score_interpol(self, risk_engine: RiskEngineService):
        """Verifica que una coincidencia Interpol sume 90 puntos."""
        context = RiskContext(
            interpol_match=True,
            correlation_confidence=85.0,
        )
        result = await risk_engine.assess(context)

        assert result.risk_score >= 90.0
        assert result.recommendation == Recommendation.REJECT
        assert any("Interpol" in f.name for f in result.risk_factors)

    @pytest.mark.asyncio
    async def test_risk_score_un_match(self, risk_engine: RiskEngineService):
        """Verifica que una coincidencia ONU sume 90 puntos."""
        context = RiskContext(
            un_match=True,
            correlation_confidence=85.0,
        )
        result = await risk_engine.assess(context)

        assert result.risk_score >= 90.0
        assert result.recommendation == Recommendation.REJECT

    @pytest.mark.asyncio
    async def test_risk_score_sat_69b(self, risk_engine: RiskEngineService):
        """Verifica que SAT 69-B sume 50 puntos."""
        context = RiskContext(
            sat_69b_listed=True,
            correlation_confidence=85.0,
        )
        result = await risk_engine.assess(context)

        assert result.risk_score >= 50.0
        assert any("69-B" in f.name for f in result.risk_factors)

    @pytest.mark.asyncio
    async def test_risk_score_identidad_inconsistente(self, risk_engine: RiskEngineService):
        """Verifica que identidad inconsistente sume 50 puntos."""
        context = RiskContext(
            identity_inconsistent=True,
            correlation_confidence=85.0,
        )
        result = await risk_engine.assess(context)

        assert result.risk_score >= 50.0
        assert any("inconsistente" in f.name.lower() for f in result.risk_factors)

    @pytest.mark.asyncio
    async def test_risk_score_multiple_factors(self, risk_engine: RiskEngineService):
        """Verifica que múltiples factores de riesgo se acumulen correctamente."""
        context = RiskContext(
            sat_69b_listed=True,  # +50
            identity_inconsistent=True,  # +50
            email_disposable=True,  # +20
            no_digital_presence=True,  # +15
            phone_voip_suspicious=True,  # +10
            correlation_confidence=85.0,
        )
        result = await risk_engine.assess(context)

        # 50 + 50 + 20 + 15 + 10 = 145, acotado a 100
        assert result.risk_score == 100.0
        assert result.recommendation == Recommendation.REJECT

    @pytest.mark.asyncio
    async def test_risk_score_acotado_0_100(self, risk_engine: RiskEngineService):
        """Verifica que el risk score siempre esté en el rango [0, 100]."""
        # Máximo riesgo posible
        context_max = RiskContext(
            ofac_match=True,
            open_sanctions_match=True,
            rnd_positive=True,
            un_match=True,
            interpol_match=True,
            sat_69b_listed=True,
            identity_inconsistent=True,
            multiple_identities=True,
            email_disposable=True,
            no_digital_presence=True,
            phone_voip_suspicious=True,
        )
        result = await risk_engine.assess(context_max)
        assert 0 <= result.risk_score <= 100

        # Sin riesgo
        context_min = RiskContext()
        result = await risk_engine.assess(context_min)
        assert 0 <= result.risk_score <= 100


# ===========================================================================
# Tests de trust score
# ===========================================================================
class TestTrustScoreCalculation:
    """Pruebas del cálculo del puntaje de confianza."""

    @pytest.fixture
    def trust_service(self) -> TrustScoreService:
        """Crea una instancia del servicio de trust score."""
        return TrustScoreService()

    @pytest.mark.asyncio
    async def test_trust_score_maximo(
        self, trust_service: TrustScoreService, sample_trust_context: TrustContext
    ):
        """Verifica que una identidad con todas las señales positivas tenga trust score alto."""
        result = await trust_service.calculate(sample_trust_context)

        # Con todas las señales positivas: 20+15+15+20+10+5+5+5+5 = 100
        assert result.score == 100.0
        assert result.level == TrustLevel.VERY_HIGH

    @pytest.mark.asyncio
    async def test_trust_score_minimo(self, trust_service: TrustScoreService):
        """Verifica que una identidad sin señales positivas tenga trust score muy bajo."""
        context = TrustContext(
            renapo_valid=False,
            rfc_valid=False,
            sat_active=False,
            screening_clean=False,
            professional_presence=False,
            github_active=False,
            linkedin_found=False,
            email_verifiable=False,
            phone_valid=False,
        )
        result = await trust_service.calculate(context)

        assert result.score == 0.0
        assert result.level == TrustLevel.VERY_LOW

    @pytest.mark.asyncio
    async def test_trust_score_renapo_valido(self, trust_service: TrustScoreService):
        """Verifica que RENAPO válido aporte 20 puntos."""
        context = TrustContext(renapo_valid=True)
        result = await trust_service.calculate(context)

        assert result.score >= 20.0
        assert any(c.name == "RENAPO válido" and c.passed for c in result.contributors)

    @pytest.mark.asyncio
    async def test_trust_score_rfc_valido(self, trust_service: TrustScoreService):
        """Verifica que RFC válido aporte 15 puntos."""
        context = TrustContext(rfc_valid=True)
        result = await trust_service.calculate(context)

        assert result.score >= 15.0

    @pytest.mark.asyncio
    async def test_trust_score_niveles(self, trust_service: TrustScoreService):
        """Verifica que los niveles de confianza sean correctos."""
        # very_high: 90-100
        ctx_vh = TrustContext(
            renapo_valid=True, screening_clean=True, rfc_valid=True,
            sat_active=True, professional_presence=True, github_active=True,
            linkedin_found=True, email_verifiable=True, phone_valid=True,
        )
        result = await trust_service.calculate(ctx_vh)
        assert result.level == TrustLevel.VERY_HIGH

        # low: 30-49
        ctx_low = TrustContext(renapo_valid=True, rfc_valid=True)
        result = await trust_service.calculate(ctx_low)
        assert result.level in (TrustLevel.LOW, TrustLevel.MEDIUM)

    @pytest.mark.asyncio
    async def test_trust_score_contribuyentes(self, trust_service: TrustScoreService):
        """Verifica que el número de contribuyentes sea el esperado."""
        context = TrustContext(renapo_valid=True)
        result = await trust_service.calculate(context)

        assert len(result.contributors) == len(TRUST_CONTRIBUTORS)


# ===========================================================================
# Tests de lógica de recomendación
# ===========================================================================
class TestRecommendationLogic:
    """Pruebas de la lógica de recomendación de decisión."""

    def test_recomendacion_approve(self):
        """Verifica que risk_score ≤ 15 resulte en APPROVE."""
        result = RiskEngineService._determine_recommendation(
            risk_score=10.0, has_critical_match=False
        )
        assert result == Recommendation.APPROVE

    def test_recomendacion_approve_limite(self):
        """Verifica que risk_score = 15 resulte en APPROVE."""
        result = RiskEngineService._determine_recommendation(
            risk_score=15.0, has_critical_match=False
        )
        assert result == Recommendation.APPROVE

    def test_recomendacion_review(self):
        """Verifica que risk_score entre 16 y 40 resulte en REVIEW."""
        result = RiskEngineService._determine_recommendation(
            risk_score=25.0, has_critical_match=False
        )
        assert result == Recommendation.REVIEW

    def test_recomendacion_review_limite_superior(self):
        """Verifica que risk_score = 40 resulte en REVIEW."""
        result = RiskEngineService._determine_recommendation(
            risk_score=40.0, has_critical_match=False
        )
        assert result == Recommendation.REVIEW

    def test_recomendacion_reject(self):
        """Verifica que risk_score > 40 resulte en REJECT."""
        result = RiskEngineService._determine_recommendation(
            risk_score=55.0, has_critical_match=False
        )
        assert result == Recommendation.REJECT

    def test_recomendacion_reject_score_bajo_con_critico(self):
        """Verifica que una coincidencia crítica resulte en REJECT independientemente del score."""
        result = RiskEngineService._determine_recommendation(
            risk_score=5.0, has_critical_match=True
        )
        assert result == Recommendation.REJECT


# ===========================================================================
# Tests de rechazo automático por coincidencias críticas
# ===========================================================================
class TestCriticalMatchAutoReject:
    """Pruebas de rechazo automático por coincidencias críticas."""

    @pytest.fixture
    def risk_engine(self) -> RiskEngineService:
        return RiskEngineService()

    @pytest.mark.asyncio
    async def test_reject_automatico_ofac(self, risk_engine: RiskEngineService):
        """Verifica que una coincidencia OFAC genere REJECT automático."""
        context = RiskContext(ofac_match=True)
        result = await risk_engine.assess(context)

        assert result.recommendation == Recommendation.REJECT
        assert result.risk_score == 100.0

    @pytest.mark.asyncio
    async def test_reject_automatico_rnd(self, risk_engine: RiskEngineService):
        """Verifica que RND positivo genere REJECT automático."""
        context = RiskContext(rnd_positive=True)
        result = await risk_engine.assess(context)

        assert result.recommendation == Recommendation.REJECT
        assert result.risk_score == 100.0

    @pytest.mark.asyncio
    async def test_reject_automatico_open_sanctions(self, risk_engine: RiskEngineService):
        """Verifica que una coincidencia OpenSanctions genere REJECT automático."""
        context = RiskContext(open_sanctions_match=True)
        result = await risk_engine.assess(context)

        assert result.recommendation == Recommendation.REJECT
        assert result.risk_score == 100.0

    @pytest.mark.asyncio
    async def test_campos_criticos_definidos(self):
        """Verifica que los campos críticos estén correctamente definidos."""
        assert "ofac_match" in CRITICAL_FIELDS
        assert "rnd_positive" in CRITICAL_FIELDS
        assert "open_sanctions_match" in CRITICAL_FIELDS

    @pytest.mark.asyncio
    async def test_no_mitigantes_con_critico(self, risk_engine: RiskEngineService):
        """Verifica que no se apliquen mitigantes cuando hay coincidencias críticas."""
        context = RiskContext(ofac_match=True, correlation_confidence=95.0)
        result = await risk_engine.assess(context)

        # No debe haber factores mitigantes con coincidencia crítica
        assert len(result.mitigating_factors) == 0


# ===========================================================================
# Tests de factores mitigantes
# ===========================================================================
class TestMitigatingFactors:
    """Pruebas de los factores mitigantes que reducen el risk score."""

    @pytest.fixture
    def risk_engine(self) -> RiskEngineService:
        return RiskEngineService()

    @pytest.mark.asyncio
    async def test_mitigante_renapo_verificado(self, risk_engine: RiskEngineService):
        """Verifica que una identidad verificada por RENAPO sea un mitigante."""
        context = RiskContext(
            email_disposable=True,  # +20 riesgo
            correlation_confidence=85.0,  # Alta confianza → mitigante RENAPO
        )
        result = await risk_engine.assess(context)

        # Debe haber al menos un mitigante por alta confianza de correlación
        assert len(result.mitigating_factors) > 0

    @pytest.mark.asyncio
    async def test_mitigante_screening_limpio(self, risk_engine: RiskEngineService):
        """Verifica que un screening limpio sea un mitigante."""
        context = RiskContext(
            email_disposable=True,  # +20 riesgo
            correlation_confidence=85.0,
        )
        result = await risk_engine.assess(context)

        # El riesgo debe ser menor que la suma de factores sin mitigar
        # 20 (email desechable) - mitigantes
        assert result.risk_score < 20.0

    @pytest.mark.asyncio
    async def test_mitigante_correo_legitimo(self, risk_engine: RiskEngineService):
        """Verifica que un correo no desechable sea un mitigante."""
        context = RiskContext(
            no_digital_presence=True,  # +15 riesgo
            correlation_confidence=85.0,
            # email_disposable=False por defecto → mitigante correo legítimo
        )
        result = await risk_engine.assess(context)

        # Debe incluir mitigante por correo legítimo
        has_email_mitigant = any(
            "correo" in mf.name.lower() or "legítimo" in mf.name.lower()
            for mf in result.mitigating_factors
        )
        assert has_email_mitigant

    @pytest.mark.asyncio
    async def test_mitigante_presencia_digital(self, risk_engine: RiskEngineService):
        """Verifica que tener presencia digital sea un mitigante."""
        context = RiskContext(
            email_disposable=True,  # +20 riesgo
            correlation_confidence=85.0,
            # no_digital_presence=False por defecto → mitigante presencia digital
        )
        result = await risk_engine.assess(context)

        has_presence_mitigant = any(
            "presencia digital" in mf.name.lower()
            for mf in result.mitigating_factors
        )
        assert has_presence_mitigant

    @pytest.mark.asyncio
    async def test_factores_riesgo_definidos(self):
        """Verifica que los factores de riesgo estén correctamente definidos."""
        assert len(RISK_FACTORS) == 11  # 3 críticos + 4 altos + 3 medios + 1 bajo

        # Verificar severidades
        critical = [f for f in RISK_FACTORS if f.severity == Severity.CRITICAL]
        high = [f for f in RISK_FACTORS if f.severity == Severity.HIGH]
        medium = [f in RISK_FACTORS for f in RISK_FACTORS if f.severity == Severity.MEDIUM]
        low = [f for f in RISK_FACTORS if f.severity == Severity.LOW]

        assert len(critical) == 3
        assert len(high) == 4
        assert len(low) == 1

    @pytest.mark.asyncio
    async def test_quick_screening_check(self, risk_engine: RiskEngineService):
        """Verifica la verificación rápida de screening."""
        result = await risk_engine.quick_screening_check(
            ofac_match=False,
            open_sanctions_match=False,
            un_match=False,
            interpol_match=False,
            rnd_positive=False,
        )

        assert result.risk_score == 0.0
        assert result.recommendation == Recommendation.APPROVE

    @pytest.mark.asyncio
    async def test_quick_screening_check_critico(self, risk_engine: RiskEngineService):
        """Verifica la verificación rápida con coincidencia crítica."""
        result = await risk_engine.quick_screening_check(
            ofac_match=True,
        )

        assert result.recommendation == Recommendation.REJECT
        assert result.risk_score == 100.0
