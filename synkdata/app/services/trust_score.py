"""
Motor de puntuación de confianza (Trust Score) para la plataforma SynkData.

Calcula el puntaje de confianza de una identidad basándose en señales
positivas derivadas de las verificaciones, screening e inteligencia
digital realizadas previamente.

Contribuyentes al Trust Score (señales positivas, máximo 100 puntos):
- RENAPO válido: +20
- RFC válido: +15
- SAT activo: +15
- Sin sanciones (screening limpio): +20
- Presencia profesional: +10
- GitHub activo: +5
- LinkedIn encontrado: +5
- Correo verificable: +5
- Teléfono válido: +5

Niveles de confianza:
- very_high: 90-100
- high: 70-89
- medium: 50-69
- low: 30-49
- very_low: 0-29

Los mensajes dirigidos al usuario están en español conforme a los
estándares de la plataforma SynkData.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import List

from app.schemas.identity import (
    ScoreContributor,
    TrustContext,
    TrustLevel,
    TrustScoreResult,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Definición de contribuyentes al trust score
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class TrustContributorDef:
    """
    Definición de un contribuyente al trust score.

    Attributes:
        name: Nombre descriptivo del factor.
        max_points: Puntos máximos que puede otorgar.
        field_name: Nombre del campo en TrustContext que activa este contribuyente.
        pass_description: Descripción cuando el factor se cumple.
        fail_description: Descripción cuando el factor no se cumple.
    """

    name: str
    max_points: float
    field_name: str
    pass_description: str
    fail_description: str


# Ordenados por importancia/peso
TRUST_CONTRIBUTORS: List[TrustContributorDef] = [
    TrustContributorDef(
        name="RENAPO válido",
        max_points=20.0,
        field_name="renapo_valid",
        pass_description="La CURP fue validada exitosamente contra RENAPO, confirmando la existencia del registro poblacional.",
        fail_description="La CURP no fue validada por RENAPO o la validación falló.",
    ),
    TrustContributorDef(
        name="Sin sanciones (screening limpio)",
        max_points=20.0,
        field_name="screening_clean",
        pass_description="El screening en listas restrictivas (OFAC, ONU, Interpol, etc.) no arrojó coincidencias.",
        fail_description="El screening en listas restrictivas arrojó coincidencias o no se realizó.",
    ),
    TrustContributorDef(
        name="RFC válido",
        max_points=15.0,
        field_name="rfc_valid",
        pass_description="El RFC pasó la validación de formato y dígito verificador.",
        fail_description="El RFC no pasó la validación de formato o dígito verificador.",
    ),
    TrustContributorDef(
        name="SAT activo",
        max_points=15.0,
        field_name="sat_active",
        pass_description="El RFC está registrado como activo en el Servicio de Administración Tributaria.",
        fail_description="El RFC no está activo en el SAT o no se pudo verificar.",
    ),
    TrustContributorDef(
        name="Presencia profesional",
        max_points=10.0,
        field_name="professional_presence",
        pass_description="Se detectó presencia profesional verificable (sitio web corporativo, perfil profesional, etc.).",
        fail_description="No se detectó presencia profesional verificable.",
    ),
    TrustContributorDef(
        name="GitHub activo",
        max_points=5.0,
        field_name="github_active",
        pass_description="Se encontró un perfil activo en GitHub con actividad reciente.",
        fail_description="No se encontró un perfil activo en GitHub.",
    ),
    TrustContributorDef(
        name="LinkedIn encontrado",
        max_points=5.0,
        field_name="linkedin_found",
        pass_description="Se encontró un perfil en LinkedIn asociado a la identidad.",
        fail_description="No se encontró un perfil en LinkedIn.",
    ),
    TrustContributorDef(
        name="Correo verificable",
        max_points=5.0,
        field_name="email_verifiable",
        pass_description="El correo electrónico es entregable (MX válido y verificación SMTP exitosa).",
        fail_description="El correo electrónico no es verificable o no se pudo confirmar su entregabilidad.",
    ),
    TrustContributorDef(
        name="Teléfono válido",
        max_points=5.0,
        field_name="phone_valid",
        pass_description="El número telefónico es válido según validación de formato y carrier.",
        fail_description="El número telefónico no es válido o no se pudo verificar.",
    ),
]


# ---------------------------------------------------------------------------
# Servicio de Trust Score
# ---------------------------------------------------------------------------
class TrustScoreService:
    """
    Servicio de cálculo del puntaje de confianza (Trust Score).

    Evalúa señales positivas derivadas de las verificaciones,
    screening e inteligencia digital para calcular un puntaje
    de confianza de 0 a 100.

    Cada contribuyente tiene su propia lógica de validación
    basada en los datos del TrustContext proporcionado.
    """

    async def calculate(self, context: TrustContext) -> TrustScoreResult:
        """
        Calcula el trust score basándose en el contexto de verificaciones.

        Args:
            context: Contexto con los resultados de todas las verificaciones
                previas (RENAPO, SAT, screening, inteligencia digital, etc.).

        Returns:
            TrustScoreResult: Puntuación de confianza con detalle de
                cada contribuyente y nivel categorizado.
        """
        contributors: List[ScoreContributor] = []
        total_score = 0.0

        for contributor_def in TRUST_CONTRIBUTORS:
            # Evaluar si el campo del contexto está activo
            passed = getattr(context, contributor_def.field_name, False)

            points = contributor_def.max_points if passed else 0.0
            total_score += points

            details = (
                contributor_def.pass_description
                if passed
                else contributor_def.fail_description
            )

            # Agregar detalles adicionales del contexto si están disponibles
            if passed and context.verification_details:
                extra = context.verification_details.get(contributor_def.field_name)
                if extra and isinstance(extra, str):
                    details += f" Detalle: {extra}"

            contributors.append(
                ScoreContributor(
                    name=contributor_def.name,
                    points=points,
                    max_points=contributor_def.max_points,
                    passed=passed,
                    details=details,
                )
            )

        # Determinar nivel de confianza
        level = self._determine_trust_level(total_score)

        logger.info(
            "Trust score calculado — score=%.1f/100, level=%s, contributors=%d",
            total_score,
            level.value,
            len(contributors),
        )

        return TrustScoreResult(
            score=round(total_score, 2),
            max_possible=100.0,
            contributors=contributors,
            level=level,
        )

    @staticmethod
    def _determine_trust_level(score: float) -> TrustLevel:
        """
        Determina el nivel de confianza categorizado a partir del puntaje.

        Rangos:
        - very_high: 90-100
        - high: 70-89
        - medium: 50-69
        - low: 30-49
        - very_low: 0-29

        Args:
            score: Puntuación de confianza (0-100).

        Returns:
            TrustLevel: Nivel de confianza categorizado.
        """
        if score >= 90:
            return TrustLevel.VERY_HIGH
        elif score >= 70:
            return TrustLevel.HIGH
        elif score >= 50:
            return TrustLevel.MEDIUM
        elif score >= 30:
            return TrustLevel.LOW
        else:
            return TrustLevel.VERY_LOW
