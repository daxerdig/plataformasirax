"""
Motor de inteligencia de riesgo para la plataforma SynkData.

Evalúa el nivel de riesgo de una identidad basándose en señales
negativas derivadas del screening, verificaciones fallidas,
inteligencia digital y resultados de correlación.

Contribuyentes al Risk Score (señales negativas, máximo 100 puntos):
- RND positivo (Registro Nacional de Detenciones): +100
- OpenSanctions Match: +100
- OFAC Match: +100
- UN Match: +90
- Interpol Match: +90
- SAT 69-B: +50
- Identidad inconsistente: +50
- Correo temporal/disposable: +20
- Múltiples identidades: +40
- Sin presencia digital: +15
- Teléfono VoIP/sospechoso: +10

Factores mitigantes (reducen el risk_score):
- Identidad verificada por RENAPO: -15
- RFC activo en SAT: -10
- Presencia profesional sólida: -10
- Correo corporativo verificado: -5

Lógica de decisión:
- risk_score ≤ 15 → APPROVE
- risk_score 16-40 → REVIEW
- risk_score > 40 → REJECT
- Cualquier coincidencia crítica (OFAC, RND) → REJECT automático

Los mensajes dirigidos al usuario están en español conforme a los
estándares de la plataforma SynkData.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import List, Optional

from app.schemas.identity import (
    MitigatingFactor,
    Recommendation,
    RiskAssessmentResult,
    RiskContext,
    RiskFactor,
    Severity,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Definición de factores de riesgo
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class RiskFactorDef:
    """
    Definición de un factor de riesgo.

    Attributes:
        name: Nombre descriptivo del factor.
        score: Puntuación de riesgo que suma si está activo.
        severity: Severidad del factor (critical, high, medium, low).
        field_name: Nombre del campo en RiskContext que activa este factor.
        active_description: Descripción cuando el factor está activo.
    """

    name: str
    score: float
    severity: Severity
    field_name: str
    active_description: str


# Factores de riesgo ordenados por severidad
RISK_FACTORS: List[RiskFactorDef] = [
    # ── CRÍTICOS → REJECT automático ─────────────────────────────────────
    RiskFactorDef(
        name="RND positivo",
        score=100.0,
        severity=Severity.CRITICAL,
        field_name="rnd_positive",
        active_description=(
            "La persona aparece en el Registro Nacional de Detenciones (RND). "
            "Esto constituye un hallazgo crítico que requiere rechazo inmediato."
        ),
    ),
    RiskFactorDef(
        name="Coincidencia en lista OFAC SDN",
        score=100.0,
        severity=Severity.CRITICAL,
        field_name="ofac_match",
        active_description=(
            "Se encontró coincidencia en la lista OFAC SDN (Specially Designated Nationals). "
            "Las personas en esta lista están sujetas a sanciones económicas del gobierno de EE.UU. "
            "Esto constituye un hallazgo crítico que requiere rechazo inmediato."
        ),
    ),
    RiskFactorDef(
        name="Coincidencia en OpenSanctions",
        score=100.0,
        severity=Severity.CRITICAL,
        field_name="open_sanctions_match",
        active_description=(
            "Se encontró coincidencia en OpenSanctions, un agregador global de listas de sanciones "
            "y personas de alto riesgo. Esto constituye un hallazgo crítico que requiere rechazo inmediato."
        ),
    ),
    # ── ALTOS ────────────────────────────────────────────────────────────
    RiskFactorDef(
        name="Coincidencia en lista de sanciones de la ONU",
        score=90.0,
        severity=Severity.HIGH,
        field_name="un_match",
        active_description=(
            "Se encontró coincidencia en la lista de sanciones del Consejo de Seguridad de la ONU. "
            "Las personas en esta lista están sujetas a medidas restrictivas internacionales."
        ),
    ),
    RiskFactorDef(
        name="Coincidencia en avisos de Interpol",
        score=90.0,
        severity=Severity.HIGH,
        field_name="interpol_match",
        active_description=(
            "Se encontró coincidencia en los avisos de Interpol (Red Notices). "
            "Las personas con avisos rojos son buscadas por autoridades internacionales."
        ),
    ),
    RiskFactorDef(
        name="SAT 69-B (presunción de operaciones simuladas)",
        score=50.0,
        severity=Severity.HIGH,
        field_name="sat_69b_listed",
        active_description=(
            "El RFC está listado en el artículo 69-B del Código Fiscal de la Federación, "
            "lo que indica presunción de operaciones simuladas por parte del SAT."
        ),
    ),
    RiskFactorDef(
        name="Identidad inconsistente",
        score=50.0,
        severity=Severity.HIGH,
        field_name="identity_inconsistent",
        active_description=(
            "La correlación de identidad reveló inconsistencias significativas entre los datos proporcionados. "
            "Esto puede indicar suplantación de identidad o datos fraudulentos."
        ),
    ),
    # ── MEDIOS ───────────────────────────────────────────────────────────
    RiskFactorDef(
        name="Múltiples identidades detectadas",
        score=40.0,
        severity=Severity.MEDIUM,
        field_name="multiple_identities",
        active_description=(
            "Se detectaron múltiples identidades asociadas a los mismos datos de contacto, "
            "lo que puede indicar fraude o uso de identidades sintéticas."
        ),
    ),
    RiskFactorDef(
        name="Correo temporal/desechable",
        score=20.0,
        severity=Severity.MEDIUM,
        field_name="email_disposable",
        active_description=(
            "El correo electrónico utiliza un dominio desechable o temporal, "
            "lo que indica una baja intención de permanencia y puede asociarse con actividades fraudulentas."
        ),
    ),
    RiskFactorDef(
        name="Sin presencia digital",
        score=15.0,
        severity=Severity.MEDIUM,
        field_name="no_digital_presence",
        active_description=(
            "No se encontró presencia digital alguna asociada a la identidad, "
            "lo que es inusual en la era digital y puede indicar una identidad ficticia."
        ),
    ),
    # ── BAJOS ────────────────────────────────────────────────────────────
    RiskFactorDef(
        name="Teléfono VoIP/sospechoso",
        score=10.0,
        severity=Severity.LOW,
        field_name="phone_voip_suspicious",
        active_description=(
            "El número telefónico parece ser VoIP o tiene características sospechosas, "
            "lo que puede dificultar la verificación de la identidad."
        ),
    ),
]

# Campos que activan rechazo automático
CRITICAL_FIELDS = {"rnd_positive", "ofac_match", "open_sanctions_match"}


# ---------------------------------------------------------------------------
# Definición de factores mitigantes
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class MitigatingFactorDef:
    """
    Definición de un factor mitigante.

    Attributes:
        name: Nombre descriptivo del factor mitigante.
        points_reduced: Puntos de riesgo que reduce si aplica.
        condition_description: Descripción de la condición para que aplique.
    """

    name: str
    points_reduced: float
    condition_description: str


MITIGATING_FACTORS: List[MitigatingFactorDef] = [
    MitigatingFactorDef(
        name="Identidad verificada por RENAPO",
        points_reduced=15.0,
        condition_description="La CURP fue validada exitosamente contra RENAPO, lo que confirma la identidad.",
    ),
    MitigatingFactorDef(
        name="RFC activo en SAT",
        points_reduced=10.0,
        condition_description="El RFC está registrado y activo en el SAT, lo que indica actividad fiscal legítima.",
    ),
    MitigatingFactorDef(
        name="Presencia profesional sólida",
        points_reduced=10.0,
        condition_description="Se detectó presencia profesional sólida (LinkedIn, sitio web corporativo, etc.).",
    ),
    MitigatingFactorDef(
        name="Correo corporativo verificado",
        points_reduced=5.0,
        condition_description="El correo electrónico usa un dominio corporativo verificado.",
    ),
]


# ---------------------------------------------------------------------------
# Servicio de evaluación de riesgo
# ---------------------------------------------------------------------------
class RiskEngineService:
    """
    Servicio de evaluación de riesgo de identidad.

    Analiza señales negativas del screening, verificaciones fallidas,
    inteligencia digital y resultados de correlación para calcular
    un puntaje de riesgo y producir una recomendación de decisión.

    El risk_score se calcula sumando las puntuaciones de todos los
    factores de riesgo activos, restando los factores mitigantes,
    y acotando el resultado a [0, 100].

    Lógica de decisión:
    - risk_score ≤ 15 → APPROVE
    - risk_score 16-40 → REVIEW
    - risk_score > 40 → REJECT
    - Cualquier coincidencia crítica (OFAC, RND, OpenSanctions) → REJECT automático
    """

    async def assess(
        self,
        context: RiskContext,
        trust_score: Optional[float] = None,
    ) -> RiskAssessmentResult:
        """
        Ejecuta la evaluación de riesgo de identidad.

        Args:
            context: Contexto con los resultados de screening, verificaciones
                fallidas, inteligencia digital y correlación.
            trust_score: Puntuación de confianza previamente calculada
                (opcional, se usa como señal complementaria).

        Returns:
            RiskAssessmentResult: Puntuación de riesgo, recomendación,
                factores de riesgo y factores mitigantes.
        """
        risk_factors: List[RiskFactor] = []
        mitigating_factors: List[MitigatingFactor] = []
        risk_score = 0.0
        has_critical_match = False

        # ── 1. Evaluar factores de riesgo ────────────────────────────────
        for factor_def in RISK_FACTORS:
            is_active = getattr(context, factor_def.field_name, False)

            if is_active:
                risk_score += factor_def.score
                risk_factors.append(
                    RiskFactor(
                        name=factor_def.name,
                        score=factor_def.score,
                        severity=factor_def.severity,
                        details=factor_def.active_description,
                    )
                )

                # Verificar si es un factor crítico
                if factor_def.field_name in CRITICAL_FIELDS:
                    has_critical_match = True

        # ── 2. Evaluar factores mitigantes ───────────────────────────────
        # Solo se aplican si NO hay coincidencias críticas
        if not has_critical_match:
            mitigating_factors = self._evaluate_mitigating_factors(context)
            total_reduction = sum(mf.points_reduced for mf in mitigating_factors)
            risk_score -= total_reduction

        # ── 3. Considerar correlación de identidad como factor adicional ──
        if context.correlation_confidence is not None:
            if context.correlation_confidence < 30:
                # Baja confianza en la identidad = mayor riesgo
                extra_risk = (30 - context.correlation_confidence) * 0.5
                risk_score += extra_risk
                risk_factors.append(
                    RiskFactor(
                        name="Baja confianza de identidad",
                        score=round(extra_risk, 2),
                        severity=Severity.MEDIUM,
                        details=(
                            f"La correlación de identidad produjo una confianza de "
                            f"{context.correlation_confidence:.1f}/100, lo que indica "
                            f"posibles inconsistencias en los datos proporcionados."
                        ),
                    )
                )

        # ── 4. Acotar el riesgo a [0, 100] ──────────────────────────────
        risk_score = max(0.0, min(100.0, risk_score))

        # ── 5. Determinar recomendación ──────────────────────────────────
        recommendation = self._determine_recommendation(
            risk_score, has_critical_match
        )

        # ── 6. Trust score (usar el proporcionado o calcular uno simple) ─
        effective_trust_score = trust_score if trust_score is not None else 0.0

        logger.info(
            "Evaluación de riesgo completada — risk_score=%.1f, trust_score=%.1f, "
            "recommendation=%s, risk_factors=%d, mitigating_factors=%d, critical=%s",
            risk_score,
            effective_trust_score,
            recommendation.value,
            len(risk_factors),
            len(mitigating_factors),
            has_critical_match,
        )

        return RiskAssessmentResult(
            risk_score=round(risk_score, 2),
            trust_score=round(effective_trust_score, 2),
            recommendation=recommendation,
            risk_factors=risk_factors,
            mitigating_factors=mitigating_factors,
        )

    def _evaluate_mitigating_factors(
        self, context: RiskContext
    ) -> List[MitigatingFactor]:
        """
        Evalúa los factores mitigantes basándose en el contexto.

        Los factores mitigantes solo se aplican cuando no hay
        coincidencias críticas (OFAC, RND, OpenSanctions).

        Args:
            context: Contexto de evaluación de riesgo.

        Returns:
            List[MitigatingFactor]: Factores mitigantes aplicables.
        """
        mitigating: List[MitigatingFactor] = []

        # RENAPO válido como mitigante
        if context.correlation_confidence is not None and context.correlation_confidence >= 70:
            mitigating.append(
                MitigatingFactor(
                    name="Identidad verificada por RENAPO",
                    points_reduced=15.0,
                    details=(
                        "La correlación de identidad produjo una confianza alta "
                        f"({context.correlation_confidence:.1f}/100), lo que sugiere "
                        "que la identidad fue verificada exitosamente contra RENAPO."
                    ),
                )
            )

        # Si el screening está limpio, es un mitigante fuerte
        if not context.ofac_match and not context.un_match and not context.interpol_match:
            # Solo agregar si no hay otros riesgos altos
            if not context.sat_69b_listed and not context.identity_inconsistent:
                mitigating.append(
                    MitigatingFactor(
                        name="Screening en listas restrictivas limpio",
                        points_reduced=10.0,
                        details="No se encontraron coincidencias en OFAC, ONU, Interpol u OpenSanctions.",
                    )
                )

        # Correo no desechable como mitigante
        if not context.email_disposable:
            mitigating.append(
                MitigatingFactor(
                    name="Correo electrónico legítimo",
                    points_reduced=5.0,
                    details="El correo electrónico no utiliza un dominio desechable o temporal.",
                )
            )

        # Presencia digital como mitigante
        if not context.no_digital_presence:
            mitigating.append(
                MitigatingFactor(
                    name="Presencia digital verificable",
                    points_reduced=5.0,
                    details="Se encontró presencia digital asociada a la identidad.",
                )
            )

        return mitigating

    @staticmethod
    def _determine_recommendation(
        risk_score: float, has_critical_match: bool
    ) -> Recommendation:
        """
        Determina la recomendación de decisión basándose en el risk score
        y la presencia de coincidencias críticas.

        Lógica:
        - Cualquier coincidencia crítica (OFAC, RND, OpenSanctions) → REJECT automático
        - risk_score ≤ 15 → APPROVE
        - risk_score 16-40 → REVIEW
        - risk_score > 40 → REJECT

        Args:
            risk_score: Puntuación de riesgo calculada.
            has_critical_match: Si se detectó alguna coincidencia crítica.

        Returns:
            Recommendation: Recomendación de decisión.
        """
        # Rechazo automático por coincidencias críticas
        if has_critical_match:
            return Recommendation.REJECT

        # Decisión basada en umbral de riesgo
        if risk_score <= 15:
            return Recommendation.APPROVE
        elif risk_score <= 40:
            return Recommendation.REVIEW
        else:
            return Recommendation.REJECT

    async def quick_screening_check(
        self,
        ofac_match: bool = False,
        open_sanctions_match: bool = False,
        un_match: bool = False,
        interpol_match: bool = False,
        rnd_positive: bool = False,
    ) -> RiskAssessmentResult:
        """
        Realiza una verificación rápida de riesgo basada solo en screening.

        Útil para una evaluación inicial antes de realizar el análisis
        completo de identidad.

        Args:
            ofac_match: Si hay coincidencia en OFAC.
            open_sanctions_match: Si hay coincidencia en OpenSanctions.
            un_match: Si hay coincidencia en la lista de la ONU.
            interpol_match: Si hay coincidencia en Interpol.
            rnd_positive: Si aparece en el RND.

        Returns:
            RiskAssessmentResult: Evaluación rápida de riesgo.
        """
        context = RiskContext(
            ofac_match=ofac_match,
            open_sanctions_match=open_sanctions_match,
            un_match=un_match,
            interpol_match=interpol_match,
            rnd_positive=rnd_positive,
        )

        return await self.assess(context, trust_score=0.0)
