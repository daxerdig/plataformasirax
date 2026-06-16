"""
Esquemas Pydantic para el módulo de inteligencia digital.

Define los modelos de validación y serialización para:
- Solicitudes de análisis de correo electrónico, teléfono, usuario (entrada)
- Resultados de inteligencia digital (salida)
- Esquemas anidados: breaches, carrier, perfiles, puntuaciones

Todos los esquemas incluyen documentación en español para la
generación automática de la documentación OpenAPI.
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, EmailStr, Field, field_validator


# ---------------------------------------------------------------------------
# Enumeraciones compartidas
# ---------------------------------------------------------------------------
class LineTypeSchema(str, Enum):
    """Tipo de línea telefónica detectada."""

    MOBILE = "mobile"
    FIXED = "fixed"
    VOIP = "voip"
    TOLL_FREE = "toll_free"
    PREMIUM = "premium"
    PAGER = "pager"
    PERSONAL = "personal"
    UNKNOWN = "unknown"


class DomainReputationSchema(str, Enum):
    """Reputación del dominio de correo electrónico."""

    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    DISPOSABLE = "disposable"
    SUSPICIOUS = "suspicious"
    UNKNOWN = "unknown"


class AnalysisStatusSchema(str, Enum):
    """Estado de una solicitud de análisis de inteligencia digital."""

    PENDING = "pending"
    COMPLETED = "completed"
    FAILED = "failed"
    PARTIAL = "partial"


# ---------------------------------------------------------------------------
# Esquemas anidados — Breach (HIBP)
# ---------------------------------------------------------------------------
class BreachInfo(BaseModel):
    """
    Información de un breach/violación de datos donde aparece un correo.

    Attributes:
        name: Nombre del breach (ej. "LinkedIn", "Adobe").
        domain: Dominio del servicio comprometido.
        breach_date: Fecha de la violación de datos.
        data_classes: Tipos de datos comprometidos (ej. emails, passwords).
        pwn_count: Número total de cuentas afectadas.
        description: Descripción del breach.
        is_verified: Si el breach ha sido verificado.
    """

    name: str = Field(
        ...,
        description="Nombre del breach (ej. 'LinkedIn', 'Adobe').",
    )
    domain: str = Field(
        default="",
        description="Dominio del servicio comprometido.",
    )
    breach_date: Optional[str] = Field(
        default=None,
        description="Fecha de la violación de datos (formato ISO 8601).",
    )
    data_classes: List[str] = Field(
        default_factory=list,
        description="Tipos de datos comprometidos (ej. emails, passwords, names).",
    )
    pwn_count: int = Field(
        default=0,
        ge=0,
        description="Número total de cuentas afectadas en el breach.",
    )
    description: str = Field(
        default="",
        description="Descripción detallada del breach.",
    )
    is_verified: bool = Field(
        default=True,
        description="Si el breach ha sido verificado por HIBP.",
    )

    model_config = {"from_attributes": True}


# ---------------------------------------------------------------------------
# Esquemas anidados — Carrier
# ---------------------------------------------------------------------------
class CarrierInfo(BaseModel):
    """
    Información del operador/carrier de un número telefónico.

    Attributes:
        name: Nombre del carrier/operador.
        mcc: Mobile Country Code.
        mnc: Mobile Network Code.
        line_type: Tipo de línea (mobile, fixed, voip, etc.).
    """

    name: str = Field(
        default="",
        description="Nombre del carrier/operador telefónico.",
    )
    mcc: str = Field(
        default="",
        description="Mobile Country Code (código de país móvil).",
    )
    mnc: str = Field(
        default="",
        description="Mobile Network Code (código de red móvil).",
    )
    line_type: LineTypeSchema = Field(
        default=LineTypeSchema.UNKNOWN,
        description="Tipo de línea detectada.",
    )

    model_config = {"from_attributes": True}


# ---------------------------------------------------------------------------
# Esquemas anidados — Perfil de plataforma
# ---------------------------------------------------------------------------
class PlatformProfile(BaseModel):
    """
    Perfil de un usuario en una plataforma específica.

    Attributes:
        platform: Nombre de la plataforma (ej. GitHub, Twitter, LinkedIn).
        url: URL del perfil del usuario.
        exists: Si el perfil fue encontrado en la plataforma.
        profile_data: Datos adicionales del perfil.
        bio: Biografía/descripción del perfil.
        avatar_url: URL del avatar/foto de perfil.
        verified: Si el perfil está verificado en la plataforma.
    """

    platform: str = Field(
        ...,
        description="Nombre de la plataforma (ej. 'GitHub', 'Twitter/X', 'LinkedIn').",
    )
    url: str = Field(
        default="",
        description="URL del perfil del usuario en la plataforma.",
    )
    exists: bool = Field(
        default=False,
        description="Si el perfil fue encontrado en la plataforma.",
    )
    profile_data: Dict[str, Any] = Field(
        default_factory=dict,
        description="Datos adicionales del perfil específicos de la plataforma.",
    )
    bio: str = Field(
        default="",
        description="Biografía o descripción del perfil.",
    )
    avatar_url: str = Field(
        default="",
        description="URL del avatar o foto de perfil.",
    )
    verified: bool = Field(
        default=False,
        description="Si el perfil está verificado oficialmente en la plataforma.",
    )

    model_config = {"from_attributes": True}


# ---------------------------------------------------------------------------
# Esquemas anidados — Perfil de LinkedIn
# ---------------------------------------------------------------------------
class LinkedInProfile(BaseModel):
    """
    Perfil de LinkedIn de una persona.

    Attributes:
        name: Nombre completo.
        headline: Título/encabezado profesional.
        company: Empresa actual.
        location: Ubicación geográfica.
        connections: Número de conexiones.
        profile_url: URL del perfil de LinkedIn.
    """

    name: str = Field(
        default="",
        description="Nombre completo de la persona.",
    )
    headline: str = Field(
        default="",
        description="Título o encabezado profesional del perfil.",
    )
    company: str = Field(
        default="",
        description="Empresa actual o más reciente.",
    )
    location: str = Field(
        default="",
        description="Ubicación geográfica del perfil.",
    )
    connections: int = Field(
        default=0,
        ge=0,
        description="Número de conexiones de LinkedIn.",
    )
    profile_url: str = Field(
        default="",
        description="URL del perfil de LinkedIn.",
    )

    model_config = {"from_attributes": True}


# ---------------------------------------------------------------------------
# Esquemas anidados — Perfil de GitHub
# ---------------------------------------------------------------------------
class GitHubProfile(BaseModel):
    """
    Perfil de GitHub de un usuario.

    Attributes:
        username: Nombre de usuario en GitHub.
        name: Nombre completo.
        bio: Biografía del perfil.
        repos: Número de repositorios públicos.
        followers: Número de seguidores.
        contributions: Contribuciones en el último año.
        languages: Lenguajes de programación principales.
        profile_url: URL del perfil de GitHub.
    """

    username: str = Field(
        ...,
        description="Nombre de usuario en GitHub.",
    )
    name: str = Field(
        default="",
        description="Nombre completo del usuario.",
    )
    bio: str = Field(
        default="",
        description="Biografía del perfil de GitHub.",
    )
    repos: int = Field(
        default=0,
        ge=0,
        description="Número de repositorios públicos.",
    )
    followers: int = Field(
        default=0,
        ge=0,
        description="Número de seguidores en GitHub.",
    )
    contributions: int = Field(
        default=0,
        ge=0,
        description="Contribuciones en el último año.",
    )
    languages: List[str] = Field(
        default_factory=list,
        description="Lenguajes de programación principales del usuario.",
    )
    profile_url: str = Field(
        default="",
        description="URL del perfil de GitHub.",
    )

    model_config = {"from_attributes": True}


# ---------------------------------------------------------------------------
# Esquemas anidados — Puntuación profesional
# ---------------------------------------------------------------------------
class ProfessionalScore(BaseModel):
    """
    Puntuación profesional calculada a partir de los perfiles encontrados.

    Attributes:
        score: Puntuación global de profesionalismo (0-100).
        factors: Factores que contribuyen a la puntuación.
    """

    score: float = Field(
        default=0.0,
        ge=0.0,
        le=100.0,
        description="Puntuación global de profesionalismo (0 a 100).",
    )
    factors: Dict[str, float] = Field(
        default_factory=dict,
        description=(
            "Factores que contribuyen a la puntuación profesional. "
            "Claves: linkedin_presence, github_activity, professional_domains, "
            "social_consistency, profile_completeness."
        ),
    )

    model_config = {"from_attributes": True}


# ---------------------------------------------------------------------------
# Esquemas de entrada (request)
# ---------------------------------------------------------------------------
class EmailAnalysisRequest(BaseModel):
    """
    Solicitud de análisis de inteligencia de correo electrónico.

    Attributes:
        email: Correo electrónico a analizar.
        check_breaches: Si se debe verificar en HIBP.
        check_deliverable: Si se debe verificar la entregabilidad.
        find_related: Si se deben buscar cuentas relacionadas.
    """

    email: str = Field(
        ...,
        description="Correo electrónico a analizar.",
        examples=["usuario@ejemplo.com"],
    )
    check_breaches: bool = Field(
        default=True,
        description="Si se debe verificar el correo en Have I Been Pwned.",
    )
    check_deliverable: bool = Field(
        default=True,
        description="Si se debe verificar la entregabilidad del correo (MX + SMTP).",
    )
    find_related: bool = Field(
        default=True,
        description="Si se deben buscar cuentas relacionadas vía Hunter.io.",
    )

    @field_validator("email")
    @classmethod
    def normalize_email(cls, v: str) -> str:
        """Normaliza el correo a minúsculas y elimina espacios."""
        return v.strip().lower()


class PhoneAnalysisRequest(BaseModel):
    """
    Solicitud de análisis de inteligencia telefónica.

    Attributes:
        phone: Número telefónico a analizar.
        country: Código de país para formato (default MX).
        check_spam: Si se debe verificar si es spam.
    """

    phone: str = Field(
        ...,
        description="Número telefónico a analizar (formato E.164 o nacional).",
        examples=["+525512345678", "5512345678"],
    )
    country: str = Field(
        default="MX",
        max_length=5,
        description="Código de país ISO 3166-1 alpha-2 para validación de formato.",
        examples=["MX", "US", "ES", "CO"],
    )
    check_spam: bool = Field(
        default=True,
        description="Si se debe verificar si el número ha sido reportado como spam.",
    )

    @field_validator("phone")
    @classmethod
    def normalize_phone(cls, v: str) -> str:
        """Elimina espacios y caracteres no numéricos excepto +."""
        return v.strip()


class UsernameAnalysisRequest(BaseModel):
    """
    Solicitud de análisis de inteligencia de nombre de usuario.

    Attributes:
        username: Nombre de usuario a buscar en múltiples plataformas.
    """

    username: str = Field(
        ...,
        min_length=1,
        max_length=100,
        description="Nombre de usuario a buscar en múltiples plataformas.",
        examples=["johndoe", "juan.perez"],
    )

    @field_validator("username")
    @classmethod
    def normalize_username(cls, v: str) -> str:
        """Normaliza el nombre de usuario eliminando espacios y convirtiendo a minúsculas."""
        return v.strip().lower()


class SocialDiscoveryRequest(BaseModel):
    """
    Solicitud de descubrimiento social y profesional.

    Attributes:
        name: Nombre completo de la persona.
        email: Correo electrónico (opcional, mejora la búsqueda).
        phone: Número telefónico (opcional).
        username: Nombre de usuario (opcional).
    """

    name: str = Field(
        ...,
        min_length=2,
        max_length=500,
        description="Nombre completo de la persona para descubrimiento social.",
        examples=["Juan Pérez López"],
    )
    email: Optional[str] = Field(
        default=None,
        description="Correo electrónico (opcional, mejora la búsqueda social).",
    )
    phone: Optional[str] = Field(
        default=None,
        description="Número telefónico (opcional).",
    )
    username: Optional[str] = Field(
        default=None,
        description="Nombre de usuario (opcional, busca perfiles en plataformas).",
    )

    @field_validator("name")
    @classmethod
    def validate_name(cls, v: str) -> str:
        """Valida que el nombre no esté vacío después de normalizar."""
        if not v.strip():
            raise ValueError("El nombre no puede estar vacío.")
        return v.strip()


# ---------------------------------------------------------------------------
# Esquemas de salida (response)
# ---------------------------------------------------------------------------
class EmailIntelligenceResult(BaseModel):
    """
    Resultado completo del análisis de inteligencia de correo electrónico.

    Attributes:
        email: Correo electrónico analizado.
        is_valid_format: Si el formato del correo es válido.
        is_disposable: Si el dominio es desechable.
        has_breaches: Si el correo aparece en algún breach.
        breach_count: Número de breaches donde aparece.
        breaches: Lista de breaches encontrados.
        is_deliverable: Si el correo es entregable.
        mx_records: Registros MX del dominio.
        related_accounts: Cuentas relacionadas encontradas.
        domain_reputation: Reputación del dominio.
        risk_flags: Indicadores de riesgo identificados.
    """

    email: str = Field(..., description="Correo electrónico analizado.")
    is_valid_format: bool = Field(
        default=False,
        description="Si el formato del correo electrónico es válido.",
    )
    is_disposable: bool = Field(
        default=False,
        description="Si el dominio pertenece a un proveedor de correo desechable.",
    )
    has_breaches: bool = Field(
        default=False,
        description="Si el correo aparece en al menos un breach de datos.",
    )
    breach_count: int = Field(
        default=0,
        ge=0,
        description="Número de breaches donde aparece el correo.",
    )
    breaches: List[BreachInfo] = Field(
        default_factory=list,
        description="Lista de breaches donde aparece el correo.",
    )
    is_deliverable: Optional[bool] = Field(
        default=None,
        description="Si el correo es entregable (None = no verificado).",
    )
    mx_records: List[str] = Field(
        default_factory=list,
        description="Registros MX del dominio.",
    )
    related_accounts: List[Dict[str, Any]] = Field(
        default_factory=list,
        description="Cuentas relacionadas encontradas vía Hunter.io.",
    )
    domain_reputation: DomainReputationSchema = Field(
        default=DomainReputationSchema.UNKNOWN,
        description="Reputación del dominio.",
    )
    risk_flags: List[str] = Field(
        default_factory=list,
        description="Indicadores de riesgo identificados.",
    )

    model_config = {"from_attributes": True}


class PhoneIntelligenceResult(BaseModel):
    """
    Resultado completo del análisis de inteligencia telefónica.

    Attributes:
        phone: Número telefónico analizado.
        is_valid: Si el número es válido.
        country_code: Código de país.
        carrier: Información del carrier.
        line_type: Tipo de línea.
        is_spam: Si es spam.
        spam_reports: Número de reportes de spam.
        region: Región geográfica.
        number_type: Tipo de número.
        risk_flags: Indicadores de riesgo.
    """

    phone: str = Field(..., description="Número telefónico analizado (formato E.164).")
    is_valid: bool = Field(
        default=False,
        description="Si el número telefónico es válido.",
    )
    country_code: str = Field(
        default="",
        description="Código de país ISO 3166-1 alpha-2.",
    )
    carrier: CarrierInfo = Field(
        default_factory=CarrierInfo,
        description="Información del carrier/operador.",
    )
    line_type: LineTypeSchema = Field(
        default=LineTypeSchema.UNKNOWN,
        description="Tipo de línea telefónica.",
    )
    is_spam: bool = Field(
        default=False,
        description="Si el número ha sido reportado como spam o estafa.",
    )
    spam_reports: int = Field(
        default=0,
        ge=0,
        description="Número de reportes de spam recibidos.",
    )
    region: str = Field(
        default="",
        description="Región geográfica asociada al número.",
    )
    number_type: str = Field(
        default="",
        description="Tipo de número según clasificación de phonenumbers.",
    )
    risk_flags: List[str] = Field(
        default_factory=list,
        description="Indicadores de riesgo identificados.",
    )

    model_config = {"from_attributes": True}


class UsernameIntelligenceResult(BaseModel):
    """
    Resultado completo del análisis de inteligencia de nombre de usuario.

    Attributes:
        username: Nombre de usuario analizado.
        total_profiles: Número total de perfiles encontrados.
        platforms_found: Nombres de plataformas donde se encontró.
        profiles: Detalle de los perfiles encontrados.
        presence_score: Puntuación de presencia digital.
        categories: Categorías de actividad.
    """

    username: str = Field(..., description="Nombre de usuario analizado.")
    total_profiles: int = Field(
        default=0,
        ge=0,
        description="Número total de perfiles encontrados en todas las plataformas.",
    )
    platforms_found: List[str] = Field(
        default_factory=list,
        description="Nombres de las plataformas donde se encontró el usuario.",
    )
    profiles: List[PlatformProfile] = Field(
        default_factory=list,
        description="Detalle de los perfiles encontrados en cada plataforma.",
    )
    presence_score: float = Field(
        default=0.0,
        ge=0.0,
        le=100.0,
        description="Puntuación de presencia digital (0 a 100).",
    )
    categories: List[str] = Field(
        default_factory=list,
        description="Categorías de actividad identificadas (developer, social, professional, etc.).",
    )

    model_config = {"from_attributes": True}


class SocialDiscoveryResult(BaseModel):
    """
    Resultado completo del descubrimiento social y profesional.

    Attributes:
        profiles_found: Número total de perfiles encontrados.
        social_profiles: Lista de perfiles sociales encontrados.
        professional_score: Puntuación profesional calculada.
        digital_footprint_score: Puntuación de huella digital.
        presence_score: Puntuación de presencia digital.
        linkedin_profiles: Perfiles de LinkedIn encontrados.
        github_profile: Perfil de GitHub encontrado.
    """

    profiles_found: int = Field(
        default=0,
        ge=0,
        description="Número total de perfiles encontrados.",
    )
    social_profiles: List[PlatformProfile] = Field(
        default_factory=list,
        description="Lista de perfiles sociales encontrados.",
    )
    professional_score: ProfessionalScore = Field(
        default_factory=ProfessionalScore,
        description="Puntuación profesional calculada.",
    )
    digital_footprint_score: float = Field(
        default=0.0,
        ge=0.0,
        le=100.0,
        description="Puntuación de huella digital (0 a 100).",
    )
    presence_score: float = Field(
        default=0.0,
        ge=0.0,
        le=100.0,
        description="Puntuación de presencia digital (0 a 100).",
    )
    linkedin_profiles: List[LinkedInProfile] = Field(
        default_factory=list,
        description="Perfiles de LinkedIn encontrados.",
    )
    github_profile: Optional[GitHubProfile] = Field(
        default=None,
        description="Perfil de GitHub encontrado.",
    )

    model_config = {"from_attributes": True}
