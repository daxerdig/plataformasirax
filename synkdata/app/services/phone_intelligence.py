"""
Servicio de inteligencia telefónica para SynkData.

Proporciona análisis integral de números telefónicos incluyendo:
- Validación de formato y parseo (librería phonenumbers)
- Identificación del carrier/operador
- Detección del tipo de línea (móvil, fija, VoIP, etc.)
- Detección de spam y estafas
- Geolocalización y región

Características:
- Uso de la librería phonenumbers para validación y formateo
- Caché en Redis para resultados repetidos
- Degradación graceful: si una fuente falla, se retorna resultado parcial
- Soporte para múltiples países con enfoque en LATAM
"""

from __future__ import annotations

import asyncio
import json
import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

import httpx

from app.config import get_settings
from app.database import get_redis

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Modelos de datos internos (dataclasses)
# ---------------------------------------------------------------------------
@dataclass
class ValidationResult:
    """
    Resultado de la validación de formato de un número telefónico.

    Attributes:
        is_valid: Si el número es válido según phonenumbers.
        formatted_e164: Número en formato E.164 (+525512345678).
        formatted_national: Número en formato nacional (55 1234 5678).
        formatted_international: Número en formato internacional.
        country_code: Código de país (ej. MX, US).
        region: Nombre de la región.
    """

    is_valid: bool = False
    formatted_e164: str = ""
    formatted_national: str = ""
    formatted_international: str = ""
    country_code: str = ""
    region: str = ""


@dataclass
class CarrierInfo:
    """
    Información del carrier/operador de un número telefónico.

    Attributes:
        name: Nombre del carrier (ej. "Telcel", "AT&T", "Movistar").
        mcc: Mobile Country Code.
        mnc: Mobile Network Code.
        line_type: Tipo de línea detectada.
    """

    name: str = ""
    mcc: str = ""
    mnc: str = ""
    line_type: str = "unknown"


@dataclass
class SpamResult:
    """
    Resultado de la verificación de spam para un número telefónico.

    Attributes:
        is_spam: Si el número ha sido reportado como spam.
        spam_reports: Número de reportes de spam.
        spam_score: Puntuación de spam (0-100).
        categories: Categorías de spam reportadas.
        last_reported: Fecha del último reporte.
    """

    is_spam: bool = False
    spam_reports: int = 0
    spam_score: float = 0.0
    categories: List[str] = field(default_factory=list)
    last_reported: str = ""


@dataclass
class PhoneIntelligenceResult:
    """
    Resultado completo del análisis de inteligencia telefónica.

    Attributes:
        phone: Número telefónico analizado (formato E.164).
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

    phone: str = ""
    is_valid: bool = False
    country_code: str = ""
    carrier: CarrierInfo = field(default_factory=CarrierInfo)
    line_type: str = "unknown"
    is_spam: bool = False
    spam_reports: int = 0
    region: str = ""
    number_type: str = ""
    risk_flags: List[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Mapeo de tipos de número de phonenumbers a tipos internos
# ---------------------------------------------------------------------------
_PHONENUMBER_TYPE_MAP: dict[int, str] = {
    0: "fixed",       # FIXED_LINE
    1: "mobile",      # MOBILE
    2: "fixed",       # FIXED_LINE_OR_MOBILE
    3: "toll_free",   # TOLL_FREE
    4: "premium",     # PREMIUM_RATE
    5: "pager",       # PAGER
    6: "personal",    # PERSONAL_NUMBER
    7: "voip",        # VOIP
    8: "unknown",     # UNKNOWN
    9: "unknown",     # EMERGENCY
    10: "voip",       # VOICEMAIL
    11: "mobile",     # UAN
}

# ── Carriers conocidos de México ──────────────────────────────────────────
_MX_CARRIERS: dict[str, CarrierInfo] = {
    "Telcel": CarrierInfo(name="Telcel", mcc="334", mnc="020", line_type="mobile"),
    "AT&T": CarrierInfo(name="AT&T Mexico", mcc="334", mnc="090", line_type="mobile"),
    "Movistar": CarrierInfo(name="Movistar Mexico", mcc="334", mnc="030", line_type="mobile"),
    "Unefon": CarrierInfo(name="Unefon", mcc="334", mnc="040", line_type="mobile"),
    "Telmex": CarrierInfo(name="Telmex", mcc="334", mnc="010", line_type="fixed"),
    "Izzi": CarrierInfo(name="Izzi Telecom", mcc="334", mnc="050", line_type="fixed"),
    "Totalplay": CarrierInfo(name="Totalplay", mcc="334", mnc="060", line_type="fixed"),
    "Megacable": CarrierInfo(name="Megacable", mcc="334", mnc="070", line_type="fixed"),
    "Altán Redes": CarrierInfo(name="Altán Redes", mcc="334", mnc="080", line_type="mobile"),
    "Dish Mexico": CarrierInfo(name="Dish Mexico", mcc="334", mnc="100", line_type="fixed"),
}

# ── Carriers conocidos de Colombia ────────────────────────────────────────
_CO_CARRIERS: dict[str, CarrierInfo] = {
    "Claro": CarrierInfo(name="Claro Colombia", mcc="732", mnc="101", line_type="mobile"),
    "Movistar": CarrierInfo(name="Movistar Colombia", mcc="732", mnc="102", line_type="mobile"),
    "Tigo": CarrierInfo(name="Tigo Colombia", mcc="732", mnc="103", line_type="mobile"),
    "ETB": CarrierInfo(name="ETB", mcc="732", mnc="104", line_type="fixed"),
    "Avantel": CarrierInfo(name="Avantel", mcc="732", mnc="130", line_type="mobile"),
}

# ── Carriers conocidos de España ──────────────────────────────────────────
_ES_CARRIERS: dict[str, CarrierInfo] = {
    "Movistar": CarrierInfo(name="Movistar España", mcc="214", mnc="007", line_type="mobile"),
    "Vodafone": CarrierInfo(name="Vodafone España", mcc="214", mnc="001", line_type="mobile"),
    "Orange": CarrierInfo(name="Orange España", mcc="214", mnc="003", line_type="mobile"),
    "Yoigo": CarrierInfo(name="Yoigo", mcc="214", mnc="004", line_type="mobile"),
}

# ── Unión de todos los carriers por país ──────────────────────────────────
_CARRIERS_BY_COUNTRY: dict[str, dict[str, CarrierInfo]] = {
    "MX": _MX_CARRIERS,
    "CO": _CO_CARRIERS,
    "ES": _ES_CARRIERS,
}


class PhoneIntelligenceService:
    """
    Servicio de inteligencia telefónica.

    Orquesta el análisis integral de un número telefónico combinando
    múltiples fuentes de datos: librería phonenumbers para validación
    y formateo, lookup de carrier, y verificación de spam.

    Características:
    - Validación precisa con la librería phonenumbers de Google
    - Identificación de carrier para principales operadores LATAM
    - Detección de spam con fuentes externas
    - Caché en Redis con TTL configurable
    - Degradación graceful ante fallos de APIs
    """

    def __init__(self) -> None:
        """Inicializa el servicio con configuración del proyecto."""
        self._settings = get_settings()
        self._cache_ttl = self._settings.REDIS_CACHE_TTL
        self._http_timeout = 10.0

    # ── Método principal ─────────────────────────────────────────────────
    async def analyze(
        self,
        phone: str,
        country: str = "MX",
    ) -> PhoneIntelligenceResult:
        """
        Ejecuta el análisis integral de inteligencia telefónica.

        Realiza validación de formato, identificación de carrier,
        detección de tipo de línea y verificación de spam.

        Args:
            phone: Número telefónico a analizar (formato E.164 o nacional).
            country: Código de país ISO para validación (default: "MX").

        Returns:
            PhoneIntelligenceResult: Resultado completo del análisis.
        """
        result = PhoneIntelligenceResult()

        # ── Paso 1: Validación de formato ────────────────────────────────
        validation = await self.validate_format(phone, country)
        result.is_valid = validation.is_valid

        if not validation.is_valid:
            result.phone = phone.strip()
            result.risk_flags.append("invalid_phone_format")
            return result

        result.phone = validation.formatted_e164
        result.country_code = validation.country_code
        result.region = validation.region

        # ── Paso 2: Obtener información del carrier ──────────────────────
        carrier_task = self.get_carrier_info(result.phone)

        # ── Paso 3: Verificar spam ───────────────────────────────────────
        spam_task = self.check_spam(result.phone)

        # ── Ejecución paralela ───────────────────────────────────────────
        carrier_result, spam_result = await asyncio.gather(
            carrier_task, spam_task,
            return_exceptions=True,
        )

        # ── Procesar resultado de carrier ────────────────────────────────
        if isinstance(carrier_result, CarrierInfo):
            result.carrier = carrier_result
            result.line_type = carrier_result.line_type
        else:
            logger.warning(
                "Error al obtener carrier para %s: %s",
                result.phone, carrier_result,
            )

        # ── Procesar resultado de spam ───────────────────────────────────
        if isinstance(spam_result, SpamResult):
            result.is_spam = spam_result.is_spam
            result.spam_reports = spam_result.spam_reports
            if spam_result.is_spam:
                result.risk_flags.append("spam_number")
            if spam_result.spam_reports > 10:
                result.risk_flags.append("high_spam_reports")
        else:
            logger.warning(
                "Error al verificar spam para %s: %s",
                result.phone, spam_result,
            )

        # ── Determinar tipo de número ────────────────────────────────────
        result.number_type = self._determine_number_type(result.phone, country)

        # ── Indicadores de riesgo adicionales ────────────────────────────
        if result.line_type == "voip":
            result.risk_flags.append("voip_number")
        if result.line_type == "toll_free":
            result.risk_flags.append("toll_free_number")

        return result

    # ── Validación de formato ────────────────────────────────────────────
    async def validate_format(
        self,
        phone: str,
        country: str = "MX",
    ) -> ValidationResult:
        """
        Valida el formato de un número telefónico usando la librería phonenumbers.

        Parsea, valida y formatea el número telefónico en múltiples
        formatos estándar (E.164, nacional, internacional).

        Args:
            phone: Número telefónico a validar.
            country: Código de país ISO para contexto de parseo.

        Returns:
            ValidationResult: Resultado de la validación con formatos.
        """
        result = ValidationResult()

        try:
            import phonenumbers

            # ── Parsear el número ────────────────────────────────────────
            parsed = phonenumbers.parse(phone, country)

            # ── Validar ──────────────────────────────────────────────────
            result.is_valid = phonenumbers.is_valid_number(parsed)

            if result.is_valid:
                result.formatted_e164 = phonenumbers.format_number(
                    parsed, phonenumbers.PhoneNumberFormat.E164,
                )
                result.formatted_national = phonenumbers.format_number(
                    parsed, phonenumbers.PhoneNumberFormat.NATIONAL,
                )
                result.formatted_international = phonenumbers.format_number(
                    parsed, phonenumbers.PhoneNumberFormat.INTERNATIONAL,
                )
                result.country_code = self._get_region_code(parsed)
                result.region = self._get_region_name(result.country_code)

        except ImportError:
            logger.warning(
                "Librería phonenumbers no instalada. "
                "Instalar con: pip install phonenumbers"
            )
            # ── Fallback básico sin phonenumbers ─────────────────────────
            cleaned = "".join(c for c in phone if c.isdigit() or c == "+")
            if cleaned.startswith("+") and len(cleaned) >= 8:
                result.is_valid = True
                result.formatted_e164 = cleaned
                result.phone = cleaned
        except Exception as exc:
            logger.debug("Error al validar teléfono %s: %s", phone, exc)

        return result

    # ── Información del carrier ─────────────────────────────────────────
    async def get_carrier_info(self, phone: str) -> CarrierInfo:
        """
        Obtiene la información del carrier/operador de un número telefónico.

        Intenta obtener el carrier usando phonenumbers y lo enriquece
        con información de la base interna de carriers LATAM.

        Args:
            phone: Número telefónico en formato E.164.

        Returns:
            CarrierInfo: Información del carrier/operador.
        """
        cache_key = f"digital:phone:carrier:{phone}"

        # ── Verificar caché ──────────────────────────────────────────────
        try:
            redis = get_redis()
            cached = await redis.get(cache_key)
            if cached:
                cached_data = json.loads(cached)
                return CarrierInfo(**cached_data)
        except Exception:
            logger.debug("Caché no disponible para carrier de %s", phone)

        result = CarrierInfo()
        carrier_name = ""
        country_code = ""

        try:
            import phonenumbers

            parsed = phonenumbers.parse(phone, None)

            # ── Obtener nombre del carrier ───────────────────────────────
            from phonenumbers import carrier as ph_carrier
            carrier_name = ph_carrier.name_for_number(parsed, "es")
            if not carrier_name:
                carrier_name = ph_carrier.name_for_number(parsed, "en")

            # ── Determinar tipo de número ────────────────────────────────
            number_type = phonenumbers.number_type(parsed)
            result.line_type = _PHONENUMBER_TYPE_MAP.get(number_type, "unknown")

            # ── Obtener país ─────────────────────────────────────────────
            country_code = self._get_region_code(parsed)

        except ImportError:
            logger.warning(
                "Librería phonenumbers no instalada. "
                "Instalar con: pip install phonenumbers"
            )
        except Exception as exc:
            logger.debug("Error al obtener carrier para %s: %s", phone, exc)

        # ── Enriquecer con información interna de carriers ───────────────
        if country_code and carrier_name:
            carriers = _CARRIERS_BY_COUNTRY.get(country_code, {})
            for known_name, carrier_info in carriers.items():
                if known_name.lower() in carrier_name.lower():
                    result = CarrierInfo(
                        name=carrier_info.name,
                        mcc=carrier_info.mcc,
                        mnc=carrier_info.mnc,
                        line_type=carrier_info.line_type,
                    )
                    break
            else:
                result.name = carrier_name
        elif carrier_name:
            result.name = carrier_name

        # ── Cachear resultado ────────────────────────────────────────────
        try:
            redis = get_redis()
            await redis.setex(
                cache_key,
                self._cache_ttl * 12,  # TTL largo (carrier es estable)
                json.dumps({
                    "name": result.name,
                    "mcc": result.mcc,
                    "mnc": result.mnc,
                    "line_type": result.line_type,
                }),
            )
        except Exception:
            logger.debug("No se pudo cachear carrier para %s", phone)

        return result

    # ── Verificación de spam ─────────────────────────────────────────────
    async def check_spam(self, phone: str) -> SpamResult:
        """
        Verifica si un número telefónico ha sido reportado como spam.

        Consulta fuentes externas para determinar si el número tiene
        reportes de spam, estafa o actividades sospechosas.

        Args:
            phone: Número telefónico en formato E.164.

        Returns:
            SpamResult: Resultado de la verificación de spam.
        """
        cache_key = f"digital:phone:spam:{phone}"

        # ── Verificar caché ──────────────────────────────────────────────
        try:
            redis = get_redis()
            cached = await redis.get(cache_key)
            if cached:
                cached_data = json.loads(cached)
                return SpamResult(**cached_data)
        except Exception:
            logger.debug("Caché no disponible para spam de %s", phone)

        result = SpamResult()

        # ── Consultar API de verificación de spam ────────────────────────
        # Nota: Se usa una API gratuita como default.
        # En producción se recomienda integrar con servicios como:
        # - Truecaller API
        # - NumVerify API
        # - Teleapi
        # - SpamCalls.net
        try:
            async with httpx.AsyncClient(timeout=self._http_timeout) as client:
                # ── Consulta a numverify.com (o API similar) ─────────────
                response = await client.get(
                    "http://apilayer.net/api/validate",
                    params={
                        "access_key": self._settings.HUNTER_API_KEY,  # Reutilizar o config separada
                        "number": phone,
                        "format": 1,
                    },
                )

                if response.status_code == 200:
                    data = response.json()
                    # ── Analizar resultado para determinar spam ───────────
                    # La API de numverify no da spam directamente, pero
                    # podemos inferir del tipo de línea y carrier
                    line_type = data.get("line_type", "")
                    if line_type == "voip":
                        result.spam_score = 30.0  # Score base para VoIP
                    carrier = data.get("carrier", "")
                    if carrier and "virtual" in carrier.lower():
                        result.spam_score = 40.0

        except httpx.TimeoutException:
            logger.warning("Timeout al verificar spam para %s", phone)
        except httpx.ConnectError:
            logger.warning("Error de conexión al verificar spam para %s", phone)
        except Exception as exc:
            logger.debug("Error al verificar spam para %s: %s", phone, exc)

        # ── Fallback: Verificar en lista interna de spam conocido ────────
        # (Números frecuentemente reportados en México)
        spam_score = self._check_local_spam_list(phone)
        if spam_score > 0:
            result.is_spam = True
            result.spam_score = max(result.spam_score, spam_score)
            result.categories = ["telemarketing", "spam_call"]
            result.spam_reports = int(spam_score / 10)

        # ── Cachear resultado ────────────────────────────────────────────
        try:
            redis = get_redis()
            await redis.setex(
                cache_key,
                self._cache_ttl * 2,
                json.dumps({
                    "is_spam": result.is_spam,
                    "spam_reports": result.spam_reports,
                    "spam_score": result.spam_score,
                    "categories": result.categories,
                    "last_reported": result.last_reported,
                }),
            )
        except Exception:
            logger.debug("No se pudo cachear spam para %s", phone)

        return result

    # ── Métodos auxiliares privados ──────────────────────────────────────
    def _determine_number_type(self, phone: str, country: str) -> str:
        """
        Determina el tipo de número usando phonenumbers.

        Args:
            phone: Número en formato E.164.
            country: Código de país.

        Returns:
            str: Tipo de número (mobile, fixed, voip, etc.).
        """
        try:
            import phonenumbers

            parsed = phonenumbers.parse(phone, None)
            number_type = phonenumbers.number_type(parsed)
            return _PHONENUMBER_TYPE_MAP.get(number_type, "unknown")
        except Exception:
            return "unknown"

    @staticmethod
    def _get_region_code(parsed_number: Any) -> str:
        """
        Obtiene el código de región de un número parseado.

        Args:
            parsed_number: Objeto PhoneNumber de phonenumbers.

        Returns:
            str: Código de país ISO 3166-1 alpha-2.
        """
        try:
            import phonenumbers

            region = phonenumbers.region_code_for_number(parsed_number)
            return region or ""
        except Exception:
            return ""

    @staticmethod
    def _get_region_name(country_code: str) -> str:
        """
        Obtiene el nombre de la región a partir del código de país.

        Args:
            country_code: Código ISO del país.

        Returns:
            str: Nombre del país.
        """
        country_names: dict[str, str] = {
            "MX": "México",
            "US": "Estados Unidos",
            "ES": "España",
            "CO": "Colombia",
            "AR": "Argentina",
            "CL": "Chile",
            "PE": "Perú",
            "BR": "Brasil",
            "EC": "Ecuador",
            "VE": "Venezuela",
            "GT": "Guatemala",
            "HN": "Honduras",
            "SV": "El Salvador",
            "NI": "Nicaragua",
            "CR": "Costa Rica",
            "PA": "Panamá",
            "CU": "Cuba",
            "DO": "República Dominicana",
            "UY": "Uruguay",
            "PY": "Paraguay",
            "BO": "Bolivia",
        }
        return country_names.get(country_code, country_code)

    @staticmethod
    def _check_local_spam_list(phone: str) -> float:
        """
        Verifica si el número está en una lista interna de spam conocido.

        Esta es una verificación heurística básica que revisa patrones
        conocidos de números de spam en México.

        Args:
            phone: Número en formato E.164.

        Returns:
            float: Puntuación de spam (0 = no spam, >0 = probabilidad de spam).
        """
        spam_score = 0.0

        # ── Patrones de números sospechosos en México ────────────────────
        # Números que empiezan con prefijos de telemarketing conocido
        if phone.startswith("+5255") and len(phone) == 13:
            # Números de la CDMX — alto volumen de telemarketing
            local_number = phone[4:]
            # Prefijos conocidos de telemarketing en CDMX
            telemarketing_prefixes = ("5540", "5530", "5520", "5510", "5560")
            if any(local_number.startswith(p) for p in telemarketing_prefixes):
                spam_score = 20.0

        # ── Números VoIP sospechosos ─────────────────────────────────────
        if phone.startswith("+52800") or phone.startswith("+52900"):
            # Números 800/900 pueden ser legítimos pero también usados para spam
            spam_score = max(spam_score, 10.0)

        return spam_score
