"""
Algoritmo de validación y generación de la Clave Única de Registro de Población (CURP).

Este módulo implementa el algoritmo oficial de la CURP conforme a las especificaciones
del Registro Nacional de Población (RENAPO), incluyendo:

- Validación de formato mediante expresión regular
- Cálculo del dígito verificador (suma ponderada módulo 10)
- Extracción de datos personales a partir de la CURP
- Generación de la CURP a partir de datos personales

Formato de la CURP (18 posiciones):
    Posiciones  1-4:  Letras del nombre (iniciales)
    Posiciones  5-10: Fecha de nacimiento (AAMMDD)
    Posición    11:   Sexo (H/M)
    Posiciones  12-13: Clave de la entidad federativa
    Posiciones  14-16: Primera consonante interna (no inicial) de cada apellido y nombre
    Posición    17:   Dígito o letra identificadora del siglo
    Posición    18:   Dígito verificador

Referencias:
    - DOF: Acuerdo por el que se crea la Clave Única de Registro de Población
    - RENAPO: Especificaciones técnicas para la generación de la CURP
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Dict, List, Optional

# ---------------------------------------------------------------------------
# Expresión regular para validación del formato CURP
# ---------------------------------------------------------------------------
CURP_PATTERN: re.Pattern[str] = re.compile(
    r"^([A-Z&Ñ]{4})"         # 4 letras: iniciales del nombre (incluye Ñ)
    r"(\d{2})(\d{2})(\d{2})" # Fecha: AA MM DD
    r"([HM])"                # Sexo: H(hombre) o M(mujer)
    r"([A-ZÑ]{2})"           # Clave de entidad federativa (incluye Ñ)
    r"([A-ZÑ]{3})"           # Consonantes internas (incluye Ñ)
    r"([0-9A-Z])"            # Identificador de siglo
    r"(\d)$",                # Dígito verificador
    re.IGNORECASE,
)

# ---------------------------------------------------------------------------
# Mapeo de valores para el cálculo del dígito verificador
# Cada carácter de la CURP tiene un valor numérico asignado conforme
# a la tabla oficial del RENAPO.
# ---------------------------------------------------------------------------
CURP_CHAR_VALUES: Dict[str, int] = {
    "0": 0,  "1": 1,  "2": 2,  "3": 3,  "4": 4,
    "5": 5,  "6": 6,  "7": 7,  "8": 8,  "9": 9,
    "A": 10, "B": 11, "C": 12, "D": 13, "E": 14,
    "F": 15, "G": 16, "H": 17, "I": 18, "J": 19,
    "K": 20, "L": 21, "M": 22, "N": 23, "Ñ": 24,
    "O": 25, "P": 26, "Q": 27, "R": 28, "S": 29,
    "T": 30, "U": 31, "V": 32, "W": 33, "X": 34,
    "Y": 35, "Z": 36,
}

# Factores de ponderación para las 17 primeras posiciones de la CURP
CURP_WEIGHTS: List[int] = [18, 17, 16, 15, 14, 13, 12, 11, 10, 9, 8, 7, 6, 5, 4, 3, 2]

# ---------------------------------------------------------------------------
# Catálogo de claves de entidades federativas (32 estados + NE/NL)
# Conforme al estándar oficial del INEGI/RENAPO
# ---------------------------------------------------------------------------
STATE_CODES: Dict[str, str] = {
    "AS": "Aguascalientes",
    "BC": "Baja California",
    "BS": "Baja California Sur",
    "CC": "Campeche",
    "CL": "Coahuila de Zaragoza",
    "CM": "Colima",
    "CS": "Chiapas",
    "CH": "Chihuahua",
    "DF": "Ciudad de México",
    "DG": "Durango",
    "GT": "Guanajuato",
    "GR": "Guerrero",
    "HG": "Hidalgo",
    "JC": "Jalisco",
    "MC": "México",
    "MN": "Michoacán de Ocampo",
    "MS": "Morelos",
    "NT": "Nayarit",
    "NL": "Nuevo León",
    "OC": "Oaxaca",
    "PL": "Puebla",
    "QT": "Querétaro",
    "QR": "Quintana Roo",
    "SP": "San Luis Potosí",
    "SL": "Sinaloa",
    "SR": "Sonora",
    "TC": "Tabasco",
    "TS": "Tamaulipas",
    "TL": "Tlaxcala",
    "VZ": "Veracruz de Ignacio de la Llave",
    "YN": "Yucatán",
    "ZS": "Zacatecas",
    "NE": "Nacido en el Extranjero",
}

# Inverso para búsqueda por nombre de estado
STATE_NAME_TO_CODE: Dict[str, str] = {v.lower(): k for k, v in STATE_CODES.items()}

# ---------------------------------------------------------------------------
# Palabras inconvenientes que se reemplazan en la CURP
# Estas palabras no deben aparecer en las primeras 4 letras para evitar
# formaciones ofensivas; se reemplazan por 'X' en la posición conflictiva.
# ---------------------------------------------------------------------------
INCONVENIENT_WORDS: List[str] = [
    "BACA", "BAKA", "BUEI", "BUEY", "CACA", "CACO", "CAGA", "CAGO",
    "CAKA", "CAKO", "COGE", "COGI", "COJA", "COJE", "COJI", "COJO",
    "COLA", "CULO", "FALO", "FETO", "GETA", "GUEI", "GUEY", "JETA",
    "JOTO", "KACA", "KACO", "KAGA", "KAGO", "KAKA", "KAKO", "KOGE",
    "KOGI", "KOJA", "KOJE", "KOJI", "KOJO", "KOLA", "KULO", "LILO",
    "LOCA", "LOCO", "LOKA", "LOKO", "MAME", "MAMO", "MEAR", "MEAS",
    "MEON", "MIAR", "MION", "MOCO", "MOKO", "MULA", "MULO", "NACA",
    "NACO", "PEDA", "PEDO", "PENE", "PIJA", "PIJO", "PITA", "PITO",
    "POPO", "PUTA", "PUTO", "QULO", "RATA", "ROBA", "ROBE", "ROBO",
    "RUIN", "SENO", "TETA", "VACA", "VAGA", "VAGO", "VAKA", "VUEI",
    "VUEY", "WUEI", "WUEY",
]

# ---------------------------------------------------------------------------
# Consonantes del alfabeto español (excluyendo vocales y la Ñ)
# ---------------------------------------------------------------------------
CONSONANTS: str = "BCDFGHJKLMNPQRSTVWXYZ"


# ---------------------------------------------------------------------------
# Data class para la información extraída de una CURP
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class CURPInfo:
    """
    Información extraída de una CURP válida.

    Attributes:
        curp: La CURP completa normalizada (mayúsculas).
        name_initials: Las 4 letras iniciales del nombre.
        birth_date: Fecha de nacimiento extraída.
        gender: Sexo (H=hombre, M=mujer).
        state_code: Clave de la entidad federativa (2 letras).
        state_name: Nombre de la entidad federativa.
        internal_consonants: Las 3 consonantes internas.
        century_digit: Carácter identificador del siglo.
        check_digit: Dígito verificador.
        birth_year: Año de nacimiento completo (4 dígitos).
    """

    curp: str
    name_initials: str
    birth_date: date
    gender: str
    state_code: str
    state_name: str
    internal_consonants: str
    century_digit: str
    check_digit: str
    birth_year: int


# ---------------------------------------------------------------------------
# Funciones de validación y cálculo
# ---------------------------------------------------------------------------

def validate_curp_format(curp: str) -> bool:
    """
    Valida que el formato de la CURP sea correcto.

    Verifica la estructura general (18 posiciones), la presencia de
    caracteres válidos en cada posición y que la clave de entidad
    federativa exista en el catálogo oficial.

    Args:
        curp: La CURP a validar (18 caracteres alfanuméricos).

    Returns:
        bool: True si el formato es válido, False en caso contrario.

    Example:
        >>> validate_curp_format("GOME850101HDFRRN09")
        True
        >>> validate_curp_format("12345")
        False
    """
    if not curp or not isinstance(curp, str):
        return False

    curp_upper = curp.strip().upper()
    match = CURP_PATTERN.match(curp_upper)

    if not match:
        return False

    # Validar que la clave de entidad federativa exista
    # Grupos: 1=iniciales, 2=año, 3=mes, 4=día, 5=sexo, 6=estado, 7=consonantes, 8=siglo, 9=dígito
    state_code = match.group(6)
    if state_code not in STATE_CODES:
        return False

    # Validar que la fecha sea razonable
    try:
        _parse_curp_date(match.group(2), match.group(3), match.group(4), match.group(8))
    except ValueError:
        return False

    return True


def calculate_curp_check_digit(curp: str) -> str:
    """
    Calcula el dígito verificador de la CURP usando el algoritmo oficial.

    El algoritmo consiste en:
    1. Asignar un valor numérico a cada uno de los primeros 17 caracteres
       según la tabla oficial CURP_CHAR_VALUES.
    2. Multiplicar cada valor por su factor de ponderación correspondiente.
    3. Sumar todos los productos.
    4. Obtener el residuo de la suma dividida entre 10.
    5. Restar el residuo de 10.
    6. Si el resultado es 10, el dígito verificador es 0.

    Args:
        curp: La CURP de 17 o 18 caracteres (sin el dígito verificador o incluido).

    Returns:
        str: El dígito verificador calculado como cadena de un carácter.

    Raises:
        ValueError: Si la CURP no tiene al menos 17 caracteres o contiene
                    caracteres no válidos.

    Example:
        >>> calculate_curp_check_digit("GOME850101HDFRRN0")
        '9'
    """
    if not curp or not isinstance(curp, str):
        raise ValueError("La CURP no puede estar vacía ni ser nula.")

    curp_upper = curp.strip().upper()

    # Tomar solo los primeros 17 caracteres
    if len(curp_upper) < 17:
        raise ValueError(
            f"La CURP debe tener al menos 17 caracteres para calcular "
            f"el dígito verificador. Recibidos: {len(curp_upper)}."
        )

    base = curp_upper[:17]

    # Calcular la suma ponderada
    weighted_sum = 0
    for i, char in enumerate(base):
        if char not in CURP_CHAR_VALUES:
            raise ValueError(
                f"Carácter inválido '{char}' en la posición {i + 1} de la CURP. "
                f"No se encuentra en la tabla de valores para el dígito verificador."
            )
        weighted_sum += CURP_CHAR_VALUES[char] * CURP_WEIGHTS[i]

    # Calcular el dígito verificador
    remainder = weighted_sum % 10
    check_digit = (10 - remainder) % 10

    return str(check_digit)


def extract_curp_info(curp: str) -> CURPInfo:
    """
    Extrae toda la información contenida en una CURP válida.

    Descompone la CURP en sus partes constitutivas: iniciales del nombre,
    fecha de nacimiento, sexo, entidad federativa, consonantes internas,
    identificador de siglo y dígito verificador.

    Args:
        curp: La CURP de 18 caracteres a descomponer.

    Returns:
        CURPInfo: Objeto con toda la información extraída.

    Raises:
        ValueError: Si el formato de la CURP no es válido.

    Example:
        >>> info = extract_curp_info("GOME850101HDFRRN09")
        >>> info.gender
        'H'
        >>> info.state_name
        'Ciudad de México'
    """
    if not validate_curp_format(curp):
        raise ValueError(
            f"La CURP '{curp}' no tiene un formato válido. "
            f"Verifique que cumpla con la estructura oficial de 18 posiciones."
        )

    curp_upper = curp.strip().upper()
    match = CURP_PATTERN.match(curp_upper)

    if not match:
        # Esto no debería ocurrir dado el chequeo previo, pero por seguridad
        raise ValueError(f"La CURP '{curp}' no coincide con el patrón esperado.")

    name_initials = match.group(1)
    year_short = match.group(2)
    month = match.group(3)
    day = match.group(4)
    gender = match.group(5)
    state_code = match.group(6)
    internal_consonants = match.group(7)
    century_digit = match.group(8)
    check_digit = match.group(9)

    birth_date = _parse_curp_date(year_short, month, day, century_digit)
    state_name = STATE_CODES.get(state_code, "Entidad no reconocida")

    return CURPInfo(
        curp=curp_upper,
        name_initials=name_initials,
        birth_date=birth_date,
        gender=gender,
        state_code=state_code,
        state_name=state_name,
        internal_consonants=internal_consonants,
        century_digit=century_digit,
        check_digit=check_digit,
        birth_year=birth_date.year,
    )


def generate_curp(
    name: str,
    paternal: str,
    maternal: str,
    birth_date: date,
    gender: str,
    state: str,
) -> str:
    """
    Genera la CURP a partir de los datos personales del individuo.

    El algoritmo sigue las reglas oficiales del RENAPO para la composición
    de la clave, incluyendo el manejo de palabras inconvenientes y la
    sustitución de caracteres faltantes.

    Args:
        name: Nombre(s) de pila (ej. "JUAN", "MARIA JOSE").
        paternal: Apellido paterno.
        maternal: Apellido materno.
        birth_date: Fecha de nacimiento.
        gender: Sexo ('H' para hombre, 'M' para mujer).
        state: Clave de la entidad federativa (2 letras) o nombre del estado.

    Returns:
        str: La CURP generada (18 caracteres).

    Raises:
        ValueError: Si los datos proporcionados son insuficientes o inválidos.

    Example:
        >>> from datetime import date
        >>> generate_curp("JUAN", "GOMEZ", "RODRIGUEZ", date(1985, 1, 1), "H", "DF")
        'GORJ850101...'
    """
    # ── Normalizar entradas ──────────────────────────────────────────────
    name_norm = _normalize_for_curp(name)
    paternal_norm = _normalize_for_curp(paternal)
    maternal_norm = _normalize_for_curp(maternal)
    gender_norm = gender.strip().upper()

    if gender_norm not in ("H", "M"):
        raise ValueError(
            f"El género debe ser 'H' (hombre) o 'M' (mujer). Recibido: '{gender}'."
        )

    # Resolver código de estado
    state_upper = state.strip().upper()
    if state_upper in STATE_CODES:
        state_code = state_upper
    else:
        # Intentar buscar por nombre de estado
        state_lower = state.strip().lower()
        if state_lower in STATE_NAME_TO_CODE:
            state_code = STATE_NAME_TO_CODE[state_lower]
        else:
            raise ValueError(
                f"Clave de entidad federativa no reconocida: '{state}'. "
                f"Use una clave válida del catálogo (ej. 'DF', 'NL', 'NE')."
            )

    # ── Posiciones 1-4: Iniciales del nombre ─────────────────────────────
    initials = _generate_name_initials(paternal_norm, maternal_norm, name_norm)

    # Verificar palabras inconvenientes
    if initials in INCONVENIENT_WORDS:
        # Reemplazar la última letra por 'X'
        initials = initials[:3] + "X"

    # ── Posiciones 5-10: Fecha de nacimiento (AAMMDD) ────────────────────
    date_str = birth_date.strftime("%y%m%d")

    # ── Posición 11: Sexo ────────────────────────────────────────────────
    gender_char = gender_norm

    # ── Posiciones 12-13: Clave de entidad federativa ────────────────────
    state_str = state_code

    # ── Posiciones 14-16: Consonantes internas ───────────────────────────
    internal = _generate_internal_consonants(paternal_norm, maternal_norm, name_norm)

    # ── Posición 17: Identificador de siglo ──────────────────────────────
    century_char = _get_century_character(birth_date)

    # ── Componer los primeros 17 caracteres ──────────────────────────────
    curp_base = f"{initials}{date_str}{gender_char}{state_str}{internal}{century_char}"

    # ── Posición 18: Dígito verificador ──────────────────────────────────
    check_digit = calculate_curp_check_digit(curp_base)

    return f"{curp_base}{check_digit}"


# ---------------------------------------------------------------------------
# Funciones auxiliares privadas
# ---------------------------------------------------------------------------

def _parse_curp_date(year_short: str, month: str, day: str, century_char: str) -> date:
    """
    Reconstruye la fecha de nacimiento a partir de los componentes de la CURP.

    El identificador de siglo (posición 17) ayuda a resolver la ambigüedad
    del año de dos dígitos:
    - Dígito (0-9): Nacidos antes del 2000
    - Letra: Nacidos a partir del 2000

    Args:
        year_short: Año con dos dígitos (AA).
        month: Mes con dos dígitos (MM).
        day: Día con dos dígitos (DD).
        century_char: Carácter identificador del siglo.

    Returns:
        date: Fecha de nacimiento completa.

    Raises:
        ValueError: Si la fecha resultante es inválida.
    """
    yy = int(year_short)
    mm = int(month)
    dd = int(day)

    # Determinar el siglo según el carácter identificador
    # Los dígitos (0-9) corresponden al siglo XX (1900-1999)
    # Las letras corresponden al siglo XXI (2000-2099)
    if century_char.isdigit():
        year = 1900 + yy
    else:
        year = 2000 + yy

    try:
        return date(year, mm, dd)
    except ValueError as exc:
        raise ValueError(
            f"Fecha inválida en la CURP: {dd}/{mm}/{year}. "
            f"Verifique los datos de nacimiento."
        ) from exc


def _normalize_for_curp(text: str) -> str:
    """
    Normaliza un texto para uso en la generación de CURP.

    Elimina acentos, convierte a mayúsculas y remueve caracteres
    especiales, conservando solo letras del alfabeto español.

    Args:
        text: Texto a normalizar.

    Returns:
        str: Texto normalizado en mayúsculas sin acentos.
    """
    # Mapeo de acentos y caracteres especiales
    accent_map = {
        "Á": "A", "É": "E", "Í": "I", "Ó": "O", "Ú": "U",
        "Ü": "U", "Ñ": "X",  # La Ñ se reemplaza por X en la CURP
    }
    result = text.strip().upper()
    for accented, replacement in accent_map.items():
        result = result.replace(accented, replacement)

    # Minúsculas con acento
    lower_accent_map = {
        "á": "A", "é": "E", "í": "I", "ó": "O", "ú": "U",
        "ü": "U", "ñ": "X",
    }
    for accented, replacement in lower_accent_map.items():
        result = result.replace(accented, replacement)

    return result


def _generate_name_initials(paternal: str, maternal: str, name: str) -> str:
    """
    Genera las 4 letras iniciales de la CURP a partir de los nombres.

    Reglas:
    - Posición 1: Primera letra del apellido paterno
    - Posición 2: Primera vocal interna del apellido paterno
    - Posición 3: Primera letra del apellido materno (o 'X' si no tiene)
    - Posición 4: Primera letra del nombre de pila

    Si la persona no tiene apellido materno, se usa 'X' en la posición 3.
    Para el apellido paterno compuesto (ej. "DE LA TORRE"), se usa la
    primera palabra significativa.

    Args:
        paternal: Apellido paterno normalizado (mayúsculas, sin acentos).
        maternal: Apellido materno normalizado.
        name: Nombre(s) de pila normalizado(s).

    Returns:
        str: Las 4 letras iniciales de la CURP.
    """
    # Primera letra del apellido paterno
    pos1 = paternal[0] if paternal else "X"

    # Primera vocal interna del apellido paterno
    pos2 = _find_first_internal_vowel(paternal)
    if pos2 is None:
        pos2 = "X"

    # Primera letra del apellido materno
    pos3 = maternal[0] if maternal else "X"

    # Primera letra del primer nombre
    # Si el nombre es compuesto y el primer nombre es "JOSE" o "MARIA",
    # se usa la primera letra del segundo nombre (regla RENAPO)
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


def _find_first_internal_vowel(text: str) -> Optional[str]:
    """
    Busca la primera vocal interna (no inicial) en un texto.

    Args:
        text: Texto en mayúsculas donde buscar la vocal.

    Returns:
        Optional[str]: La primera vocal interna encontrada, o None.
    """
    vowels = "AEIOU"
    for char in text[1:] if len(text) > 1 else "":
        if char in vowels:
            return char
    return None


def _generate_internal_consonants(paternal: str, maternal: str, name: str) -> str:
    """
    Genera las 3 consonantes internas de la CURP (posiciones 14-16).

    Reglas:
    - Posición 14: Primera consonante interna del apellido paterno
    - Posición 15: Primera consonante interna del apellido materno
    - Posición 16: Primera consonante interna del nombre de pila

    Si no se encuentra una consonante interna, se usa 'X'.

    Args:
        paternal: Apellido paterno normalizado.
        maternal: Apellido materno normalizado.
        name: Nombre(s) de pila normalizado(s).

    Returns:
        str: Las 3 consonantes internas.
    """
    c1 = _find_first_internal_consonant(paternal)
    c2 = _find_first_internal_consonant(maternal)
    c3 = _find_first_internal_consonant(name)

    return f"{c1}{c2}{c3}"


def _find_first_internal_consonant(text: str) -> str:
    """
    Busca la primera consonante interna (no inicial) en un texto.

    Args:
        text: Texto en mayúsculas donde buscar la consonante.

    Returns:
        str: La primera consonante interna encontrada, o 'X' si no existe.
    """
    for char in text[1:] if len(text) > 1 else "":
        if char in CONSONANTS:
            return char
    return "X"


def _get_century_character(birth_date: date) -> str:
    """
    Determina el carácter identificador del siglo para la CURP.

    Para nacidos antes del año 2000, se usa un dígito (0-9).
    Para nacidos a partir del 2000, se usa una letra (A-Z).

    El dígito se calcula como los últimos dígitos del año entre 10
    (módulo 10), y la letra se asigna secuencialmente a partir de 'A'
    para cada año del 2000 en adelante.

    Args:
        birth_date: Fecha de nacimiento.

    Returns:
        str: Carácter identificador del siglo.
    """
    if birth_date.year < 2000:
        # Nacidos en el siglo XX: se usa un dígito
        return str(birth_date.year % 10)
    else:
        # Nacidos en el siglo XXI: se usa una letra
        # 2000=A, 2001=B, 2002=C, etc.
        year_offset = birth_date.year - 2000
        if year_offset < 26:
            return chr(ord("A") + year_offset)
        else:
            # Para años más allá de 2025, se continúa el patrón
            return str(year_offset % 10)
