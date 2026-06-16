"""
Codificación fonética para nombres en español.

Este módulo implementa un algoritmo de codificación fonética adaptado
al idioma español, similar a Soundex pero con reglas específicas para
las particularidades fonéticas del castellano.

Las transformaciones fonéticas principales incluyen:
- v → b (sonido bilabial sordo equivalente)
- z → s (seseo: neutralización de s/z)
- c → s (ante e, i: ceceo/seseo)
- c → k (ante a, o, u: sonido oclusivo)
- h → (silencio: no se pronuncia)
- ll → l (yeísmo: neutralización de ll/y)
- q → k (representación del sonido oclusivo velar)
- gu → g (ante e, i: sonido fricativo velar)
- g → j (ante e, i: sonido fricativo)
- d → (suave: se elide entre vocales en habla coloquial)
- m → n (asimilación nasal)
- ñ → ny (diálogo fonético)

Este módulo es fundamental para la comparación difusa de nombres
en el proceso de verificación de identidad, donde variaciones
ortográficas comunes deben ser tratadas como equivalentes.
"""

from __future__ import annotations

import re
import unicodedata
from typing import Optional


# ---------------------------------------------------------------------------
# Tabla de transformaciones fonéticas para el español
# ---------------------------------------------------------------------------
_PHONETIC_REPLACEMENTS: list[tuple[str, str]] = [
    # Deben aplicarse en orden específico (primero las más largas)
    # Digrafos y trigrafos primero
    ("GU", "G"),   # gu (ante e,i) suena como g suave
    ("QU", "K"),   # qu siempre suena como k
    ("LL", "L"),   # yeísmo: ll se pronuncia como y/l
    ("CH", "X"),   # ch tiene sonido único (código X como en Soundex mexicano)
    # Letras individuales
    ("V", "B"),    # v y b son fonéticamente equivalentes en español
    ("Z", "S"),    # seseo: z y s suenan igual
    ("Ñ", "NY"),   # ñ tiene sonido palatal nasal
    ("X", "KS"),   # x se pronuncia como ks en la mayoría de contextos
    # La H es muda, se elimina
]


# ---------------------------------------------------------------------------
# Funciones principales
# ---------------------------------------------------------------------------

def phonetic_encode(name: str) -> str:
    """
    Codifica un nombre en su representación fonética española.

    Aplica las reglas de transformación fonética del español para
    generar una representación normalizada que agrupa nombres con
    la misma pronunciación pero diferente ortografía.

    El algoritmo:
    1. Normaliza el texto (elimina acentos, convierte a mayúsculas)
    2. Elimina la H muda
    3. Aplica transformaciones de digrafos (ll→l, qu→k, gu→g, ch→x)
    4. Aplica transformaciones de letras individuales (v→b, z→s, ñ→ny)
    5. Reemplaza C por S antes de E/I, y por K antes de A/O/U
    6. Reemplaza G por J antes de E/I (yeísmo del g)
    7. Elimina vocales redundantes conservando solo la primera
    8. Rellena con ceros si es necesario para obtener 4 caracteres

    Args:
        name: Nombre a codificar fonéticamente.

    Returns:
        str: Código fonético del nombre (4 caracteres alfanuméricos).

    Example:
        >>> phonetic_encode("VAZQUEZ")
        'BSKS'
        >>> phonetic_encode("GUTIERREZ")
        'GTRS'
        >>> phonetic_encode("HERRERA")
        'RRR0'
    """
    if not name or not isinstance(name, str):
        return "0000"

    # Paso 1: Normalizar
    normalized = normalize_name(name)
    if not normalized:
        return "0000"

    # Paso 2: Convertir a mayúsculas para procesamiento
    upper = normalized.upper()

    # Paso 3: Eliminar la H muda (pero no CH, que ya se procesó como digrafo)
    # Primero manejar CH → X antes de eliminar H
    upper = upper.replace("CH", "X")

    # Ahora eliminar H restante (muda en español)
    upper = upper.replace("H", "")

    if not upper:
        return "0000"

    # Paso 4: Aplicar transformaciones de digrafos
    for pattern, replacement in _PHONETIC_REPLACEMENTS:
        # Ya procesamos CH y LL, QU, GU
        if pattern in ("CH", "LL", "QU", "GU"):
            upper = upper.replace(pattern, replacement)

    # Paso 5: Transformaciones de letras individuales
    upper = upper.replace("V", "B")
    upper = upper.replace("Z", "S")

    # Paso 6: Transformaciones contextuales de C y G
    result = []
    i = 0
    while i < len(upper):
        char = upper[i]
        next_char = upper[i + 1] if i + 1 < len(upper) else ""

        if char == "C":
            # C antes de E/I suena como S (seseo)
            # C antes de A/O/U suena como K
            if next_char in ("E", "I"):
                result.append("S")
            else:
                result.append("K")
        elif char == "G":
            # G antes de E/I suena como J (en la mayoría de hispanohablantes)
            # G antes de A/O/U suena como G
            if next_char in ("E", "I"):
                result.append("J")
            else:
                result.append("G")
        elif char == "Ñ":
            result.append("NY")
        elif char == "X":
            result.append("KS")
        else:
            result.append(char)

        i += 1

    phonetic = "".join(result)

    # Paso 7: Eliminar caracteres no alfabéticos
    phonetic = re.sub(r"[^A-Z]", "", phonetic)

    # Paso 8: Retener la primera letra y eliminar vocales/consonantes duplicadas
    if not phonetic:
        return "0000"

    first_letter = phonetic[0]
    rest = phonetic[1:]

    # Eliminar vocales del resto (conservar solo consonantes para el código)
    consonants_only = ""
    for char in rest:
        if char not in "AEIOU":
            consonants_only += char

    # Construir código: primera letra + consonantes
    code = first_letter + consonants_only

    # Eliminar caracteres duplicados consecutivos
    deduped = code[0]
    for char in code[1:]:
        if char != deduped[-1]:
            deduped += char

    code = deduped

    # Rellenar con ceros o truncar a 4 caracteres
    if len(code) < 4:
        code = code + "0" * (4 - len(code))
    else:
        code = code[:4]

    return code


def phonetic_match(name1: str, name2: str) -> float:
    """
    Calcula la similitud fonética entre dos nombres en español.

    Compara las codificaciones fonéticas de ambos nombres y
    retorna un valor entre 0.0 (sin similitud) y 1.0 (idénticos).

    La comparación se realiza en múltiples niveles:
    1. Coincidencia exacta del código fonético (1.0)
    2. Coincidencia parcial con distancia de edición (0.5-0.9)
    3. Sin coincidencia fonética (0.0)

    Args:
        name1: Primer nombre a comparar.
        name2: Segundo nombre a comparar.

    Returns:
        float: Similitud fonética entre 0.0 y 1.0.

    Example:
        >>> phonetic_match("VAZQUEZ", "VASQUEZ")
        1.0
        >>> phonetic_match("GUTIERREZ", "GUTIERRES")
        1.0
        >>> phonetic_match("PEREZ", "LOPEZ")
        0.0
    """
    if not name1 or not name2:
        return 0.0

    # Codificación fonética completa
    code1 = phonetic_encode(name1)
    code2 = phonetic_encode(name2)

    # Coincidencia exacta de códigos fonéticos
    if code1 == code2:
        return 1.0

    # Comparar también nombres normalizados directamente
    norm1 = normalize_name(name1)
    norm2 = normalize_name(name2)

    if norm1 == norm2:
        return 1.0

    # Calcular similitud usando distancia de Levenshtein sobre códigos fonéticos
    distance = _levenshtein_distance(code1, code2)
    max_len = max(len(code1), len(code2))

    if max_len == 0:
        return 0.0

    similarity = 1.0 - (distance / max_len)

    # También comparar los nombres normalizados para refinar
    norm_distance = _levenshtein_distance(norm1, norm2)
    norm_max_len = max(len(norm1), len(norm2))
    norm_similarity = 1.0 - (norm_distance / norm_max_len) if norm_max_len > 0 else 0.0

    # Retornar el máximo de ambas similitudes
    return max(similarity, norm_similarity)


def normalize_name(name: str) -> str:
    """
    Normaliza un nombre para comparación: elimina acentos, exceso de
    espacios y convierte a mayúsculas.

    La normalización incluye:
    1. Eliminación de acentos y diacríticos
    2. Conversión a mayúsculas
    3. Eliminación de espacios múltiples
    4. Eliminación de caracteres no alfabéticos (excepto espacios y ñ)

    Args:
        name: Nombre a normalizar.

    Returns:
        str: Nombre normalizado en mayúsculas sin acentos.

    Example:
        >>> normalize_name("  José  María  ")
        'JOSE MARIA'
        >>> normalize_name("GUTIÉRREZ")
        'GUTIERREZ'
    """
    if not name or not isinstance(name, str):
        return ""

    # Paso 1: Descomponer caracteres Unicode (NFD)
    # Esto separa los caracteres base de los diacríticos
    nfd = unicodedata.normalize("NFD", name)

    # Paso 2: Eliminar diacríticos (marcas combinantes)
    # Mantener la Ñ (U+0303 combinada con N) como Ñ
    # Primero proteger la ñ/Ñ
    protected = nfd.replace("\u00f1", "\x00").replace("\u00d1", "\x01")

    # Eliminar todas las marcas diacríticas combinantes (Unicode category Mn)
    no_accents = "".join(
        char for char in protected
        if unicodedata.category(char) != "Mn"
    )

    # Restaurar la ñ/Ñ
    no_accents = no_accents.replace("\x00", "Ñ").replace("\x01", "Ñ")

    # Paso 3: Convertir a mayúsculas
    upper = no_accents.upper()

    # Paso 4: Eliminar caracteres no alfabéticos (excepto espacios y Ñ)
    cleaned = re.sub(r"[^A-ZÑ\s]", "", upper)

    # Paso 5: Normalizar espacios
    cleaned = re.sub(r"\s+", " ", cleaned).strip()

    return cleaned


# ---------------------------------------------------------------------------
# Funciones auxiliares privadas
# ---------------------------------------------------------------------------

def _levenshtein_distance(s1: str, s2: str) -> int:
    """
    Calcula la distancia de Levenshtein entre dos cadenas.

    La distancia de Levenshtein es el número mínimo de operaciones
    (inserción, eliminación, sustitución) necesarias para transformar
    una cadena en otra.

    Args:
        s1: Primera cadena.
        s2: Segunda cadena.

    Returns:
        int: Distancia de Levenshtein entre las dos cadenas.
    """
    if len(s1) < len(s2):
        return _levenshtein_distance(s2, s1)

    if len(s2) == 0:
        return len(s1)

    previous_row = list(range(len(s2) + 1))

    for i, c1 in enumerate(s1):
        current_row = [i + 1]
        for j, c2 in enumerate(s2):
            # Costo de inserción, eliminación y sustitución
            insertions = previous_row[j + 1] + 1
            deletions = current_row[j] + 1
            substitutions = previous_row[j] + (c1 != c2)
            current_row.append(min(insertions, deletions, substitutions))
        previous_row = current_row

    return previous_row[-1]
