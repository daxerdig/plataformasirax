"""
Servicio de comparación difusa y fonética para la plataforma SynkData.

Implementa comparación de nombres con soporte para:
- Emparejamiento difuso basado en Levenshtein (fuzzywuzzy)
- Emparejamiento fonético adaptado al español
- Comparación con alias y nombres alternativos
- Normalización de entidades para comparación (acentos, mayúsculas, partículas)
- Manejo de inversión de nombres, nombres parciales e iniciales

Este módulo es fundamental para el proceso de screening en listas restrictivas,
donde variaciones ortográficas y fonéticas deben ser detectadas como coincidencias
potenciales para evitar falsos negativos en el cumplimiento normativo.
"""

from __future__ import annotations

import logging
import re
import unicodedata
from dataclasses import dataclass, field
from enum import Enum
from itertools import permutations
from typing import Optional

from fuzzywuzzy import fuzz

from app.utils.phonetic import phonetic_encode, phonetic_match
from app.utils.text_normalizer import (
    _NAME_PARTICLES,
    normalize_for_comparison,
    remove_accents,
    split_full_name,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Tipos de coincidencia
# ---------------------------------------------------------------------------
class MatchType(str, Enum):
    """Tipos de coincidencia identificados por el motor de comparación."""

    EXACT = "exact"
    FUZZY = "fuzzy"
    PHONETIC = "phonetic"
    ALIAS = "alias"


# ---------------------------------------------------------------------------
# Modelo de resultado
# ---------------------------------------------------------------------------
@dataclass(frozen=True, slots=True)
class MatchResult:
    """
    Resultado de una comparación difusa o fonética.

    Attributes:
        target: Cadena objetivo contra la que se comparó.
        score: Puntuación de similitud (0.0 a 1.0).
        match_type: Tipo de coincidencia detectada.
        confidence: Nivel de confianza del resultado (0.0 a 1.0).
            Difiere del score en que considera el tipo de coincidencia
            y la calidad general del emparejamiento.
    """

    target: str
    score: float
    match_type: MatchType
    confidence: float

    def __post_init__(self) -> None:
        """Valida que los valores numéricos estén en rango [0.0, 1.0]."""
        for field_name in ("score", "confidence"):
            value = getattr(self, field_name)
            if not 0.0 <= value <= 1.0:
                raise ValueError(
                    f"{field_name} debe estar entre 0.0 y 1.0, recibido: {value}"
                )


# ---------------------------------------------------------------------------
# Partículas comunes en nombres en español para normalización avanzada
# ---------------------------------------------------------------------------
_SPANISH_PARTICLES: set[str] = {
    "DE", "DEL", "DE LA", "DE LOS", "DE LAS",
    "LA", "LAS", "LOS", "EL",
    "Y", "E", "O", "U",
    "EN", "POR", "CON", "PARA", "A",
    "VON", "VAN", "DI", "DA", "DOS", "DAS",
    "SAN", "SANTA", "SANTO",
}

# Nombres compuestos comunes en español
_COMPOUND_NAMES: set[str] = {
    "JOSE LUIS", "JOSE MANUEL", "JOSE ANGEL", "JOSE ANTONIO",
    "JOSE CARLOS", "JOSE EDUARDO", "JOSE FRANCISCO", "JOSE GUADALUPE",
    "JOSE MIGUEL", "JOSE PEDRO", "JOSE RAMON", "JOSE RAFAEL",
    "JOSE ROBERTO", "JOSE RICARDO",
    "MARIA DEL CARMEN", "MARIA ELENA", "MARIA TERESA", "MARIA GUADALUPE",
    "MARIA ISABEL", "MARIA JOSE", "MARIA LUISA", "MARIA DE LOS ANGELES",
    "MARIA DE LA PAZ", "MARIA DEL ROSARIO", "MARIA DEL PILAR",
    "MARIA CRISTINA", "MARIA DE LA LUZ", "MARIA FERNANDA",
    "MARIA MARGARITA", "MARIA SOLEDAD", "MARIA VICTORIA",
    "JUAN CARLOS", "JUAN MANUEL", "JUAN JOSE", "JUAN ANTONIO",
    "JUAN PEDRO", "JUAN LUIS", "JUAN FRANCISCO", "JUAN EDUARDO",
    "CARLOS ALBERTO", "CARLOS EDUARDO", "CARLOS MANUEL",
    "LUIS ALBERTO", "LUIS MANUEL", "LUIS CARLOS",
    "PEDRO ANTONIO", "PEDRO MANUEL",
    "MIGUEL ANGEL", "MIGUEL ANTONIO",
    "FRANCISCO JAVIER", "FRANCISCO JOSE",
    "ANTONIO JOSE", "ANTONIO MANUEL",
    "ROBERTO CARLOS",
    "ANA MARIA", "ANA LUISA", "ANA CRISTINA",
    "ROSA MARIA", "ROSA ELENA",
    "LAURA PATRICIA", "LAURA ELENA",
}


# ---------------------------------------------------------------------------
# Servicio principal
# ---------------------------------------------------------------------------
class FuzzyMatcherService:
    """
    Servicio de comparación difusa y fonética para nombres y entidades.

    Provee métodos para comparar nombres contra listas de objetivos
    utilizando múltiples estrategias de comparación:
    - Comparación exacta (normalizada)
    - Comparación difusa (Levenshtein via fuzzywuzzy)
    - Comparación fonética (algoritmo adaptado al español)
    - Comparación con alias y nombres alternativos

    El servicio normaliza automáticamente los nombres antes de la
    comparación, eliminando acentos, mayúsculas y partículas comunes.

    Example:
        >>> matcher = FuzzyMatcherService()
        >>> results = matcher.match("José Vázquez", ["JOSE VAZQUEZ", "PEDRO LOPEZ"])
        >>> len(results)
        1
        >>> results[0].match_type
        <MatchType.EXACT: 'exact'>
    """

    def __init__(self, *, min_score: float = 0.5) -> None:
        """
        Inicializa el servicio de comparación difusa.

        Args:
            min_score: Puntuación mínima para incluir un resultado.
                Resultados con score menor son descartados.
        """
        self._min_score = min_score

    # ── Comparación difusa principal ─────────────────────────────────────

    def match(
        self,
        query: str,
        targets: list[str],
        threshold: float = 0.85,
    ) -> list[MatchResult]:
        """
        Compara una cadena de consulta contra una lista de objetivos.

        Aplica múltiples estrategias de comparación y retorna las
        coincidencias que superan el umbral especificado:
        1. Comparación exacta normalizada
        2. Comparación difusa (Levenshtein)
        3. Comparación fonética (español)
        4. Comparación con inversión de nombre/apellido

        Args:
            query: Nombre o cadena a buscar.
            targets: Lista de nombres objetivos contra los que comparar.
            threshold: Umbral mínimo de similitud (0.0 a 1.0).

        Returns:
            Lista de MatchResult ordenada por score descendente,
            sin duplicados (se conserva el mejor resultado por target).
        """
        if not query or not targets:
            return []

        normalized_query = self.normalize_entity(query)
        if not normalized_query:
            return []

        results: dict[str, MatchResult] = {}

        for target in targets:
            if not target:
                continue

            # ── 1. Comparación exacta normalizada ──────────────────────
            normalized_target = self.normalize_entity(target)
            if not normalized_target:
                continue

            if normalized_query == normalized_target:
                self._upsert_result(
                    results,
                    target,
                    MatchResult(
                        target=target,
                        score=1.0,
                        match_type=MatchType.EXACT,
                        confidence=1.0,
                    ),
                )
                continue

            # ── 2. Comparación difusa ──────────────────────────────────
            fuzzy_score = self._compute_fuzzy_score(normalized_query, normalized_target)
            if fuzzy_score >= threshold:
                confidence = self._compute_confidence(fuzzy_score, MatchType.FUZZY)
                self._upsert_result(
                    results,
                    target,
                    MatchResult(
                        target=target,
                        score=fuzzy_score,
                        match_type=MatchType.FUZZY,
                        confidence=confidence,
                    ),
                )

            # ── 3. Comparación fonética ────────────────────────────────
            phonetic_score = phonetic_match(query, target)
            if phonetic_score >= threshold:
                confidence = self._compute_confidence(phonetic_score, MatchType.PHONETIC)
                self._upsert_result(
                    results,
                    target,
                    MatchResult(
                        target=target,
                        score=phonetic_score,
                        match_type=MatchType.PHONETIC,
                        confidence=confidence,
                    ),
                )

            # ── 4. Inversión de nombre/apellido ────────────────────────
            reversed_score = self._match_reversed(normalized_query, normalized_target)
            if reversed_score >= threshold:
                confidence = self._compute_confidence(reversed_score, MatchType.FUZZY)
                self._upsert_result(
                    results,
                    target,
                    MatchResult(
                        target=target,
                        score=reversed_score,
                        match_type=MatchType.FUZZY,
                        confidence=confidence,
                    ),
                )

            # ── 5. Nombres parciales e iniciales ───────────────────────
            partial_score = self._match_partial(normalized_query, normalized_target)
            if partial_score >= threshold:
                confidence = self._compute_confidence(partial_score, MatchType.FUZZY)
                self._upsert_result(
                    results,
                    target,
                    MatchResult(
                        target=target,
                        score=partial_score,
                        match_type=MatchType.FUZZY,
                        confidence=confidence,
                    ),
                )

        # Filtrar por score mínimo y ordenar
        filtered = [
            r for r in results.values() if r.score >= self._min_score
        ]
        return sorted(filtered, key=lambda r: r.score, reverse=True)

    # ── Comparación fonética ────────────────────────────────────────────

    def match_phonetic(
        self,
        name: str,
        targets: list[str],
    ) -> list[MatchResult]:
        """
        Compara un nombre contra objetivos utilizando solo fonética española.

        Utiliza el algoritmo de codificación fonética adaptado al español
        que considera seseo, yeísmo, equivalencia v/b, etc.

        Args:
            name: Nombre a buscar.
            targets: Lista de nombres objetivos.

        Returns:
            Lista de MatchResult con coincidencias fonéticas.
        """
        if not name or not targets:
            return []

        results: list[MatchResult] = []

        for target in targets:
            if not target:
                continue

            phonetic_score = phonetic_match(name, target)

            if phonetic_score >= self._min_score:
                confidence = self._compute_confidence(phonetic_score, MatchType.PHONETIC)
                results.append(
                    MatchResult(
                        target=target,
                        score=phonetic_score,
                        match_type=MatchType.PHONETIC,
                        confidence=confidence,
                    )
                )

        return sorted(results, key=lambda r: r.score, reverse=True)

    # ── Comparación con alias ───────────────────────────────────────────

    def match_with_aliases(
        self,
        name: str,
        aliases: list[str],
        threshold: float = 0.8,
    ) -> list[MatchResult]:
        """
        Compara un nombre contra una lista de alias/nombres alternativos.

        Los alias suelen tener mayor tolerancia en el umbral de coincidencia
        ya que representan variaciones intencionales del nombre (apodos,
        nombres abreviados, transliteraciones).

        Args:
            name: Nombre a buscar.
            aliases: Lista de alias o nombres alternativos.
            threshold: Umbral mínimo de similitud (por defecto 0.8, menor
                que el estándar de 0.85 para mayor tolerancia).

        Returns:
            Lista de MatchResult con coincidencias contra alias.
        """
        if not name or not aliases:
            return []

        normalized_name = self.normalize_entity(name)
        if not normalized_name:
            return []

        results: dict[str, MatchResult] = {}

        for alias in aliases:
            if not alias:
                continue

            normalized_alias = self.normalize_entity(alias)
            if not normalized_alias:
                continue

            # Coincidencia exacta de alias
            if normalized_name == normalized_alias:
                self._upsert_result(
                    results,
                    alias,
                    MatchResult(
                        target=alias,
                        score=1.0,
                        match_type=MatchType.ALIAS,
                        confidence=0.95,
                    ),
                )
                continue

            # Comparación difusa con alias
            fuzzy_score = self._compute_fuzzy_score(normalized_name, normalized_alias)
            if fuzzy_score >= threshold:
                confidence = self._compute_confidence(fuzzy_score, MatchType.ALIAS)
                self._upsert_result(
                    results,
                    alias,
                    MatchResult(
                        target=alias,
                        score=fuzzy_score,
                        match_type=MatchType.ALIAS,
                        confidence=confidence,
                    ),
                )

            # Comparación fonética de alias
            phonetic_score = phonetic_match(name, alias)
            if phonetic_score >= threshold:
                confidence = self._compute_confidence(phonetic_score, MatchType.ALIAS)
                self._upsert_result(
                    results,
                    alias,
                    MatchResult(
                        target=alias,
                        score=phonetic_score,
                        match_type=MatchType.ALIAS,
                        confidence=confidence,
                    ),
                )

        filtered = [r for r in results.values() if r.score >= self._min_score]
        return sorted(filtered, key=lambda r: r.score, reverse=True)

    # ── Normalización de entidades ──────────────────────────────────────

    def normalize_entity(self, entity: str) -> str:
        """
        Normaliza una entidad (nombre) para comparación.

        Aplica las siguientes transformaciones:
        1. Eliminación de acentos y diacríticos
        2. Conversión a mayúsculas
        3. Eliminación de partículas comunes (de, del, la, y, etc.)
        4. Normalización de espacios en blanco
        5. Eliminación de caracteres no alfabéticos (excepto Ñ)

        Args:
            entity: Nombre o entidad a normalizar.

        Returns:
            str: Entidad normalizada lista para comparación.

        Example:
            >>> matcher = FuzzyMatcherService()
            >>> matcher.normalize_entity("José de la Cruz Vázquez")
            'JOSE CRUZ VAZQUEZ'
        """
        if not entity:
            return ""

        # Normalización base (acentos, mayúsculas, espacios)
        normalized = normalize_for_comparison(entity)

        if not normalized:
            return ""

        # Eliminar partículas comunes en español
        words = normalized.split()
        filtered_words = [
            w for w in words
            if w not in _SPANISH_PARTICLES
        ]

        # Si se eliminaron todas las palabras, mantener la normalización base
        if not filtered_words:
            return normalized

        return " ".join(filtered_words)

    # ── Métodos auxiliares privados ─────────────────────────────────────

    def _compute_fuzzy_score(self, query: str, target: str) -> float:
        """
        Calcula la puntuación difusa combinando múltiples métricas.

        Combina:
        - ratio: Similitud general (Levenshtein normalizado)
        - token_sort_ratio: Similitud con tokens ordenados
        - token_set_ratio: Similitud con conjuntos de tokens
        - partial_ratio: Similitud parcial

        Retorna el máximo ponderado de todas las métricas.

        Args:
            query: Cadena de consulta normalizada.
            target: Cadena objetivo normalizada.

        Returns:
            float: Puntuación de similitud entre 0.0 y 1.0.
        """
        if not query or not target:
            return 0.0

        # Coincidencia exacta rápida
        if query == target:
            return 1.0

        # Múltiples métricas de fuzzywuzzy
        ratio = fuzz.ratio(query, target) / 100.0
        token_sort = fuzz.token_sort_ratio(query, target) / 100.0
        token_set = fuzz.token_set_ratio(query, target) / 100.0
        partial = fuzz.partial_ratio(query, target) / 100.0

        # Penalizar partial_ratio si las longitudes difieren mucho
        len_query = len(query)
        len_target = len(target)
        length_ratio = min(len_query, len_target) / max(len_query, len_target)
        if length_ratio < 0.5:
            partial *= length_ratio

        # Ponderación: token_set es la métrica más robusta para nombres
        weighted = max(
            ratio * 0.25,
            token_sort * 0.35,
            token_set * 0.30,
            partial * 0.10,
        )

        return round(weighted, 4)

    def _compute_confidence(self, score: float, match_type: MatchType) -> float:
        """
        Calcula el nivel de confianza de una coincidencia.

        La confianza difiere de la puntuación en que considera el tipo
        de coincidencia. Las coincidencias exactas y fonéticas tienen
        mayor confianza que las difusas para el mismo score.

        Args:
            score: Puntuación de similitud (0.0 a 1.0).
            match_type: Tipo de coincidencia detectada.

        Returns:
            float: Nivel de confianza entre 0.0 y 1.0.
        """
        # Multiplicadores de confianza por tipo de coincidencia
        confidence_multipliers: dict[MatchType, float] = {
            MatchType.EXACT: 1.0,
            MatchType.PHONETIC: 0.90,
            MatchType.ALIAS: 0.85,
            MatchType.FUZZY: 0.80,
        }

        multiplier = confidence_multipliers.get(match_type, 0.80)
        return round(score * multiplier, 4)

    def _match_reversed(self, query: str, target: str) -> float:
        """
        Compara nombres con inversión de nombre/apellido.

        En español es común que los nombres se registren en diferente
        orden (nombre primero vs. apellido primero). Este método
        intenta la comparación con el orden invertido.

        Args:
            query: Nombre de consulta normalizado.
            target: Nombre objetivo normalizado.

        Returns:
            float: Mejor puntuación con inversión.
        """
        query_parts = query.split()
        target_parts = target.split()

        if len(query_parts) < 2 or len(target_parts) < 2:
            return 0.0

        # Invertir las partes del query
        reversed_query = " ".join(reversed(query_parts))
        reversed_score = self._compute_fuzzy_score(reversed_query, target)

        return reversed_score

    def _match_partial(self, query: str, target: str) -> float:
        """
        Compara nombres parciales y con iniciales.

        Maneja casos como:
        - "J PEREZ" coincide con "JUAN PEREZ"
        - "JOSE M" coincide con "JOSE MANUEL GARCIA"
        - "PEREZ" coincide con "JUAN PEREZ LOPEZ"

        Args:
            query: Nombre de consulta normalizado.
            target: Nombre objetivo normalizado.

        Returns:
            float: Puntuación de similitud parcial.
        """
        query_parts = query.split()
        target_parts = target.split()

        if not query_parts or not target_parts:
            return 0.0

        # Verificar si alguna parte del query es una inicial
        has_initial = any(
            len(part) == 1 and part.isalpha()
            for part in query_parts
        )

        if not has_initial:
            # Comparación de subconjunto: ¿el query está contenido en el target?
            if set(query_parts).issubset(set(target_parts)):
                coverage = len(query_parts) / len(target_parts)
                return round(max(coverage, 0.7), 4)

            # Verificar si el query es un apellido contenido en el target
            for part in query_parts:
                if len(part) > 2 and part in target_parts:
                    coverage = len(part) / max(len(query), len(target))
                    return round(max(coverage, 0.6), 4)

            return 0.0

        # Expandir iniciales del query y comparar contra el target
        match_count = 0
        total_parts = len(query_parts)

        for q_part in query_parts:
            if len(q_part) == 1:
                # Es una inicial: verificar si alguna parte del target comienza con ella
                if any(t_part.startswith(q_part) for t_part in target_parts):
                    match_count += 1
            else:
                # Es una palabra completa: verificar coincidencia exacta o difusa
                for t_part in target_parts:
                    if t_part == q_part or fuzz.ratio(q_part, t_part) / 100.0 >= 0.85:
                        match_count += 1
                        break

        if match_count == 0:
            return 0.0

        partial_score = match_count / total_parts
        # Reducir confianza si solo hay coincidencias parciales
        return round(partial_score * 0.85, 4)

    def _upsert_result(
        self,
        results: dict[str, MatchResult],
        target: str,
        new_result: MatchResult,
    ) -> None:
        """
        Inserta o actualiza un resultado, conservando siempre el mejor.

        Si ya existe un resultado para el mismo target, conserva el
        que tenga mayor score.

        Args:
            results: Diccionario de resultados acumulados.
            target: Clave del objetivo.
            new_result: Nuevo resultado a insertar/considerar.
        """
        existing = results.get(target)
        if existing is None or new_result.score > existing.score:
            results[target] = new_result

    # ── Métodos de utilidad ─────────────────────────────────────────────

    def generate_name_variants(self, name: str) -> list[str]:
        """
        Genera variantes de un nombre para búsqueda exhaustiva.

        Incluye:
        - Nombre completo normalizado
        - Nombre sin partículas
        - Inversión apellido/nombre
        - Iniciales
        - Variante fonética
        - Nombres parciales (solo apellidos)

        Args:
            name: Nombre completo.

        Returns:
            Lista de variantes del nombre sin duplicados.
        """
        if not name:
            return []

        variants: set[str] = set()

        # Nombre normalizado completo
        full = normalize_for_comparison(name)
        if full:
            variants.add(full)

        # Nombre sin partículas
        no_particles = self.normalize_entity(name)
        if no_particles:
            variants.add(no_particles)

        # Inversión de nombre/apellido
        parts = full.split() if full else []
        if len(parts) >= 2:
            reversed_name = " ".join(reversed(parts))
            variants.add(reversed_name)

        # Solo apellidos (últimas dos palabras)
        if len(parts) >= 3:
            surnames = " ".join(parts[-2:])
            variants.add(surnames)

        # Solo primer apellido
        if len(parts) >= 2:
            variants.add(parts[-2])

        # Iniciales
        from app.utils.text_normalizer import extract_initials

        initials = extract_initials(name)
        if initials and len(initials) >= 2:
            variants.add(initials)

        # Código fonético
        phonetic = phonetic_encode(name)
        if phonetic and phonetic != "0000":
            variants.add(f"PHON:{phonetic}")

        return list(variants)

    def is_significant_match(
        self,
        result: MatchResult,
        *,
        strict: bool = False,
    ) -> bool:
        """
        Determina si un resultado de comparación es significativo.

        Un resultado significativo es aquel que merece ser reportado
        como una coincidencia potencial en el proceso de screening.

        Args:
            result: Resultado a evaluar.
            strict: Si True, aplica criterios más estrictos.

        Returns:
            bool: True si el resultado es significativo.
        """
        if strict:
            min_score = 0.90
            min_confidence = 0.85
        else:
            min_score = 0.80
            min_confidence = 0.70

        return result.score >= min_score and result.confidence >= min_confidence
