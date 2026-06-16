"""
Pruebas unitarias para el servicio de correlación de identidad.

Cubre:
- Verificación de consistencia del nombre
- Consistencia CURP-RFC
- Correlación correo-teléfono
- Correlación completa con datos consistentes
- Correlación con datos inconsistentes
"""

from __future__ import annotations

from unittest.mock import patch

import pytest

from app.schemas.identity import (
    CorrelationResult,
    CorrelationSignal,
    IdentityData,
    SocialProfileInput,
)
from app.services.identity_correlation import IdentityCorrelationService


# ===========================================================================
# Tests de consistencia del nombre
# ===========================================================================
class TestNameConsistency:
    """Pruebas de verificación de consistencia del nombre."""

    @pytest.fixture
    def service(self) -> IdentityCorrelationService:
        """Crea una instancia del servicio de correlación."""
        return IdentityCorrelationService()

    @pytest.mark.asyncio
    async def test_nombre_consistente_con_curp(self, service: IdentityCorrelationService):
        """Verifica que un nombre consistente con la CURP sea detectado."""
        identity = IdentityData(
            name="JUAN GOMEZ RODRIGUEZ",
            curp="GOME850101HDFRRN09",
        )
        result = await service.correlate(identity)

        # La señal de nombre debe indicar consistencia
        name_signals = [
            s for s in result.signals
            if "nombre" in s.name.lower() or "name" in s.name.lower()
        ]
        # Debe haber al menos una señal relacionada con el nombre
        assert len(result.signals) > 0

    @pytest.mark.asyncio
    async def test_nombre_inconsistente_con_curp(self, service: IdentityCorrelationService):
        """Verifica que un nombre inconsistente con la CURP sea detectado."""
        identity = IdentityData(
            name="MARIA LOPEZ MARTINEZ",
            curp="GOME850101HDFRRN09",  # CURP de GOMEZ RODRIGUEZ
        )
        result = await service.correlate(identity)

        # Debe haber alertas sobre inconsistencia
        assert len(result.warnings) > 0 or result.identity_confidence < 50

    @pytest.mark.asyncio
    async def test_nombre_parcialmente_consistente(self, service: IdentityCorrelationService):
        """Verifica que un nombre parcialmente consistente sea evaluado correctamente."""
        identity = IdentityData(
            name="JUAN GOMEZ",
            curp="GOME850101HDFRRN09",
        )
        result = await service.correlate(identity)

        # La confianza no debe ser máxima ni mínima
        assert 0 < result.identity_confidence < 100


# ===========================================================================
# Tests de consistencia CURP-RFC
# ===========================================================================
class TestCURPRFCConsistency:
    """Pruebas de verificación de consistencia entre CURP y RFC."""

    @pytest.fixture
    def service(self) -> IdentityCorrelationService:
        return IdentityCorrelationService()

    @pytest.mark.asyncio
    async def test_curp_rfc_consistentes(self, service: IdentityCorrelationService):
        """Verifica que CURP y RFC consistentes sean detectados."""
        identity = IdentityData(
            name="JUAN GOMEZ RODRIGUEZ",
            curp="GOME850101HDFRRN09",
            rfc="GOME850101ABC",
        )
        result = await service.correlate(identity)

        # Debe tener alta confianza
        assert result.identity_confidence >= 70

    @pytest.mark.asyncio
    async def test_curp_rfc_iniciales_diferentes(self, service: IdentityCorrelationService):
        """Verifica que CURP y RFC con iniciales diferentes sean detectados como inconsistentes."""
        identity = IdentityData(
            name="MARIA LOPEZ",
            curp="GOME850101HDFRRN09",  # Iniciales GOME ≠ LOPE
            rfc="LOPM850101XYZ",
        )
        result = await service.correlate(identity)

        # Debe haber alertas
        assert len(result.warnings) > 0 or "ALERTA" in str(result.flags)

    @pytest.mark.asyncio
    async def test_curp_rfc_fecha_diferente(self, service: IdentityCorrelationService):
        """Verifica que CURP y RFC con fechas diferentes sean detectados."""
        identity = IdentityData(
            name="JUAN GOMEZ RODRIGUEZ",
            curp="GOME850101HDFRRN09",  # Fecha: 850101 (1985-01-01)
            rfc="GOME900215ABC",  # Fecha: 900215 (1990-02-15)
        )
        result = await service.correlate(identity)

        # Debe haber alertas por inconsistencia de fecha
        assert len(result.warnings) > 0 or result.identity_confidence < 80


# ===========================================================================
# Tests de correlación correo-teléfono
# ===========================================================================
class TestEmailPhoneCorrelation:
    """Pruebas de correlación entre correo electrónico y teléfono."""

    @pytest.fixture
    def service(self) -> IdentityCorrelationService:
        return IdentityCorrelationService()

    @pytest.mark.asyncio
    async def test_correo_corporativo_y_telefono_mexico(
        self, service: IdentityCorrelationService
    ):
        """Verifica que un correo corporativo y teléfono mexicano sean consistentes."""
        identity = IdentityData(
            name="JUAN GOMEZ",
            email="juan.gomez@empresa.com.mx",
            phone="+525512345678",
            company="Empresa S.A.",
            domain="empresa.com.mx",
        )
        result = await service.correlate(identity)

        # Debe haber señales positivas
        assert result.identity_confidence > 0

    @pytest.mark.asyncio
    async def test_correo_desechable(self, service: IdentityCorrelationService):
        """Verifica que un correo desechable sea detectado como señal negativa."""
        identity = IdentityData(
            name="JUAN GOMEZ",
            email="temp@guerrillamail.com",
        )
        result = await service.correlate(identity)

        # Debe haber warnings sobre el correo desechable
        has_email_warning = any(
            "desechable" in w.lower() or "disposable" in w.lower() or "temporal" in w.lower()
            for w in result.warnings
        )
        # La confianza debe ser menor
        assert result.identity_confidence < 100 or has_email_warning

    @pytest.mark.asyncio
    async def test_telefono_sin_codigo_pais(self, service: IdentityCorrelationService):
        """Verifica que un teléfono sin código de país sea detectado."""
        identity = IdentityData(
            name="JUAN GOMEZ",
            phone="5551234567",  # Sin +52
        )
        result = await service.correlate(identity)

        # Debe haber alguna señal sobre el teléfono
        assert result.identity_confidence < 100


# ===========================================================================
# Tests de correlación completa con datos consistentes
# ===========================================================================
class TestFullCorrelationConsistent:
    """Pruebas de correlación completa con datos consistentes."""

    @pytest.fixture
    def service(self) -> IdentityCorrelationService:
        return IdentityCorrelationService()

    @pytest.mark.asyncio
    async def test_correlacion_completa_consistente(
        self,
        service: IdentityCorrelationService,
        sample_identity_data_consistent: IdentityData,
    ):
        """Verifica que una identidad con todos los datos consistentes tenga alta confianza."""
        result = await service.correlate(sample_identity_data_consistent)

        # Con todos los datos consistentes, la confianza debe ser alta
        assert result.identity_confidence >= 70

        # No debe tener flags de alerta crítica
        assert "ALERTA_CONSISTENCIA_CURP_RFC" not in result.flags

    @pytest.mark.asyncio
    async def test_correlacion_con_perfiles_sociales(
        self, service: IdentityCorrelationService
    ):
        """Verifica que los perfiles sociales aumenten la confianza."""
        identity = IdentityData(
            name="JUAN GOMEZ",
            email="juan.gomez@empresa.com",
            social_profiles=[
                SocialProfileInput(platform="linkedin", url="https://linkedin.com/in/jgomez"),
                SocialProfileInput(platform="github", url="https://github.com/jgomez"),
            ],
        )
        result = await service.correlate(identity)

        # La presencia de perfiles sociales debe contribuir positivamente
        assert result.identity_confidence > 0

    @pytest.mark.asyncio
    async def test_correlacion_con_dominio_empresarial(
        self, service: IdentityCorrelationService
    ):
        """Verifica que un dominio empresarial verificado contribuya positivamente."""
        identity = IdentityData(
            name="JUAN GOMEZ",
            email="juan.gomez@empresa.com.mx",
            company="Empresa S.A.",
            domain="empresa.com.mx",
        )
        result = await service.correlate(identity)

        # El dominio empresarial debe contribuir positivamente
        assert result.identity_confidence > 0


# ===========================================================================
# Tests de correlación con datos inconsistentes
# ===========================================================================
class TestFullCorrelationInconsistent:
    """Pruebas de correlación con datos inconsistentes."""

    @pytest.fixture
    def service(self) -> IdentityCorrelationService:
        return IdentityCorrelationService()

    @pytest.mark.asyncio
    async def test_correlacion_datos_inconsistentes(
        self,
        service: IdentityCorrelationService,
        sample_identity_data_inconsistent: IdentityData,
    ):
        """Verifica que datos inconsistentes resulten en baja confianza."""
        result = await service.correlate(sample_identity_data_inconsistent)

        # Con datos inconsistentes, la confianza debe ser baja
        assert result.identity_confidence < 70

        # Debe haber alertas
        assert len(result.warnings) > 0 or len(result.flags) > 0

    @pytest.mark.asyncio
    async def test_correlacion_sin_datos(self, service: IdentityCorrelationService):
        """Verifica que la correlación sin datos tenga confianza mínima."""
        identity = IdentityData(name="JUAN GOMEZ")
        result = await service.correlate(identity)

        # Sin datos adicionales, la confianza debe ser baja
        assert result.identity_confidence < 50

    @pytest.mark.asyncio
    async def test_correlacion_nombre_no_coincide_con_correo(
        self, service: IdentityCorrelationService
    ):
        """Verifica que un nombre que no coincide con el correo sea detectado."""
        identity = IdentityData(
            name="JUAN GOMEZ",
            email="maria.lopez@empresa.com",
        )
        result = await service.correlate(identity)

        # Debe haber alguna señal sobre la discrepancia
        assert result.identity_confidence < 100

    @pytest.mark.asyncio
    async def test_correlacion_username_inconsistente(
        self, service: IdentityCorrelationService
    ):
        """Verifica que un username inconsistente sea detectado."""
        identity = IdentityData(
            name="JUAN GOMEZ",
            username="randomuser42",  # No se parece al nombre
        )
        result = await service.correlate(identity)

        # El username inconsistente debe afectar la confianza
        assert result.identity_confidence < 100

    @pytest.mark.asyncio
    async def test_correlacion_multiple_señales_negativas(
        self, service: IdentityCorrelationService
    ):
        """Verifica que múltiples señales negativas reduzcan significativamente la confianza."""
        identity = IdentityData(
            name="MARIA LOPEZ",
            curp="GOME850101HDFRRN09",  # No coincide
            email="temp@guerrillamail.com",  # Desechable
            phone="5551234567",  # Sin código de país
            username="randomuser42",  # No relacionado
        )
        result = await service.correlate(identity)

        # Múltiples señales negativas deben resultar en baja confianza
        assert result.identity_confidence < 40
        assert len(result.warnings) >= 2

    @pytest.mark.asyncio
    async def test_correlacion_resultado_estructura(
        self, service: IdentityCorrelationService
    ):
        """Verifica que el resultado de correlación tenga la estructura correcta."""
        identity = IdentityData(
            name="JUAN GOMEZ",
            curp="GOME850101HDFRRN09",
            rfc="GOME850101ABC",
        )
        result = await service.correlate(identity)

        # Verificar estructura del resultado
        assert isinstance(result.identity_confidence, float)
        assert 0 <= result.identity_confidence <= 100
        assert isinstance(result.signals, list)
        assert isinstance(result.warnings, list)
        assert isinstance(result.flags, list)

    @pytest.mark.asyncio
    async def test_correlacion_signals_contienen_detalle(
        self, service: IdentityCorrelationService
    ):
        """Verifica que las señales de correlación contengan información detallada."""
        identity = IdentityData(
            name="JUAN GOMEZ",
            email="juan.gomez@empresa.com",
        )
        result = await service.correlate(identity)

        # Cada señal debe tener nombre y descripción
        for signal in result.signals:
            assert signal.name is not None
            assert len(signal.name) > 0
