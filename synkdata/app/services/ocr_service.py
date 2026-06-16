"""
Servicio de OCR para documentos de identidad mexicanos.

Gestiona la extracción de texto y datos estructurados desde imágenes
de documentos de identidad utilizando pytesseract y Pillow, con
patrones de extracción específicos para documentos mexicanos:
- INE/IFE (Credencial para votar)
- Pasaporte mexicano
- Comprobante de domicilio

Incluye:
- Extracción de texto genérica con puntuación de confianza
- Extracción especializada para INE (frente y vuelta)
- Extracción de datos de pasaporte (incluyendo MRZ)
- Extracción de datos de comprobante de domicilio
- Validación de documentos contra datos esperados
- Puntuación de confianza por campo

Todos los mensajes dirigidos al usuario están en español.
"""

from __future__ import annotations

import io
import logging
import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional

from app.config import get_settings

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Enumeraciones
# ---------------------------------------------------------------------------
class IneType(str, Enum):
    """
    Tipo de credencial INE/IFE.

    La letra indica la versión del diseño:
    - A, B, C: Diseños antiguos (IFE)
    - D, E: Diseños vigentes (INE)
    """

    A = "A"
    B = "B"
    C = "C"
    D = "D"
    E = "E"


class DocumentType(str, Enum):
    """Tipos de documento soportados para OCR."""

    INE = "ine"
    PASSPORT = "passport"
    PROOF_OF_ADDRESS = "proof_of_address"
    UNKNOWN = "unknown"


# ---------------------------------------------------------------------------
# Modelos de datos de resultado
# ---------------------------------------------------------------------------
@dataclass(frozen=True, slots=True)
class FieldConfidence:
    """
    Confianza de un campo extraído por OCR.

    Attributes:
        field_name: Nombre del campo.
        value: Valor extraído.
        confidence: Nivel de confianza (0.0 a 1.0).
    """

    field_name: str
    value: str
    confidence: float


@dataclass(frozen=True, slots=True)
class OcrResult:
    """
    Resultado genérico de extracción de texto por OCR.

    Attributes:
        text: Texto completo extraído de la imagen.
        confidence: Confianza promedio de la extracción.
        language: Idioma detectado o utilizado.
        word_count: Número de palabras extraídas.
        field_confidences: Confianza por campo si se aplicó extracción.
    """

    text: str
    confidence: float
    language: str
    word_count: int
    field_confidences: List[FieldConfidence] = field(default_factory=list)


@dataclass(frozen=True, slots=True)
class IneData:
    """
    Datos extraídos de una credencial INE/IFE mexicana.

    Attributes:
        name: Nombre completo del titular.
        curp: CURP del titular.
        address: Dirección del titular.
        section: Sección electoral.
        folio: Folio de la credencial.
        emission_year: Año de emisión.
        version: Versión del diseño (A/B/C/D/E).
        type: Tipo de credencial (A/B/C/D/E).
        confidence: Confianza promedio de la extracción.
        field_confidences: Confianza por campo extraído.
    """

    name: str
    curp: str
    address: str
    section: str
    folio: str
    emission_year: str
    version: str
    type: IneType
    confidence: float
    field_confidences: List[FieldConfidence] = field(default_factory=list)


@dataclass(frozen=True, slots=True)
class PassportData:
    """
    Datos extraídos de un pasaporte mexicano.

    Attributes:
        name: Nombre completo del titular.
        nationality: Nacionalidad del titular.
        passport_number: Número de pasaporte.
        birth_date: Fecha de nacimiento (YYYY-MM-DD).
        expiry_date: Fecha de expiración (YYYY-MM-DD).
        mrz_line1: Primera línea de la zona de lectura mecánica (MRZ).
        mrz_line2: Segunda línea de la zona de lectura mecánica (MRZ).
        confidence: Confianza promedio de la extracción.
        field_confidences: Confianza por campo extraído.
    """

    name: str
    nationality: str
    passport_number: str
    birth_date: str
    expiry_date: str
    mrz_line1: str
    mrz_line2: str
    confidence: float
    field_confidences: List[FieldConfidence] = field(default_factory=list)


@dataclass(frozen=True, slots=True)
class AddressData:
    """
    Datos extraídos de un comprobante de domicilio.

    Attributes:
        street: Nombre de la calle.
        number: Número exterior/interior.
        colony: Nombre de la colonia.
        city: Nombre de la ciudad.
        state: Nombre del estado.
        zip_code: Código postal.
        confidence: Confianza promedio de la extracción.
        field_confidences: Confianza por campo extraído.
    """

    street: str
    number: str
    colony: str
    city: str
    state: str
    zip_code: str
    confidence: float
    field_confidences: List[FieldConfidence] = field(default_factory=list)


@dataclass(frozen=True, slots=True)
class DocumentValidation:
    """
    Resultado de la validación de un documento contra datos esperados.

    Attributes:
        is_valid: Si el documento es válido contra los datos esperados.
        confidence: Confianza general de la validación.
        extracted_fields: Campos extraídos del documento.
        mismatches: Lista de campos que no coinciden con los esperados.
    """

    is_valid: bool
    confidence: float
    extracted_fields: Dict[str, str]
    mismatches: List[Dict[str, Any]]


# ---------------------------------------------------------------------------
# Patrones de extracción para documentos mexicanos
# ---------------------------------------------------------------------------
_CURP_PATTERN = re.compile(
    r"[A-Z]{4}\d{6}[HM][A-Z]{5}[A-Z0-9]\d"
)
_SECTION_PATTERN = re.compile(r"\b(\d{4})\b")
_FOLIO_PATTERN = re.compile(r"\b(\d{9,13})\b")
_PASSPORT_NUMBER_PATTERN = re.compile(r"\b([A-Z0-9]{8,10})\b")
_ZIP_CODE_PATTERN = re.compile(r"\b(\d{5})\b")
_MRZ_LINE_PATTERN = re.compile(r"[A-Z0-9<]{44}")

# Patrones de fecha
_DATE_YYYYMMDD = re.compile(r"(\d{4}[-/]\d{2}[-/]\d{2})")
_DATE_DDMMYYYY = re.compile(r"(\d{2}[-/]\d{2}[-/]\d{4})")

# Palabras clave para comprobante de domicilio
_ADDRESS_KEYWORDS = {
    "street": re.compile(
        r"(?:CALLE|Calle|calle|AV|Av|av|AVENIDA|Avenida|avenida|BLVD|Blvd|PROL)"
        r"\s*\.?\s*:?\s*(.+?)(?:\n|,|Núm|$)",
        re.IGNORECASE,
    ),
    "number": re.compile(
        r"(?:N[ÚU]M|N[úu]m|No\.?|NUMERO|N[úu]mero)"
        r"\s*\.?\s*:?\s*(\d+\s*(?:-[A-Z])?)",
        re.IGNORECASE,
    ),
    "colony": re.compile(
        r"(?:COL|Col|COLONIA|Colonia|colonia)"
        r"\s*\.?\s*:?\s*(.+?)(?:\n|,|C\.P|$)",
        re.IGNORECASE,
    ),
    "city": re.compile(
        r"(?:CIUDAD|MUNICIPIO|DELEGACIÓN|ALCALDÍA)"
        r"\s*\.?\s*:?\s*(.+?)(?:\n|,|ESTADO|$)",
        re.IGNORECASE,
    ),
    "state": re.compile(
        r"(?:ESTADO|Estado|EDO|Edo)"
        r"\s*\.?\s*:?\s*(.+?)(?:\n|,|C\.P|$)",
        re.IGNORECASE,
    ),
}

# Estados de México (para matching en comprobantes)
_MEXICAN_STATES = [
    "AGUASCALIENTES", "BAJA CALIFORNIA", "BAJA CALIFORNIA SUR",
    "CAMPECHE", "CHIAPAS", "CHIHUAHUA", "CIUDAD DE MÉXICO",
    "COAHUILA", "COLIMA", "DURANGO", "ESTADO DE MÉXICO",
    "GUANAJUATO", "GUERRERO", "HIDALGO", "JALISCO",
    "MICHOACÁN", "MORELOS", "NAYARIT", "NUEVO LEÓN",
    "OAXACA", "PUEBLA", "QUERÉTARO", "QUINTANA ROO",
    "SAN LUIS POTOSÍ", "SINALOA", "SONORA", "TABASCO",
    "TAMAULIPAS", "TLAXCALA", "VERACRUZ", "YUCATÁN", "ZACATECAS",
]


# ---------------------------------------------------------------------------
# Servicio de OCR
# ---------------------------------------------------------------------------
class OcrService:
    """
    Servicio de OCR para documentos de identidad mexicanos.

    Utiliza pytesseract y Pillow para la extracción de texto desde
    imágenes, con patrones específicos para cada tipo de documento
    mexicano (INE, pasaporte, comprobante de domicilio).

    Incluye preprocesamiento de imágenes para mejorar la calidad
    de la extracción y puntuación de confianza por campo.

    Example:
        >>> service = OcrService()
        >>> with open("ine_front.jpg", "rb") as f:
        ...     front = f.read()
        >>> with open("ine_back.jpg", "rb") as f:
        ...     back = f.read()
        >>> ine_data = await service.extract_ine(front, back)
    """

    def __init__(self) -> None:
        """Inicializa el servicio con la configuración del proyecto."""
        self._settings = get_settings()

    # ── Extracción genérica ───────────────────────────────────────────────

    async def extract_text(self, image_bytes: bytes) -> OcrResult:
        """
        Extrae texto genérico de una imagen mediante OCR.

        Realiza el preprocesamiento de la imagen y ejecuta pytesseract
        para obtener el texto con puntuaciones de confianza.

        Args:
            image_bytes: Bytes de la imagen a procesar.

        Returns:
            OcrResult: Texto extraído con confianza y metadata.

        Raises:
            ValueError: Si la imagen es vacía o el formato no es soportado.
        """
        if not image_bytes:
            raise ValueError("La imagen no puede estar vacía.")

        self._validate_image_size(image_bytes)

        try:
            from PIL import Image

            import pytesseract

            # Configurar Tesseract si se especificó ruta
            if self._settings.TESSERACT_CMD:
                pytesseract.pytesseract.tesseract_cmd = (
                    self._settings.TESSERACT_CMD
                )

            # Cargar imagen
            image = Image.open(io.BytesIO(image_bytes))

            # Preprocesar imagen
            processed = self._preprocess_image(image)

            # Extraer texto con datos de confianza
            lang = self._settings.TESSERACT_LANG
            data = pytesseract.image_to_data(
                processed,
                lang=lang,
                output_type=pytesseract.Output.DICT,
            )

            # Construir texto y calcular confianza
            words: List[str] = []
            confidences: List[float] = []
            for i, word in enumerate(data["text"]):
                conf = data["conf"][i]
                if word.strip() and int(conf) > 0:
                    words.append(word)
                    confidences.append(int(conf) / 100.0)

            full_text = " ".join(words)
            avg_confidence = (
                sum(confidences) / len(confidences) if confidences else 0.0
            )

            return OcrResult(
                text=full_text,
                confidence=round(avg_confidence, 4),
                language=lang,
                word_count=len(words),
                field_confidences=[],
            )

        except ImportError:
            logger.warning(
                "pytesseract/Pillow no instalados. Usando extracción simulada."
            )
            return OcrResult(
                text="",
                confidence=0.0,
                language=self._settings.TESSERACT_LANG,
                word_count=0,
                field_confidences=[],
            )
        except Exception as exc:
            logger.error("Error en extracción de texto OCR: %s", exc)
            raise

    # ── Extracción INE ────────────────────────────────────────────────────

    async def extract_ine(
        self, front: bytes, back: bytes
    ) -> IneData:
        """
        Extrae datos de una credencial INE/IFE (frente y vuelta).

        Procesa ambas caras de la credencial para extraer:
        - Nombre completo, CURP, dirección (frente)
        - Sección electoral, folio, año de emisión (vuelta)
        - Tipo de credencial (A/B/C/D/E)

        Args:
            front: Bytes de la imagen del frente de la INE.
            back: Bytes de la imagen de la vuelta de la INE.

        Returns:
            IneData: Datos extraídos de la credencial.

        Raises:
            ValueError: Si alguna imagen está vacía.
        """
        if not front or not back:
            raise ValueError(
                "Se requieren ambas caras de la INE (frente y vuelta)."
            )

        # Extraer texto de ambas caras
        front_result = await self.extract_text(front)
        back_result = await self.extract_text(back)

        front_text = front_result.text.upper()
        back_text = back_result.text.upper()

        # Extraer campos con patrones
        name = self._extract_ine_name(front_text)
        curp = self._extract_curp(front_text + " " + back_text)
        address = self._extract_ine_address(front_text)
        section = self._extract_ine_section(back_text)
        folio = self._extract_ine_folio(back_text)
        emission_year = self._extract_ine_emission_year(back_text)
        ine_type = self._detect_ine_type(front_text + " " + back_text)

        # Calcular confianza por campo
        field_confidences = [
            FieldConfidence(field_name="name", value=name, confidence=0.85 if name else 0.0),
            FieldConfidence(field_name="curp", value=curp, confidence=0.95 if curp else 0.0),
            FieldConfidence(field_name="address", value=address, confidence=0.70 if address else 0.0),
            FieldConfidence(field_name="section", value=section, confidence=0.80 if section else 0.0),
            FieldConfidence(field_name="folio", value=folio, confidence=0.85 if folio else 0.0),
            FieldConfidence(field_name="emission_year", value=emission_year, confidence=0.75 if emission_year else 0.0),
        ]

        # Confianza promedio
        valid_confidences = [fc.confidence for fc in field_confidences if fc.confidence > 0]
        avg_confidence = (
            sum(valid_confidences) / len(valid_confidences)
            if valid_confidences
            else 0.0
        )

        return IneData(
            name=name,
            curp=curp,
            address=address,
            section=section,
            folio=folio,
            emission_year=emission_year,
            version=ine_type.value,
            type=ine_type,
            confidence=round(avg_confidence, 4),
            field_confidences=field_confidences,
        )

    # ── Extracción Pasaporte ──────────────────────────────────────────────

    async def extract_passport(
        self, image_bytes: bytes
    ) -> PassportData:
        """
        Extrae datos de un pasaporte mexicano.

        Procesa la imagen del pasaporte para extraer:
        - Nombre completo, nacionalidad, número de pasaporte
        - Fechas de nacimiento y expiración
        - Zona de lectura mecánica (MRZ)

        Args:
            image_bytes: Bytes de la imagen del pasaporte.

        Returns:
            PassportData: Datos extraídos del pasaporte.

        Raises:
            ValueError: Si la imagen está vacía.
        """
        if not image_bytes:
            raise ValueError("La imagen del pasaporte no puede estar vacía.")

        ocr_result = await self.extract_text(image_bytes)
        full_text = ocr_result.text.upper()

        # Extraer campos
        name = self._extract_passport_name(full_text)
        nationality = self._extract_passport_nationality(full_text)
        passport_number = self._extract_passport_number(full_text)
        birth_date = self._extract_passport_birth_date(full_text)
        expiry_date = self._extract_passport_expiry_date(full_text)
        mrz_line1, mrz_line2 = self._extract_passport_mrz(full_text)

        field_confidences = [
            FieldConfidence(field_name="name", value=name, confidence=0.80 if name else 0.0),
            FieldConfidence(field_name="nationality", value=nationality, confidence=0.90 if nationality else 0.0),
            FieldConfidence(field_name="passport_number", value=passport_number, confidence=0.90 if passport_number else 0.0),
            FieldConfidence(field_name="birth_date", value=birth_date, confidence=0.75 if birth_date else 0.0),
            FieldConfidence(field_name="expiry_date", value=expiry_date, confidence=0.75 if expiry_date else 0.0),
            FieldConfidence(field_name="mrz_line1", value=mrz_line1, confidence=0.85 if mrz_line1 else 0.0),
            FieldConfidence(field_name="mrz_line2", value=mrz_line2, confidence=0.85 if mrz_line2 else 0.0),
        ]

        valid_confidences = [fc.confidence for fc in field_confidences if fc.confidence > 0]
        avg_confidence = (
            sum(valid_confidences) / len(valid_confidences)
            if valid_confidences
            else 0.0
        )

        return PassportData(
            name=name,
            nationality=nationality,
            passport_number=passport_number,
            birth_date=birth_date,
            expiry_date=expiry_date,
            mrz_line1=mrz_line1,
            mrz_line2=mrz_line2,
            confidence=round(avg_confidence, 4),
            field_confidences=field_confidences,
        )

    # ── Extracción Comprobante de Domicilio ───────────────────────────────

    async def extract_proof_of_address(
        self, image_bytes: bytes
    ) -> AddressData:
        """
        Extrae datos de un comprobante de domicilio.

        Procesa la imagen del comprobante para extraer:
        - Calle, número, colonia, ciudad, estado, código postal

        Args:
            image_bytes: Bytes de la imagen del comprobante.

        Returns:
            AddressData: Datos de dirección extraídos.

        Raises:
            ValueError: Si la imagen está vacía.
        """
        if not image_bytes:
            raise ValueError(
                "La imagen del comprobante no puede estar vacía."
            )

        ocr_result = await self.extract_text(image_bytes)
        full_text = ocr_result.text

        # Extraer cada campo de dirección
        street = self._extract_address_field(full_text, "street")
        number = self._extract_address_field(full_text, "number")
        colony = self._extract_address_field(full_text, "colony")
        city = self._extract_address_field(full_text, "city")
        state = self._extract_address_state(full_text)
        zip_code = self._extract_zip_code(full_text)

        field_confidences = [
            FieldConfidence(field_name="street", value=street, confidence=0.70 if street else 0.0),
            FieldConfidence(field_name="number", value=number, confidence=0.75 if number else 0.0),
            FieldConfidence(field_name="colony", value=colony, confidence=0.65 if colony else 0.0),
            FieldConfidence(field_name="city", value=city, confidence=0.70 if city else 0.0),
            FieldConfidence(field_name="state", value=state, confidence=0.80 if state else 0.0),
            FieldConfidence(field_name="zip_code", value=zip_code, confidence=0.90 if zip_code else 0.0),
        ]

        valid_confidences = [fc.confidence for fc in field_confidences if fc.confidence > 0]
        avg_confidence = (
            sum(valid_confidences) / len(valid_confidences)
            if valid_confidences
            else 0.0
        )

        return AddressData(
            street=street,
            number=number,
            colony=colony,
            city=city,
            state=state,
            zip_code=zip_code,
            confidence=round(avg_confidence, 4),
            field_confidences=field_confidences,
        )

    # ── Validación de documentos ──────────────────────────────────────────

    async def validate_document(
        self,
        document_type: str,
        image_bytes: bytes,
        expected_data: dict,
    ) -> DocumentValidation:
        """
        Valida un documento contra datos esperados.

        Extrae los datos del documento y los compara con los datos
        esperados para determinar si el documento es válido.

        Args:
            document_type: Tipo de documento (ine, passport, proof_of_address).
            image_bytes: Bytes de la imagen del documento.
            expected_data: Datos esperados para comparación.

        Returns:
            DocumentValidation: Resultado de la validación.

        Raises:
            ValueError: Si el tipo de documento no es soportado.
        """
        valid_types = {dt.value for dt in DocumentType if dt != DocumentType.UNKNOWN}
        if document_type not in valid_types:
            raise ValueError(
                f"Tipo de documento inválido: '{document_type}'. "
                f"Tipos válidos: {', '.join(sorted(valid_types))}"
            )

        # Extraer datos según el tipo de documento
        extracted_fields: Dict[str, str] = {}
        if document_type == DocumentType.INE.value:
            ine_data = await self.extract_ine(
                image_bytes, image_bytes  # Se requiere frente y vuelta
            )
            extracted_fields = {
                "name": ine_data.name,
                "curp": ine_data.curp,
                "address": ine_data.address,
                "section": ine_data.section,
                "folio": ine_data.folio,
            }
        elif document_type == DocumentType.PASSPORT.value:
            passport_data = await self.extract_passport(image_bytes)
            extracted_fields = {
                "name": passport_data.name,
                "passport_number": passport_data.passport_number,
                "nationality": passport_data.nationality,
                "birth_date": passport_data.birth_date,
            }
        elif document_type == DocumentType.PROOF_OF_ADDRESS.value:
            address_data = await self.extract_proof_of_address(image_bytes)
            extracted_fields = {
                "street": address_data.street,
                "number": address_data.number,
                "colony": address_data.colony,
                "city": address_data.city,
                "state": address_data.state,
                "zip_code": address_data.zip_code,
            }

        # Comparar con datos esperados
        mismatches: List[Dict[str, Any]] = []
        match_count = 0
        total_fields = 0

        for expected_key, expected_value in expected_data.items():
            if not expected_value:
                continue

            total_fields += 1
            extracted_value = extracted_fields.get(expected_key, "")

            if not extracted_value:
                mismatches.append(
                    {
                        "field": expected_key,
                        "expected": expected_value,
                        "extracted": "",
                        "issue": "Campo no encontrado en el documento",
                    }
                )
                continue

            # Comparación normalizada (sin acentos, mayúsculas)
            norm_expected = self._normalize_text(str(expected_value))
            norm_extracted = self._normalize_text(extracted_value)

            if norm_expected == norm_extracted:
                match_count += 1
            elif norm_expected in norm_extracted or norm_extracted in norm_expected:
                # Coincidencia parcial
                match_count += 0.5
                mismatches.append(
                    {
                        "field": expected_key,
                        "expected": expected_value,
                        "extracted": extracted_value,
                        "issue": "Coincidencia parcial",
                    }
                )
            else:
                # Comparación por similitud
                similarity = self._calculate_similarity(
                    norm_expected, norm_extracted
                )
                if similarity >= 0.85:
                    match_count += 0.7
                    mismatches.append(
                        {
                            "field": expected_key,
                            "expected": expected_value,
                            "extracted": extracted_value,
                            "issue": f"Coincidencia difusa ({similarity:.0%})",
                        }
                    )
                else:
                    mismatches.append(
                        {
                            "field": expected_key,
                            "expected": expected_value,
                            "extracted": extracted_value,
                            "issue": "No coincide",
                        }
                    )

        # Calcular validez y confianza
        confidence = match_count / total_fields if total_fields > 0 else 0.0
        is_valid = confidence >= 0.8 and len(mismatches) == 0

        return DocumentValidation(
            is_valid=is_valid,
            confidence=round(confidence, 4),
            extracted_fields=extracted_fields,
            mismatches=mismatches,
        )

    # ── Métodos privados de extracción ────────────────────────────────────

    def _extract_ine_name(self, text: str) -> str:
        """
        Extrae el nombre del titular de la INE.

        Busca patrones comunes como "NOMBRE" seguido del nombre completo.

        Args:
            text: Texto OCR del frente de la INE (en mayúsculas).

        Returns:
            str: Nombre extraído o cadena vacía.
        """
        # Patrón: NOMBRE seguido del nombre completo
        name_patterns = [
            re.compile(
                r"NOMBRE\s*\.?\s*:?\s*([A-ZÁÉÍÓÚÑ\s]{5,50})(?:\n|CURP|DOMICILIO|$)",
                re.IGNORECASE,
            ),
            re.compile(
                r"NOMBRE\s+([A-ZÁÉÍÓÚÑ]+(?:\s+[A-ZÁÉÍÓÚÑ]+){2,5})",
                re.IGNORECASE,
            ),
        ]

        for pattern in name_patterns:
            match = pattern.search(text)
            if match:
                name = match.group(1).strip()
                # Limpiar espacios múltiples
                name = re.sub(r"\s+", " ", name)
                return name

        return ""

    def _extract_curp(self, text: str) -> str:
        """
        Extrae la CURP del texto OCR.

        Args:
            text: Texto OCR donde buscar la CURP.

        Returns:
            str: CURP encontrada o cadena vacía.
        """
        match = _CURP_PATTERN.search(text)
        return match.group(0) if match else ""

    def _extract_ine_address(self, text: str) -> str:
        """
        Extrae la dirección del frente de la INE.

        Args:
            text: Texto OCR del frente de la INE (en mayúsculas).

        Returns:
            str: Dirección extraída o cadena vacía.
        """
        patterns = [
            re.compile(
                r"DOMICILIO\s*\.?\s*:?\s*(.+?)(?:\n|CLAVE|SECCIÓN|$)",
                re.IGNORECASE,
            ),
            re.compile(
                r"DOM\s*\.?\s*:?\s*(.+?)(?:\n|CLAVE|$)",
                re.IGNORECASE,
            ),
        ]

        for pattern in patterns:
            match = pattern.search(text)
            if match:
                address = match.group(1).strip()
                address = re.sub(r"\s+", " ", address)
                return address

        return ""

    def _extract_ine_section(self, text: str) -> str:
        """
        Extrae la sección electoral de la INE.

        Args:
            text: Texto OCR de la vuelta de la INE (en mayúsculas).

        Returns:
            str: Sección electoral o cadena vacía.
        """
        # Buscar "SECCIÓN" o "SECC" seguido de números
        patterns = [
            re.compile(r"SECCI[OÓ]N\s*\.?\s*:?\s*(\d{4})", re.IGNORECASE),
            re.compile(r"SECC\s*\.?\s*:?\s*(\d{4})", re.IGNORECASE),
        ]

        for pattern in patterns:
            match = pattern.search(text)
            if match:
                return match.group(1)

        return ""

    def _extract_ine_folio(self, text: str) -> str:
        """
        Extrae el folio de la INE.

        Args:
            text: Texto OCR de la vuelta de la INE (en mayúsculas).

        Returns:
            str: Folio o cadena vacía.
        """
        patterns = [
            re.compile(
                r"FOLIO\s*\.?\s*:?\s*(\d{9,13})", re.IGNORECASE
            ),
            re.compile(
                r"CLAVE\s*(?:DE\s*)?ELECTOR\s*\.?\s*:?\s*(\d{9,18})",
                re.IGNORECASE,
            ),
        ]

        for pattern in patterns:
            match = pattern.search(text)
            if match:
                return match.group(1)

        return ""

    def _extract_ine_emission_year(self, text: str) -> str:
        """
        Extrae el año de emisión de la INE.

        Args:
            text: Texto OCR de la vuelta de la INE (en mayúsculas).

        Returns:
            str: Año de emisión o cadena vacía.
        """
        patterns = [
            re.compile(r"A[ÑN]O\s*\.?\s*:?\s*(\d{4})", re.IGNORECASE),
            re.compile(r"EMISI[OÓ]N\s*\.?\s*:?\s*(\d{4})", re.IGNORECASE),
        ]

        for pattern in patterns:
            match = pattern.search(text)
            if match:
                year = int(match.group(1))
                if 1990 <= year <= 2030:
                    return match.group(1)

        return ""

    def _detect_ine_type(self, text: str) -> IneType:
        """
        Detecta el tipo/version de la credencial INE/IFE.

        Basado en palabras clave presentes en el texto extraído.

        Args:
            text: Texto OCR combinado (frente + vuelta).

        Returns:
            IneType: Tipo detectado de credencial.
        """
        text_upper = text.upper()

        # Versiones recientes (INE)
        if "CREDENCIAL PARA VOTAR" in text_upper and "2024" in text_upper:
            return IneType.E
        if "CREDENCIAL PARA VOTAR" in text_upper and "2020" in text_upper:
            return IneType.E
        if "INE" in text_upper and "IDENTIDAD" in text_upper:
            return IneType.D

        # Versiones antiguas (IFE)
        if "IFE" in text_upper:
            if "FOLIO" in text_upper:
                return IneType.C
            return IneType.B

        # Por defecto asumir la versión más reciente
        return IneType.D

    def _extract_passport_name(self, text: str) -> str:
        """
        Extrae el nombre del pasaporte.

        Args:
            text: Texto OCR del pasaporte (en mayúsculas).

        Returns:
            str: Nombre extraído o cadena vacía.
        """
        patterns = [
            re.compile(
                r"(?:NOMBRE|NAME|NOM)\s*/\s*([A-ZÁÉÍÓÚÑ\s/]{5,60})",
                re.IGNORECASE,
            ),
            re.compile(
                r"(?:NOMBRE|NAME)\s*\.?\s*:?\s*([A-ZÁÉÍÓÚÑ\s]{5,60})(?:\n|NACIONALIDAD|PASAPORTE|$)",
                re.IGNORECASE,
            ),
        ]

        for pattern in patterns:
            match = pattern.search(text)
            if match:
                name = match.group(1).strip()
                # Limpiar caracteres de MRZ y espacios
                name = name.replace("<", " ").replace("  ", " ").strip()
                return name

        return ""

    def _extract_passport_nationality(self, text: str) -> str:
        """
        Extrae la nacionalidad del pasaporte.

        Args:
            text: Texto OCR del pasaporte (en mayúsculas).

        Returns:
            str: Nacionalidad extraída o cadena vacía.
        """
        patterns = [
            re.compile(
                r"NACIONALIDAD\s*\.?\s*:?\s*(MEXICANA|MEXICANO|MEX)",
                re.IGNORECASE,
            ),
            re.compile(
                r"NATIONALITY\s*\.?\s*:?\s*(MEXICAN|MEX)",
                re.IGNORECASE,
            ),
        ]

        for pattern in patterns:
            match = pattern.search(text)
            if match:
                return match.group(1)

        # Si no se encuentra, asumir mexicano si contiene "MEXICO"
        if "MEXICO" in text or "MEXICANA" in text:
            return "MEXICANA"

        return ""

    def _extract_passport_number(self, text: str) -> str:
        """
        Extrae el número de pasaporte.

        Args:
            text: Texto OCR del pasaporte (en mayúsculas).

        Returns:
            str: Número de pasaporte o cadena vacía.
        """
        patterns = [
            re.compile(
                r"PASAPORTE\s*(?:NO|N[ÚU]M)?\s*\.?\s*:?\s*([A-Z0-9]{8,10})",
                re.IGNORECASE,
            ),
            re.compile(
                r"(?:NO|N[ÚU]M)\s*\.?\s*:?\s*([A-Z0-9]{8,10})",
                re.IGNORECASE,
            ),
        ]

        for pattern in patterns:
            match = pattern.search(text)
            if match:
                return match.group(1)

        return ""

    def _extract_passport_birth_date(self, text: str) -> str:
        """
        Extrae la fecha de nacimiento del pasaporte.

        Args:
            text: Texto OCR del pasaporte.

        Returns:
            str: Fecha en formato YYYY-MM-DD o cadena vacía.
        """
        patterns = [
            re.compile(
                r"(?:FECHA\s+DE\s+NACIMIENTO|DATE\s+OF\s+BIRTH|NAC\.)"
                r"\s*\.?\s*:?\s*(\d{2}[/\-\.]\d{2}[/\-\.]\d{4})",
                re.IGNORECASE,
            ),
            re.compile(
                r"(?:FECHA\s+DE\s+NACIMIENTO|NAC\.)"
                r"\s*\.?\s*:?\s*(\d{4}[/\-\.]\d{2}[/\-\.]\d{2})",
                re.IGNORECASE,
            ),
        ]

        for pattern in patterns:
            match = pattern.search(text)
            if match:
                date_str = match.group(1)
                return self._normalize_date(date_str)

        return ""

    def _extract_passport_expiry_date(self, text: str) -> str:
        """
        Extrae la fecha de expiración del pasaporte.

        Args:
            text: Texto OCR del pasaporte.

        Returns:
            str: Fecha en formato YYYY-MM-DD o cadena vacía.
        """
        patterns = [
            re.compile(
                r"(?:FECHA\s+DE\s+EXPIRACI[OÓ]N|EXPIRACI[OÓ]N|EXPIRY)"
                r"\s*\.?\s*:?\s*(\d{2}[/\-\.]\d{2}[/\-\.]\d{4})",
                re.IGNORECASE,
            ),
            re.compile(
                r"(?:VENCIMIENTO|VÁLIDO\s+HASTA)"
                r"\s*\.?\s*:?\s*(\d{2}[/\-\.]\d{2}[/\-\.]\d{4})",
                re.IGNORECASE,
            ),
        ]

        for pattern in patterns:
            match = pattern.search(text)
            if match:
                date_str = match.group(1)
                return self._normalize_date(date_str)

        return ""

    def _extract_passport_mrz(
        self, text: str
    ) -> tuple[str, str]:
        """
        Extrae las dos líneas de la zona de lectura mecánica (MRZ).

        Args:
            text: Texto OCR del pasaporte (en mayúsculas).

        Returns:
            tuple: (mrz_line1, mrz_line2) o ("", "") si no se encuentra.
        """
        # Buscar líneas que parezcan MRZ (44 caracteres alfanuméricos + <)
        mrz_lines = _MRZ_LINE_PATTERN.findall(text)

        if len(mrz_lines) >= 2:
            return mrz_lines[0], mrz_lines[1]
        elif len(mrz_lines) == 1:
            return mrz_lines[0], ""

        return "", ""

    def _extract_address_field(
        self, text: str, field_name: str
    ) -> str:
        """
        Extrae un campo específico de dirección usando patrones.

        Args:
            text: Texto OCR del comprobante.
            field_name: Nombre del campo (street, number, colony, city, state).

        Returns:
            str: Valor del campo o cadena vacía.
        """
        pattern = _ADDRESS_KEYWORDS.get(field_name)
        if not pattern:
            return ""

        match = pattern.search(text)
        if match:
            value = match.group(1).strip()
            # Limpiar caracteres residuales
            value = re.sub(r"[\n\r]+", " ", value)
            value = re.sub(r"\s+", " ", value)
            return value

        return ""

    def _extract_address_state(self, text: str) -> str:
        """
        Extrae el estado del comprobante de domicilio.

        Busca primero por patrón de texto y luego por matching
        directo contra la lista de estados mexicanos.

        Args:
            text: Texto OCR del comprobante.

        Returns:
            str: Estado extraído o cadena vacía.
        """
        # Intentar extracción por patrón
        state = self._extract_address_field(text, "state")
        if state:
            return state

        # Búsqueda directa de estados mexicanos en el texto
        text_upper = text.upper()
        for mex_state in _MEXICAN_STATES:
            if mex_state in text_upper:
                return mex_state.title()

        return ""

    def _extract_zip_code(self, text: str) -> str:
        """
        Extrae el código postal del comprobante.

        Args:
            text: Texto OCR del comprobante.

        Returns:
            str: Código postal o cadena vacía.
        """
        # Buscar "C.P." seguido de 5 dígitos
        patterns = [
            re.compile(r"C\.?\s*P\.?\s*\.?\s*:?\s*(\d{5})", re.IGNORECASE),
            re.compile(
                r"C[OÓ]DIGO\s+POSTAL\s*\.?\s*:?\s*(\d{5})",
                re.IGNORECASE,
            ),
        ]

        for pattern in patterns:
            match = pattern.search(text)
            if match:
                return match.group(1)

        # Buscar cualquier código postal de 5 dígitos aislado
        all_zips = _ZIP_CODE_PATTERN.findall(text)
        # Filtrar códigos postales válidos de México (rangos conocidos)
        for zip_code in all_zips:
            zip_int = int(zip_code)
            if 1000 <= zip_int <= 99999:
                return zip_code

        return ""

    # ── Métodos privados de utilería ──────────────────────────────────────

    def _preprocess_image(self, image) -> Any:
        """
        Preprocesa una imagen para mejorar la calidad del OCR.

        Aplica:
        - Conversión a escala de grises
        - Aumento de contraste
        - Binarización adaptativa (umbral)
        - Aumento de resolución (DPI)

        Args:
            image: Objeto PIL Image.

        Returns:
            Imagen preprocesada.
        """
        try:
            from PIL import Image, ImageEnhance, ImageFilter

            # Convertir a escala de grises
            if image.mode != "L":
                processed = image.convert("L")
            else:
                processed = image.copy()

            # Aumentar resolución si es necesario
            dpi = self._settings.OCR_DPI
            current_dpi = processed.info.get("dpi", (72, 72))
            if current_dpi[0] < dpi:
                scale_factor = dpi / current_dpi[0]
                new_size = (
                    int(processed.width * scale_factor),
                    int(processed.height * scale_factor),
                )
                processed = processed.resize(new_size, Image.Resampling.LANCZOS)

            # Aumentar contraste
            enhancer = ImageEnhance.Contrast(processed)
            processed = enhancer.enhance(1.5)

            # Aplicar filtro de nitidez
            processed = processed.filter(ImageFilter.SHARPEN)

            # Binarización (umbral adaptativo simple)
            threshold = 128
            processed = processed.point(
                lambda p: 255 if p > threshold else 0
            )

            return processed

        except ImportError:
            return image
        except Exception as exc:
            logger.warning("Error en preprocesamiento de imagen: %s", exc)
            return image

    def _validate_image_size(self, image_bytes: bytes) -> None:
        """
        Valida que el tamaño de la imagen esté dentro de los límites.

        Args:
            image_bytes: Bytes de la imagen.

        Raises:
            ValueError: Si la imagen excede el tamaño máximo.
        """
        max_size = self._settings.OCR_MAX_FILE_SIZE_MB * 1024 * 1024
        if len(image_bytes) > max_size:
            raise ValueError(
                f"La imagen excede el tamaño máximo permitido "
                f"({self._settings.OCR_MAX_FILE_SIZE_MB} MB). "
                f"Tamaño actual: {len(image_bytes) / 1024 / 1024:.1f} MB."
            )

    @staticmethod
    def _normalize_text(text: str) -> str:
        """
        Normaliza texto para comparación: elimina acentos, puntuación
        y convierte a mayúsculas.

        Args:
            text: Texto a normalizar.

        Returns:
            str: Texto normalizado.
        """
        import unicodedata

        # Eliminar acentos
        nfkd = unicodedata.normalize("NFKD", text)
        without_accents = "".join(
            c for c in nfkd if not unicodedata.combining(c)
        )
        # Convertir a mayúsculas y eliminar puntuación
        normalized = re.sub(r"[^\w\s]", "", without_accents.upper())
        return re.sub(r"\s+", " ", normalized).strip()

    @staticmethod
    def _normalize_date(date_str: str) -> str:
        """
        Normaliza una fecha al formato YYYY-MM-DD.

        Args:
            date_str: Fecha en formato DD/MM/YYYY o YYYY-MM-DD.

        Returns:
            str: Fecha en formato YYYY-MM-DD.
        """
        # Intentar DD/MM/YYYY
        match = _DATE_DDMMYYYY.match(date_str)
        if match:
            parts = re.split(r"[/\-\.]", date_str)
            if len(parts) == 3:
                return f"{parts[2]}-{parts[1]}-{parts[0]}"

        # Intentar YYYY-MM-DD
        match = _DATE_YYYYMMDD.match(date_str)
        if match:
            return date_str.replace("/", "-")

        return date_str

    @staticmethod
    def _calculate_similarity(s1: str, s2: str) -> float:
        """
        Calcula la similitud entre dos cadenas usando distancia de
        Levenshtein normalizada.

        Args:
            s1: Primera cadena.
            s2: Segunda cadena.

        Returns:
            float: Similitud entre 0.0 y 1.0.
        """
        if not s1 or not s2:
            return 0.0

        # Implementación simplificada de Levenshtein
        len1, len2 = len(s1), len(s2)
        if len1 == 0:
            return 0.0 if len2 > 0 else 1.0

        # Crear matriz de distancia
        prev_row = list(range(len2 + 1))

        for i in range(1, len1 + 1):
            curr_row = [i]
            for j in range(1, len2 + 1):
                cost = 0 if s1[i - 1] == s2[j - 1] else 1
                curr_row.append(
                    min(
                        curr_row[j - 1] + 1,  # inserción
                        prev_row[j] + 1,  # eliminación
                        prev_row[j - 1] + cost,  # sustitución
                    )
                )
            prev_row = curr_row

        distance = prev_row[len2]
        max_len = max(len1, len2)
        return 1.0 - (distance / max_len) if max_len > 0 else 1.0
