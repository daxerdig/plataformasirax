"""
Utilidades de la plataforma SynkData.

Provee algoritmos de validación, codificación fonética y normalización
de texto para los módulos de verificación de identidad.
"""

from app.utils.curp_algorithm import (
    CURP_CHAR_VALUES,
    CURP_WEIGHTS,
    CURPInfo,
    STATE_CODES,
    calculate_curp_check_digit,
    extract_curp_info,
    generate_curp,
    validate_curp_format,
)
from app.utils.phonetic import normalize_name, phonetic_encode, phonetic_match
from app.utils.rfc_algorithm import (
    RFC_CHAR_VALUES,
    RFCInfo,
    calculate_rfc_check_digit,
    extract_rfc_info,
    generate_rfc,
    validate_rfc_format,
)
from app.utils.text_normalizer import (
    extract_initials,
    normalize_for_comparison,
    normalize_whitespace,
    remove_accents,
    split_full_name,
)

__all__ = [
    # CURP
    "CURP_CHAR_VALUES",
    "CURP_WEIGHTS",
    "CURPInfo",
    "STATE_CODES",
    "calculate_curp_check_digit",
    "extract_curp_info",
    "generate_curp",
    "validate_curp_format",
    # RFC
    "RFC_CHAR_VALUES",
    "RFCInfo",
    "calculate_rfc_check_digit",
    "extract_rfc_info",
    "generate_rfc",
    "validate_rfc_format",
    # Fonética
    "normalize_name",
    "phonetic_encode",
    "phonetic_match",
    # Normalización de texto
    "extract_initials",
    "normalize_for_comparison",
    "normalize_whitespace",
    "remove_accents",
    "split_full_name",
]
