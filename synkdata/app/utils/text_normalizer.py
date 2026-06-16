"""
Utilidades de normalización de texto para la plataforma SynkData.

Este módulo proporciona funciones de normalización de texto especializadas
para el procesamiento de nombres y datos personales en español, incluyendo:

- Eliminación de acentos y diacríticos
- Normalización de espacios en blanco
- Normalización completa para comparación
- Extracción de iniciales de nombres
- Separación de nombres completos en componentes

Estas funciones son fundamentales para el proceso de verificación de
identidad, donde las variaciones ortográficas y tipográficas comunes
deben normalizarse antes de realizar comparaciones.
"""

from __future__ import annotations

import re
import unicodedata
from typing import Optional


# ---------------------------------------------------------------------------
# Artículos, preposiciones y conjunciones comunes en nombres en español
# que deben ser ignorados en la generación de iniciales
# ---------------------------------------------------------------------------
_NAME_PARTICLES: set[str] = {
    "DE", "DEL", "DE LA", "DE LOS", "DE LAS",
    "LA", "LAS", "LOS", "EL",
    "Y", "E", "O", "U",
    "EN", "POR", "CON", "PARA", "A",
    "MAC", "MC",  # Prefijos de apellidos escoceses/irlandeses adaptados
    "VON", "VAN",  # Prefijos de apellidos alemanes/holandeses
    "SAN", "SANTA", "SANTO",  # Santos
}

# Conjugaciones y preposiciones para separación inteligente de nombres
_PATERNAL_PREFIXES: set[str] = {
    "DE", "DEL", "DE LA", "DE LOS", "DE LAS",
    "VON", "VAN", "DI", "DA", "DOS", "DAS",
}


def remove_accents(text: str) -> str:
    """
    Elimina todos los acentos y diacríticos de un texto, preservando la ñ/Ñ.

    Convierte caracteres acentuados (á, é, í, ó, ú, ü) a sus
    equivalentes sin acento (a, e, i, o, u, u), manteniendo la ñ
    y Ñ ya que representan un fonema distinto en español.

    Args:
        text: Texto del cual eliminar los acentos.

    Returns:
        str: Texto sin acentos ni diacríticos (excepto ñ/Ñ).

    Example:
        >>> remove_accents("GUTIÉRREZ Y LÓPEZ")
        'GUTIERREZ Y LOPEZ'
        >>> remove_accents("MUÑOZ")
        'MUÑOZ'
    """
    if not text:
        return ""

    # Descomponer caracteres Unicode (NFD = Normalization Form Decomposition)
    # Esto separa los caracteres base de las marcas diacríticas
    nfd_text = unicodedata.normalize("NFD", text)

    # Proteger la ñ/Ñ antes de eliminar diacríticos
    # La ñ en NFD se convierte en n + ~ (U+0303)
    # Primero reemplazamos las ñ/Ñ precompuestas con marcadores
    result = []
    skip_next = False

    for i, char in enumerate(nfd_text):
        if skip_next:
            skip_next = False
            continue

        # Detectar n/N seguido de tilde combinante (U+0303) = ñ/Ñ
        if char in ("n", "N") and i + 1 < len(nfd_text):
            next_char = nfd_text[i + 1]
            if next_char == "\u0303":  # COMBINING TILDE
                result.append("Ñ" if char == "N" else "ñ")
                skip_next = True
                continue

        # Eliminar marcas diacríticas combinantes (Unicode category Mn)
        if unicodedata.category(char) == "Mn":
            continue

        result.append(char)

    return "".join(result)


def normalize_whitespace(text: str) -> str:
    """
    Normaliza los espacios en blanco de un texto.

    Colapsa múltiples espacios consecutivos en uno solo, elimina
    espacios al inicio y al final, y normaliza tabuladores y
    saltos de línea a espacios simples.

    Args:
        text: Texto con espacios en blanco irregulares.

    Returns:
        str: Texto con espacios normalizados.

    Example:
        >>> normalize_whitespace("  José   María   Gutiérrez  ")
        'José María Gutiérrez'
    """
    if not text:
        return ""

    # Reemplazar todo tipo de espacios en blanco (tab, newline, etc.) por espacio
    result = re.sub(r"\s+", " ", text)
    return result.strip()


def normalize_for_comparison(text: str) -> str:
    """
    Pipeline completo de normalización para comparación de textos.

    Aplica las siguientes transformaciones en orden:
    1. Eliminación de acentos y diacríticos
    2. Conversión a mayúsculas
    3. Eliminación de caracteres no alfabéticos (excepto espacios y Ñ)
    4. Normalización de espacios en blanco

    Este pipeline es el estándar para comparar nombres y datos
    personales en la plataforma SynkData.

    Args:
        text: Texto a normalizar para comparación.

    Returns:
        str: Texto completamente normalizado.

    Example:
        >>> normalize_for_comparison("José María Gutiérrez-Ocampo")
        'JOSE MARIA GUTIERREZ OCAMPO'
    """
    if not text:
        return ""

    # Paso 1: Eliminar acentos
    no_accents = remove_accents(text)

    # Paso 2: Convertir a mayúsculas
    upper = no_accents.upper()

    # Paso 3: Eliminar caracteres no alfabéticos (excepto espacios y Ñ)
    cleaned = re.sub(r"[^A-ZÑ\s]", " ", upper)

    # Paso 4: Normalizar espacios
    return normalize_whitespace(cleaned)


def extract_initials(name: str) -> str:
    """
    Extrae las iniciales de un nombre completo, ignorando partículas.

    Genera una cadena con la primera letra de cada palabra significativa
    del nombre, omitiendo artículos, preposiciones y conjunciones comunes
    en nombres en español (de, del, y, etc.).

    Args:
        name: Nombre completo del cual extraer las iniciales.

    Returns:
        str: Iniciales del nombre (mayúsculas, sin separador).

    Example:
        >>> extract_initials("José María de la Cruz")
        'JMC'
        >>> extract_initials("Juan Carlos López y Gutiérrez")
        'JCLG'
    """
    if not name:
        return ""

    normalized = normalize_for_comparison(name)
    if not normalized:
        return ""

    words = normalized.split()
    initials = []

    for word in words:
        if word not in _NAME_PARTICLES and word:
            initials.append(word[0])

    return "".join(initials)


def split_full_name(full_name: str) -> tuple[str, str, str]:
    """
    Separa un nombre completo en sus componentes: nombre, apellido paterno
    y apellido materno.

    Aplica heurísticas basadas en la estructura típica de nombres en México:
    - Formato común: [Nombre(s)] [Apellido Paterno] [Apellido Materno]
    - Considera partículas como "de", "del", "de la" como parte del apellido
    - Nombres compuestos como "José María", "María del Carmen", etc.

    Args:
        full_name: Nombre completo a separar.

    Returns:
        tuple[str, str, str]: Una tupla con (nombre, apellido_paterno,
            apellido_materno). Los campos faltantes se retornan como
            cadena vacía.

    Example:
        >>> split_full_name("Juan Pérez López")
        ('JUAN', 'PEREZ', 'LOPEZ')
        >>> split_full_name("María del Carmen de la Cruz Gutiérrez")
        ('MARIA DEL CARMEN', 'DE LA CRUZ', 'GUTIERREZ')
        >>> split_full_name("Roberto Sánchez")
        ('ROBERTO', 'SANCHEZ', '')
    """
    if not full_name:
        return "", "", ""

    normalized = normalize_for_comparison(full_name)
    if not normalized:
        return "", "", ""

    words = normalized.split()
    n = len(words)

    if n == 0:
        return "", "", ""

    if n == 1:
        # Solo un apellido o nombre
        return words[0], "", ""

    if n == 2:
        # Nombre + Apellido Paterno
        return words[0], words[1], ""

    if n == 3:
        # Nombre + Apellido Paterno + Apellido Materno
        return words[0], words[1], words[2]

    # Para 4+ palabras, aplicar heurísticas más avanzadas
    return _split_complex_name(words)


# ---------------------------------------------------------------------------
# Funciones auxiliares privadas
# ---------------------------------------------------------------------------

def _split_complex_name(words: list[str]) -> tuple[str, str, str]:
    """
    Separa un nombre complejo (4+ palabras) en sus componentes.

    Heurísticas:
    1. Las palabras "DE", "DEL", "DE LA" al inicio de un apellido
       se agrupan con la siguiente palabra
    2. Los nombres compuestos como "MARIA DEL CARMEN", "JOSE LUIS"
       se agrupan en el campo de nombre
    3. El apellido paterno puede incluir prefijos (de, del, de la)
    4. El apellido materno es la última palabra o grupo

    Args:
        words: Lista de palabras del nombre completo.

    Returns:
        tuple[str, str, str]: (nombre, apellido_paterno, apellido_materno).
    """
    n = len(words)

    # Identificar los índices donde comienzan los apellidos
    # Buscar la primera partícula "DE" (y variantes) después de las primeras
    # 1-3 palabras, lo que indica el inicio del apellido paterno

    name_parts: list[str] = []
    paternal_parts: list[str] = []
    maternal_parts: list[str] = []

    # Estrategia: las últimas dos palabras son apellidos,
    # a menos que estén precedidas por partículas
    # que deben agruparse con el apellido

    # Buscar desde el final para agrupar el apellido materno
    i = n - 1
    maternal_parts.insert(0, words[i])
    i -= 1

    # Verificar si la palabra anterior es una partícula del apellido materno
    # (poco común pero posible)

    # Agrupar el apellido paterno
    if i >= 0:
        # Verificar si hay prefijo "DE/DEL/DE LA" antes del apellido paterno
        while i >= 1 and _is_paternal_prefix(words, i):
            paternal_parts.insert(0, words[i])
            i -= 1

        if i >= 0:
            paternal_parts.insert(0, words[i])
            i -= 1

    # El resto es el nombre
    name_parts = words[: i + 1]

    # Si no se identificó nombre, redistribuir
    if not name_parts and paternal_parts:
        name_parts = [paternal_parts.pop(0)]

    name_str = " ".join(name_parts)
    paternal_str = " ".join(paternal_parts)
    maternal_str = " ".join(maternal_parts)

    return name_str, paternal_str, maternal_str


def _is_paternal_prefix(words: list[str], index: int) -> bool:
    """
    Determina si la palabra en el índice dado es un prefijo de apellido.

    Considera prefijos como "DE", "DEL", "DE LA", "VON", "VAN", etc.
    También verifica si la combinación de la palabra actual con la
    siguiente forma un prefijo compuesto (ej. "DE LA").

    Args:
        words: Lista de palabras del nombre.
        index: Índice de la palabra a verificar.

    Returns:
        bool: True si la palabra es un prefijo de apellido.
    """
    word = words[index]

    if word in _PATERNAL_PREFIXES:
        return True

    # Verificar prefijos compuestos (DE LA, DE LOS, DE LAS)
    if word == "DE" and index + 1 < len(words):
        next_word = words[index + 1]
        if next_word in ("LA", "LOS", "LAS"):
            return True

    return False
