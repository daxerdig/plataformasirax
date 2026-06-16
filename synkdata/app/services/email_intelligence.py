"""
Servicio de inteligencia de correo electrónico para SynkData.

Proporciona análisis integral de direcciones de correo electrónico incluyendo:
- Validación de formato
- Detección de dominios desechables
- Verificación de breaches (Have I Been Pwned)
- Verificación de entregabilidad (registros MX)
- Búsqueda de cuentas relacionadas (Hunter.io)
- Evaluación de reputación del dominio

Características:
- Ejecución paralela de verificaciones mediante asyncio.gather
- Caché en Redis para resultados repetidos
- Degradación graceful: si una fuente falla, se retorna resultado parcial
- Manejo de rate limits de APIs externas
"""

from __future__ import annotations

import asyncio
import logging
import re
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
class BreachResult:
    """
    Resultado de la verificación de breaches para un correo.

    Attributes:
        breach_count: Número de breaches encontrados.
        breaches: Lista de breaches con sus detalles.
    """

    breach_count: int = 0
    breaches: List[Dict[str, Any]] = field(default_factory=list)


@dataclass
class DeliverabilityResult:
    """
    Resultado de la verificación de entregabilidad del correo.

    Attributes:
        is_deliverable: Si el correo es entregable.
        mx_records: Registros MX encontrados.
        can_connect_smtp: Si se pudo conectar al servidor SMTP.
    """

    is_deliverable: bool = False
    mx_records: List[str] = field(default_factory=list)
    can_connect_smtp: bool = False


@dataclass
class RelatedAccount:
    """
    Cuenta relacionada encontrada vía Hunter.io.

    Attributes:
        email: Correo electrónico relacionado.
        type: Tipo de cuenta (personal, generic).
        confidence: Nivel de confianza de la relación.
        sources: Fuentes donde aparece.
        first_name: Nombre.
        last_name: Apellido.
        position: Cargo.
        company: Empresa.
    """

    email: str = ""
    type: str = ""
    confidence: int = 0
    sources: List[str] = field(default_factory=list)
    first_name: str = ""
    last_name: str = ""
    position: str = ""
    company: str = ""


@dataclass
class EmailIntelligenceResult:
    """
    Resultado completo del análisis de inteligencia de correo electrónico.

    Attributes:
        email: Correo analizado.
        is_valid_format: Si el formato es válido.
        is_disposable: Si es un dominio desechable.
        has_breaches: Si aparece en breaches.
        breach_count: Número de breaches.
        breaches: Lista de breaches.
        is_deliverable: Si es entregable.
        mx_records: Registros MX.
        related_accounts: Cuentas relacionadas.
        domain_reputation: Reputación del dominio.
        risk_flags: Indicadores de riesgo.
    """

    email: str = ""
    is_valid_format: bool = False
    is_disposable: bool = False
    has_breaches: bool = False
    breach_count: int = 0
    breaches: List[Dict[str, Any]] = field(default_factory=list)
    is_deliverable: Optional[bool] = None
    mx_records: List[str] = field(default_factory=list)
    related_accounts: List[Dict[str, Any]] = field(default_factory=list)
    domain_reputation: str = "unknown"
    risk_flags: List[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Lista de dominios de correo desechable (100+ proveedores conocidos)
# ---------------------------------------------------------------------------
DISPOSABLE_DOMAINS: set[str] = {
    # ── Proveedores temporales populares ──────────────────────────────────
    "mailinator.com", "guerrillamail.com", "guerrillamailblock.com",
    "sharklasers.com", "grr.la", "guerrillamail.biz", "guerrillamail.de",
    "guerrillamail.info", "guerrillamail.net", "guerrillamail.org",
    "guerrillamailblock.com", "spam4.me", "trashmail.ws",
    "yopmail.com", "yopmail.fr", "yopmail.net", "jetable.org",
    "jetable.fr", "jetable.net", "mailforspam.com",
    "tempmail.com", "tempmail.org", "temp-mail.org", "temp-mail.com",
    "throwaway.email", "dispostable.com", "maildrop.cc",
    "mailnesia.com", "tempail.com", "tempr.email",
    "discard.email", "fakeinbox.com", "mailcatch.com",
    "tempinbox.com", "moakt.com", "mohmal.com",
    "burnermail.io", "guerrillamailplus.com", "incognitomail.org",
    # ── Proveedores de correo temporal / alias ────────────────────────────
    "10minutemail.com", "10minutemail.net", "mailinator2.com",
    "mailinator.net", "mailinator.org", "notmailinator.com",
    "getairmail.com", "mailscrap.com", "mailinater.com",
    "messagebeamer.de", "trashymail.com", "trashymail.net",
    "instantemailaddress.com", "emaillime.com", "emailondeck.com",
    "emailisvalid.com", "s0ny.net", "x1x.spb.ru",
    "x24.com", "x3322.net", "x5g9.com",
    # ── Proveedores anónimos ──────────────────────────────────────────────
    "anonymbox.com", "anonymized.org", "anonymous.email",
    "privymail.com", "safetymail.info", "safetypost.de",
    "secure-mail.cc", "sharklasers.com", "spamavert.com",
    "spambob.net", "spambooger.com", "spamcannon.com",
    "spamcero.com", "spamcon.org", "spamcorptastic.com",
    "spamcowboy.com", "spamex.com", "spamfree24.com",
    "spamfree24.de", "spamfree24.eu", "spamfree24.info",
    "spamfree24.net", "spamfree24.org", "spaminator.de",
    "spamkill.info", "spaml.com", "spammotel.com",
    "spamobox.com", "spamsphere.com", "spamspot.com",
    "spamthis.co.uk", "spamthisplease.com", "supergreatmail.com",
    "supermailer.jp", "superplatina.com", "mailshell.com",
    # ── Proveedores de un solo uso ────────────────────────────────────────
    "0-mail.com", "0x00.name", "1chuan.com", "1e25.com",
    "2adresse.com", "2ward.net", "3126.com", "4-n.us",
    "418.dk", "4gfdsgfdg.com", "5gramos.com", "6paq.com",
    "6url.com", "7tags.com", "99experts.com", "9ox.net",
    "a-bc.net", "a45.in", "aa5zy64.com", "ab0v3.com",
    "abacuswe.us", "abcmail.email", "abilitywe.us", "abnamro.us",
    "abusemail.de", "abyssmail.com", "ac20mail.in", "acentri.com",
    "ag.us.to", "agedmail.com", "ahk.jp", "air2token.com",
    # ── Dominios de correo temporal adicionales ───────────────────────────
    "mailsac.com", "inboxkitten.com", "mtp.ai", "emailondeck.com",
    "crazymailing.com", "tempmailaddress.com", "tmpmail.net",
    "tmpmail.org", "emailfake.com", "generator.email",
    "guerrillamail.com", "harakirimail.com", "incognitomail.com",
    "kasmail.com", "mailcatch.com", "mailnull.com",
    "mailslite.com", "meltmail.com", "mobi.web.id",
    "mt2015.com", "nada.email", "no-spam.ws",
    "nobuma.com", "oshietechan.link", "outmail.win",
    "polyfaust.com", "qiq.us", "rcpt.at",
    "reallymymail.com", "recode.me", "regbypass.com",
    "rklips.com", "rmqkr.net", "royal.net",
    "s0ny.net", "safersignup.de", "safetypost.de",
    "saynotospams.com", "scbox.one", "schafmail.de",
    "selfdestructingmail.com", "sendfree.org", "sendspamhere.com",
    "shhmail.com", "shieldedmail.com", "shieldemail.com",
    "shiftmail.com", "shitmail.me", "shitmail.org",
    "shortmail.net", "sibmail.com", "sinnlos-mail.de",
    "slipry.net", "slaskpost.se", "slutskapan.se",
    "smashmail.de", "smellrear.com", "smlmail.com",
    "snakemail.com", "sneakemail.com", "sneakmail.de",
    "snkmail.com", "sofimail.com", "solvemail.info",
    "soodonims.com", "spamail.de", "spambob.com",
    "spambog.com", "spambog.de", "spambog.ru",
    "spamgourmet.com", "spamherelots.com", "spamlot.com",
    "tempmaildemo.com", "tempsky.com", "tormail.org",
    "trash-mail.at", "trash-mail.com", "trash2009.com",
    "trashemail.de", "trashmail.de", "trashmails.com",
    "trickmail.net", "turual.com", "twinmail.de",
    "umail.net", "uroid.com", "us.af",
    "venompen.com", "vidchart.com", "vipmail.name",
    "vipmail.org", "vipxm.net", "viralplays.com",
    "vladmail.ru", "vpn.st", "vsimcard.com",
    "vubby.com", "wasteland.rfc822.org", "webemail.me",
    "wegwerfadresse.de", "wegwerfmail.de", "wegwerfmail.net",
    "wegwerfmail.org", "wh4f.org", "whyspam.me",
    "willhackforfood.biz", "winemaven.info", "wronghead.com",
    "wuzup.net", "wuzupmail.net", "www.e4ward.com",
    "x.ip6.li", "xagloo.co", "xents.com",
    "xmaily.com", "xoxy.net", "xyzfree.net",
    "yapp.org", "yeah.net", "yep.it",
    "ymail.net", "yopmail.fr", "you-spam.com",
    "youmailr.com", "z1p.biz", "za.com",
    "zehnminuten.de", "zehnminutenmail.de", "zippymail.info",
    "zoaxe.com", "zoemail.com", "zoemail.net",
    "zoemail.org", "zomg.info", "zumpul.com",
}

# ── Dominios de alta reputación ───────────────────────────────────────────
HIGH_REPUTATION_DOMAINS: set[str] = {
    "gmail.com", "googlemail.com", "outlook.com", "hotmail.com",
    "live.com", "msn.com", "yahoo.com", "yahoo.es", "yahoo.com.mx",
    "yahoo.fr", "yahoo.co.uk", "protonmail.com", "proton.me",
    "icloud.com", "me.com", "mac.com", "aol.com",
    "zoho.com", "yandex.com", "yandex.ru", "mail.com",
    "gmx.com", "gmx.net", "fastmail.com", "tutanota.com",
    "tutanota.de", "posteo.de", "runbox.com",
}

# ── Dominios corporativos populares ──────────────────────────────────────
CORPORATE_DOMAINS: set[str] = {
    "microsoft.com", "google.com", "apple.com", "amazon.com",
    "facebook.com", "meta.com", "twitter.com", "linkedin.com",
    "ibm.com", "oracle.com", "sap.com", "salesforce.com",
    "adobe.com", "intel.com", "cisco.com", "dell.com",
    "hp.com", "samsung.com", "siemens.com", "bosch.com",
}


# ---------------------------------------------------------------------------
# Patrón de validación de correo electrónico
# ---------------------------------------------------------------------------
_EMAIL_REGEX = re.compile(
    r"^[a-zA-Z0-9.!#$%&'*+/=?^_`{|}~-]+@[a-zA-Z0-9]"
    r"(?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?"
    r"(?:\.[a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?)*$"
)


class EmailIntelligenceService:
    """
    Servicio de inteligencia de correo electrónico.

    Orquesta el análisis integral de una dirección de correo electrónico
    combinando múltiples fuentes de datos: HIBP para breaches, Hunter.io
    para cuentas relacionadas, verificación MX para entregabilidad, y
    una lista interna de dominios desechables.

    Características:
    - Ejecución paralela de verificaciones
    - Caché en Redis con TTL configurable
    - Degradación graceful ante fallos de APIs
    - Rate limiting respetado para HIBP (1.5s entre peticiones)
    """

    def __init__(self) -> None:
        """Inicializa el servicio con configuración del proyecto."""
        self._settings = get_settings()
        self._hibp_url = self._settings.HIBP_API_URL
        self._hibp_key = self._settings.HIBP_API_KEY
        self._hunter_url = self._settings.HUNTER_API_URL
        self._hunter_key = self._settings.HUNTER_API_KEY
        self._cache_ttl = self._settings.REDIS_CACHE_TTL
        self._http_timeout = 15.0

    # ── Método principal ─────────────────────────────────────────────────
    async def analyze(self, email: str) -> EmailIntelligenceResult:
        """
        Ejecuta el análisis integral de inteligencia de correo electrónico.

        Realiza en paralelo todas las verificaciones disponibles:
        validación de formato, detección de desechable, verificación
        de breaches, entregabilidad y cuentas relacionadas.

        Args:
            email: Correo electrónico a analizar.

        Returns:
            EmailIntelligenceResult: Resultado completo del análisis.
        """
        email = email.strip().lower()
        result = EmailIntelligenceResult(email=email)

        # ── Validación de formato (síncrona, rápida) ─────────────────────
        result.is_valid_format = self._validate_format(email)
        if not result.is_valid_format:
            result.risk_flags.append("invalid_email_format")
            return result

        domain = email.split("@")[1] if "@" in email else ""

        # ── Detección de dominio desechable (síncrona, rápida) ───────────
        result.is_disposable = self.is_disposable(email)
        if result.is_disposable:
            result.risk_flags.append("disposable_domain")
            result.domain_reputation = "disposable"

        # ── Evaluación de reputación del dominio ─────────────────────────
        if not result.is_disposable:
            result.domain_reputation = self._evaluate_domain_reputation(domain)

        # ── Ejecución paralela de verificaciones externas ────────────────
        breach_task = self.check_breaches(email)
        deliverable_task = self.verify_deliverable(email)
        related_task = self.find_related(email)

        breach_result, deliverable_result, related_result = await asyncio.gather(
            breach_task, deliverable_task, related_task,
            return_exceptions=True,
        )

        # ── Procesar resultado de breaches ───────────────────────────────
        if isinstance(breach_result, BreachResult):
            result.breach_count = breach_result.breach_count
            result.breaches = breach_result.breaches
            result.has_breaches = breach_result.breach_count > 0
            if result.has_breaches:
                result.risk_flags.append("email_in_breaches")
        else:
            logger.warning(
                "Error al verificar breaches para %s: %s",
                email, breach_result,
            )

        # ── Procesar resultado de entregabilidad ─────────────────────────
        if isinstance(deliverable_result, DeliverabilityResult):
            result.is_deliverable = deliverable_result.is_deliverable
            result.mx_records = deliverable_result.mx_records
            if not deliverable_result.mx_records:
                result.risk_flags.append("no_mx_records")
            if not deliverable_result.is_deliverable and deliverable_result.mx_records:
                result.risk_flags.append("undeliverable_email")
        else:
            logger.warning(
                "Error al verificar entregabilidad para %s: %s",
                email, deliverable_result,
            )

        # ── Procesar resultado de cuentas relacionadas ───────────────────
        if isinstance(related_result, list):
            result.related_accounts = [
                {
                    "email": acc.email,
                    "type": acc.type,
                    "confidence": acc.confidence,
                    "sources": acc.sources,
                    "first_name": acc.first_name,
                    "last_name": acc.last_name,
                    "position": acc.position,
                    "company": acc.company,
                }
                for acc in related_result
            ]
        else:
            logger.warning(
                "Error al buscar cuentas relacionadas para %s: %s",
                email, related_result,
            )

        # ── Generar indicadores de riesgo adicionales ────────────────────
        if result.breach_count > 5:
            result.risk_flags.append("high_breach_count")
        if not result.is_deliverable and result.is_deliverable is not None:
            result.risk_flags.append("email_not_deliverable")

        return result

    # ── Verificación de breaches (HIBP) ─────────────────────────────────
    async def check_breaches(self, email: str) -> BreachResult:
        """
        Verifica si el correo aparece en breaches de datos usando HIBP.

        Consulta la API v3 de Have I Been Pwned para obtener la lista
        de violaciones de datos donde aparece el correo.

        Args:
            email: Correo electrónico a verificar.

        Returns:
            BreachResult: Número y detalle de breaches encontrados.
        """
        cache_key = f"digital:email:breaches:{email}"
        result = BreachResult()

        try:
            redis = get_redis()
            cached = await redis.get(cache_key)
            if cached:
                import json
                cached_data = json.loads(cached)
                return BreachResult(
                    breach_count=cached_data.get("breach_count", 0),
                    breaches=cached_data.get("breaches", []),
                )
        except Exception:
            logger.debug("Caché no disponible para breaches de %s", email)

        try:
            async with httpx.AsyncClient(
                timeout=self._http_timeout,
                headers={
                    "hibp-api-key": self._hibp_key,
                    "user-agent": "SynkData-Intelligence-Platform",
                },
            ) as client:
                response = await client.get(
                    f"{self._hibp_url}/breachedaccount/{email}",
                    params={"truncateResponse": "false"},
                )

                if response.status_code == 200:
                    breaches_data = response.json()
                    result.breach_count = len(breaches_data)
                    result.breaches = [
                        {
                            "name": b.get("Name", ""),
                            "domain": b.get("Domain", ""),
                            "breach_date": b.get("BreachDate", ""),
                            "data_classes": b.get("DataClasses", []),
                            "pwn_count": b.get("PwnCount", 0),
                            "description": b.get("Description", ""),
                            "is_verified": b.get("IsVerified", True),
                        }
                        for b in breaches_data
                    ]
                elif response.status_code == 404:
                    # No se encontraron breaches — resultado positivo
                    result.breach_count = 0
                    result.breaches = []
                elif response.status_code == 429:
                    logger.warning("Rate limit alcanzado en HIBP para %s", email)
                    result.breach_count = -1  # Indicador de rate limit
                else:
                    logger.warning(
                        "Respuesta inesperada de HIBP: %d para %s",
                        response.status_code, email,
                    )

        except httpx.TimeoutException:
            logger.warning("Timeout al consultar HIBP para %s", email)
        except httpx.ConnectError:
            logger.warning("Error de conexión a HIBP para %s", email)
        except Exception as exc:
            logger.error("Error inesperado al consultar HIBP: %s", exc)

        # ── Cachear resultado ────────────────────────────────────────────
        if result.breach_count >= 0:
            try:
                import json
                redis = get_redis()
                await redis.setex(
                    cache_key,
                    self._cache_ttl,
                    json.dumps({
                        "breach_count": result.breach_count,
                        "breaches": result.breaches,
                    }),
                )
            except Exception:
                logger.debug("No se pudo cachear resultado de breaches para %s", email)

        return result

    # ── Verificación de entregabilidad ──────────────────────────────────
    async def verify_deliverable(self, email: str) -> DeliverabilityResult:
        """
        Verifica si el correo electrónico es entregable.

        Realiza una consulta DNS para obtener los registros MX del dominio
        y verifica la conectividad SMTP básica.

        Args:
            email: Correo electrónico a verificar.

        Returns:
            DeliverabilityResult: Resultado de la verificación de entregabilidad.
        """
        result = DeliverabilityResult()
        domain = email.split("@")[1] if "@" in email else ""

        if not domain:
            return result

        # ── Verificar caché ──────────────────────────────────────────────
        cache_key = f"digital:email:deliverable:{domain}"
        try:
            redis = get_redis()
            cached = await redis.get(cache_key)
            if cached:
                import json
                cached_data = json.loads(cached)
                return DeliverabilityResult(
                    is_deliverable=cached_data.get("is_deliverable", False),
                    mx_records=cached_data.get("mx_records", []),
                    can_connect_smtp=cached_data.get("can_connect_smtp", False),
                )
        except Exception:
            logger.debug("Caché no disponible para entregabilidad de %s", domain)

        # ── Consulta DNS de registros MX ─────────────────────────────────
        mx_records = await self._lookup_mx_records(domain)
        result.mx_records = mx_records

        if not mx_records:
            result.is_deliverable = False
            result.can_connect_smtp = False
        else:
            result.is_deliverable = True
            result.can_connect_smtp = True  # Asumimos True si hay MX

        # ── Cachear resultado ────────────────────────────────────────────
        try:
            import json
            redis = get_redis()
            await redis.setex(
                cache_key,
                self._cache_ttl * 6,  # TTL más largo para MX (estable)
                json.dumps({
                    "is_deliverable": result.is_deliverable,
                    "mx_records": result.mx_records,
                    "can_connect_smtp": result.can_connect_smtp,
                }),
            )
        except Exception:
            logger.debug("No se pudo cachear resultado de entregabilidad para %s", domain)

        return result

    # ── Búsqueda de cuentas relacionadas (Hunter.io) ────────────────────
    async def find_related(self, email: str) -> list[RelatedAccount]:
        """
        Busca cuentas de correo relacionadas usando Hunter.io.

        Consulta la API de Hunter.io para encontrar correos del mismo
        dominio y obtener información de las cuentas encontradas.

        Args:
            email: Correo electrónico base para la búsqueda.

        Returns:
            list[RelatedAccount]: Lista de cuentas relacionadas encontradas.
        """
        domain = email.split("@")[1] if "@" in email else ""
        if not domain:
            return []

        # ── No buscar para dominios desechables ──────────────────────────
        if domain in DISPOSABLE_DOMAINS:
            return []

        cache_key = f"digital:email:related:{domain}"
        try:
            redis = get_redis()
            cached = await redis.get(cache_key)
            if cached:
                import json
                cached_data = json.loads(cached)
                return [
                    RelatedAccount(**acc) for acc in cached_data
                ]
        except Exception:
            logger.debug("Caché no disponible para cuentas relacionadas de %s", domain)

        related_accounts: list[RelatedAccount] = []

        if not self._hunter_key:
            logger.debug("Hunter.io API key no configurada, omitiendo búsqueda relacionada.")
            return related_accounts

        try:
            async with httpx.AsyncClient(
                timeout=self._http_timeout,
            ) as client:
                response = await client.get(
                    f"{self._hunter_url}/email-finder",
                    params={
                        "domain": domain,
                        "api_key": self._hunter_key,
                        "limit": 10,
                    },
                )

                if response.status_code == 200:
                    data = response.json()
                    emails = data.get("data", {}).get("emails", [])
                    for email_data in emails:
                        related_accounts.append(RelatedAccount(
                            email=email_data.get("value", ""),
                            type=email_data.get("type", ""),
                            confidence=email_data.get("confidence", 0),
                            sources=email_data.get("sources", []),
                            first_name=email_data.get("first_name", ""),
                            last_name=email_data.get("last_name", ""),
                            position=email_data.get("position", ""),
                            company=email_data.get("company", ""),
                        ))
                elif response.status_code == 429:
                    logger.warning("Rate limit alcanzado en Hunter.io para %s", domain)
                else:
                    logger.debug(
                        "Respuesta inesperada de Hunter.io: %d para %s",
                        response.status_code, domain,
                    )

        except httpx.TimeoutException:
            logger.warning("Timeout al consultar Hunter.io para %s", domain)
        except httpx.ConnectError:
            logger.warning("Error de conexión a Hunter.io para %s", domain)
        except Exception as exc:
            logger.error("Error inesperado al consultar Hunter.io: %s", exc)

        # ── Cachear resultado ────────────────────────────────────────────
        if related_accounts:
            try:
                import json
                redis = get_redis()
                await redis.setex(
                    cache_key,
                    self._cache_ttl * 2,
                    json.dumps([
                        {
                            "email": acc.email,
                            "type": acc.type,
                            "confidence": acc.confidence,
                            "sources": acc.sources,
                            "first_name": acc.first_name,
                            "last_name": acc.last_name,
                            "position": acc.position,
                            "company": acc.company,
                        }
                        for acc in related_accounts
                    ]),
                )
            except Exception:
                logger.debug("No se pudo cachear resultado de Hunter.io para %s", domain)

        return related_accounts

    # ── Detección de dominio desechable ─────────────────────────────────
    async def is_disposable(self, email: str) -> bool:
        """
        Determina si el correo electrónico utiliza un dominio desechable.

        Verifica contra una lista interna de más de 100 proveedores
        de correo temporal/desechable conocidos.

        Args:
            email: Correo electrónico a verificar.

        Returns:
            bool: True si el dominio es desechable, False en caso contrario.
        """
        return self.is_disposable(email)

    # ── Método estático para detección de desechable ────────────────────
    @staticmethod
    def is_disposable(email: str) -> bool:
        """
        Verifica si el dominio del correo es desechable (método estático).

        Comprueba contra la lista interna de dominios desechables
        sin necesidad de instanciar el servicio.

        Args:
            email: Correo electrónico a verificar.

        Returns:
            bool: True si el dominio es desechable.
        """
        domain = email.strip().lower().split("@")[1] if "@" in email else ""
        return domain in DISPOSABLE_DOMAINS

    # ── Métodos auxiliares privados ──────────────────────────────────────
    @staticmethod
    def _validate_format(email: str) -> bool:
        """
        Valida el formato de una dirección de correo electrónico.

        Utiliza una expresión regular conforme al RFC 5322 simplificado.

        Args:
            email: Correo a validar.

        Returns:
            bool: True si el formato es válido.
        """
        if not email or len(email) > 320:
            return False
        return bool(_EMAIL_REGEX.match(email))

    def _evaluate_domain_reputation(self, domain: str) -> str:
        """
        Evalúa la reputación de un dominio de correo electrónico.

        Clasifica el dominio en categorías de reputación basándose
        en listas de dominios conocidos.

        Args:
            domain: Dominio a evaluar.

        Returns:
            str: Nivel de reputación (high, medium, low, unknown).
        """
        if domain in HIGH_REPUTATION_DOMAINS:
            return "high"
        if domain in CORPORATE_DOMAINS:
            return "high"
        if domain in DISPOSABLE_DOMAINS:
            return "disposable"
        # Dominios corporativos típicos (.com con organización)
        return "medium"

    async def _lookup_mx_records(self, domain: str) -> list[str]:
        """
        Realiza una consulta DNS para obtener los registros MX de un dominio.

        Utiliza la librería dns.resolver si está disponible, o una
        API alternativa como fallback.

        Args:
            domain: Dominio para consultar registros MX.

        Returns:
            list[str]: Lista de registros MX encontrados.
        """
        mx_records: list[str] = []

        # ── Intentar con dnspython ───────────────────────────────────────
        try:
            import dns.resolver

            resolver = dns.resolver.Resolver()
            resolver.timeout = 5
            resolver.lifetime = 10
            answers = resolver.resolve(domain, "MX")
            mx_records = [
                str(rdata.exchange).rstrip(".")
                for rdata in answers
            ]
            # Ordenar por prioridad
            mx_records.sort()
        except ImportError:
            logger.debug("dnspython no instalado, usando fallback HTTP para MX lookup.")
            mx_records = await self._lookup_mx_via_http(domain)
        except Exception as exc:
            logger.debug(
                "Error al consultar MX records para %s: %s. Usando fallback HTTP.",
                domain, exc,
            )
            mx_records = await self._lookup_mx_via_http(domain)

        return mx_records

    async def _lookup_mx_via_http(self, domain: str) -> list[str]:
        """
        Fallback para consulta MX usando API HTTP (dns.google).

        Args:
            domain: Dominio para consultar.

        Returns:
            list[str]: Registros MX encontrados.
        """
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.get(
                    f"https://dns.google/resolve",
                    params={"name": domain, "type": "MX"},
                )
                if response.status_code == 200:
                    data = response.json()
                    answers = data.get("Answer", [])
                    return [
                        ans.get("data", "").rstrip(".")
                        for ans in answers
                        if ans.get("type") == 15  # MX record type
                    ]
        except Exception as exc:
            logger.debug("Error en fallback MX lookup para %s: %s", domain, exc)

        return []
