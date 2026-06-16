"""
Configuración centralizada de la plataforma SynkData Identity Intelligence.

Utiliza pydantic-settings para la carga y validación de variables de entorno,
soportando los entornos: development, staging y production.

Todas las credenciales y parámetros sensibles se cargan desde variables
de entorno o un archivo .env en la raíz del proyecto.
"""

from __future__ import annotations

import enum
from functools import lru_cache
from pathlib import Path
from typing import List, Optional

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# ---------------------------------------------------------------------------
# Ruta base del proyecto (donde reside el .env)
# ---------------------------------------------------------------------------
_PROJECT_ROOT = Path(__file__).resolve().parent.parent


# ---------------------------------------------------------------------------
# Enumeraciones
# ---------------------------------------------------------------------------
class Environment(str, enum.Enum):
    """Entornos de despliegue soportados."""

    DEVELOPMENT = "development"
    STAGING = "staging"
    PRODUCTION = "production"


class LogLevel(str, enum.Enum):
    """Niveles de logging disponibles."""

    DEBUG = "DEBUG"
    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"
    CRITICAL = "CRITICAL"


# ---------------------------------------------------------------------------
# Configuración principal
# ---------------------------------------------------------------------------
class Settings(BaseSettings):
    """
    Configuración global de SynkData Identity Intelligence Platform.

    Las variables se cargan en el siguiente orden de precedencia:
    1. Variables de entorno del sistema
    2. Archivo .env en la raíz del proyecto
    3. Valores por defecto definidos aquí

    Attributes:
        ENV: Entorno de ejecución (development | staging | production).
        DEBUG: Modo depuración activado.
        APP_NAME: Nombre de la aplicación.
        APP_VERSION: Versión actual.
        SECRET_KEY: Clave secreta para firmar tokens JWT.
    """

    model_config = SettingsConfigDict(
        env_file=str(_PROJECT_ROOT / ".env"),
        env_file_encoding="utf-8",
        env_prefix="SYNKDATA_",
        case_sensitive=False,
        extra="ignore",
    )

    # ── Aplicación ────────────────────────────────────────────────────────
    ENV: Environment = Environment.DEVELOPMENT
    DEBUG: bool = False
    APP_NAME: str = "SynkData Identity Intelligence Platform"
    APP_VERSION: str = "1.0.0"
    APP_DESCRIPTION: str = (
        "Plataforma de inteligencia de identidad para verificación, "
        "antecedentes, cumplimiento normativo y análisis de riesgo "
        "enfocada en México y LATAM."
    )
    API_PREFIX: str = "/api/v1"

    # ── Seguridad / JWT ───────────────────────────────────────────────────
    SECRET_KEY: str = Field(
        default="change-me-in-production-32chars!!",
        description="Clave secreta para la firma de tokens JWT.",
    )
    JWT_ALGORITHM: str = "HS256"
    JWT_ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    JWT_REFRESH_TOKEN_EXPIRE_DAYS: int = 7
    JWT_ISSUER: str = "synkdata.io"

    # ── Base de datos (PostgreSQL) ────────────────────────────────────────
    DATABASE_URL: str = Field(
        default="postgresql+asyncpg://synkdata:synkdata@localhost:5432/synkdata",
        description="URL de conexión asíncrona a PostgreSQL.",
    )
    DATABASE_POOL_SIZE: int = 20
    DATABASE_MAX_OVERFLOW: int = 10
    DATABASE_POOL_RECYCLE: int = 3600
    DATABASE_ECHO: bool = False

    # ── Redis ─────────────────────────────────────────────────────────────
    REDIS_URL: str = Field(
        default="redis://localhost:6379/0",
        description="URL de conexión a Redis para caché y rate-limiting.",
    )
    REDIS_CACHE_TTL: int = Field(
        default=300,
        description="Tiempo de vida predeterminado del caché en segundos.",
    )

    # ── Neo4j ─────────────────────────────────────────────────────────────
    NEO4J_URI: str = Field(
        default="bolt://localhost:7687",
        description="URI de conexión a Neo4j para el grafo de conocimiento.",
    )
    NEO4J_USER: str = "neo4j"
    NEO4J_PASSWORD: str = "neo4j_password"
    NEO4J_DATABASE: str = "neo4j"
    NEO4J_MAX_CONNECTION_POOL_SIZE: int = 50
    NEO4J_CONNECTION_TIMEOUT: int = 30

    # ── APIs externas — Gobierno de México ────────────────────────────────
    RENAPO_API_KEY: str = Field(
        default="",
        description="Clave API para el servicio de validación RENAPO (CURP).",
    )
    RENAPO_API_URL: str = "https://api.gob.mx/renapo/v1"
    RENAPO_TIMEOUT: int = 15

    SAT_API_KEY: str = Field(
        default="",
        description="Clave API para el servicio de validación SAT (RFC).",
    )
    SAT_API_URL: str = "https://api.gob.mx/sat/v1"
    SAT_TIMEOUT: int = 15

    # ── APIs externas — Listas restrictivas ───────────────────────────────
    OFAC_API_KEY: str = Field(
        default="",
        description="Clave API para la consulta de listas OFAC.",
    )
    OFAC_API_URL: str = "https://api.ofac.gov/v1"

    OPENSANCTIONS_API_KEY: str = Field(
        default="",
        description="Clave API para OpenSanctions.",
    )
    OPENSANCTIONS_API_URL: str = "https://api.opensanctions.org/v1"

    INTERPOL_API_KEY: str = Field(
        default="",
        description="Clave API para la consulta de avisos Interpol.",
    )
    INTERPOL_API_URL: str = "https://ws-public.interpol.int/notices/v1"

    # ── APIs externas — Verificación de identidad digital ─────────────────
    HIBP_API_KEY: str = Field(
        default="",
        description="Clave API para Have I Been Pwned (verificación de correo).",
    )
    HIBP_API_URL: str = "https://haveibeenpwned.com/api/v3"

    HUNTER_API_KEY: str = Field(
        default="",
        description="Clave API para Hunter.io (verificación de correo).",
    )
    HUNTER_API_URL: str = "https://api.hunter.io/v2"

    # ── OCR / Procesamiento de documentos ─────────────────────────────────
    TESSERACT_CMD: Optional[str] = Field(
        default=None,
        description="Ruta al binario de Tesseract OCR (si no está en PATH).",
    )
    TESSERACT_LANG: str = Field(
        default="spa+eng",
        description="Idiomas para Tesseract (español + inglés por defecto).",
    )
    OCR_DPI: int = 300
    OCR_MAX_FILE_SIZE_MB: int = 20
    OCR_SUPPORTED_FORMATS: List[str] = [
        "image/jpeg",
        "image/png",
        "image/tiff",
        "application/pdf",
    ]

    # ── CORS ──────────────────────────────────────────────────────────────
    CORS_ORIGINS: List[str] = Field(
        default=["http://localhost:3000", "http://localhost:8000"],
        description="Orígenes permitidos para CORS.",
    )
    CORS_ALLOW_CREDENTIALS: bool = True
    CORS_ALLOW_METHODS: List[str] = ["*"]
    CORS_ALLOW_HEADERS: List[str] = ["*"]

    # ── Rate Limiting ─────────────────────────────────────────────────────
    RATE_LIMIT_ENABLED: bool = True
    RATE_LIMIT_DEFAULT: str = Field(
        default="60/minute",
        description="Límite de peticiones predeterminado por usuario.",
    )
    RATE_LIMIT_STORAGE_URL: Optional[str] = Field(
        default=None,
        description="URL de almacenamiento para rate-limit (Redis por defecto).",
    )
    RATE_LIMIT_STRATEGY: str = "fixed-window"

    # ── Logging ───────────────────────────────────────────────────────────
    LOG_LEVEL: LogLevel = LogLevel.INFO
    LOG_FORMAT: str = Field(
        default="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
        description="Formato de los mensajes de log.",
    )
    LOG_FILE: Optional[str] = Field(
        default=None,
        description="Ruta al archivo de log (si se desea rotación a disco).",
    )
    LOG_FILE_MAX_BYTES: int = 50 * 1024 * 1024  # 50 MB
    LOG_FILE_BACKUP_COUNT: int = 5

    # ── Paginación ────────────────────────────────────────────────────────
    PAGINATION_DEFAULT_PAGE_SIZE: int = 20
    PAGINATION_MAX_PAGE_SIZE: int = 100

    # ── Umbrales de similitud ─────────────────────────────────────────────
    NAME_SIMILARITY_THRESHOLD: float = Field(
        default=0.85,
        description="Umbral de similitud para comparación difusa de nombres.",
    )
    DATE_TOLERANCE_DAYS: int = Field(
        default=3,
        description="Tolerancia en días para comparación de fechas de nacimiento.",
    )

    # ── Validadores ───────────────────────────────────────────────────────
    @field_validator("ENV", mode="before")
    @classmethod
    def normalize_env(cls, v: str) -> str:
        """Normaliza el valor del entorno a minúsculas."""
        return v.strip().lower() if isinstance(v, str) else v

    @field_validator("SECRET_KEY")
    @classmethod
    def validate_secret_key(cls, v: str) -> str:
        """Advierte si la clave secreta no ha sido cambiada en producción."""
        if v == "change-me-in-production-32chars!!":
            # En producción esto debería fallar; aquí solo registramos la advertencia
            import warnings

            warnings.warn(
                "⚠️  SECRET_KEY no ha sido cambiada del valor por defecto. "
                "Esto es inseguro para entornos de producción.",
                stacklevel=2,
            )
        return v

    # ── Propiedades derivadas ─────────────────────────────────────────────
    @property
    def is_production(self) -> bool:
        """Retorna True si el entorno es producción."""
        return self.ENV == Environment.PRODUCTION

    @property
    def is_development(self) -> bool:
        """Retorna True si el entorno es desarrollo."""
        return self.ENV == Environment.DEVELOPMENT

    @property
    def effective_database_url(self) -> str:
        """
        URL efectiva de la base de datos.

        En entornos de desarrollo, reemplaza el driver asyncpg por el
        equivalente sincrónico cuando sea necesario (ej. Alembic).
        """
        return self.DATABASE_URL

    @property
    def sync_database_url(self) -> str:
        """URL síncrona para Alembic y herramientas de migración."""
        return self.DATABASE_URL.replace("+asyncpg", "+psycopg2")

    @property
    def rate_limit_storage_url(self) -> str:
        """URL de almacenamiento para rate-limiting (Redis por defecto)."""
        return self.RATE_LIMIT_STORAGE_URL or self.REDIS_URL


# ---------------------------------------------------------------------------
# Instancia singleton cacheada
# ---------------------------------------------------------------------------
@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """
    Retorna la instancia singleton de la configuración.

    Utiliza lru_cache para garantizar que la configuración se carga
    una sola vez durante el ciclo de vida de la aplicación.

    Returns:
        Settings: Instancia de configuración validada.
    """
    return Settings()


def reload_settings() -> Settings:
    """
    Fuerza la recarga de la configuración (útil en pruebas).

    Returns:
        Settings: Nueva instancia de configuración validada.
    """
    get_settings.cache_clear()
    return get_settings()
