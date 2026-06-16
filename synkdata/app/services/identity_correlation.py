"""
Motor de correlación de identidad para la plataforma SynkData.

Realiza la correlación cruzada de todas las señales de identidad
proporcionadas (nombre, CURP, RFC, correo, teléfono, redes sociales)
para determinar la consistencia y confianza de la identidad declarada.

Señales de correlación evaluadas:
- Consistencia del nombre a través de CURP, RFC, correo y perfiles sociales
- Consistencia CURP-RFC (el RFC derivado de la CURP debe coincidir)
- Correlación correo-teléfono (indicadores del mismo propietario)
- Coincidencia de nombre en redes sociales vs. nombre declarado
- Verificación empresa/dominio (dominio del correo coincide con empresa)
- Consistencia de nombre de usuario entre plataformas

Produce un puntaje identity_confidence (0-100):
- 95-100: Todas las señales son consistentes
- 70-94: Inconsistencias menores
- 30-69: Inconsistencias mayores
- 0-29: Señales contradictorias

Los mensajes dirigidos al usuario están en español conforme a los
estándares de la plataforma SynkData.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from app.schemas.identity import (
    CorrelationResult,
    CorrelationSignal,
    IdentityData,
)
from app.utils.curp_algorithm import extract_curp_info, validate_curp_format
from app.utils.rfc_algorithm import extract_rfc_info, validate_rfc_format
from app.utils.text_normalizer import normalize_for_comparison, split_full_name

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Listas de dominios de correo desechable
# ---------------------------------------------------------------------------
DISPOSABLE_EMAIL_DOMAINS: set[str] = {
    "mailinator.com", "guerrillamail.com", "guerrillamailblock.com",
    "sharklasers.com", "grr.la", "guerrillamail.info", "guerrillamail.net",
    "guerrillamail.org", "tempmail.com", "temp-mail.org", "throwaway.email",
    "yopmail.com", "yopmail.fr", "yopmail.net", "jetable.org", "jetable.com",
    "mailforspam.com", "safetymail.info", "filzmail.com", "incognitomail.org",
    "incognitomail.com", "incognitomail.net", "notmail.net", "mailcatch.com",
    "tempinbox.com", "mailme.lv", "trashmail.ws", "trashmail.com",
    "10minutemail.com", "20minutemail.com", "30minutemail.com",
    "dispostable.com", "maildrop.cc", "mailnesia.com", "tempail.com",
    "tempr.email", "discard.email", "fakeinbox.com", "mailshell.com",
}

# Dominios de correo gratuito de alta reputación
FREE_EMAIL_DOMAINS: set[str] = {
    "gmail.com", "outlook.com", "hotmail.com", "live.com", "yahoo.com",
    "yahoo.com.mx", "protonmail.com", "icloud.com", "me.com", "aol.com",
}


# ---------------------------------------------------------------------------
# Funciones auxiliares
# ---------------------------------------------------------------------------
def _extract_email_domain(email: str) -> str:
    """Extrae el dominio de un correo electrónico normalizado."""
    if not email or "@" not in email:
        return ""
    return email.strip().lower().split("@")[-1]


def _is_disposable_email(email: str) -> bool:
    """Verifica si el correo electrónico usa un dominio desechable."""
    domain = _extract_email_domain(email)
    return domain in DISPOSABLE_EMAIL_DOMAINS


def _names_match(name1: str, name2: str, threshold: float = 0.80) -> bool:
    """
    Compara dos nombres normalizados para determinar si coinciden.

    Usa comparación de iniciales y similitud de subcadenas
    como aproximación ligera (sin dependencias externas).

    Args:
        name1: Primer nombre a comparar (ya normalizado).
        name2: Segundo nombre a comparar (ya normalizado).
        threshold: Umbral de similitud (0-1).

    Returns:
        bool: True si los nombres se consideran coincidentes.
    """
    if not name1 or not name2:
        return False

    n1 = normalize_for_comparison(name1)
    n2 = normalize_for_comparison(name2)

    # Coincidencia exacta
    if n1 == n2:
        return True

    # Verificar si uno contiene al otro (nombre parcial)
    if n1 in n2 or n2 in n1:
        return True

    # Comparación de conjuntos de palabras (solapamiento)
    words1 = set(n1.split())
    words2 = set(n2.split())

    if not words1 or not words2:
        return False

    intersection = words1 & words2
    union = words1 | words2
    jaccard = len(intersection) / len(union) if union else 0.0

    return jaccard >= threshold


def _derive_rfc_from_curp(curp: str) -> str:
    """
    Deriva el RFC base (10 caracteres) a partir de una CURP válida.

    El RFC de una persona física se compone de:
    - Posiciones 1-4 de la CURP (iniciales del nombre)
    - Posiciones 5-10 de la CURP (fecha AAMMDD)

    Args:
        curp: CURP de 18 caracteres.

    Returns:
        str: RFC base derivado (10 caracteres) o cadena vacía si falla.
    """
    if not curp or len(curp) < 10:
        return ""

    curp_upper = curp.strip().upper()
    if not validate_curp_format(curp_upper):
        return ""

    # RFC = primeras 4 letras + fecha (6 dígitos) de la CURP
    return curp_upper[:10]


def _extract_name_from_curp(curp: str) -> str:
    """
    Extrae una representación parcial del nombre desde la CURP.

    Nota: La CURP solo contiene las iniciales del nombre (4 letras),
    por lo que no es posible reconstruir el nombre completo. Esta
    función verifica la consistencia de las iniciales.

    Returns:
        str: Iniciales del nombre extraídas de la CURP, o cadena vacía.
    """
    if not curp or not validate_curp_format(curp.strip().upper()):
        return ""
    return curp.strip().upper()[:4]


def _extract_name_initials_from_name(full_name: str) -> str:
    """
    Genera las 4 letras iniciales de la CURP/RFC a partir de un nombre completo.

    Usa la misma lógica del algoritmo RENAPO para comparar con las
    iniciales extraídas de la CURP o RFC.

    Returns:
        str: Las 4 letras iniciales calculadas, o cadena vacía si no se puede.
    """
    if not full_name:
        return ""

    name_parts = split_full_name(full_name)
    first_name, paternal, maternal = name_parts

    if not paternal:
        return ""

    n = normalize_for_comparison(first_name)
    p = normalize_for_comparison(paternal)
    m = normalize_for_comparison(maternal)

    # Posición 1: Primera letra del apellido paterno
    pos1 = p[0] if p else "X"

    # Posición 2: Primera vocal interna del apellido paterno
    vowels = "AEIOU"
    pos2 = "X"
    for char in p[1:] if len(p) > 1 else "":
        if char in vowels:
            pos2 = char
            break

    # Posición 3: Primera letra del apellido materno
    pos3 = m[0] if m else "X"

    # Posición 4: Primera letra del primer nombre
    # Regla Jose/Maria
    names = n.split() if n else []
    if len(names) > 1 and names[0] in ("JOSE", "J", "MARIA", "MA", "M"):
        pos4 = names[1][0] if len(names) > 1 else (names[0][0] if names else "X")
    else:
        pos4 = names[0][0] if names else "X"

    return f"{pos1}{pos2}{pos3}{pos4}"


def _check_company_domain_match(company: str, domain: str) -> bool:
    """
    Verifica si el dominio declarado coincide con la empresa declarada.

    Heurística simple: normaliza el nombre de la empresa y verifica
    si el dominio contiene las palabras clave del nombre.

    Returns:
        bool: True si hay una correspondencia razonable.
    """
    if not company or not domain:
        return False

    # Normalizar nombre de empresa: eliminar sufijos comunes
    company_norm = normalize_for_comparison(company)
    suffixes = [
        "SA DE CV", "S A DE C V", "SAB DE CV", "S A B DE C V",
        "SA", "S A", "SC", "S C", "AC", "A C",
        "DE CV", "DE C V",
    ]
    for suffix in suffixes:
        company_norm = company_norm.replace(suffix, "")
    company_norm = company_norm.strip()

    if not company_norm:
        return False

    # Extraer palabras clave del nombre (ignorar partículas)
    particles = {"DE", "DEL", "LA", "LAS", "LOS", "EL", "Y", "EN"}
    keywords = [w for w in company_norm.split() if w not in particles and len(w) > 2]

    if not keywords:
        return False

    domain_lower = domain.lower().replace(".", " ").replace("-", " ")

    # Verificar si las palabras clave principales aparecen en el dominio
    matches = sum(1 for kw in keywords if kw.lower() in domain_lower)
    return matches > 0 and matches / len(keywords) >= 0.5


# ---------------------------------------------------------------------------
# Servicio de correlación de identidad
# ---------------------------------------------------------------------------
class IdentityCorrelationService:
    """
    Servicio de correlación de identidad.

    Realiza la correlación cruzada de todas las señales de identidad
    para determinar la consistencia y confianza de la identidad declarada.

    Cada verificación produce un CorrelationSignal con:
    - name: Nombre descriptivo de la señal
    - passed: Si la verificación pasó
    - score: Puntuación (0-100)
    - weight: Peso relativo en el cálculo global
    - details: Descripción del resultado

    El puntaje identity_confidence se calcula como un promedio ponderado
    de las señales evaluadas.
    """

    async def correlate(self, identity_data: IdentityData) -> CorrelationResult:
        """
        Ejecuta la correlación cruzada de todas las señales de identidad.

        Args:
            identity_data: Datos de identidad a correlacionar.

        Returns:
            CorrelationResult: Resultado con puntuación de confianza,
                señales evaluadas, advertencias e indicadores.
        """
        signals: List[CorrelationSignal] = []
        warnings: List[str] = []
        flags: List[str] = []

        # ── 1. Consistencia del nombre a través de documentos ────────────
        signals.append(await self._check_name_consistency(identity_data))

        # ── 2. Consistencia CURP-RFC ─────────────────────────────────────
        signals.append(await self._check_curp_rfc_consistency(identity_data))

        # ── 3. Correlación correo-teléfono ───────────────────────────────
        signals.append(await self._check_email_phone_correlation(identity_data))

        # ── 4. Coincidencia de nombre en redes sociales ──────────────────
        signals.append(await self._check_social_name_match(identity_data))

        # ── 5. Verificación empresa/dominio ──────────────────────────────
        signals.append(await self._check_company_domain_verification(identity_data))

        # ── 6. Consistencia de username entre plataformas ────────────────
        signals.append(await self._check_username_consistency(identity_data))

        # ── Calcular puntuación global ───────────────────────────────────
        identity_confidence = self._calculate_confidence(signals)

        # ── Generar advertencias y banderas ──────────────────────────────
        for signal in signals:
            if not signal.passed and signal.weight >= 0.20:
                warnings.append(
                    f"Señal fallida con peso alto: {signal.name} — {signal.details}"
                )
            if not signal.passed and signal.score < 30:
                flags.append(f"ALERTA_{signal.name.upper().replace(' ', '_')}")

        # Verificar correo desechable
        if identity_data.email and _is_disposable_email(identity_data.email):
            warnings.append("El correo electrónico utiliza un dominio desechable.")
            flags.append("CORREO_DESECHABLE")

        logger.info(
            "Correlación completada — confidence=%.1f, signals=%d, warnings=%d, flags=%d",
            identity_confidence,
            len(signals),
            len(warnings),
            len(flags),
        )

        return CorrelationResult(
            identity_confidence=round(identity_confidence, 2),
            signals=signals,
            warnings=warnings,
            flags=flags,
        )

    # ── Verificaciones individuales ──────────────────────────────────────

    async def _check_name_consistency(
        self, data: IdentityData
    ) -> CorrelationSignal:
        """
        Verifica la consistencia del nombre a través de CURP, RFC y correo.

        Compara las iniciales derivadas del nombre declarado con las
        contenidas en la CURP y el RFC.
        """
        if not data.name:
            return CorrelationSignal(
                name="Consistencia del nombre",
                passed=False,
                score=0.0,
                weight=0.25,
                details="No se proporcionó nombre para verificar consistencia.",
            )

        expected_initials = _extract_name_initials_from_name(data.name)
        checks_passed = 0
        total_checks = 0
        details_parts: List[str] = []

        # Verificar contra CURP
        if data.curp:
            total_checks += 1
            curp_initials = _extract_name_from_curp(data.curp)
            if curp_initials and expected_initials:
                if curp_initials == expected_initials:
                    checks_passed += 1
                    details_parts.append(
                        f"Iniciales CURP ({curp_initials}) coinciden con nombre declarado."
                    )
                else:
                    details_parts.append(
                        f"Iniciales CURP ({curp_initials}) NO coinciden con nombre declarado ({expected_initials})."
                    )

        # Verificar contra RFC
        if data.rfc:
            total_checks += 1
            try:
                is_valid, _ = validate_rfc_format(data.rfc)
                if is_valid:
                    rfc_info = extract_rfc_info(data.rfc)
                    rfc_initials = rfc_info.name_initials
                    if expected_initials and rfc_initials == expected_initials:
                        checks_passed += 1
                        details_parts.append(
                            f"Iniciales RFC ({rfc_initials}) coinciden con nombre declarado."
                        )
                    else:
                        details_parts.append(
                            f"Iniciales RFC ({rfc_initials}) NO coinciden con nombre declarado ({expected_initials})."
                        )
            except (ValueError, Exception):
                details_parts.append("No se pudieron extraer iniciales del RFC (formato inválido).")

        # Verificar contra correo electrónico (nombre en la parte local)
        if data.email and "@" in data.email:
            total_checks += 1
            local_part = data.email.split("@")[0].lower()
            name_norm = normalize_for_comparison(data.name).lower()
            name_words = name_norm.split()
            # Verificar si las palabras del nombre aparecen en el correo
            name_in_email = any(
                word in local_part for word in name_words if len(word) > 2
            )
            if name_in_email:
                checks_passed += 1
                details_parts.append("El correo contiene partes del nombre declarado.")
            else:
                details_parts.append("El correo NO contiene partes reconocibles del nombre declarado.")

        if total_checks == 0:
            return CorrelationSignal(
                name="Consistencia del nombre",
                passed=True,
                score=75.0,
                weight=0.25,
                details="Nombre proporcionado pero sin documentos para comparar. Se otorga puntaje base.",
            )

        score = (checks_passed / total_checks) * 100
        passed = score >= 70.0

        return CorrelationSignal(
            name="Consistencia del nombre",
            passed=passed,
            score=round(score, 2),
            weight=0.25,
            details="; ".join(details_parts) if details_parts else "Sin datos suficientes para comparar.",
        )

    async def _check_curp_rfc_consistency(
        self, data: IdentityData
    ) -> CorrelationSignal:
        """
        Verifica la consistencia entre la CURP y el RFC.

        El RFC derivado de la CURP (primeros 10 caracteres) debe
        coincidir con los primeros 10 caracteres del RFC proporcionado.
        """
        if not data.curp or not data.rfc:
            return CorrelationSignal(
                name="Consistencia CURP-RFC",
                passed=False,
                score=0.0,
                weight=0.20,
                details="Se requieren tanto CURP como RFC para verificar consistencia.",
            )

        curp_upper = data.curp.strip().upper()
        rfc_upper = data.rfc.strip().upper()

        # Validar formato de CURP
        if not validate_curp_format(curp_upper):
            return CorrelationSignal(
                name="Consistencia CURP-RFC",
                passed=False,
                score=0.0,
                weight=0.20,
                details="La CURP proporcionada no tiene un formato válido.",
            )

        # Validar formato de RFC
        rfc_valid, _ = validate_rfc_format(rfc_upper)
        if not rfc_valid:
            return CorrelationSignal(
                name="Consistencia CURP-RFC",
                passed=False,
                score=0.0,
                weight=0.20,
                details="El RFC proporcionado no tiene un formato válido.",
            )

        # Derivar RFC base desde la CURP
        derived_rfc = _derive_rfc_from_curp(curp_upper)
        rfc_base = rfc_upper[:10]

        if derived_rfc == rfc_base:
            return CorrelationSignal(
                name="Consistencia CURP-RFC",
                passed=True,
                score=100.0,
                weight=0.20,
                details=f"El RFC derivado de la CURP ({derived_rfc}) coincide con el RFC proporcionado ({rfc_base}).",
            )
        else:
            return CorrelationSignal(
                name="Consistencia CURP-RFC",
                passed=False,
                score=0.0,
                weight=0.20,
                details=(
                    f"INCONSISTENCIA: El RFC derivado de la CURP ({derived_rfc}) "
                    f"NO coincide con el RFC proporcionado ({rfc_base}). "
                    f"Esto puede indicar documentos de diferentes personas o un error en los datos."
                ),
            )

    async def _check_email_phone_correlation(
        self, data: IdentityData
    ) -> CorrelationSignal:
        """
        Verifica la correlación entre correo electrónico y teléfono.

        Evalúa indicadores de que el correo y el teléfono pertenecen
        al mismo propietario: mismo país, dominio no desechable, etc.
        """
        if not data.email and not data.phone:
            return CorrelationSignal(
                name="Correlación correo-teléfono",
                passed=False,
                score=0.0,
                weight=0.15,
                details="No se proporcionó correo ni teléfono para correlacionar.",
            )

        if not data.email or not data.phone:
            return CorrelationSignal(
                name="Correlación correo-teléfono",
                passed=True,
                score=50.0,
                weight=0.15,
                details="Solo se proporcionó uno de los dos (correo o teléfono). No se puede correlacionar completamente.",
            )

        details_parts: List[str] = []
        score = 50.0  # Base por tener ambos

        # Verificar si el correo es desechable
        if _is_disposable_email(data.email):
            score -= 30.0
            details_parts.append("El correo utiliza un dominio desechable, lo que reduce la correlación.")
        else:
            domain = _extract_email_domain(data.email)
            if domain in FREE_EMAIL_DOMAINS:
                score += 10.0
                details_parts.append(f"El correo usa un dominio gratuito de alta reputación ({domain}).")
            elif domain:
                score += 15.0
                details_parts.append(f"El correo usa un dominio personalizado ({domain}), indicador de propiedad verificada.")

        # Verificar indicio de mismo país (México)
        phone = data.phone.strip()
        if phone.startswith("+52") or phone.startswith("52"):
            email_domain = _extract_email_domain(data.email)
            if ".mx" in email_domain or email_domain in FREE_EMAIL_DOMAINS:
                score += 10.0
                details_parts.append("El teléfono y correo sugieren origen México, consistencia geográfica.")

        score = max(0.0, min(100.0, score))
        passed = score >= 60.0

        return CorrelationSignal(
            name="Correlación correo-teléfono",
            passed=passed,
            score=round(score, 2),
            weight=0.15,
            details="; ".join(details_parts) if details_parts else "Correlación básica entre correo y teléfono.",
        )

    async def _check_social_name_match(
        self, data: IdentityData
    ) -> CorrelationSignal:
        """
        Verifica que el nombre en los perfiles sociales coincida
        con el nombre declarado.
        """
        if not data.social_profiles or not data.name:
            return CorrelationSignal(
                name="Coincidencia nombre en redes sociales",
                passed=False,
                score=0.0,
                weight=0.15,
                details="No se proporcionaron perfiles sociales o nombre para comparar.",
            )

        matched_profiles = 0
        total_profiles = 0
        details_parts: List[str] = []

        for profile in data.social_profiles:
            if profile.display_name:
                total_profiles += 1
                if _names_match(data.name, profile.display_name):
                    matched_profiles += 1
                    details_parts.append(
                        f"Nombre en {profile.platform} coincide con el declarado."
                    )
                else:
                    details_parts.append(
                        f"Nombre en {profile.platform} ({profile.display_name}) "
                        f"NO coincide con el declarado ({data.name})."
                    )

        if total_profiles == 0:
            return CorrelationSignal(
                name="Coincidencia nombre en redes sociales",
                passed=True,
                score=50.0,
                weight=0.15,
                details="Perfiles sociales sin nombre visible. No se puede verificar coincidencia.",
            )

        score = (matched_profiles / total_profiles) * 100
        passed = score >= 70.0

        return CorrelationSignal(
            name="Coincidencia nombre en redes sociales",
            passed=passed,
            score=round(score, 2),
            weight=0.15,
            details="; ".join(details_parts),
        )

    async def _check_company_domain_verification(
        self, data: IdentityData
    ) -> CorrelationSignal:
        """
        Verifica que el dominio del correo coincida con la empresa declarada.

        Si la persona declara trabajar en una empresa y proporciona un
        correo, el dominio del correo debería estar relacionado con
        la empresa.
        """
        if not data.company and not data.domain and not data.email:
            return CorrelationSignal(
                name="Verificación empresa/dominio",
                passed=False,
                score=0.0,
                weight=0.15,
                details="No se proporcionó empresa, dominio ni correo para verificar.",
            )

        details_parts: List[str] = []

        # Caso 1: empresa + correo (verificar dominio del correo vs empresa)
        if data.company and data.email:
            email_domain = _extract_email_domain(data.email)
            if email_domain in FREE_EMAIL_DOMAINS:
                details_parts.append(
                    f"El correo usa dominio gratuito ({email_domain}), no se puede verificar afiliación con {data.company}."
                )
                return CorrelationSignal(
                    name="Verificación empresa/dominio",
                    passed=True,
                    score=40.0,
                    weight=0.15,
                    details="; ".join(details_parts),
                )
            elif _check_company_domain_match(data.company, email_domain):
                details_parts.append(
                    f"El dominio del correo ({email_domain}) coincide con la empresa declarada ({data.company})."
                )
                return CorrelationSignal(
                    name="Verificación empresa/dominio",
                    passed=True,
                    score=100.0,
                    weight=0.15,
                    details="; ".join(details_parts),
                )
            else:
                details_parts.append(
                    f"El dominio del correo ({email_domain}) NO parece relacionado con la empresa declarada ({data.company})."
                )
                return CorrelationSignal(
                    name="Verificación empresa/dominio",
                    passed=False,
                    score=20.0,
                    weight=0.15,
                    details="; ".join(details_parts),
                )

        # Caso 2: empresa + dominio declarado
        if data.company and data.domain:
            if _check_company_domain_match(data.company, data.domain):
                details_parts.append(
                    f"El dominio declarado ({data.domain}) coincide con la empresa ({data.company})."
                )
                return CorrelationSignal(
                    name="Verificación empresa/dominio",
                    passed=True,
                    score=90.0,
                    weight=0.15,
                    details="; ".join(details_parts),
                )
            else:
                details_parts.append(
                    f"El dominio declarado ({data.domain}) NO coincide con la empresa ({data.company})."
                )
                return CorrelationSignal(
                    name="Verificación empresa/dominio",
                    passed=False,
                    score=15.0,
                    weight=0.15,
                    details="; ".join(details_parts),
                )

        # Caso 3: solo correo (sin empresa)
        if data.email:
            email_domain = _extract_email_domain(data.email)
            if email_domain in FREE_EMAIL_DOMAINS:
                details_parts.append(f"Correo con dominio gratuito ({email_domain}). Sin empresa para comparar.")
                return CorrelationSignal(
                    name="Verificación empresa/dominio",
                    passed=True,
                    score=50.0,
                    weight=0.15,
                    details="; ".join(details_parts),
                )
            else:
                details_parts.append(f"Correo con dominio personalizado ({email_domain}). Sin empresa para comparar.")
                return CorrelationSignal(
                    name="Verificación empresa/dominio",
                    passed=True,
                    score=65.0,
                    weight=0.15,
                    details="; ".join(details_parts),
                )

        return CorrelationSignal(
            name="Verificación empresa/dominio",
            passed=True,
            score=50.0,
            weight=0.15,
            details="Datos insuficientes para verificación completa de empresa/dominio.",
        )

    async def _check_username_consistency(
        self, data: IdentityData
    ) -> CorrelationSignal:
        """
        Verifica la consistencia del nombre de usuario entre plataformas.

        Si se proporciona un username genérico y perfiles sociales,
        verifica que los usernames en los perfiles coincidan o sean
        similares al username declarado.
        """
        if not data.username and not data.social_profiles:
            return CorrelationSignal(
                name="Consistencia de nombre de usuario",
                passed=False,
                score=0.0,
                weight=0.10,
                details="No se proporcionó username ni perfiles sociales para comparar.",
            )

        if not data.social_profiles:
            return CorrelationSignal(
                name="Consistencia de nombre de usuario",
                passed=True,
                score=60.0,
                weight=0.10,
                details="Username proporcionado pero sin perfiles sociales para comparar.",
            )

        if not data.username:
            # Verificar si los usernames en diferentes plataformas son consistentes entre sí
            usernames = [
                p.username.lower()
                for p in data.social_profiles
                if p.username
            ]
            if len(usernames) < 2:
                return CorrelationSignal(
                    name="Consistencia de nombre de usuario",
                    passed=True,
                    score=50.0,
                    weight=0.10,
                    details="Solo un perfil con username visible. No hay suficiente información para comparar.",
                )

            unique_usernames = set(usernames)
            if len(unique_usernames) == 1:
                return CorrelationSignal(
                    name="Consistencia de nombre de usuario",
                    passed=True,
                    score=100.0,
                    weight=0.10,
                    details=f"Todos los perfiles usan el mismo username: {usernames[0]}.",
                )
            else:
                return CorrelationSignal(
                    name="Consistencia de nombre de usuario",
                    passed=False,
                    score=30.0,
                    weight=0.10,
                    details=f"Los perfiles usan usernames diferentes: {', '.join(unique_usernames)}.",
                )

        # Verificar username declarado vs perfiles
        declared_username = data.username.lower()
        matching_profiles = 0
        total_with_username = 0
        details_parts: List[str] = []

        for profile in data.social_profiles:
            if profile.username:
                total_with_username += 1
                profile_username = profile.username.lower()
                if profile_username == declared_username or declared_username in profile_username:
                    matching_profiles += 1
                    details_parts.append(
                        f"Username en {profile.platform} ({profile_username}) coincide con el declarado."
                    )
                else:
                    details_parts.append(
                        f"Username en {profile.platform} ({profile_username}) difiere del declarado ({declared_username})."
                    )

        if total_with_username == 0:
            return CorrelationSignal(
                name="Consistencia de nombre de usuario",
                passed=True,
                score=50.0,
                weight=0.10,
                details="Username declarado pero los perfiles no tienen username visible.",
            )

        score = (matching_profiles / total_with_username) * 100
        passed = score >= 70.0

        return CorrelationSignal(
            name="Consistencia de nombre de usuario",
            passed=passed,
            score=round(score, 2),
            weight=0.10,
            details="; ".join(details_parts),
        )

    # ── Cálculo del puntaje global ───────────────────────────────────────

    @staticmethod
    def _calculate_confidence(signals: List[CorrelationSignal]) -> float:
        """
        Calcula la puntuación de confianza de identidad como promedio ponderado.

        Las señales con mayor peso contribuyen más al puntaje global.
        Si no hay señales con datos suficientes, se retorna un valor bajo.

        Args:
            signals: Lista de señales de correlación evaluadas.

        Returns:
            float: Puntuación de confianza de identidad (0-100).
        """
        if not signals:
            return 0.0

        total_weight = sum(s.weight for s in signals)
        if total_weight == 0:
            return 0.0

        weighted_sum = sum(s.score * s.weight for s in signals)
        confidence = weighted_sum / total_weight

        return max(0.0, min(100.0, confidence))
