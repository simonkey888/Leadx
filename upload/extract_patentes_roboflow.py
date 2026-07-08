#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
LeadX Patent Extractor - Roboflow Pipeline
Extracción de patentes argentinas desde imágenes de grupos de Facebook
Arquitectura: Roboflow Detection → DocTR OCR → Regex AR → Enriquecimiento Lead

Autor: LeadX Team
Versión: 4.1
Budget: $0 (Roboflow Free Tier: 15,000 OCR calls/mes)
"""

import os
import re
import json
import time
import base64
import hashlib
import logging
from pathlib import Path
from typing import Optional, List, Dict, Tuple
from dataclasses import dataclass, asdict
from datetime import datetime

import requests
from PIL import Image
import cv2
import numpy as np

# Configuración de logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s | %(levelname)s | %(message)s',
    handlers=[
        logging.FileHandler('patente_extraction.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════════════════════
# CONFIGURACIÓN
# ═══════════════════════════════════════════════════════════════════════════════

@dataclass
class Config:
    """Configuración del pipeline de extracción de patentes."""
    # Roboflow API
    ROBOFLOW_API_KEY: str = os.getenv('ROBOFLOW_API_KEY', '')
    ROBOFLOW_MODEL_ID: str = "xenon-bo5e9/patentes-argentinas-master"  # Dataset público AR
    ROBOFLOW_VERSION: int = 1
    ROBOFLOW_CONFIDENCE: float = 0.4  # Umbral de confianza para detección

    # Límites Free Tier
    MAX_OCR_CALLS_PER_RUN: int = 500  # Seguro para no exceder 15K/mes
    MAX_IMAGES_PER_LEAD: int = 3      # Máximo imágenes a procesar por lead

    # Paths
    INPUT_DIR: Path = Path("./data/lead_images")
    OUTPUT_DIR: Path = Path("./data/patentes_extracted")
    TEMP_DIR: Path = Path("./tmp")

    # Regex patentes Argentina
    PATENTE_VIEJA_RE: str = r'\b[A-Z]{3}\s?\d{3}\b'           # ABC 123
    PATENTE_MERCOSUR_RE: str = r'\b[A-Z]{2}\s?\d{3}\s?[A-Z]{2}\b'  # AB 123 CD

    # DNRPA / Registro Automotor (consulta manual)
    DNRPA_URL_TEMPLATE: str = "https://www.dnrpa.gov.ar/consulta_patente.php?patente={}"

    # Delays para rate limiting
    REQUEST_DELAY: float = 1.5  # Segundos entre calls a Roboflow


# ═══════════════════════════════════════════════════════════════════════════════
# CLASES DE DATOS
# ═══════════════════════════════════════════════════════════════════════════════

@dataclass
class PatenteResult:
    """Resultado de extracción de una patente."""
    patente_raw: str                    # Texto crudo extraído
    patente_normalizada: str            # Formato estándar
    tipo: str                           # 'vieja' | 'mercosur' | 'desconocido'
    confianza_ocr: float                # Confianza del OCR (0-1)
    confianza_detection: float          # Confianza de detección (0-1)
    imagen_fuente: str                  # Path de la imagen origen
    lead_id: str                        # ID del lead asociado
    timestamp: str = ""                 # ISO timestamp
    dnrpa_consultable: bool = False     # Si se puede consultar en DNRPA

    def __post_init__(self):
        if not self.timestamp:
            self.timestamp = datetime.now().isoformat()

    def to_dict(self) -> Dict:
        return asdict(self)


@dataclass
class LeadEnrichment:
    """Enriquecimiento de un lead con datos de patente."""
    lead_id: str
    patentes: List[PatenteResult]
    score_boost: int = 0                # Incremento de score por patente
    contacto_sugerido: str = ""         # Canal sugerido (wa.me / m.me / email)

    def to_dict(self) -> Dict:
        return {
            'lead_id': self.lead_id,
            'patentes': [p.to_dict() for p in self.patentes],
            'score_boost': self.score_boost,
            'contacto_sugerido': self.contacto_sugerido
        }


# ═══════════════════════════════════════════════════════════════════════════════
# DETECTOR DE PATENTES - ROBOFLOW INFERENCE API
# ═══════════════════════════════════════════════════════════════════════════════

class RoboflowPatenteDetector:
    """
    Detector de patentes usando Roboflow Inference API.
    Usa el dataset público 'Patentes Argentinas - Master'.
    """

    def __init__(self, config: Config):
        self.config = config
        self.api_url = (
            f"https://detect.roboflow.com/{config.ROBOFLOW_MODEL_ID}/"
            f"{config.ROBOFLOW_VERSION}"
        )
        self.headers = {
            "Content-Type": "application/x-www-form-urlencoded"
        }
        self.ocr_calls_made = 0

    def _check_api_key(self) -> bool:
        """Verifica que la API key esté configurada."""
        if not self.config.ROBOFLOW_API_KEY:
            logger.error("❌ ROBOFLOW_API_KEY no configurada. Seteá la env var.")
            return False
        return True

    def detect_patente_region(self, image_path: Path) -> Optional[Dict]:
        """
        Detecta la región de la patente en una imagen usando Roboflow.

        Returns:
            Dict con bounding box (x, y, width, height, confidence) o None
        """
        if not self._check_api_key():
            return None

        if self.ocr_calls_made >= self.config.MAX_OCR_CALLS_PER_RUN:
            logger.warning("⚠️ Límite de OCR calls alcanzado para este run.")
            return None

        try:
            # Leer imagen y codificar en base64
            with open(image_path, "rb") as f:
                image_data = base64.b64encode(f.read()).decode('utf-8')

            # Construir URL con API key
            url = f"{self.api_url}?api_key={self.config.ROBOFLOW_API_KEY}"

            # Hacer request
            response = requests.post(
                url,
                data=image_data,
                headers=self.headers,
                timeout=30
            )
            response.raise_for_status()

            self.ocr_calls_made += 1
            time.sleep(self.config.REQUEST_DELAY)  # Rate limiting

            result = response.json()

            # Procesar predicciones
            predictions = result.get('predictions', [])
            if not predictions:
                logger.info(f"📭 No se detectó patente en {image_path.name}")
                return None

            # Tomar la predicción con mayor confianza
            best_pred = max(predictions, key=lambda x: x.get('confidence', 0))
            confidence = best_pred.get('confidence', 0)

            if confidence < self.config.ROBOFLOW_CONFIDENCE:
                logger.info(
                    f"📭 Confianza baja ({confidence:.2f}) en {image_path.name}"
                )
                return None

            bbox = {
                'x': best_pred['x'],
                'y': best_pred['y'],
                'width': best_pred['width'],
                'height': best_pred['height'],
                'confidence': confidence
            }

            logger.info(
                f"✅ Patente detectada en {image_path.name} "
                f"(conf: {confidence:.2f})"
            )
            return bbox

        except requests.exceptions.RequestException as e:
            logger.error(f"❌ Error en request Roboflow: {e}")
            return None
        except Exception as e:
            logger.error(f"❌ Error inesperado en detección: {e}")
            return None

    def crop_patente_region(
        self, 
        image_path: Path, 
        bbox: Dict
    ) -> Optional[np.ndarray]:
        """
        Recorta la región de la patente de la imagen original.

        Args:
            image_path: Path a la imagen original
            bbox: Bounding box con x, y, width, height

        Returns:
            numpy array del crop o None
        """
        try:
            img = cv2.imread(str(image_path))
            if img is None:
                logger.error(f"❌ No se pudo leer {image_path}")
                return None

            h, w = img.shape[:2]

            # Convertir coordenadas centrales a esquina superior izquierda
            x1 = int(max(0, bbox['x'] - bbox['width'] / 2))
            y1 = int(max(0, bbox['y'] - bbox['height'] / 2))
            x2 = int(min(w, bbox['x'] + bbox['width'] / 2))
            y2 = int(min(h, bbox['y'] + bbox['height'] / 2))

            # Agregar padding del 10% para asegurar captura completa
            pad_x = int((x2 - x1) * 0.1)
            pad_y = int((y2 - y1) * 0.1)

            x1 = max(0, x1 - pad_x)
            y1 = max(0, y1 - pad_y)
            x2 = min(w, x2 + pad_x)
            y2 = min(h, y2 + pad_y)

            crop = img[y1:y2, x1:x2]

            if crop.size == 0:
                logger.warning(f"⚠️ Crop vacío para {image_path.name}")
                return None

            return crop

        except Exception as e:
            logger.error(f"❌ Error en crop: {e}")
            return None


# ═══════════════════════════════════════════════════════════════════════════════
# OCR ENGINE - DOCTR (ROBOFLOW) O TESSERACT
# ═══════════════════════════════════════════════════════════════════════════════

class OCREngine:
    """
    Motor OCR para lectura de texto de patentes.
    Intenta DocTR primero, fallback a Tesseract.
    """

    def __init__(self, config: Config):
        self.config = config
        self.use_tesseract = True  # Fallback seguro
        self.use_doctr = False

        # Intentar importar DocTR (requiere instalación)
        try:
            from doctr.io import DocumentFile
            from doctr.models import ocr_predictor
            self.doctr_predictor = ocr_predictor(
                det_arch='db_resnet50',
                reco_arch='crnn_vgg16_bn',
                pretrained=True
            )
            self.use_doctr = True
            logger.info("✅ DocTR OCR cargado correctamente")
        except ImportError:
            logger.warning(
                "⚠️ DocTR no instalado. Usando Tesseract como fallback."
            )

        # Verificar Tesseract
        try:
            import pytesseract
            pytesseract.get_tesseract_version()
            logger.info("✅ Tesseract OCR disponible")
        except Exception:
            logger.error(
                "❌ Tesseract no disponible. Instalar: "
                "sudo apt-get install tesseract-ocr tesseract-ocr-spa"
            )
            self.use_tesseract = False

    def preprocess_for_ocr(self, image: np.ndarray) -> np.ndarray:
        """
        Preprocesa la imagen para mejorar OCR.
        Aplica: escala de grises, threshold, denoise, deskew.
        """
        # Escala de grises
        if len(image.shape) == 3:
            gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        else:
            gray = image

        # Denoise
        denoised = cv2.fastNlMeansDenoising(gray, None, 10, 7, 21)

        # Threshold adaptativo
        _, thresh = cv2.threshold(
            denoised, 0, 255, 
            cv2.THRESH_BINARY + cv2.THRESH_OTSU
        )

        # Deskew (corregir inclinación)
        coords = np.column_stack(np.where(thresh > 0))
        if len(coords) > 0:
            angle = cv2.minAreaRect(coords)[-1]
            if angle < -45:
                angle = -(90 + angle)
            else:
                angle = -angle

            if abs(angle) > 0.5:  # Solo corregir si hay inclinación significativa
                (h, w) = thresh.shape[:2]
                center = (w // 2, h // 2)
                M = cv2.getRotationMatrix2D(center, angle, 1.0)
                thresh = cv2.warpAffine(
                    thresh, M, (w, h),
                    flags=cv2.INTER_CUBIC,
                    borderMode=cv2.BORDER_REPLICATE
                )

        # Resize para mejorar OCR (mínimo 300px de ancho)
        h, w = thresh.shape
        if w < 300:
            scale = 300 / w
            thresh = cv2.resize(
                thresh, None, 
                fx=scale, fy=scale,
                interpolation=cv2.INTER_CUBIC
            )

        return thresh

    def extract_text_tesseract(self, image: np.ndarray) -> Tuple[str, float]:
        """
        Extrae texto usando Tesseract OCR.

        Returns:
            Tuple(texto_extraído, confianza_estimada)
        """
        try:
            import pytesseract

            # Configuración optimizada para patentes
            custom_config = r'--oem 3 --psm 7 -c tessedit_char_whitelist=ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789 '

            # OCR con datos de confianza
            data = pytesseract.image_to_data(
                image,
                config=custom_config,
                output_type=pytesseract.Output.DICT
            )

            # Filtrar solo texto con confianza > 30
            text_parts = []
            confidences = []

            for i, conf in enumerate(data['conf']):
                if int(conf) > 30:
                    text_parts.append(data['text'][i])
                    confidences.append(int(conf))

            text = ' '.join(text_parts).strip()
            avg_conf = sum(confidences) / len(confidences) if confidences else 0

            return text, avg_conf / 100.0

        except Exception as e:
            logger.error(f"❌ Error Tesseract: {e}")
            return "", 0.0

    def extract_text(self, image: np.ndarray) -> Tuple[str, float]:
        """
        Extrae texto de una imagen de patente.
        Intenta DocTR primero, fallback a Tesseract.

        Returns:
            Tuple(texto_extraído, confianza)
        """
        # Preprocesar
        processed = self.preprocess_for_ocr(image)

        # Intentar DocTR si está disponible
        if self.use_doctr:
            try:
                from doctr.io import DocumentFile

                # Guardar temporalmente para DocTR
                temp_path = self.config.TEMP_DIR / f"temp_{hashlib.md5(image.tobytes()).hexdigest()}.png"
                cv2.imwrite(str(temp_path), processed)

                doc = DocumentFile.from_images(str(temp_path))
                result = self.doctr_predictor(doc)

                text = " ".join([
                    word.value 
                    for page in result.pages 
                    for block in page.blocks 
                    for line in block.lines 
                    for word in line.words
                ])

                conf = sum([
                    word.confidence 
                    for page in result.pages 
                    for block in page.blocks 
                    for line in block.lines 
                    for word in line.words
                ]) / max(1, sum([
                    1 for page in result.pages 
                    for block in page.blocks 
                    for line in block.lines 
                    for word in line.words
                ]))

                # Limpiar temp
                temp_path.unlink(missing_ok=True)

                if text.strip():
                    logger.info(f"✅ DocTR extrajo: '{text}' (conf: {conf:.2f})")
                    return text.upper(), conf

            except Exception as e:
                logger.warning(f"⚠️ DocTR falló, usando Tesseract: {e}")

        # Fallback a Tesseract
        if self.use_tesseract:
            text, conf = self.extract_text_tesseract(processed)
            if text.strip():
                logger.info(f"✅ Tesseract extrajo: '{text}' (conf: {conf:.2f})")
                return text.upper(), conf

        logger.warning("⚠️ No se pudo extraer texto de la imagen")
        return "", 0.0


# ═══════════════════════════════════════════════════════════════════════════════
# VALIDADOR DE PATENTES ARGENTINAS
# ═══════════════════════════════════════════════════════════════════════════════

class PatenteValidator:
    """
    Valida y normaliza patentes argentinas.
    Soporta formato viejo (ABC 123) y Mercosur (AB 123 CD).
    """

    # Regex compilados
    PATENTE_VIEJA_RE = re.compile(r'\b([A-Z]{3})\s?(\d{3})\b')
    PATENTE_MERCOSUR_RE = re.compile(r'\b([A-Z]{2})\s?(\d{3})\s?([A-Z]{2})\b')

    # Letras prohibidas en patentes argentinas (para evitar confusiones)
    LETRAS_PROHIBIDAS = {'I', 'O', 'Q', 'Ñ'}

    @classmethod
    def validate_and_normalize(cls, text: str) -> Optional[Dict]:
        """
        Valida y normaliza un texto como patente argentina.

        Returns:
            Dict con patente normalizada y tipo, o None si no es válida
        """
        if not text or len(text) < 6:
            return None

        text = text.upper().strip().replace(' ', '')

        # Intentar formato viejo: ABC123
        match_vieja = cls.PATENTE_VIEJA_RE.search(text)
        if match_vieja:
            letras = match_vieja.group(1)
            numeros = match_vieja.group(2)

            # Validar que no use letras prohibidas
            if not any(l in cls.LETRAS_PROHIBIDAS for l in letras):
                return {
                    'patente': f"{letras} {numeros}",
                    'tipo': 'vieja',
                    'raw': text
                }

        # Intentar formato Mercosur: AB123CD
        match_mercosur = cls.PATENTE_MERCOSUR_RE.search(text)
        if match_mercosur:
            letras1 = match_mercosur.group(1)
            numeros = match_mercosur.group(2)
            letras2 = match_mercosur.group(3)

            # Validar letras prohibidas
            all_letras = letras1 + letras2
            if not any(l in cls.LETRAS_PROHIBIDAS for l in all_letras):
                return {
                    'patente': f"{letras1} {numeros} {letras2}",
                    'tipo': 'mercosur',
                    'raw': text
                }

        return None

    @classmethod
    def is_dnrpa_consultable(cls, patente: str) -> bool:
        """
        Verifica si una patente puede consultarse en DNRPA.
        Actualmente solo verifica formato válido.
        """
        result = cls.validate_and_normalize(patente)
        return result is not None


# ═══════════════════════════════════════════════════════════════════════════════
# PIPELINE PRINCIPAL
# ═══════════════════════════════════════════════════════════════════════════════

class PatenteExtractionPipeline:
    """
    Pipeline completo de extracción de patentes.
    Orquesta: Detector → Cropper → OCR → Validator → Enrichment
    """

    def __init__(self, config: Config = None):
        self.config = config or Config()
        self.detector = RoboflowPatenteDetector(self.config)
        self.ocr = OCREngine(self.config)

        # Crear directorios
        self.config.OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        self.config.TEMP_DIR.mkdir(parents=True, exist_ok=True)

    def process_single_image(
        self, 
        image_path: Path, 
        lead_id: str
    ) -> Optional[PatenteResult]:
        """
        Procesa una sola imagen para extraer patente.

        Args:
            image_path: Path a la imagen
            lead_id: ID del lead asociado

        Returns:
            PatenteResult o None
        """
        logger.info(f"🔍 Procesando imagen: {image_path.name} (lead: {lead_id})")

        # Paso 1: Detectar región de patente
        bbox = self.detector.detect_patente_region(image_path)
        if not bbox:
            return None

        # Paso 2: Recortar región
        crop = self.detector.crop_patente_region(image_path, bbox)
        if crop is None:
            return None

        # Guardar crop para debug (opcional)
        crop_path = self.config.TEMP_DIR / f"crop_{lead_id}_{image_path.stem}.png"
        cv2.imwrite(str(crop_path), crop)

        # Paso 3: OCR
        text, ocr_conf = self.ocr.extract_text(crop)
        if not text:
            return None

        # Paso 4: Validar patente
        validation = PatenteValidator.validate_and_normalize(text)
        if not validation:
            logger.info(f"📭 Texto no es patente válida: '{text}'")
            return None

        # Crear resultado
        result = PatenteResult(
            patente_raw=text,
            patente_normalizada=validation['patente'],
            tipo=validation['tipo'],
            confianza_ocr=ocr_conf,
            confianza_detection=bbox['confidence'],
            imagen_fuente=str(image_path),
            lead_id=lead_id,
            dnrpa_consultable=PatenteValidator.is_dnrpa_consultable(text)
        )

        logger.info(
            f"✅ Patente extraída: {result.patente_normalizada} "
            f"({result.tipo}) | conf OCR: {ocr_conf:.2f}"
        )

        return result

    def process_lead(self, lead_id: str, image_paths: List[Path]) -> LeadEnrichment:
        """
        Procesa todas las imágenes de un lead y enriquece con patentes.

        Args:
            lead_id: ID del lead
            image_paths: Lista de paths a imágenes

        Returns:
            LeadEnrichment con patentes encontradas
        """
        logger.info(f"🚀 Procesando lead: {lead_id} ({len(image_paths)} imágenes)")

        patentes = []
        max_images = min(len(image_paths), self.config.MAX_IMAGES_PER_LEAD)

        for i, img_path in enumerate(image_paths[:max_images]):
            if not img_path.exists():
                logger.warning(f"⚠️ Imagen no existe: {img_path}")
                continue

            result = self.process_single_image(img_path, lead_id)
            if result:
                patentes.append(result)
                # Si encontramos una patente válida, podemos parar
                # (asumimos que un lead = un vehículo)
                break

        # Calcular score boost
        score_boost = 0
        if patentes:
            score_boost = min(20, len(patentes) * 10)  # +10 por patente, máx 20

        enrichment = LeadEnrichment(
            lead_id=lead_id,
            patentes=patentes,
            score_boost=score_boost
        )

        logger.info(
            f"📊 Lead {lead_id}: {len(patentes)} patentes | "
            f"score boost: +{score_boost}"
        )

        return enrichment

    def process_batch(self, leads_dir: Path) -> List[LeadEnrichment]:
        """
        Procesa un batch de leads desde un directorio.
        Estructura esperada:
        leads_dir/
          lead_001/
            img1.jpg
            img2.png
          lead_002/
            img1.jpg

        Args:
            leads_dir: Directorio con subdirectorios por lead

        Returns:
            Lista de LeadEnrichment
        """
        results = []

        for lead_dir in sorted(leads_dir.iterdir()):
            if not lead_dir.is_dir():
                continue

            lead_id = lead_dir.name
            image_paths = [
                f for f in lead_dir.iterdir()
                if f.suffix.lower() in {'.jpg', '.jpeg', '.png', '.webp'}
            ]

            if not image_paths:
                logger.warning(f"⚠️ Lead {lead_id} sin imágenes")
                continue

            enrichment = self.process_lead(lead_id, image_paths)
            results.append(enrichment)

        return results

    def save_results(self, results: List[LeadEnrichment], filename: str = None):
        """Guarda resultados en JSON."""
        if not filename:
            filename = f"patentes_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"

        output_path = self.config.OUTPUT_DIR / filename

        data = {
            'timestamp': datetime.now().isoformat(),
            'total_leads': len(results),
            'leads_with_patente': sum(1 for r in results if r.patentes),
            'results': [r.to_dict() for r in results]
        }

        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)

        logger.info(f"💾 Resultados guardados en: {output_path}")
        return output_path


# ═══════════════════════════════════════════════════════════════════════════════
# INTEGRACIÓN CON LEADX - WEBHOOK PARA WORKER.JS
# ═══════════════════════════════════════════════════════════════════════════════

class LeadXIntegration:
    """
    Integra los resultados de extracción de patentes con el CRM LeadX.
    Genera payload para enviar al webhook de Cloudflare Worker.
    """

    @staticmethod
    def build_webhook_payload(enrichment: LeadEnrichment) -> Dict:
        """
        Construye payload para enviar a /api/apify-webhook o endpoint de enriquecimiento.

        Returns:
            Dict con formato compatible con LeadX KV
        """
        payload = {
            'lead_id': enrichment.lead_id,
            'enrichment_type': 'patente_extraction',
            'timestamp': datetime.now().isoformat(),
            'patentes': [],
            'score_boost': enrichment.score_boost,
            'dnrpa_links': [],
            'contacto_sugerido': enrichment.contacto_sugerido
        }

        for patente in enrichment.patentes:
            p_data = {
                'patente': patente.patente_normalizada,
                'tipo': patente.tipo,
                'confianza': round((patente.confianza_ocr + patente.confianza_detection) / 2, 2),
                'dnrpa_consultable': patente.dnrpa_consultable
            }
            payload['patentes'].append(p_data)

            # Generar link a DNRPA (consulta manual)
            if patente.dnrpa_consultable:
                dnrpa_url = (
                    f"https://www.dnrpa.gov.ar/consulta_patente.php?"
                    f"patente={patente.patente_normalizada.replace(' ', '')}"
                )
                payload['dnrpa_links'].append(dnrpa_url)

        return payload

    @staticmethod
    def send_to_worker(payload: Dict, worker_url: str, secret: str):
        """
        Envía payload enriquecido al Cloudflare Worker de LeadX.

        Args:
            payload: Dict con datos de enriquecimiento
            worker_url: URL del endpoint del Worker
            secret: INGEST_SECRET para autenticación
        """
        try:
            headers = {
                'Content-Type': 'application/json',
                'X-Ingest-Secret': secret
            }

            response = requests.post(
                f"{worker_url}/api/enrich-patente",
                json=payload,
                headers=headers,
                timeout=10
            )
            response.raise_for_status()

            logger.info(f"✅ Enriquecimiento enviado para lead {payload['lead_id']}")
            return True

        except Exception as e:
            logger.error(f"❌ Error enviando a Worker: {e}")
            return False


# ═══════════════════════════════════════════════════════════════════════════════
# EJECUCIÓN PRINCIPAL
# ═══════════════════════════════════════════════════════════════════════════════

def main():
    """Ejecuta el pipeline completo de extracción de patentes."""

    print("=" * 70)
    print("  LeadX Patent Extractor v4.1")
    print("  Roboflow Detection + DocTR/Tesseract OCR + Regex AR")
    print("=" * 70)
    print()

    # Inicializar configuración
    config = Config()

    # Verificar API key
    if not config.ROBOFLOW_API_KEY:
        print("❌ ERROR: Seteá la variable de entorno ROBOFLOW_API_KEY")
        print("   Obtener gratis en: https://app.roboflow.com")
        return 1

    # Inicializar pipeline
    pipeline = PatenteExtractionPipeline(config)

    # Procesar batch de leads
    leads_dir = config.INPUT_DIR

    if not leads_dir.exists():
        print(f"⚠️ Directorio de entrada no existe: {leads_dir}")
        print("   Creando estructura de ejemplo...")
        leads_dir.mkdir(parents=True, exist_ok=True)

        # Crear estructura de ejemplo
        ejemplo = leads_dir / "ejemplo_lead_fb_001"
        ejemplo.mkdir(exist_ok=True)
        print(f"   Creado: {ejemplo}/")
        print("   Colocá las imágenes de actas de infracción ahí.")
        return 0

    # Ejecutar procesamiento
    results = pipeline.process_batch(leads_dir)

    # Guardar resultados
    output_file = pipeline.save_results(results)

    # Resumen
    total = len(results)
    with_patente = sum(1 for r in results if r.patentes)

    print()
    print("=" * 70)
    print("  RESUMEN DE EXTRACCIÓN")
    print("=" * 70)
    print(f"  Total leads procesados: {total}")
    print(f"  Leads con patente:      {with_patente} ({with_patente/total*100:.1f}%)")
    print(f"  Leads sin patente:      {total - with_patente}")
    print(f"  OCR calls usados:       {pipeline.detector.ocr_calls_made}")
    print(f"  Output:                 {output_file}")
    print("=" * 70)

    return 0


if __name__ == "__main__":
    exit(main())
