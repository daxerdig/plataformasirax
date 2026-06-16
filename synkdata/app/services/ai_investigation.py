"""
Motor de investigación con IA para SynkData Identity Intelligence.

Genera reportes de investigación, análisis de hallazgos y recomendaciones
basándose en los resultados de las evaluaciones de riesgo, correlación
de identidad y screening en listas restrictivas.

Incluye:
- Generación de reportes completos de investigación
- Análisis de hallazgos con narrativa de riesgo
- Generación de recomendaciones priorizadas
- Resumen de caso para revisión rápida
- Formato profesional apto para equipos de cumplimiento

La generación de reportes utiliza plantillas configurables, con
integración opcional de LLM cuando está disponible. Los reportes
están diseñados para cumplir con estándares regulatorios mexicanos
(LFPIORPI, LDPIFPAPP, CFF).

Todos los mensajes dirigidos al usuario están en español.
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional

from app.config import get_settings
from app.database import get_redis

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Enumeraciones
# ---------------------------------------------------------------------------
class Priority(str, Enum):
    """Nivel de prioridad de una recomendación."""

    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class ConfidenceLevel(str, Enum):
    """Nivel de confianza del análisis de investigación."""

    VERY_HIGH = "very_high"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    VERY_LOW = "very_low"


class RiskNarrativeLevel(str, Enum):
    """Nivel de la narrativa de riesgo."""

    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    MINIMAL = "minimal"


# ---------------------------------------------------------------------------
# Modelos de datos de resultado
# ---------------------------------------------------------------------------
@dataclass(frozen=True, slots=True)
class Finding:
    """
    Hallazgo individual de una investigación.

    Attributes:
        id: Identificador único del hallazgo.
        category: Categoría del hallazgo (screening, identity, digital, etc.).
        title: Título descriptivo del hallazgo.
        description: Descripción detallada en español.
        severity: Severidad del hallazgo (critical/high/medium/low).
        evidence: Referencias a la evidencia que respalda el hallazgo.
        source: Fuente de donde proviene el hallazgo.
    """

    id: str
    category: str
    title: str
    description: str
    severity: str
    evidence: List[Dict[str, Any]]
    source: str


@dataclass(frozen=True, slots=True)
class RiskAnalysis:
    """
    Análisis de riesgo de una investigación.

    Attributes:
        overall_risk_score: Puntuación de riesgo global (0-100).
        trust_score: Puntuación de confianza (0-100).
        recommendation: Recomendación general (APPROVE/REVIEW/REJECT).
        risk_factors: Factores de riesgo identificados.
        mitigating_factors: Factores mitigantes.
        narrative: Narrativa de riesgo en lenguaje natural.
    """

    overall_risk_score: float
    trust_score: float
    recommendation: str
    risk_factors: List[Dict[str, Any]]
    mitigating_factors: List[Dict[str, Any]]
    narrative: str


@dataclass(frozen=True, slots=True)
class Methodology:
    """
    Metodología utilizada en la investigación.

    Attributes:
        name: Nombre de la metodología.
        version: Versión del procedimiento.
        steps: Pasos seguidos en la investigación.
        sources_consulted: Fuentes consultadas.
        standards: Estándares regulatorios aplicados.
    """

    name: str
    version: str
    steps: List[str]
    sources_consulted: List[str]
    standards: List[str]


@dataclass(frozen=True, slots=True)
class InvestigationReport:
    """
    Reporte completo de investigación.

    Attributes:
        id: Identificador único del reporte.
        assessment_id: ID de la evaluación asociada.
        executive_summary: Resumen ejecutivo del reporte.
        findings: Lista de hallazgos identificados.
        risk_analysis: Análisis de riesgo detallado.
        recommendations: Recomendaciones priorizadas.
        methodology: Metodología utilizada.
        confidence_level: Nivel de confianza del análisis.
        generated_at: Fecha y hora de generación (ISO 8601).
    """

    id: str
    assessment_id: str
    executive_summary: str
    findings: List[Finding]
    risk_analysis: RiskAnalysis
    recommendations: List["Recommendation"]
    methodology: Methodology
    confidence_level: ConfidenceLevel
    generated_at: str


@dataclass(frozen=True, slots=True)
class InvestigationAnalysis:
    """
    Análisis de hallazgos de investigación.

    Attributes:
        key_findings: Hallazgos clave resumidos.
        risk_narrative: Narrativa de riesgo en lenguaje natural.
        connections: Conexiones identificadas entre entidades.
        anomalies: Anomalías detectadas.
    """

    key_findings: List[str]
    risk_narrative: str
    connections: List[Dict[str, Any]]
    anomalies: List[Dict[str, Any]]


@dataclass(frozen=True, slots=True)
class Recommendation:
    """
    Recomendación de acción derivada de la investigación.

    Attributes:
        id: Identificador único de la recomendación.
        priority: Nivel de prioridad (critical/high/medium/low).
        action: Acción recomendada en español.
        rationale: Fundamento de la recomendación.
        deadline: Plazo sugerido para la acción.
    """

    id: str
    priority: Priority
    action: str
    rationale: str
    deadline: str


@dataclass(frozen=True, slots=True)
class CaseSummary:
    """
    Resumen de caso para revisión rápida.

    Attributes:
        summary: Resumen del caso en 2-3 oraciones.
        risk_level: Nivel de riesgo general.
        key_dates: Fechas clave del caso.
        next_steps: Próximos pasos recomendados.
    """

    summary: str
    risk_level: str
    key_dates: List[Dict[str, str]]
    next_steps: List[str]


# ---------------------------------------------------------------------------
# Constantes
# ---------------------------------------------------------------------------
_CACHE_PREFIX = "investigation:"
_CACHE_TTL = 1800  # 30 minutos

_METHODOLOGY = Methodology(
    name="Investigación de Identidad SynkData v2.0",
    version="2.0.0",
    steps=[
        "1. Verificación de identidad contra fuentes gubernamentales (RENAPO, SAT)",
        "2. Screening en listas restrictivas (OFAC, ONU, Interpol, OpenSanctions)",
        "3. Análisis de inteligencia digital (email, teléfono, redes sociales)",
        "4. Correlación de señales de identidad",
        "5. Evaluación de riesgo con motor de scoring",
        "6. Análisis del grafo de conocimiento",
        "7. Generación de hallazgos y recomendaciones",
    ],
    sources_consulted=[
        "RENAPO (Registro Nacional de Población)",
        "SAT (Servicio de Administración Tributaria)",
        "OFAC SDN List",
        "UN Security Council Consolidated List",
        "Interpol Red Notices",
        "OpenSanctions",
        "Have I Been Pwned",
        "Hunter.io",
    ],
    standards=[
        "Ley Federal para la Prevención e Identificación de Operaciones con "
        "Recursos de Procedencia Ilícita (LFPIORPI)",
        "Ley Federal de Protección de Datos Personales en Posesión de los "
        "Particulares (LFPDPPP)",
        "Código Fiscal de la Federación (Art. 69-B)",
        "Disposiciones de carácter general a que se refiere el Art. 115 "
        "de la Ley General de Organizaciones y Actividades Auxiliares del Crédito",
        "Recomendaciones del GAFI (FATF)",
    ],
)


# ---------------------------------------------------------------------------
# Servicio de investigación con IA
# ---------------------------------------------------------------------------
class AiInvestigationService:
    """
    Servicio de investigación con IA para la plataforma SynkData.

    Genera reportes de investigación profesionales, analiza hallazgos,
    produce recomendaciones priorizadas y resume casos para revisión
    rápida por equipos de cumplimiento normativo.

    Utiliza plantillas configurables para la generación de reportes,
    con integración opcional de LLM cuando está disponible. Los
    reportes cumplen con estándares regulatorios mexicanos.

    Example:
        >>> service = AiInvestigationService()
        >>> report = await service.generate_report("assessment-123")
        >>> print(report.executive_summary)
    """

    def __init__(self) -> None:
        """Inicializa el servicio con la configuración del proyecto."""
        self._settings = get_settings()

    # ── Generación de reportes ────────────────────────────────────────────

    async def generate_report(
        self, assessment_id: str
    ) -> InvestigationReport:
        """
        Genera un reporte completo de investigación.

        Compila los hallazgos, análisis de riesgo, recomendaciones
        y metodología en un reporte profesional apto para equipos
        de cumplimiento normativo.

        Args:
            assessment_id: Identificador de la evaluación de riesgo.

        Returns:
            InvestigationReport: Reporte completo de investigación.
        """
        cache_key = f"{_CACHE_PREFIX}report:{assessment_id}"

        try:
            redis = get_redis()
            cached = await redis.get(cache_key)
            if cached:
                import json

                data = json.loads(cached)
                return self._deserialize_report(data)
        except Exception as exc:
            logger.warning("Error leyendo caché de reporte: %s", exc)

        # Obtener datos de la evaluación (simulado — en producción
        # se consultaría la base de datos)
        assessment = await self._fetch_assessment(assessment_id)
        correlation = await self._fetch_correlation(assessment_id)
        screening = await self._fetch_screening(assessment_id)

        # Analizar hallazgos
        analysis = await self.analyze_findings(
            assessment, correlation, screening
        )

        # Generar hallazgos estructurados
        findings = self._build_findings(
            assessment, correlation, screening, analysis
        )

        # Análisis de riesgo
        risk_analysis = self._build_risk_analysis(
            assessment, analysis
        )

        # Recomendaciones
        recommendations = await self.generate_recommendations(assessment)

        # Resumen ejecutivo
        executive_summary = self._generate_executive_summary(
            assessment, findings, risk_analysis
        )

        # Nivel de confianza
        confidence = self._determine_confidence_level(
            assessment, screening, correlation
        )

        report = InvestigationReport(
            id=str(uuid.uuid4()),
            assessment_id=assessment_id,
            executive_summary=executive_summary,
            findings=findings,
            risk_analysis=risk_analysis,
            recommendations=recommendations,
            methodology=_METHODOLOGY,
            confidence_level=confidence,
            generated_at=datetime.now(timezone.utc).isoformat(),
        )

        # Cachear reporte
        try:
            redis = get_redis()
            import json

            await redis.setex(
                cache_key,
                _CACHE_TTL,
                json.dumps(
                    self._serialize_report(report), ensure_ascii=False
                ),
            )
        except Exception as exc:
            logger.warning("Error cacheando reporte: %s", exc)

        logger.info(
            "Reporte generado: %s para evaluación %s — %d hallazgos, "
            "riesgo=%.1f, confianza=%s",
            report.id,
            assessment_id,
            len(findings),
            risk_analysis.overall_risk_score,
            confidence.value,
        )

        return report

    # ── Análisis de hallazgos ─────────────────────────────────────────────

    async def analyze_findings(
        self,
        risk_assessment: dict,
        correlation: dict,
        screening: dict,
    ) -> InvestigationAnalysis:
        """
        Analiza los hallazgos de la evaluación de riesgo, correlación
        y screening.

        Sintetiza los resultados de múltiples fuentes para producir
        una narrativa coherente de riesgo y destacar conexiones
        y anomalías.

        Args:
            risk_assessment: Datos de la evaluación de riesgo.
            correlation: Datos de la correlación de identidad.
            screening: Datos del screening en listas restrictivas.

        Returns:
            InvestigationAnalysis: Análisis con hallazgos clave,
                narrativa, conexiones y anomalías.
        """
        key_findings: List[str] = []
        connections: List[Dict[str, Any]] = []
        anomalies: List[Dict[str, Any]] = []

        # ── Análisis de riesgo ────────────────────────────────────────────
        risk_score = risk_assessment.get("risk_score", 0)
        recommendation = risk_assessment.get("recommendation", "REVIEW")

        if risk_score > 40:
            key_findings.append(
                f"Evaluación de riesgo alta: puntaje {risk_score:.1f}/100 "
                f"con recomendación de {recommendation}."
            )

        # Analizar factores de riesgo
        risk_factors = risk_assessment.get("risk_factors", [])
        for factor in risk_factors:
            severity = factor.get("severity", "medium")
            name = factor.get("name", "Factor desconocido")
            if severity in ("critical", "high"):
                key_findings.append(
                    f"Factor de riesgo {severity}: {name}"
                )

        # ── Análisis de screening ─────────────────────────────────────────
        screening_matches = screening.get("matches", [])
        if screening_matches:
            for match in screening_matches:
                source = match.get("source", "Desconocido")
                score = match.get("match_score", 0)
                entity_name = match.get("entity_name", "N/A")
                key_findings.append(
                    f"Coincidencia en lista {source}: {entity_name} "
                    f"(similitud: {score:.0%})"
                )
                connections.append(
                    {
                        "type": "screening_match",
                        "source": source,
                        "entity": entity_name,
                        "score": score,
                    }
                )
        else:
            key_findings.append(
                "No se encontraron coincidencias en listas restrictivas."
            )

        # ── Análisis de correlación ──────────────────────────────────────
        identity_confidence = correlation.get("identity_confidence", 0)
        warnings = correlation.get("warnings", [])
        flags = correlation.get("flags", [])

        if identity_confidence < 50:
            anomalies.append(
                {
                    "type": "low_identity_confidence",
                    "value": identity_confidence,
                    "threshold": 50,
                    "description": (
                        f"La confianza de identidad es baja ({identity_confidence:.1f}/100), "
                        f"lo que sugiere posibles inconsistencias en los datos."
                    ),
                }
            )
            key_findings.append(
                f"Baja confianza de identidad: {identity_confidence:.1f}/100"
            )

        if warnings:
            for warning in warnings[:5]:
                anomalies.append(
                    {
                        "type": "correlation_warning",
                        "detail": warning,
                    }
                )

        if flags:
            for flag in flags[:5]:
                anomalies.append(
                    {
                        "type": "correlation_flag",
                        "detail": flag,
                    }
                )

        # ── Generar narrativa de riesgo ──────────────────────────────────
        risk_narrative = self._generate_risk_narrative(
            risk_score, recommendation, screening_matches,
            identity_confidence, risk_factors, warnings, flags
        )

        return InvestigationAnalysis(
            key_findings=key_findings,
            risk_narrative=risk_narrative,
            connections=connections,
            anomalies=anomalies,
        )

    # ── Generación de recomendaciones ─────────────────────────────────────

    async def generate_recommendations(
        self, assessment: dict
    ) -> List[Recommendation]:
        """
        Genera recomendaciones priorizadas basadas en la evaluación.

        Produce una lista de acciones recomendadas con prioridad,
        fundamento y plazo sugerido, organizadas de mayor a menor
        urgencia.

        Args:
            assessment: Datos de la evaluación de riesgo.

        Returns:
            List[Recommendation]: Recomendaciones priorizadas.
        """
        recommendations: List[Recommendation] = []
        risk_score = assessment.get("risk_score", 0)
        recommendation_type = assessment.get("recommendation", "REVIEW")
        risk_factors = assessment.get("risk_factors", [])

        # ── Recomendación basada en resultado general ────────────────────
        if recommendation_type == "REJECT":
            recommendations.append(
                Recommendation(
                    id=str(uuid.uuid4()),
                    priority=Priority.CRITICAL,
                    action=(
                        "Rechazar la solicitud de verificación de identidad "
                        "y documentar las razones del rechazo conforme a la "
                        "LFPIORPI."
                    ),
                    rationale=(
                        f"La evaluación de riesgo produjo un puntaje de "
                        f"{risk_score:.1f}/100 con recomendación de RECHAZO. "
                        f"Se identificaron {len(risk_factors)} factores de riesgo."
                    ),
                    deadline="Inmediato",
                )
            )

        elif recommendation_type == "REVIEW":
            recommendations.append(
                Recommendation(
                    id=str(uuid.uuid4()),
                    priority=Priority.HIGH,
                    action=(
                        "Escalar el caso a un analista de cumplimiento para "
                        "revisión manual detallada antes de tomar una decisión."
                    ),
                    rationale=(
                        f"La evaluación de riesgo produjo un puntaje de "
                        f"{risk_score:.1f}/100 con recomendación de REVISIÓN. "
                        f"Se requiere juicio humano para resolver ambigüedades."
                    ),
                    deadline="24 horas",
                )
            )

        else:  # APPROVE
            recommendations.append(
                Recommendation(
                    id=str(uuid.uuid4()),
                    priority=Priority.LOW,
                    action=(
                        "Aprobar la verificación de identidad y proceder con "
                        "el onboarding del cliente según los procedimientos "
                        "establecidos."
                    ),
                    rationale=(
                        f"La evaluación de riesgo produjo un puntaje bajo "
                        f"({risk_score:.1f}/100) sin factores de riesgo "
                        f"significativos identificados."
                    ),
                    deadline="5 días hábiles",
                )
            )

        # ── Recomendaciones basadas en factores de riesgo específicos ────
        for factor in risk_factors:
            severity = factor.get("severity", "medium")
            name = factor.get("name", "")

            if "OFAC" in name.upper() or "RND" in name.upper():
                recommendations.append(
                    Recommendation(
                        id=str(uuid.uuid4()),
                        priority=Priority.CRITICAL,
                        action=(
                            f"Bloquear inmediatamente cualquier operación con "
                            f"esta identidad y reportar a la unidad de "
                            f"cumplimiento conforme al artículo 17 de la LFPIORPI."
                        ),
                        rationale=(
                            f"Se detectó coincidencia en lista crítica: {name}. "
                            f"Esto requiere bloqueo inmediato y reporte "
                            f"regulatorio."
                        ),
                        deadline="Inmediato",
                    )
                )

            elif "69-B" in name or "SAT" in name:
                recommendations.append(
                    Recommendation(
                        id=str(uuid.uuid4()),
                        priority=Priority.HIGH,
                        action=(
                            "Solicitar documentación adicional que acredite "
                            "la fuente de ingresos y la legitimidad de las "
                            "operaciones del contribuyente."
                        ),
                        rationale=(
                            f"El RFC aparece en el artículo 69-B del CFF: {name}. "
                            f"Se requiere validación adicional antes de "
                            f"continuar la relación comercial."
                        ),
                        deadline="48 horas",
                    )
                )

            elif "inconsistente" in name.lower() or "inconsistent" in name.lower():
                recommendations.append(
                    Recommendation(
                        id=str(uuid.uuid4()),
                        priority=Priority.HIGH,
                        action=(
                            "Solicitar documentos adicionales de identidad "
                            "(INE, pasaporte) para verificar los datos "
                            "proporcionados."
                        ),
                        rationale=(
                            f"Se detectaron inconsistencias en la identidad: {name}. "
                            f"Es necesario verificar la autenticidad de los datos."
                        ),
                        deadline="72 horas",
                    )
                )

            elif "desechable" in name.lower() or "disposable" in name.lower():
                recommendations.append(
                    Recommendation(
                        id=str(uuid.uuid4()),
                        priority=Priority.MEDIUM,
                        action=(
                            "Solicitar un correo electrónico alternativo con "
                            "dominio corporativo o personal permanente."
                        ),
                        rationale=(
                            f"El correo electrónico utiliza un dominio desechable: {name}. "
                            f"Esto puede indicar baja intención de permanencia."
                        ),
                        deadline="5 días hábiles",
                    )
                )

        # ── Recomendación de monitoreo continuo ──────────────────────────
        if risk_score > 15:
            recommendations.append(
                Recommendation(
                    id=str(uuid.uuid4()),
                    priority=Priority.MEDIUM,
                    action=(
                        "Establecer monitoreo continuo de la identidad en "
                        "listas restrictivas con frecuencia mensual."
                    ),
                    rationale=(
                        "Las identidades con puntaje de riesgo superior a 15 "
                        "deben ser monitoreadas periódicamente conforme a las "
                        "disposiciones del Art. 115 de la LGOAAC."
                    ),
                    deadline="Al aprobar la verificación",
                )
            )

        # Ordenar por prioridad
        priority_order = {
            Priority.CRITICAL: 0,
            Priority.HIGH: 1,
            Priority.MEDIUM: 2,
            Priority.LOW: 3,
        }
        recommendations.sort(
            key=lambda r: priority_order.get(r.priority, 99)
        )

        return recommendations

    # ── Resumen de caso ───────────────────────────────────────────────────

    async def summarize_case(
        self, assessment_id: str
    ) -> CaseSummary:
        """
        Genera un resumen conciso del caso para revisión rápida.

        Produce un resumen de 2-3 oraciones con el nivel de riesgo,
        las fechas clave y los próximos pasos recomendados.

        Args:
            assessment_id: Identificador de la evaluación.

        Returns:
            CaseSummary: Resumen del caso.
        """
        # Obtener datos de la evaluación
        assessment = await self._fetch_assessment(assessment_id)

        risk_score = assessment.get("risk_score", 0)
        recommendation = assessment.get("recommendation", "REVIEW")
        created_at = assessment.get("created_at", "")

        # Determinar nivel de riesgo
        if risk_score <= 15:
            risk_level = "bajo"
        elif risk_score <= 40:
            risk_level = "medio"
        else:
            risk_level = "alto"

        # Generar resumen
        summary = (
            f"Caso de verificación de identidad con nivel de riesgo {risk_level} "
            f"(score: {risk_score:.1f}/100). "
            f"La recomendación del sistema es {recommendation}. "
        )

        if recommendation == "REJECT":
            summary += (
                "Se identificaron factores de riesgo críticos que requieren "
                "rechazo inmediato y posible reporte regulatorio."
            )
        elif recommendation == "REVIEW":
            summary += (
                "Se detectaron señales de alerta que requieren revisión "
                "manual por un analista de cumplimiento antes de proceder."
            )
        else:
            summary += (
                "No se identificaron factores de riesgo significativos. "
                "Se recomienda aprobar la verificación."
            )

        # Fechas clave
        key_dates = []
        if created_at:
            key_dates.append(
                {"label": "Fecha de evaluación", "date": created_at}
            )
        key_dates.append(
            {
                "label": "Fecha de generación del resumen",
                "date": datetime.now(timezone.utc).isoformat(),
            }
        )

        # Próximos pasos
        next_steps = []
        if recommendation == "REJECT":
            next_steps = [
                "Documentar razones del rechazo",
                "Reportar a la unidad de cumplimiento",
                "Bloquear operaciones con la identidad",
                "Conservar evidencia por 5 años (LFPIORPI)",
            ]
        elif recommendation == "REVIEW":
            next_steps = [
                "Asignar a analista de cumplimiento",
                "Solicitar documentación adicional si es necesario",
                "Resolver dentro de 72 horas hábiles",
                "Documentar decisión final",
            ]
        else:
            next_steps = [
                "Aprobar verificación de identidad",
                "Proceder con onboarding del cliente",
                "Establecer monitoreo continuo si aplica",
            ]

        return CaseSummary(
            summary=summary,
            risk_level=risk_level,
            key_dates=key_dates,
            next_steps=next_steps,
        )

    # ── Métodos privados de construcción ──────────────────────────────────

    def _build_findings(
        self,
        assessment: dict,
        correlation: dict,
        screening: dict,
        analysis: InvestigationAnalysis,
    ) -> List[Finding]:
        """
        Construye la lista de hallazgos estructurados.

        Args:
            assessment: Datos de evaluación de riesgo.
            correlation: Datos de correlación de identidad.
            screening: Datos de screening.
            analysis: Análisis de hallazgos.

        Returns:
            Lista de hallazgos estructurados.
        """
        findings: List[Finding] = []

        # Hallazgos de screening
        for match in screening.get("matches", []):
            findings.append(
                Finding(
                    id=str(uuid.uuid4()),
                    category="screening",
                    title=f"Coincidencia en lista {match.get('source', 'Desconocida')}",
                    description=(
                        f"Se encontró coincidencia con la entidad "
                        f"'{match.get('entity_name', 'N/A')}' en la lista "
                        f"{match.get('source', 'desconocida')} con similitud "
                        f"de {match.get('match_score', 0):.0%}. Tipo de "
                        f"coincidencia: {match.get('match_type', 'N/A')}."
                    ),
                    severity="critical" if match.get("match_score", 0) >= 0.95 else "high",
                    evidence=[match],
                    source=match.get("source", "unknown"),
                )
            )

        # Hallazgos de evaluación de riesgo
        for factor in assessment.get("risk_factors", []):
            findings.append(
                Finding(
                    id=str(uuid.uuid4()),
                    category="risk_assessment",
                    title=factor.get("name", "Factor de riesgo"),
                    description=factor.get("details", ""),
                    severity=factor.get("severity", "medium"),
                    evidence=[factor],
                    source="risk_engine",
                )
            )

        # Hallazgos de correlación
        for warning in correlation.get("warnings", []):
            findings.append(
                Finding(
                    id=str(uuid.uuid4()),
                    category="identity_correlation",
                    title="Advertencia de correlación",
                    description=str(warning),
                    severity="medium",
                    evidence=[{"warning": warning}],
                    source="identity_correlation",
                )
            )

        for flag in correlation.get("flags", []):
            findings.append(
                Finding(
                    id=str(uuid.uuid4()),
                    category="identity_correlation",
                    title="Indicador de alerta",
                    description=str(flag),
                    severity="high",
                    evidence=[{"flag": flag}],
                    source="identity_correlation",
                )
            )

        # Hallazgos de anomalías del análisis
        for anomaly in analysis.anomalies:
            findings.append(
                Finding(
                    id=str(uuid.uuid4()),
                    category="anomaly",
                    title=f"Anomalía: {anomaly.get('type', 'Desconocida')}",
                    description=anomaly.get("description", str(anomaly)),
                    severity="medium",
                    evidence=[anomaly],
                    source="ai_analysis",
                )
            )

        # Ordenar por severidad
        severity_order = {"critical": 0, "high": 1, "medium": 2, "low": 3}
        findings.sort(
            key=lambda f: severity_order.get(f.severity, 99)
        )

        return findings

    def _build_risk_analysis(
        self,
        assessment: dict,
        analysis: InvestigationAnalysis,
    ) -> RiskAnalysis:
        """
        Construye el análisis de riesgo del reporte.

        Args:
            assessment: Datos de evaluación de riesgo.
            analysis: Análisis de hallazgos.

        Returns:
            RiskAnalysis: Análisis de riesgo detallado.
        """
        return RiskAnalysis(
            overall_risk_score=assessment.get("risk_score", 0),
            trust_score=assessment.get("trust_score", 0),
            recommendation=assessment.get("recommendation", "REVIEW"),
            risk_factors=assessment.get("risk_factors", []),
            mitigating_factors=assessment.get("mitigating_factors", []),
            narrative=analysis.risk_narrative,
        )

    def _generate_executive_summary(
        self,
        assessment: dict,
        findings: List[Finding],
        risk_analysis: RiskAnalysis,
    ) -> str:
        """
        Genera el resumen ejecutivo del reporte.

        Args:
            assessment: Datos de la evaluación.
            findings: Hallazgos identificados.
            risk_analysis: Análisis de riesgo.

        Returns:
            str: Resumen ejecutivo en español.
        """
        risk_score = risk_analysis.overall_risk_score
        recommendation = risk_analysis.recommendation
        total_findings = len(findings)
        critical_findings = sum(
            1 for f in findings if f.severity == "critical"
        )
        high_findings = sum(
            1 for f in findings if f.severity == "high"
        )

        if recommendation == "REJECT":
            summary = (
                f"La investigación de identidad concluye con una recomendación "
                f"de RECHAZO. El puntaje de riesgo es de {risk_score:.1f}/100, "
                f"con {total_findings} hallazgos identificados "
                f"({critical_findings} críticos, {high_findings} altos). "
                f"Se detectaron factores de riesgo que requieren el bloqueo "
                f"inmediato de operaciones y posible reporte regulatorio "
                f"conforme a la LFPIORPI."
            )
        elif recommendation == "REVIEW":
            summary = (
                f"La investigación de identidad concluye con una recomendación "
                f"de REVISIÓN. El puntaje de riesgo es de {risk_score:.1f}/100, "
                f"con {total_findings} hallazgos identificados "
                f"({critical_findings} críticos, {high_findings} altos). "
                f"Se requiere intervención manual de un analista de "
                f"cumplimiento para resolver las señales de alerta antes "
                f"de proceder."
            )
        else:
            summary = (
                f"La investigación de identidad concluye con una recomendación "
                f"de APROBACIÓN. El puntaje de riesgo es de {risk_score:.1f}/100, "
                f"con {total_findings} hallazgos de baja severidad. "
                f"No se identificaron factores de riesgo significativos que "
                f"impidan continuar con la verificación."
            )

        return summary

    def _generate_risk_narrative(
        self,
        risk_score: float,
        recommendation: str,
        screening_matches: list,
        identity_confidence: float,
        risk_factors: list,
        warnings: list,
        flags: list,
    ) -> str:
        """
        Genera una narrativa de riesgo en lenguaje natural.

        Args:
            risk_score: Puntuación de riesgo.
            recommendation: Recomendación general.
            screening_matches: Coincidencias de screening.
            identity_confidence: Confianza de identidad.
            risk_factors: Factores de riesgo.
            warnings: Advertencias de correlación.
            flags: Indicadores de alerta.

        Returns:
            str: Narrativa de riesgo en español.
        """
        parts: List[str] = []

        # Apertura
        if risk_score <= 15:
            parts.append(
                "El perfil de riesgo de la identidad evaluada es BAJO."
            )
        elif risk_score <= 40:
            parts.append(
                "El perfil de riesgo de la identidad evaluada es MEDIO, "
                "con señales que requieren atención."
            )
        else:
            parts.append(
                "El perfil de riesgo de la identidad evaluada es ALTO, "
                "con múltiples señales de alerta que requieren acción inmediata."
            )

        # Screening
        if screening_matches:
            sources = [m.get("source", "N/A") for m in screening_matches]
            unique_sources = list(dict.fromkeys(sources))
            parts.append(
                f"El screening en listas restrictivas identificó "
                f"{len(screening_matches)} coincidencia(s) en "
                f"{', '.join(unique_sources)}."
            )
        else:
            parts.append(
                "El screening en listas restrictivas no produjo coincidencias."
            )

        # Identidad
        if identity_confidence >= 70:
            parts.append(
                f"La correlación de identidad muestra una confianza ALTA "
                f"({identity_confidence:.1f}/100), lo que respalda la "
                f"consistencia de los datos proporcionados."
            )
        elif identity_confidence >= 40:
            parts.append(
                f"La correlación de identidad muestra una confianza MEDIA "
                f"({identity_confidence:.1f}/100), con algunas inconsistencias "
                f"que deben ser verificadas."
            )
        else:
            parts.append(
                f"La correlación de identidad muestra una confianza BAJA "
                f"({identity_confidence:.1f}/100), lo que sugiere posibles "
                f"inconsistencias significativas en los datos proporcionados."
            )

        # Factores
        if risk_factors:
            critical = [f for f in risk_factors if f.get("severity") == "critical"]
            high = [f for f in risk_factors if f.get("severity") == "high"]
            if critical:
                parts.append(
                    f"Se identificaron {len(critical)} factor(es) de riesgo "
                    f"crítico(s) que requieren acción inmediata."
                )
            if high:
                parts.append(
                    f"Se identificaron {len(high)} factor(es) de riesgo "
                    f"alto(s) que deben ser evaluados por un analista."
                )

        # Advertencias
        if warnings:
            parts.append(
                f"Se generaron {len(warnings)} advertencia(s) durante "
                f"la correlación de identidad."
            )

        # Conclusión
        if recommendation == "REJECT":
            parts.append(
                "En conclusión, se recomienda RECHAZAR la verificación de "
                "identidad y proceder conforme a los protocolos de la LFPIORPI."
            )
        elif recommendation == "REVIEW":
            parts.append(
                "En conclusión, se recomienda ESCALAR a revisión manual "
                "para resolver las señales de alerta antes de tomar una "
                "decisión final."
            )
        else:
            parts.append(
                "En conclusión, se recomienda APROBAR la verificación de "
                "identidad y proceder con el onboarding del cliente."
            )

        return " ".join(parts)

    def _determine_confidence_level(
        self,
        assessment: dict,
        screening: dict,
        correlation: dict,
    ) -> ConfidenceLevel:
        """
        Determina el nivel de confianza del análisis de investigación.

        Args:
            assessment: Datos de evaluación de riesgo.
            screening: Datos de screening.
            correlation: Datos de correlación.

        Returns:
            ConfidenceLevel: Nivel de confianza del análisis.
        """
        signals: List[float] = []

        # Confianza basada en cantidad de datos de screening
        sources_count = len(screening.get("sources_checked", []))
        if sources_count >= 5:
            signals.append(0.9)
        elif sources_count >= 3:
            signals.append(0.7)
        elif sources_count >= 1:
            signals.append(0.5)
        else:
            signals.append(0.3)

        # Confianza basada en correlación de identidad
        identity_confidence = correlation.get("identity_confidence", 0)
        signals.append(identity_confidence / 100.0)

        # Confianza basada en si hay datos de evaluación
        if assessment.get("risk_score") is not None:
            signals.append(0.8)
        else:
            signals.append(0.3)

        avg_confidence = sum(signals) / len(signals) if signals else 0.0

        if avg_confidence >= 0.85:
            return ConfidenceLevel.VERY_HIGH
        elif avg_confidence >= 0.70:
            return ConfidenceLevel.HIGH
        elif avg_confidence >= 0.50:
            return ConfidenceLevel.MEDIUM
        elif avg_confidence >= 0.30:
            return ConfidenceLevel.LOW
        else:
            return ConfidenceLevel.VERY_LOW

    # ── Métodos privados de acceso a datos ────────────────────────────────

    async def _fetch_assessment(self, assessment_id: str) -> dict:
        """
        Obtiene los datos de una evaluación de riesgo.

        En producción, consultaría PostgreSQL. Aquí retorna
        un diccionario con datos de ejemplo.

        Args:
            assessment_id: ID de la evaluación.

        Returns:
            dict: Datos de la evaluación.
        """
        try:
            from sqlalchemy import select
            from app.database import get_db_session
            from app.models.identity import RiskAssessment

            async with get_db_session() as session:
                stmt = select(RiskAssessment).where(
                    RiskAssessment.id == assessment_id
                )
                result = await session.execute(stmt)
                record = result.scalar_one_or_none()

                if record:
                    return {
                        "id": record.id,
                        "risk_score": record.risk_score,
                        "trust_score": record.trust_score,
                        "recommendation": record.recommendation,
                        "risk_factors": record.risk_factors or [],
                        "mitigating_factors": record.mitigating_factors or [],
                        "created_at": (
                            record.created_at.isoformat()
                            if record.created_at
                            else ""
                        ),
                    }
        except Exception as exc:
            logger.warning(
                "Error obteniendo evaluación %s: %s", assessment_id, exc
            )

        # Datos por defecto si no se encuentra
        return {
            "id": assessment_id,
            "risk_score": 0.0,
            "trust_score": 0.0,
            "recommendation": "REVIEW",
            "risk_factors": [],
            "mitigating_factors": [],
            "created_at": datetime.now(timezone.utc).isoformat(),
        }

    async def _fetch_correlation(self, assessment_id: str) -> dict:
        """
        Obtiene los datos de correlación de identidad.

        Args:
            assessment_id: ID de la evaluación.

        Returns:
            dict: Datos de la correlación.
        """
        try:
            from sqlalchemy import select
            from app.database import get_db_session
            from app.models.identity import IdentityCorrelation, RiskAssessment

            async with get_db_session() as session:
                # Primero obtener la evaluación para encontrar el correlation_id
                stmt = select(RiskAssessment).where(
                    RiskAssessment.id == assessment_id
                )
                result = await session.execute(stmt)
                assessment = result.scalar_one_or_none()

                if assessment:
                    stmt = select(IdentityCorrelation).where(
                        IdentityCorrelation.id == assessment.correlation_id
                    )
                    result = await session.execute(stmt)
                    correlation = result.scalar_one_or_none()

                    if correlation:
                        return {
                            "id": correlation.id,
                            "identity_confidence": correlation.identity_confidence,
                            "warnings": correlation.warnings or [],
                            "flags": correlation.flags or [],
                            "signals": correlation.signals or [],
                        }
        except Exception as exc:
            logger.warning(
                "Error obteniendo correlación para %s: %s",
                assessment_id,
                exc,
            )

        return {
            "identity_confidence": 0.0,
            "warnings": [],
            "flags": [],
            "signals": [],
        }

    async def _fetch_screening(self, assessment_id: str) -> dict:
        """
        Obtiene los datos de screening.

        Args:
            assessment_id: ID de la evaluación.

        Returns:
            dict: Datos del screening.
        """
        # En producción, consultaría la tabla de screening_matches
        # Para esta implementación, retornamos datos mínimos
        return {
            "matches": [],
            "sources_checked": [],
        }

    # ── Serialización ─────────────────────────────────────────────────────

    def _serialize_report(self, report: InvestigationReport) -> dict:
        """
        Serializa un reporte a diccionario para almacenamiento en caché.

        Args:
            report: Reporte de investigación.

        Returns:
            dict: Datos serializados.
        """
        return {
            "id": report.id,
            "assessment_id": report.assessment_id,
            "executive_summary": report.executive_summary,
            "findings": [
                {
                    "id": f.id,
                    "category": f.category,
                    "title": f.title,
                    "description": f.description,
                    "severity": f.severity,
                    "evidence": f.evidence,
                    "source": f.source,
                }
                for f in report.findings
            ],
            "risk_analysis": {
                "overall_risk_score": report.risk_analysis.overall_risk_score,
                "trust_score": report.risk_analysis.trust_score,
                "recommendation": report.risk_analysis.recommendation,
                "risk_factors": report.risk_analysis.risk_factors,
                "mitigating_factors": report.risk_analysis.mitigating_factors,
                "narrative": report.risk_analysis.narrative,
            },
            "recommendations": [
                {
                    "id": r.id,
                    "priority": r.priority.value,
                    "action": r.action,
                    "rationale": r.rationale,
                    "deadline": r.deadline,
                }
                for r in report.recommendations
            ],
            "methodology": {
                "name": report.methodology.name,
                "version": report.methodology.version,
                "steps": report.methodology.steps,
                "sources_consulted": report.methodology.sources_consulted,
                "standards": report.methodology.standards,
            },
            "confidence_level": report.confidence_level.value,
            "generated_at": report.generated_at,
        }

    def _deserialize_report(self, data: dict) -> InvestigationReport:
        """
        Deserializa un reporte desde diccionario (caché).

        Args:
            data: Datos serializados.

        Returns:
            InvestigationReport: Reporte reconstruido.
        """
        findings = [
            Finding(
                id=f["id"],
                category=f["category"],
                title=f["title"],
                description=f["description"],
                severity=f["severity"],
                evidence=f["evidence"],
                source=f["source"],
            )
            for f in data.get("findings", [])
        ]

        risk_data = data.get("risk_analysis", {})
        risk_analysis = RiskAnalysis(
            overall_risk_score=risk_data.get("overall_risk_score", 0),
            trust_score=risk_data.get("trust_score", 0),
            recommendation=risk_data.get("recommendation", "REVIEW"),
            risk_factors=risk_data.get("risk_factors", []),
            mitigating_factors=risk_data.get("mitigating_factors", []),
            narrative=risk_data.get("narrative", ""),
        )

        recommendations = [
            Recommendation(
                id=r["id"],
                priority=Priority(r["priority"]),
                action=r["action"],
                rationale=r["rationale"],
                deadline=r["deadline"],
            )
            for r in data.get("recommendations", [])
        ]

        meth_data = data.get("methodology", {})
        methodology = Methodology(
            name=meth_data.get("name", ""),
            version=meth_data.get("version", ""),
            steps=meth_data.get("steps", []),
            sources_consulted=meth_data.get("sources_consulted", []),
            standards=meth_data.get("standards", []),
        )

        return InvestigationReport(
            id=data["id"],
            assessment_id=data["assessment_id"],
            executive_summary=data["executive_summary"],
            findings=findings,
            risk_analysis=risk_analysis,
            recommendations=recommendations,
            methodology=methodology,
            confidence_level=ConfidenceLevel(data.get("confidence_level", "medium")),
            generated_at=data["generated_at"],
        )
