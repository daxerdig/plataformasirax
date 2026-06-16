"""
Configuración de fixtures para las pruebas de SynkData.

Provee fixtures compartidas para:
- Cliente de pruebas asíncrono (httpx AsyncClient)
- Mock de Redis
- Mock de Neo4j
- Mock de httpx
- Base de datos de prueba (SQLite en memoria)
- Datos de prueba (CURP, RFC, etc.)

Las fixtures están diseñadas para ser reutilizadas en todos los
módulos de prueba de la plataforma.
"""

from __future__ import annotations

import asyncio
from datetime import date, datetime, timezone
from typing import Any, AsyncGenerator, Dict, List, Optional
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient, Response as HttpxResponse

# ---------------------------------------------------------------------------
# Configuración de event loop
# ---------------------------------------------------------------------------
@pytest.fixture(scope="session")
def event_loop():
    """Crea un event loop para la sesión de pruebas."""
    policy = asyncio.get_event_loop_policy()
    loop = policy.new_event_loop()
    yield loop
    loop.close()


# ---------------------------------------------------------------------------
# Mock de Redis
# ---------------------------------------------------------------------------
@pytest_asyncio.fixture
async def mock_redis() -> AsyncMock:
    """
    Fixture que provee un mock del cliente Redis asíncrono.

    Simula las operaciones básicas de Redis:
    - get/set/delete
    - incr/expire
    - pipeline
    - ping
    - setex

    Returns:
        AsyncMock: Mock del cliente Redis.
    """
    redis = AsyncMock()
    redis._data: Dict[str, Any] = {}

    async def _get(key: str) -> Optional[str]:
        return redis._data.get(key)

    async def _set(key: str, value: str, **kwargs) -> bool:
        redis._data[key] = value
        return True

    async def _delete(*keys: str) -> int:
        deleted = 0
        for key in keys:
            if key in redis._data:
                del redis._data[key]
                deleted += 1
        return deleted

    async def _incr(key: str) -> int:
        current = int(redis._data.get(key, 0))
        current += 1
        redis._data[key] = str(current)
        return current

    async def _expire(key: str, seconds: int) -> bool:
        return key in redis._data

    async def _ttl(key: str) -> int:
        return 60 if key in redis._data else -2

    async def _setex(key: str, seconds: int, value: str) -> bool:
        redis._data[key] = value
        return True

    async def _ping() -> bool:
        return True

    async def _aclose() -> None:
        pass

    redis.get = AsyncMock(side_effect=_get)
    redis.set = AsyncMock(side_effect=_set)
    redis.delete = AsyncMock(side_effect=_delete)
    redis.incr = AsyncMock(side_effect=_incr)
    redis.expire = AsyncMock(side_effect=_expire)
    redis.ttl = AsyncMock(side_effect=_ttl)
    redis.setex = AsyncMock(side_effect=_setex)
    redis.ping = AsyncMock(side_effect=_ping)
    redis.aclose = AsyncMock(side_effect=_aclose)

    # Pipeline mock
    pipeline_mock = AsyncMock()
    pipeline_mock.incr = MagicMock(return_value=None)
    pipeline_mock.ttl = MagicMock(return_value=None)
    pipeline_mock.expire = AsyncMock(return_value=None)
    pipeline_mock.execute = AsyncMock(return_value=[1, -1])

    async def _pipeline():
        return pipeline_mock

    redis.pipeline = MagicMock(side_effect=_pipeline)

    return redis


# ---------------------------------------------------------------------------
# Mock de Neo4j
# ---------------------------------------------------------------------------
@pytest_asyncio.fixture
async def mock_neo4j() -> AsyncMock:
    """
    Fixture que provee un mock de la sesión de Neo4j.

    Simula las operaciones básicas de Neo4j:
    - run (ejecución de consultas Cypher)
    - close

    Returns:
        AsyncMock: Mock de la sesión de Neo4j.
    """
    session = AsyncMock()

    # Resultado de consulta vacío por defecto
    result_mock = AsyncMock()
    result_mock.data = AsyncMock(return_value=[])
    result_mock.single = AsyncMock(return_value=None)
    result_mock.consume = AsyncMock()

    session.run = AsyncMock(return_value=result_mock)
    session.close = AsyncMock()

    # Driver mock
    driver = AsyncMock()
    driver.session = MagicMock(return_value=session)
    driver.close = AsyncMock()

    return driver


# ---------------------------------------------------------------------------
# Mock de httpx (para clientes HTTP externos)
# ---------------------------------------------------------------------------
@pytest.fixture
def mock_httpx_client() -> AsyncMock:
    """
    Fixture que provee un mock del cliente httpx asíncrono.

    Simula las respuestas de APIs externas (RENAPO, SAT, OFAC, etc.).

    Returns:
        AsyncMock: Mock del cliente httpx.
    """
    client = AsyncMock()

    # Respuesta por defecto (200 OK, JSON vacío)
    default_response = MagicMock(spec=HttpxResponse)
    default_response.status_code = 200
    default_response.json = MagicMock(return_value={})
    default_response.text = "{}"
    default_response.raise_for_status = MagicMock()

    client.get = AsyncMock(return_value=default_response)
    client.post = AsyncMock(return_value=default_response)
    client.aclose = AsyncMock()

    return client


# ---------------------------------------------------------------------------
# Base de datos de prueba (SQLite en memoria)
# ---------------------------------------------------------------------------
@pytest_asyncio.fixture
async def test_db_engine():
    """
    Fixture que provee un motor SQLAlchemy asíncrono con SQLite en memoria.

    Crea todas las tablas definidas en los modelos y las destruye
    al finalizar la prueba.

    Returns:
        AsyncEngine: Motor asíncrono de SQLAlchemy.
    """
    from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, create_async_engine
    from sqlalchemy import text

    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        echo=False,
    )

    # Importar Base para crear las tablas
    from app.models.base import Base

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    yield engine

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)

    await engine.dispose()


@pytest_asyncio.fixture
async def test_db_session(test_db_engine) -> AsyncGenerator:
    """
    Fixture que provee una sesión de base de datos de prueba.

    Usa el motor SQLite en memoria y proporciona una sesión
    con rollback automático al finalizar cada prueba.

    Returns:
        AsyncSession: Sesión asíncrona de SQLAlchemy.
    """
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

    session_factory = async_sessionmaker(
        bind=test_db_engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )

    async with session_factory() as session:
        yield session
        await session.rollback()


# ---------------------------------------------------------------------------
# Cliente de pruebas asíncrono
# ---------------------------------------------------------------------------
@pytest_asyncio.fixture
async def async_client(mock_redis) -> AsyncGenerator[AsyncClient, None]:
    """
    Fixture que provee un cliente HTTP asíncrono para pruebas.

    Crea una instancia de la aplicación FastAPI con dependencias
    mockeadas (Redis, base de datos) y retorna un AsyncClient
    para realizar peticiones de prueba.

    Returns:
        AsyncClient: Cliente HTTP asíncrono configurado.
    """
    with patch("app.database.get_redis", return_value=mock_redis):
        from app.main import create_app

        app = create_app()

        transport = ASGITransport(app=app)
        async with AsyncClient(
            transport=transport,
            base_url="http://testserver",
        ) as client:
            yield client


# ---------------------------------------------------------------------------
# Datos de prueba — CURP
# ---------------------------------------------------------------------------
@pytest.fixture
def sample_curp_valid() -> str:
    """CURP válida para pruebas (persona física, CDMX, 1985)."""
    return "GOME850101HDFRRN09"


@pytest.fixture
def sample_curp_info() -> Dict[str, Any]:
    """Datos esperados al extraer información de la CURP de prueba."""
    return {
        "curp": "GOME850101HDFRRN09",
        "name_initials": "GOME",
        "gender": "H",
        "state_code": "DF",
        "state_name": "Ciudad de México",
        "internal_consonants": "RRN",
        "century_digit": "0",
        "check_digit": "9",
        "birth_year": 1985,
    }


@pytest.fixture
def sample_curp_invalid() -> str:
    """CURP inválida para pruebas (formato incorrecto)."""
    return "12345ABCDEF"


@pytest.fixture
def all_state_codes() -> Dict[str, str]:
    """
    Catálogo completo de las 32 entidades federativas + Nacido en el Extranjero.

    Returns:
        dict: Mapeo de códigos de estado a nombres.
    """
    from app.utils.curp_algorithm import STATE_CODES

    return STATE_CODES


# ---------------------------------------------------------------------------
# Datos de prueba — RFC
# ---------------------------------------------------------------------------
@pytest.fixture
def sample_rfc_fisica_valid() -> str:
    """RFC válido de persona física para pruebas."""
    return "GOME850101ABC"


@pytest.fixture
def sample_rfc_moral_valid() -> str:
    """RFC válido de persona moral para pruebas."""
    return "ABC850101XYZ"


@pytest.fixture
def sample_rfc_invalid() -> str:
    """RFC inválido para pruebas (formato incorrecto)."""
    return "12345"


@pytest.fixture
def sample_rfc_info_fisica() -> Dict[str, Any]:
    """Datos esperados al extraer información del RFC física de prueba."""
    return {
        "rfc": "GOME850101ABC",
        "person_type": "fisica",
        "name_initials": "GOME",
        "homoclave": "ABC",
        "birth_year": 1985,
    }


# ---------------------------------------------------------------------------
# Datos de prueba — Screening
# ---------------------------------------------------------------------------
@pytest.fixture
def sample_screening_match() -> Dict[str, Any]:
    """Coincidencia de screening de ejemplo."""
    return {
        "source": "ofac",
        "score": 0.95,
        "match_type": "fuzzy",
        "entity_name": "JUAN GOMEZ RODRIGUEZ",
        "entity_data": {
            "list": "SDN",
            "program": "SDGT",
            "country": "MX",
        },
        "is_confirmed": False,
    }


@pytest.fixture
def sample_pep_data() -> Dict[str, Any]:
    """Datos de ejemplo de una Persona Políticamente Expuesta."""
    return {
        "is_pep": True,
        "positions": ["Senador de la República"],
        "country": "MX",
        "level": "national",
        "source": "PEP_DB",
    }


# ---------------------------------------------------------------------------
# Datos de prueba — Riesgo
# ---------------------------------------------------------------------------
@pytest.fixture
def sample_risk_context_clean() -> Dict[str, Any]:
    """Contexto de riesgo sin señales negativas (identidad limpia)."""
    from app.schemas.identity import RiskContext

    return RiskContext(
        ofac_match=False,
        open_sanctions_match=False,
        un_match=False,
        interpol_match=False,
        rnd_positive=False,
        sat_69b_listed=False,
        identity_inconsistent=False,
        multiple_identities=False,
        email_disposable=False,
        no_digital_presence=False,
        phone_voip_suspicious=False,
        correlation_confidence=85.0,
    )


@pytest.fixture
def sample_risk_context_critical() -> Dict[str, Any]:
    """Contexto de riesgo con coincidencia crítica (OFAC)."""
    from app.schemas.identity import RiskContext

    return RiskContext(
        ofac_match=True,
        open_sanctions_match=False,
        un_match=False,
        interpol_match=False,
        rnd_positive=False,
        sat_69b_listed=False,
        identity_inconsistent=False,
        multiple_identities=False,
        email_disposable=False,
        no_digital_presence=False,
        phone_voip_suspicious=False,
        correlation_confidence=85.0,
    )


@pytest.fixture
def sample_risk_context_medium() -> Dict[str, Any]:
    """Contexto de riesgo con señales medias (correo desechable + sin presencia digital)."""
    from app.schemas.identity import RiskContext

    return RiskContext(
        ofac_match=False,
        open_sanctions_match=False,
        un_match=False,
        interpol_match=False,
        rnd_positive=False,
        sat_69b_listed=False,
        identity_inconsistent=False,
        multiple_identities=False,
        email_disposable=True,
        no_digital_presence=True,
        phone_voip_suspicious=True,
        correlation_confidence=45.0,
    )


# ---------------------------------------------------------------------------
# Datos de prueba — Identidad / Correlación
# ---------------------------------------------------------------------------
@pytest.fixture
def sample_identity_data_consistent() -> Dict[str, Any]:
    """Datos de identidad consistentes para pruebas de correlación."""
    from app.schemas.identity import IdentityData, SocialProfileInput

    return IdentityData(
        name="JUAN GOMEZ RODRIGUEZ",
        curp="GOME850101HDFRRN09",
        rfc="GOME850101ABC",
        email="juan.gomez@empresa.com.mx",
        phone="+525512345678",
        username="jgomez",
        company="Empresa Corporativo S.A.",
        domain="empresa.com.mx",
        social_profiles=[
            SocialProfileInput(platform="linkedin", url="https://linkedin.com/in/jgomez"),
            SocialProfileInput(platform="github", url="https://github.com/jgomez"),
        ],
    )


@pytest.fixture
def sample_identity_data_inconsistent() -> Dict[str, Any]:
    """Datos de identidad inconsistentes para pruebas de correlación."""
    from app.schemas.identity import IdentityData

    return IdentityData(
        name="MARIA LOPEZ MARTINEZ",
        curp="GOME850101HDFRRN09",  # CURP no coincide con el nombre
        rfc="LOPM850101XYZ",
        email="temp@guerrillamail.com",  # Dominio desechable
        phone="5551234567",  # Sin código de país
        username="randomuser42",
    )


@pytest.fixture
def sample_trust_context() -> Dict[str, Any]:
    """Contexto de trust score para pruebas."""
    from app.schemas.identity import TrustContext

    return TrustContext(
        renapo_valid=True,
        rfc_valid=True,
        sat_active=True,
        screening_clean=True,
        professional_presence=True,
        github_active=True,
        linkedin_found=True,
        email_verifiable=True,
        phone_valid=True,
        verification_details={},
    )
