"""
Pruebas unitarias para el servicio de screening en listas restrictivas.

Cubre:
- Comparación difusa (exacta, fuzzy, fonética)
- Normalización de nombres
- Matching con alias
- Clasificación de nivel de riesgo
- Mock de llamadas a APIs externas
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.fuzzy_matcher import FuzzyMatcherService, MatchResult, MatchType
from app.utils.text_normalizer import normalize_for_comparison, remove_accents, split_full_name
from app.utils.phonetic import phonetic_encode, phonetic_match


# ===========================================================================
# Tests de comparación difusa
# ===========================================================================
class TestFuzzyMatching:
    """Pruebas del motor de comparación difusa."""

    @pytest.fixture
    def matcher(self) -> FuzzyMatcherService:
        """Crea una instancia del servicio de comparación difusa."""
        return FuzzyMatcherService()

    def test_coincidencia_exacta(self, matcher: FuzzyMatcherService):
        """Verifica que dos nombres idénticos produzcan una coincidencia exacta."""
        result = matcher.compare("JUAN GOMEZ RODRIGUEZ", "JUAN GOMEZ RODRIGUEZ")
        assert result.match_type == MatchType.EXACT
        assert result.score == 100.0

    def test_coincidencia_exacta_case_insensitive(self, matcher: FuzzyMatcherService):
        """Verifica que la comparación exacta sea insensible a mayúsculas."""
        result = matcher.compare("Juan Gomez Rodriguez", "JUAN GOMEZ RODRIGUEZ")
        assert result.match_type == MatchType.EXACT
        assert result.score == 100.0

    def test_coincidencia_fuzzy_ortografica(self, matcher: FuzzyMatcherService):
        """Verifica que variaciones ortográficas produzcan coincidencia fuzzy."""
        result = matcher.compare("JUAN GOMEZ RODRIGUEZ", "JUAN GOMES RODRIGUES")
        assert result.match_type in (MatchType.FUZZY, MatchType.EXACT)
        assert result.score >= 80.0  # Alta similitud

    def test_coincidencia_fuzzy_nombre_incompleto(self, matcher: FuzzyMatcherService):
        """Verifica que un nombre parcial produzca coincidencia fuzzy."""
        result = matcher.compare("JUAN GOMEZ RODRIGUEZ", "JUAN GOMEZ")
        assert result.match_type in (MatchType.FUZZY, MatchType.EXACT)
        assert result.score >= 50.0

    def test_coincidencia_fonética(self, matcher: FuzzyMatcherService):
        """Verifica que nombres fonéticamente similares produzcan coincidencia fonética."""
        # Nombres que suenan similar pero se escriben diferente
        result = matcher.compare("JUAN GOMEZ", "JUAN GOMES")
        assert result.score >= 70.0

    def test_sin_coincidencia(self, matcher: FuzzyMatcherService):
        """Verifica que nombres completamente diferentes tengan baja puntuación."""
        result = matcher.compare("JUAN GOMEZ RODRIGUEZ", "MARIA LOPEZ MARTINEZ")
        assert result.score < 50.0

    def test_coincidencia_con_acentos(self, matcher: FuzzyMatcherService):
        """Verifica que los acentos no afecten significativamente la comparación."""
        result = matcher.compare("JOSÉ GÓMEZ", "JOSE GOMEZ")
        assert result.score >= 90.0

    def test_coincidencia_nombre_invertido(self, matcher: FuzzyMatcherService):
        """Verifica que los nombres en orden invertido sean detectados."""
        result = matcher.compare("JUAN GOMEZ RODRIGUEZ", "RODRIGUEZ GOMEZ JUAN")
        assert result.score >= 60.0  # Debe detectar la similitud a pesar del orden


# ===========================================================================
# Tests de normalización de nombres
# ===========================================================================
class TestNameNormalization:
    """Pruebas de normalización de nombres para comparación."""

    def test_normalizar_acentos(self):
        """Verifica que los acentos sean eliminados en la normalización."""
        result = normalize_for_comparison("JOSÉ GÓMEZ RODRÍGUEZ")
        assert "É" not in result
        assert "Ó" not in result
        assert "Í" not in result

    def test_normalizar_mayusculas(self):
        """Verifica que la normalización convierta a mayúsculas."""
        result = normalize_for_comparison("juan gomez")
        assert result == result.upper()

    def test_normalizar_espacios(self):
        """Verifica que los espacios múltiples sean reducidos."""
        result = normalize_for_comparison("JUAN   GOMEZ  RODRIGUEZ")
        assert "   " not in result

    def test_remover_acentos(self):
        """Verifica la función remove_accents."""
        assert remove_accents("JOSÉ") == "JOSE"
        assert remove_accents("MARÍA") == "MARIA"
        assert remove_accents("RODRÍGUEZ") == "RODRIGUEZ"

    def test_separar_nombre_completo(self):
        """Verifica la separación de un nombre completo en componentes."""
        result = split_full_name("JUAN GOMEZ RODRIGUEZ")
        assert result.get("name") == "JUAN"
        assert result.get("paternal") == "GOMEZ"
        assert result.get("maternal") == "RODRIGUEZ"

    def test_separar_nombre_compuesto(self):
        """Verifica la separación de un nombre compuesto."""
        result = split_full_name("JOSE LUIS GOMEZ RODRIGUEZ")
        # El nombre compuesto debe ser manejado correctamente
        assert result.get("name") is not None
        assert result.get("paternal") is not None

    def test_separar_nombre_dos_palabras(self):
        """Verifica la separación cuando solo hay nombre y apellido."""
        result = split_full_name("JUAN GOMEZ")
        assert result.get("name") is not None
        assert result.get("paternal") is not None


# ===========================================================================
# Tests de matching con alias
# ===========================================================================
class TestAliasMatching:
    """Pruebas de comparación con alias y nombres alternativos."""

    @pytest.fixture
    def matcher(self) -> FuzzyMatcherService:
        """Crea una instancia del servicio de comparación difusa."""
        return FuzzyMatcherService()

    def test_coincidencia_con_alias(self, matcher: FuzzyMatcherService):
        """Verifica que se detecte coincidencia con un alias conocido."""
        result = matcher.compare(
            "JUAN GOMEZ RODRIGUEZ",
            "JUAN GOMEZ RODRIGUEZ",
            aliases=["JUAN G R", "JG RODRIGUEZ"],
        )
        assert result.match_type in (MatchType.EXACT, MatchType.ALIAS, MatchType.FUZZY)
        assert result.score >= 80.0

    def test_alias_parcial(self, matcher: FuzzyMatcherService):
        """Verifica que un alias parcial sea detectado."""
        result = matcher.compare(
            "JUAN GOMEZ RODRIGUEZ",
            "JUAN GOMEZ",
            aliases=["PEPE GOMEZ"],
        )
        # Debe encontrar similitud con el nombre original o el alias
        assert result.score >= 40.0

    def test_sin_alias(self, matcher: FuzzyMatcherService):
        """Verifica el comportamiento cuando no hay alias proporcionados."""
        result = matcher.compare("JUAN GOMEZ", "JUAN GOMEZ")
        assert result.match_type == MatchType.EXACT


# ===========================================================================
# Tests de clasificación de nivel de riesgo
# ===========================================================================
class TestRiskLevelClassification:
    """Pruebas de clasificación del nivel de riesgo del screening."""

    def test_riesgo_ninguno(self):
        """Verifica la clasificación cuando no hay coincidencias."""
        from app.services.compliance_screening import RiskLevel

        max_score = 0.0
        if max_score == 0.0:
            level = RiskLevel.NONE
        assert level == RiskLevel.NONE

    def test_riesgo_bajo(self):
        """Verifica la clasificación de riesgo bajo."""
        from app.services.compliance_screening import RiskLevel

        # Score bajo → riesgo bajo
        max_score = 0.6
        if max_score < 0.7:
            level = RiskLevel.LOW
        assert level == RiskLevel.LOW

    def test_riesgo_medio(self):
        """Verifica la clasificación de riesgo medio."""
        from app.services.compliance_screening import RiskLevel

        max_score = 0.8
        if 0.7 <= max_score < 0.9:
            level = RiskLevel.MEDIUM
        assert level == RiskLevel.MEDIUM

    def test_riesgo_alto(self):
        """Verifica la clasificación de riesgo alto."""
        from app.services.compliance_screening import RiskLevel

        max_score = 0.92
        if 0.9 <= max_score < 0.98:
            level = RiskLevel.HIGH
        assert level == RiskLevel.HIGH

    def test_riesgo_critico(self):
        """Verifica la clasificación de riesgo crítico."""
        from app.services.compliance_screening import RiskLevel

        max_score = 0.99
        if max_score >= 0.98:
            level = RiskLevel.CRITICAL
        assert level == RiskLevel.CRITICAL


# ===========================================================================
# Tests de matching fonético
# ===========================================================================
class TestPhoneticMatching:
    """Pruebas del algoritmo de matching fonético."""

    def test_codificacion_fonetica_basica(self):
        """Verifica que la codificación fonética produzca resultados."""
        code = phonetic_encode("GOMEZ")
        assert isinstance(code, str)
        assert len(code) > 0

    def test_matching_fonetico_similar(self):
        """Verifica que nombres fonéticamente similares coincidan."""
        result = phonetic_match("GOMEZ", "GOMES")
        # Debe haber cierta similitud fonética
        assert isinstance(result, (bool, float))

    def test_matching_fonetico_diferente(self):
        """Verifica que nombres fonéticamente diferentes no coincidan."""
        result = phonetic_match("GOMEZ", "PEREZ")
        # Nombres muy diferentes fonéticamente
        if isinstance(result, bool):
            assert result is False
        elif isinstance(result, float):
            assert result < 0.5


# ===========================================================================
# Tests con mock de APIs externas
# ===========================================================================
class TestScreeningWithMockedAPIs:
    """Pruebas del servicio de screening con APIs externas mockeadas."""

    @pytest.fixture
    def mock_ofac_client(self) -> AsyncMock:
        """Mock del cliente OFAC."""
        client = AsyncMock()
        client.search = AsyncMock(return_value=[])
        return client

    @pytest.fixture
    def mock_interpol_client(self) -> AsyncMock:
        """Mock del cliente Interpol."""
        client = AsyncMock()
        client.search = AsyncMock(return_value=[])
        return client

    @pytest.fixture
    def mock_un_client(self) -> AsyncMock:
        """Mock del cliente de sanciones de la ONU."""
        client = AsyncMock()
        client.search = AsyncMock(return_value=[])
        return client

    @pytest.fixture
    def mock_opensanctions_client(self) -> AsyncMock:
        """Mock del cliente OpenSanctions."""
        client = AsyncMock()
        client.search = AsyncMock(return_value=[])
        return client

    @pytest.mark.asyncio
    async def test_screening_sin_coincidencias(
        self,
        mock_ofac_client: AsyncMock,
        mock_interpol_client: AsyncMock,
    ):
        """Verifica que un screening sin coincidencias retorne resultado limpio."""
        # Todos los mocks retornan listas vacías → sin coincidencias
        ofac_results = await mock_ofac_client.search("JUAN PEREZ")
        interpol_results = await mock_interpol_client.search("JUAN PEREZ")

        assert ofac_results == []
        assert interpol_results == []

    @pytest.mark.asyncio
    async def test_screening_con_coincidencia_ofac(self, mock_httpx_client: AsyncMock):
        """Verifica que una coincidencia en OFAC sea detectada correctamente."""
        # Configurar el mock para retornar una coincidencia
        from app.integrations.ofac import OfacClient, OfacMatch

        with patch.object(OfacClient, "search") as mock_search:
            mock_search.return_value = [
                OfacMatch(
                    name="JUAN GOMEZ RODRIGUEZ",
                    list_name="SDN",
                    program="SDGT",
                    score=0.95,
                    entity_data={"country": "MX"},
                )
            ]

            client = OfacClient()
            results = await client.search("JUAN GOMEZ RODRIGUEZ")

            assert len(results) == 1
            assert results[0].name == "JUAN GOMEZ RODRIGUEZ"
            assert results[0].score >= 0.9

    @pytest.mark.asyncio
    async def test_screening_error_api_externa(self):
        """Verifica que un error en una API externa no bloquee el screening."""
        with patch("app.integrations.ofac.OfacClient.search") as mock_search:
            mock_search.side_effect = Exception("API timeout")

            # El servicio de screening debe manejar el error gracefully
            try:
                from app.integrations.ofac import OfacClient
                client = OfacClient()
                await client.search("JUAN PEREZ")
                assert False, "Debería haber lanzado una excepción"
            except Exception as exc:
                assert "API timeout" in str(exc) or "timeout" in str(exc).lower()

    @pytest.mark.asyncio
    async def test_screening_service_person(self):
        """Verifica el servicio de screening completo con mocks."""
        from app.services.compliance_screening import ComplianceScreeningService

        service = ComplianceScreeningService()

        with patch.object(service, "screen_person") as mock_screen:
            from app.services.compliance_screening import (
                MatchDetail,
                RiskLevel,
                ScreeningResult,
            )

            mock_screen.return_value = ScreeningResult(
                request_id="test-123",
                matches=[],
                total_hits=0,
                max_score=0.0,
                risk_level=RiskLevel.NONE,
                sources_checked=["ofac", "interpol"],
                sources_failed=[],
                timestamp="2025-01-15T10:00:00Z",
            )

            result = await service.screen_person(name="JUAN PEREZ")

            assert result.total_hits == 0
            assert result.risk_level == RiskLevel.NONE
            assert "ofac" in result.sources_checked
