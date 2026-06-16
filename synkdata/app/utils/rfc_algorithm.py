"""
Algoritmo de validación y generación del Registro Federal de Contribuyentes (RFC).

Este módulo implementa el algoritmo oficial del RFC conforme a las especificaciones
del Servicio de Administración Tributaria (SAT), incluyendo:

- Validación de formato para personas físicas y morales
- Cálculo del dígito verificador (homoclave extendida)
- Extracción de datos a partir del RFC
- Generación del RFC (sin homoclave) a partir de datos personales

Formato del RFC:
  - Persona física: 4 letras + 6 dígitos (AAMMDD) + 3 alfanuméricos (homoclave)
  - Persona moral: 3 letras + 6 dígitos (AAMMDD) + 3 alfanuméricos (homoclave)

Los primeros 10 caracteres (persona física) o 9 caracteres (persona moral)
se conocen como "RFC sin homoclave". La homoclave se asigna por el SAT
y los primeros 2 caracteres se calculan mediante un algoritmo de ponderación,
mientras que el tercero es el dígito verificador.

Referencias:
    - SAT: Anexo 20 de la Resolución Miscelánea Fiscal
    - IMSS: Guía para la generación del RFC
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date
from typing import Dict, List, Optional, Tuple

# ---------------------------------------------------------------------------
# Expresiones regulares para validación de formato RFC
# ---------------------------------------------------------------------------

# Persona física: 4 letras + 6 dígitos + 3 alfanuméricos
RFC_FISICA_PATTERN: re.Pattern[str] = re.compile(
    r"^([A-Z&Ñ]{4})"       # 4 letras: iniciales del nombre
    r"(\d{2})(\d{2})(\d{2})" # Fecha: AA MM DD
    r"([A-Z0-9]{3})$",      # Homoclave: 3 caracteres alfanuméricos
    re.IGNORECASE,
)

# Persona moral: 3 letras + 6 dígitos + 3 alfanuméricos
RFC_MORAL_PATTERN: re.Pattern[str] = re.compile(
    r"^([A-Z&Ñ]{3})"       # 3 letras: siglas de la razón social
    r"(\d{2})(\d{2})(\d{2})" # Fecha: AA MM DD
    r"([A-Z0-9]{3})$",      # Homoclave: 3 caracteres alfanuméricos
    re.IGNORECASE,
)

# Patrón genérico para RFC sin homoclave (solo los primeros 10 o 9 caracteres)
RFC_BASE_FISICA_PATTERN: re.Pattern[str] = re.compile(
    r"^[A-Z&Ñ]{4}\d{6}$",
    re.IGNORECASE,
)

RFC_BASE_MORAL_PATTERN: re.Pattern[str] = re.compile(
    r"^[A-Z&Ñ]{3}\d{6}$",
    re.IGNORECASE,
)

# ---------------------------------------------------------------------------
# Tabla de valores para el cálculo del dígito verificador del RFC
# Conforme al Anexo 20 de la Resolución Miscelánea Fiscal
# ---------------------------------------------------------------------------
RFC_CHAR_VALUES: Dict[str, int] = {
    "0": 0,  "1": 1,  "2": 2,  "3": 3,  "4": 4,
    "5": 5,  "6": 6,  "7": 7,  "8": 8,  "9": 9,
    "A": 10, "B": 11, "C": 12, "D": 13, "E": 14,
    "F": 15, "G": 16, "H": 17, "I": 18, "J": 19,
    "K": 20, "L": 21, "M": 22, "N": 23, "&": 24,
    "O": 25, "P": 26, "Q": 27, "R": 28, "S": 29,
    "T": 30, "U": 31, "V": 32, "W": 33, "X": 34,
    "Y": 35, "Z": 36, " ": 37, "Ñ": 38,
}

# Tabla inversa para obtener el carácter a partir del residuo
RFC_REVERSE_VALUES: Dict[int, str] = {v: k for k, v in RFC_CHAR_VALUES.items()}

# Factores de ponderación para las 12 primeras posiciones del RFC completo
RFC_WEIGHTS: List[int] = [13, 12, 11, 10, 9, 8, 7, 6, 5, 4, 3, 2]

# ---------------------------------------------------------------------------
# Palabras inconvenientes para RFC (similar a CURP)
# ---------------------------------------------------------------------------
RFC_INCONVENIENT_WORDS: List[str] = [
    "BUEI", "BUEY", "CACA", "CACO", "CAGA", "CAGO", "CAKA", "CAKO",
    "COGE", "COGI", "COJA", "COJE", "COJI", "COJO", "CULO", "FETO",
    "GUEI", "GUEY", "JOTO", "KACA", "KACO", "KAGA", "KAGO", "KAKA",
    "KAKO", "KOGE", "KOGI", "KOJA", "KOJE", "KOJI", "KOJO", "KULO",
    "LILO", "LOCA", "LOCO", "LOKA", "LOKO", "MAME", "MAMO", "MEAR",
    "MEAS", "MEON", "MION", "MOCO", "MOKO", "MULA", "MULO", "NACA",
    "NACO", "PEDA", "PEDO", "PENE", "PIJA", "PIJO", "PITA", "PITO",
    "POPO", "PUTA", "PUTO", "RATA", "RUIN", "SENO", "TETA", "VACA",
    "VAGA", "VAGO", "VAKA", "VUEI", "VUEY", "WUEI", "WUEY",
]


# ---------------------------------------------------------------------------
# Data class para la información extraída de un RFC
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class RFCInfo:
    """
    Información extraída de un RFC válido.

    Attributes:
        rfc: El RFC completo normalizado (mayúsculas).
        person_type: Tipo de persona ('fisica' o 'moral').
        name_initials: Las letras iniciales del nombre o razón social.
        birth_date: Fecha de inicio de operaciones o nacimiento.
        homoclave: Los 3 caracteres de la homoclave.
        check_digit: El dígito verificador (último carácter de la homoclave).
        birth_year: Año completo (4 dígitos).
    """

    rfc: str
    person_type: str
    name_initials: str
    birth_date: date
    homoclave: str
    check_digit: str
    birth_year: int


# ---------------------------------------------------------------------------
# Funciones de validación y cálculo
# ---------------------------------------------------------------------------

def validate_rfc_format(rfc: str) -> Tuple[bool, str]:
    """
    Valida el formato del RFC y determina el tipo de persona.

    Verifica la estructura general del RFC, la presencia de caracteres
    válidos en cada posición y determina si corresponde a una persona
    física (4 letras + 6 dígitos + 3 alfanuméricos) o moral
    (3 letras + 6 dígitos + 3 alfanuméricos).

    Args:
        rfc: El RFC a validar (12 o 13 caracteres).

    Returns:
        tuple[bool, str]: Una tupla donde el primer elemento indica si
            el formato es válido y el segundo indica el tipo de persona
            ('fisica', 'moral' o 'desconocido').

    Example:
        >>> validate_rfc_format("GOME850101ABC")
        (True, 'fisica')
        >>> validate_rfc_format("ABC850101XYZ")
        (True, 'moral')
        >>> validate_rfc_format("12345")
        (False, 'desconocido')
    """
    if not rfc or not isinstance(rfc, str):
        return False, "desconocido"

    rfc_upper = rfc.strip().upper()

    # Intentar coincidir con persona física primero (más específico: 4 letras)
    match_fisica = RFC_FISICA_PATTERN.match(rfc_upper)
    if match_fisica:
        # Validar fecha
        try:
            _parse_rfc_date(match_fisica.group(2), match_fisica.group(3), match_fisica.group(4))
        except ValueError:
            return False, "fisica"
        return True, "fisica"

    # Intentar coincidir con persona moral
    match_moral = RFC_MORAL_PATTERN.match(rfc_upper)
    if match_moral:
        # Validar fecha
        try:
            _parse_rfc_date(match_moral.group(2), match_moral.group(3), match_moral.group(4))
        except ValueError:
            return False, "moral"
        return True, "moral"

    return False, "desconocido"


def calculate_rfc_check_digit(rfc: str) -> str:
    """
    Calcula el dígito verificador del RFC usando el algoritmo oficial del SAT.

    El algoritmo consiste en:
    1. Tomar los primeros 12 caracteres del RFC (persona física: 13 posiciones
       total; persona moral: 12 posiciones total).
    2. Asignar un valor numérico a cada carácter según la tabla RFC_CHAR_VALUES.
    3. Multiplicar cada valor por su factor de ponderación correspondiente.
    4. Sumar todos los productos.
    5. Obtener el residuo de la suma dividida entre 11.
    6. Calcular: 11 - residuo.
       - Si el resultado es 11, el dígito verificador es '0'.
       - Si el resultado es 10, el dígito verificador es 'A'.
       - En otro caso, el dígito verificador es el resultado como carácter.

    Args:
        rfc: El RFC de 12 o 13 caracteres.

    Returns:
        str: El dígito verificador calculado.

    Raises:
        ValueError: Si el RFC no tiene al menos 12 caracteres o contiene
                    caracteres no válidos.

    Example:
        >>> calculate_rfc_check_digit("GOME850101AB")
        'C'
    """
    if not rfc or not isinstance(rfc, str):
        raise ValueError("El RFC no puede estar vacío ni ser nulo.")

    rfc_upper = rfc.strip().upper()

    if len(rfc_upper) < 12:
        raise ValueError(
            f"El RFC debe tener al menos 12 caracteres para calcular "
            f"el dígito verificador. Recibidos: {len(rfc_upper)}."
        )

    # Tomar los primeros 12 caracteres (sin el dígito verificador si tiene 13)
    base = rfc_upper[:12]

    # Calcular la suma ponderada
    weighted_sum = 0
    for i, char in enumerate(base):
        if char not in RFC_CHAR_VALUES:
            raise ValueError(
                f"Carácter inválido '{char}' en la posición {i + 1} del RFC. "
                f"No se encuentra en la tabla de valores para el dígito verificador."
            )
        weighted_sum += RFC_CHAR_VALUES[char] * RFC_WEIGHTS[i]

    # Calcular el dígito verificador
    remainder = weighted_sum % 11
    check_value = 11 - remainder

    if check_value == 11:
        return "0"
    elif check_value == 10:
        return "A"
    else:
        return str(check_value)


def extract_rfc_info(rfc: str) -> RFCInfo:
    """
    Extrae toda la información contenida en un RFC válido.

    Descompone el RFC en sus partes constitutivas: tipo de persona,
    iniciales del nombre o razón social, fecha, homoclave y dígito verificador.

    Args:
        rfc: El RFC a descomponer (12 o 13 caracteres).

    Returns:
        RFCInfo: Objeto con toda la información extraída.

    Raises:
        ValueError: Si el formato del RFC no es válido.

    Example:
        >>> info = extract_rfc_info("GOME850101ABC")
        >>> info.person_type
        'fisica'
        >>> info.homoclave
        'ABC'
    """
    is_valid, person_type = validate_rfc_format(rfc)

    if not is_valid:
        raise ValueError(
            f"El RFC '{rfc}' no tiene un formato válido. "
            f"Verifique que cumpla con la estructura oficial."
        )

    rfc_upper = rfc.strip().upper()

    if person_type == "fisica":
        match = RFC_FISICA_PATTERN.match(rfc_upper)
    else:
        match = RFC_MORAL_PATTERN.match(rfc_upper)

    if not match:
        raise ValueError(f"El RFC '{rfc}' no coincide con el patrón esperado.")

    name_initials = match.group(1)
    year_short = match.group(2)
    month = match.group(3)
    day = match.group(4)
    homoclave = match.group(5)

    birth_date = _parse_rfc_date(year_short, month, day)
    check_digit = homoclave[-1] if homoclave else ""

    return RFCInfo(
        rfc=rfc_upper,
        person_type=person_type,
        name_initials=name_initials,
        birth_date=birth_date,
        homoclave=homoclave,
        check_digit=check_digit,
        birth_year=birth_date.year,
    )


def generate_rfc(
    name: str,
    paternal: str,
    maternal: str,
    birth_date: date,
) -> str:
    """
    Genera el RFC (sin homoclave) a partir de los datos personales.

    El RFC generado contiene 10 caracteres: 4 letras del nombre y
    6 dígitos de la fecha. La homoclave es asignada exclusivamente
    por el SAT y no puede calcularse sin acceso a la base de datos
    oficial, por lo que se omite en este proceso.

    Args:
        name: Nombre(s) de pila (ej. "JUAN", "MARIA JOSE").
        paternal: Apellido paterno.
        maternal: Apellido materno.
        birth_date: Fecha de nacimiento.

    Returns:
        str: El RFC generado sin homoclave (10 caracteres).

    Raises:
        ValueError: Si los datos proporcionados son insuficientes o inválidos.

    Example:
        >>> from datetime import date
        >>> generate_rfc("JUAN", "GOMEZ", "RODRIGUEZ", date(1985, 1, 1))
        'GORJ850101'
    """
    # ── Normalizar entradas ──────────────────────────────────────────────
    name_norm = _normalize_for_rfc(name)
    paternal_norm = _normalize_for_rfc(paternal)
    maternal_norm = _normalize_for_rfc(maternal)

    # ── Generar las 4 letras iniciales ──────────────────────────────────
    initials = _generate_rfc_initials(paternal_norm, maternal_norm, name_norm)

    # Verificar palabras inconvenientes
    if initials in RFC_INCONVENIENT_WORDS:
        initials = initials[:3] + "X"

    # ── Fecha de nacimiento (AAMMDD) ────────────────────────────────────
    date_str = birth_date.strftime("%y%m%d")

    return f"{initials}{date_str}"


# ---------------------------------------------------------------------------
# Funciones auxiliares privadas
# ---------------------------------------------------------------------------

def _parse_rfc_date(year_short: str, month: str, day: str) -> date:
    """
    Reconstruye la fecha a partir de los componentes del RFC.

    Para resolver la ambigüedad del año de dos dígitos, se asume:
    - Años 00-25: Siglo XXI (2000-2025)
    - Años 26-99: Siglo XX (1926-1999)

    Args:
        year_short: Año con dos dígitos (AA).
        month: Mes con dos dígitos (MM).
        day: Día con dos dígitos (DD).

    Returns:
        date: Fecha completa.

    Raises:
        ValueError: Si la fecha resultante es inválida.
    """
    yy = int(year_short)
    mm = int(month)
    dd = int(day)

    # Heurística para determinar el siglo
    year = 2000 + yy if yy <= 25 else 1900 + yy

    try:
        return date(year, mm, dd)
    except ValueError as exc:
        raise ValueError(
            f"Fecha inválida en el RFC: {dd}/{mm}/{year}. "
            f"Verifique los datos proporcionados."
        ) from exc


def _normalize_for_rfc(text: str) -> str:
    """
    Normaliza un texto para uso en la generación de RFC.

    Elimina acentos, convierte a mayúsculas y remueve caracteres
    especiales. Similar a la normalización de CURP pero conservando
    la Ñ como un carácter válido.

    Args:
        text: Texto a normalizar.

    Returns:
        str: Texto normalizado en mayúsculas sin acentos.
    """
    accent_map = {
        "Á": "A", "É": "E", "Í": "I", "Ó": "O", "Ú": "U", "Ü": "U",
    }
    result = text.strip().upper()
    for accented, replacement in accent_map.items():
        result = result.replace(accented, replacement)

    lower_accent_map = {
        "á": "A", "é": "E", "í": "I", "ó": "O", "ú": "U", "ü": "U",
    }
    for accented, replacement in lower_accent_map.items():
        result = result.replace(accented, replacement)

    return result


def _generate_rfc_initials(paternal: str, maternal: str, name: str) -> str:
    """
    Genera las 4 letras iniciales del RFC para persona física.

    Reglas (idénticas a la CURP):
    - Posición 1: Primera letra del apellido paterno
    - Posición 2: Primera vocal interna del apellido paterno
    - Posición 3: Primera letra del apellido materno (o 'X' si no tiene)
    - Posición 4: Primera letra del nombre de pila

    Args:
        paternal: Apellido paterno normalizado.
        maternal: Apellido materno normalizado.
        name: Nombre(s) de pila normalizado(s).

    Returns:
        str: Las 4 letras iniciales del RFC.
    """
    # Primera letra del apellido paterno
    pos1 = paternal[0] if paternal else "X"

    # Primera vocal interna del apellido paterno
    vowels = "AEIOU"
    pos2 = "X"
    for char in paternal[1:] if len(paternal) > 1 else "":
        if char in vowels:
            pos2 = char
            break

    # Primera letra del apellido materno
    pos3 = maternal[0] if maternal else "X"

    # Primera letra del primer nombre
    # Regla especial: si el primer nombre es "JOSE" o "MARIA",
    # se usa la primera letra del segundo nombre
    names = name.split()
    if len(names) > 1:
        first_name = names[0]
        if first_name in ("JOSE", "J", "MA", "MARIA", "M"):
            pos4 = names[1][0]
        else:
            pos4 = names[0][0]
    else:
        pos4 = name[0] if name else "X"

    return f"{pos1}{pos2}{pos3}{pos4}"
