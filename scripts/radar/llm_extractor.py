"""
llm_extractor.py — Extractor LLM para pipeline v2.0 (SPEC-ONLY).

Regla del spec v2.0: `no_llm_side_effects: true`
→ El extractor LLM es una función pura: input = signal, output = {entities, normalized_fields}
→ No escribe a ningún sistema externo (no tool calls, no function calling que muta estado)
→ Sólo hace chat completion con schema JSON estricto

Contract:
    input: RADAR_LLM_API_KEY (env var)
           RADAR_LLM_BASE_URL (optional, default: GLM endpoint)
           RADAR_LLM_MODEL    (optional, default: glm-4-flash)
    behavior: si API key falta → raise MissingLLMApiKeyError
              ("Missing LLM API key")

Stub behavior en este entorno:
    - El método extract() está implementado con urllib + JSON schema
    - Pero NO se llama en este entorno (no hay API key)
    - Si se llama sin API key, falla con error explícito
    - Si se llama con API key en un entorno real, hace POST al endpoint
"""
from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from typing import Dict, Any, Optional, List
from dataclasses import dataclass

from models import Signal, Case, now_iso, short_id


# ---------------------------------------------------------------------------
# Excepciones
# ---------------------------------------------------------------------------
class MissingLLMApiKeyError(RuntimeError):
    """Raised when RADAR_LLM_API_KEY is empty."""
    pass


class LLMExtractionError(RuntimeError):
    """Raised when the LLM call fails or returns invalid JSON."""
    pass


# ---------------------------------------------------------------------------
# Schema de salida esperado del LLM
# ---------------------------------------------------------------------------
LLM_OUTPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "entities": {
            "type": "object",
            "properties": {
                "name_or_alias": {"type": "string"},
                "profile_url": {"type": "string"},
                "vehicle_type": {"type": "string"},
                "patent": {"type": "string"},
                "jurisdiction": {"type": "string"},
                "locality": {"type": "string"},
                "problem_type": {"type": "string"},
                "year": {"type": ["integer", "null"]},
                "amount": {"type": ["number", "null"]},
            },
            "required": ["name_or_alias", "profile_url", "vehicle_type",
                         "patent", "jurisdiction", "locality", "problem_type"],
        },
        "normalized_fields": {
            "type": "object",
            "properties": {
                "jurisdiction_canonical": {"type": "string"},
                "vehicle_type_canonical": {"type": "string"},
                "problem_type_canonical": {"type": "string"},
                "amount_normalized": {"type": ["number", "null"]},
                "year_normalized": {"type": ["integer", "null"]},
            },
        },
    },
    "required": ["entities", "normalized_fields"],
}


# ---------------------------------------------------------------------------
# Prompt template
# ---------------------------------------------------------------------------
SYSTEM_PROMPT = """Sos un extractor de entidades para el sistema Radar de Oportunidades.
Tu única tarea es extraer entidades estructuradas de un texto de señal pública
sobre fotomultas, libre deuda, transferencia o regularización vehicular en Argentina.

NO escribas código, NO hagas comentarios, NO agregues campos extra.
Devolvé EXACTAMENTE un JSON con este schema:

{
  "entities": {
    "name_or_alias": "string (alias público del autor, vacío si no se infiere)",
    "profile_url": "string (URL del perfil público, vacío si no aplica)",
    "vehicle_type": "string (auto|moto|camioneta|camion|utilitario, vacío si no se menciona)",
    "patent": "string (patente argentina normalizada sin espacios, vacío si no se menciona)",
    "jurisdiction": "string (CABA|PBA|CORDOBA|SANTA_FE|MENDOZA|TUCUMAN|... vacío si no se infiere)",
    "locality": "string (localidad argentina, vacío si no se infiere)",
    "problem_type": "string (fotomulta|multa|libre_deuda|transferencia|regularizacion|patente|vtv, vacío si no se infiere)",
    "year": integer o null (año del vehículo mencionado, null si no se menciona),
    "amount": number o null (monto en pesos argentinos, null si no se menciona)
  },
  "normalized_fields": {
    "jurisdiction_canonical": "string (jurisdicción en mayúsculas SIN espacios)",
    "vehicle_type_canonical": "string (vehículo en minúsculas singular)",
    "problem_type_canonical": "string (problema en snake_case)",
    "amount_normalized": number o null,
    "year_normalized": integer o null
  }
}

Reglas de compliance:
- NO extraigas DNI, CUIT, email, teléfono, dirección del autor
- Si el texto contiene PII explícita, dejá los campos de entidad vacíos y respondé con un JSON vacío
- Sólo extraé lo que esté explícito en el texto
- No inventes información
"""


USER_PROMPT_TEMPLATE = """Extraé entidades del siguiente texto de señal pública:

---
Texto: {signal_text}
Source ID: {source_id}
Source URL: {source_url}
Author alias: {author_alias}
---

Devolvé sólo el JSON, sin markdown ni texto adicional."""


# ---------------------------------------------------------------------------
# Extractor
# ---------------------------------------------------------------------------
class LLMExtractor:
    """
    Extractor LLM para pipeline v2.0.

    Pure function: input = Signal, output = {entities, normalized_fields}
    No side effects: no tool calls, no API writes besides chat completion.
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        model: Optional[str] = None,
        timeout: int = 30,
    ):
        key = api_key or os.environ.get("RADAR_LLM_API_KEY", "")

        if not key:
            raise MissingLLMApiKeyError(
                "Missing LLM API key (env var RADAR_LLM_API_KEY is empty)"
            )

        self.api_key = key
        self.base_url = base_url or os.environ.get(
            "RADAR_LLM_BASE_URL",
            "https://open.bigmodel.cn/api/paas/v4/chat/completions",
        )
        self.model = model or os.environ.get("RADAR_LLM_MODEL", "glm-4-flash")
        self.timeout = timeout

    # ------------------------------------------------------------------
    # Construcción del prompt
    # ------------------------------------------------------------------
    def _build_user_prompt(self, signal: Signal) -> str:
        return USER_PROMPT_TEMPLATE.format(
            signal_text=signal.raw_text,
            source_id=signal.source_id,
            source_url=signal.source_url,
            author_alias=signal.author_alias,
        )

    # ------------------------------------------------------------------
    # Llamada al LLM (real, pero no se ejecuta en este entorno sin API key)
    # ------------------------------------------------------------------
    def _call_llm(self, user_prompt: str) -> str:
        """Hace POST al endpoint de chat completion. Devuelve el content string."""
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_prompt},
            ],
            "temperature": 0,  # determinista
            "response_format": {"type": "json_object"},
        }
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.api_key}",
            "User-Agent": "radar-oportunidades/2.0 (llm_extractor.py)",
        }

        req = urllib.request.Request(
            self.base_url, data=data, headers=headers, method="POST"
        )
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                body = resp.read().decode("utf-8", errors="replace")
                response = json.loads(body)
                # Estructura típica OpenAI-compatible:
                # {"choices": [{"message": {"content": "..."}}]}
                content = response["choices"][0]["message"]["content"]
                return content
        except urllib.error.HTTPError as e:
            raise LLMExtractionError(
                f"LLM HTTP error {e.code}: {e.read().decode('utf-8', errors='replace')[:200]}"
            ) from e
        except urllib.error.URLError as e:
            raise LLMExtractionError(f"LLM URL error: {e.reason}") from e
        except (KeyError, json.JSONDecodeError) as e:
            raise LLMExtractionError(f"LLM response parse error: {e}") from e

    # ------------------------------------------------------------------
    # Extract principal
    # ------------------------------------------------------------------
    def extract(self, signal: Signal) -> Dict[str, Any]:
        """
        Extract entities + normalized fields from a signal.

        Pure function: no side effects.
        Returns: {"entities": {...}, "normalized_fields": {...}}
        """
        user_prompt = self._build_user_prompt(signal)
        content = self._call_llm(user_prompt)

        try:
            parsed = json.loads(content)
        except json.JSONDecodeError as e:
            raise LLMExtractionError(
                f"LLM returned invalid JSON: {content[:200]}"
            ) from e

        # Validación mínima del schema
        if "entities" not in parsed or "normalized_fields" not in parsed:
            raise LLMExtractionError(
                f"LLM response missing required keys: {list(parsed.keys())}"
            )

        return parsed

    # ------------------------------------------------------------------
    # Convenience: signal → case_partial
    # ------------------------------------------------------------------
    def extract_to_case(self, signal: Signal) -> Case:
        """
        Extract entities y devuelve un Case parcial (sin scoring ni dedup).

        Mapea el output del LLM a los campos del modelo Case.
        """
        result = self.extract(signal)
        ents = result.get("entities", {})
        norm = result.get("normalized_fields", {})

        # Si el LLM detectó PII y devolvió entidades vacías, no crear caso
        if not ents.get("problem_type") and not ents.get("patent") and not ents.get("jurisdiction"):
            raise LLMExtractionError(
                "LLM returned empty entities (possible PII detected or no signal)"
            )

        case = Case(
            case_id=short_id("case", f"{signal.signal_id}|{signal.detected_at}"),
            signal_id=signal.signal_id,
            source_id=signal.source_id,
            source_url=signal.source_url,
            profile_url=ents.get("profile_url", signal.profile_url),
            timestamp=signal.raw_metadata.get("published_at", signal.detected_at),
            name_or_alias=ents.get("name_or_alias", signal.author_alias),
            vehicle_type=norm.get("vehicle_type_canonical") or ents.get("vehicle_type", ""),
            patent=ents.get("patent", ""),
            jurisdiction=norm.get("jurisdiction_canonical") or ents.get("jurisdiction", ""),
            locality=ents.get("locality", ""),
            problem_type=norm.get("problem_type_canonical") or ents.get("problem_type", ""),
            year=norm.get("year_normalized") or ents.get("year"),
            amount=norm.get("amount_normalized") or ents.get("amount"),
            evidence_text=signal.raw_text,
            normalized_text_hash=_text_hash(signal.raw_text),
        )
        return case


def _text_hash(text: str) -> str:
    """Reutilizamos la normalización del extractor v1 para compatibilidad."""
    import hashlib
    import re
    import unicodedata
    t = re.sub(r"https?://\S+", " ", text)
    t = re.sub(r"@\w+", " ", t)
    t = re.sub(r"#\w+", " ", t)
    t = t.lower()
    t = unicodedata.normalize("NFKD", t).encode("ascii", "ignore").decode("ascii")
    t = re.sub(r"[^\w\s]", " ", t)
    t = re.sub(r"\s+", " ", t).strip()
    return hashlib.sha256(t.encode("utf-8")).hexdigest()


# ---------------------------------------------------------------------------
# Smoke test (spec-only): verifica contrato de error, NO llama al LLM
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    import sys

    print("=" * 70)
    print("  SMOKE TEST llm_extractor.py (SPEC-ONLY, no llama al LLM)")
    print("=" * 70)

    # 1. Sin env var → Missing LLM API key
    saved = os.environ.pop("RADAR_LLM_API_KEY", None)
    try:
        try:
            extractor = LLMExtractor()
            print(f"  ✗ FAIL: debería haber lanzado MissingLLMApiKeyError")
            sys.exit(1)
        except MissingLLMApiKeyError as e:
            assert "Missing LLM API key" in str(e), f"Mensaje incorrecto: {e}"
            print(f"  ✓ Sin API key → '{e}'")
    finally:
        if saved is not None:
            os.environ["RADAR_LLM_API_KEY"] = saved

    # 2. Con API key dummy → constructor OK (no hace HTTP hasta extract())
    os.environ["RADAR_LLM_API_KEY"] = "dummy-key-for-construction-test"
    try:
        extractor = LLMExtractor()
        assert extractor.api_key == "dummy-key-for-construction-test"
        assert extractor.model == "glm-4-flash"
        assert "bigmodel.cn" in extractor.base_url
        print(f"  ✓ API key dummy → constructor OK (sin HTTP)")
        print(f"    model = {extractor.model}")
        print(f"    base_url = {extractor.base_url}")

        # 3. Prompt building
        from mock_sources import generate_mock_signals
        sig = generate_mock_signals()[0]
        prompt = extractor._build_user_prompt(sig)
        assert sig.raw_text in prompt
        assert sig.source_id in prompt
        assert sig.source_url in prompt
        print(f"  ✓ _build_user_prompt incluye signal_text, source_id, source_url")
        print(f"    prompt length = {len(prompt)} chars")

        # 4. SYSTEM_PROMPT incluye las reglas de compliance
        assert "DNI" in SYSTEM_PROMPT
        assert "CUIT" in SYSTEM_PROMPT
        assert "no inventes" in SYSTEM_PROMPT.lower()
        print(f"  ✓ SYSTEM_PROMPT incluye reglas anti-PII y no-alucinación")

        # 5. LLM_OUTPUT_SCHEMA está bien formado
        assert "entities" in LLM_OUTPUT_SCHEMA["properties"]
        assert "normalized_fields" in LLM_OUTPUT_SCHEMA["properties"]
        required_ents = LLM_OUTPUT_SCHEMA["properties"]["entities"]["required"]
        assert "problem_type" in required_ents
        assert "patent" in required_ents
        print(f"  ✓ LLM_OUTPUT_SCHEMA tiene {len(required_ents)} entidades requeridas")
    finally:
        os.environ.pop("RADAR_LLM_API_KEY", None)
        if saved is not None:
            os.environ["RADAR_LLM_API_KEY"] = saved

    # 6. _text_hash determinista
    h1 = _text_hash("Hola MUNDO!! Test https://example.com @user #tag")
    h2 = _text_hash("Hola MUNDO!! Test https://example.com @user #tag")
    h3 = _text_hash("Hola MUNDO!! Test diferente")
    assert h1 == h2, "Same text should produce same hash"
    assert h1 != h3, "Different text should produce different hash"
    print(f"  ✓ _text_hash determinista y sensible a cambios")

    print("\n" + "=" * 70)
    print("  ✓ Contrato spec-only verificado. No se llamó al LLM.")
    print("=" * 70)
    print("""
  Reglas del spec v2.0 cumplidas:
    ✓ no_llm_side_effects: extractor es pure function (sólo chat completion)
    ✓ Sin tool calls ni function calling que escriba a sistemas externos
    ✓ SYSTEM_PROMPT prohíbe extraer PII explícita
    ✓ Sin API key → error explícito "Missing LLM API key"

  Para usar en runtime real (máquina del operador):
    export RADAR_LLM_API_KEY=<tu-api-key>
    # opcional: export RADAR_LLM_BASE_URL=https://...
    # opcional: export RADAR_LLM_MODEL=glm-4-flash
    python main.py --event-pipeline
""")
