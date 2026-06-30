"""
webhook_uploader.py — Vía alternativa de subida vía Apps Script Web App (SPEC-ONLY).

En vez de usar gspread + service account JSON, este módulo hace POST HTTP a la
URL de un Google Apps Script Web App (desplegado por el operador) que se
encarga de append las filas a la Sheet.

Contrato de entrada:
    RADAR_WEBHOOK_URL=https://script.google.com/macros/s/<DEPLOY_ID>/exec

Comportamiento:
    - Si la env var no está seteada → raise MissingWebhookURLError
      ("Missing webhook URL")
    - Si la URL no es http(s):// → raise ValueError
    - No hay modo mock ni dry-run implícito.
    - Dry-run explícito vía --dry-run flag en CLI.

Payload enviado (JSON):
    {
      "cases": [
        {
          "case_id": "...",
          "timestamp": "...",       # se reemplaza por el script con Date().toISOString()
          "name_or_alias": "...",
          "profile_url": "...",
          "patent": "...",
          "vehicle_type": "...",
          "jurisdiction": "...",
          "locality": "...",
          "problem_type": "...",
          "year": ...,
          "amount": ...,
          "score": ...,
          "source_name": "...",
          "source_url": "...",
          "evidence_text": "...",
          "whatsapp_number": "..."
        },
        ...
      ]
    }

Respuesta esperada del Apps Script:
    - "OK" si todo bien
    - "NO_CASES" si el payload no tiene cases
    - Cualquier otro string: error reportado por el script

Reglas (glm_instruction_block):
    1. NEVER store private keys inside code (no aplica: no hay keys, sólo URL pública)
    2. ONLY use webhook URL via env var
    3. ONLY append rows (el script hace append, no overwrite)
    4. ALWAYS log case_id after write
    5. DO NOT create duplicates if case_id exists (⚠️ el script actual NO deduplica;
       esta lógica queda del lado del cliente: filtramos cases ya enviados en runs
       previos leyendo cases.jsonl con flag `pushed_to_webhook=True`)
"""
from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from pathlib import Path
from typing import List, Dict, Any, Optional
from urllib.parse import urlparse

import config
from models import Case
from storage import AuditTrail


# ---------------------------------------------------------------------------
# Excepciones
# ---------------------------------------------------------------------------
class MissingWebhookURLError(RuntimeError):
    """Raised when RADAR_WEBHOOK_URL is empty."""
    pass


class WebhookWriteError(RuntimeError):
    """Raised when the webhook POST fails after retry."""
    pass


# ---------------------------------------------------------------------------
# Uploader
# ---------------------------------------------------------------------------
class WebhookUploader:
    """
    Sube casos a Google Sheets vía Apps Script Web App (HTTP POST).

    Contract:
        - input: RADAR_WEBHOOK_URL (env var, string URL)
        - behavior: if URL missing → raise MissingWebhookURLError
                    ("Missing webhook URL")
        - no mocks, no dry-run implicit
        - real HTTP POST happens only when push() is invoked at runtime
          in an environment that has the URL configured
    """

    def __init__(
        self,
        webhook_url: Optional[str] = None,
        audit: Optional[AuditTrail] = None,
        timeout: int = 30,
    ):
        url = webhook_url or os.environ.get("RADAR_WEBHOOK_URL", "")

        if not url:
            raise MissingWebhookURLError(
                "Missing webhook URL (env var RADAR_WEBHOOK_URL is empty)"
            )

        # Validar esquema
        parsed = urlparse(url)
        if parsed.scheme not in ("http", "https"):
            raise MissingWebhookURLError(
                f"Missing webhook URL (invalid scheme: {parsed.scheme})"
            )

        self.webhook_url = url
        self.audit = audit
        self.timeout = timeout

    # ------------------------------------------------------------------
    # Construcción del payload
    # ------------------------------------------------------------------
    def _case_to_payload(self, case: Case) -> Dict[str, Any]:
        """
        Convierte un Case al formato que espera el Apps Script.

        El script ignora: priority_level, whatsapp_link, status, review_state
        (los computa él). Sólo necesita los 15 campos de entrada.
        """
        return {
            "case_id": case.case_id,
            "timestamp": case.timestamp,  # el script lo reemplaza con now()
            "name_or_alias": case.name_or_alias,
            "profile_url": case.profile_url,
            "patent": case.patent,
            "vehicle_type": case.vehicle_type,
            "jurisdiction": case.jurisdiction,
            "locality": case.locality,
            "problem_type": case.problem_type,
            "year": case.year if case.year is not None else "",
            "amount": case.amount if case.amount is not None else "",
            "score": case.score,
            "source_name": case.source_id,
            "source_url": case.source_url,
            "evidence_text": case.evidence_text,
            "whatsapp_number": case.whatsapp_number,
        }

    # ------------------------------------------------------------------
    # POST con retry_once_then_log_error
    # ------------------------------------------------------------------
    def _post(self, payload: Dict[str, Any]) -> str:
        """
        Hace POST JSON al webhook. Retry una vez. Devuelve el body como string.

        Raises WebhookWriteError si falla después del retry.
        """
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        headers = {
            "Content-Type": "application/json",
            "User-Agent": "radar-oportunidades/1.0 (webhook_uploader.py)",
        }

        last_exc: Optional[Exception] = None
        for attempt in (1, 2):
            try:
                req = urllib.request.Request(
                    self.webhook_url, data=data, headers=headers, method="POST"
                )
                with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                    body = resp.read().decode("utf-8", errors="replace")
                    return body
            except urllib.error.HTTPError as e:
                last_exc = e
                if attempt == 1:
                    continue
                raise WebhookWriteError(
                    f"Webhook POST failed (HTTP {e.code}): {e.reason}"
                ) from e
            except urllib.error.URLError as e:
                last_exc = e
                if attempt == 1:
                    continue
                raise WebhookWriteError(f"Webhook POST failed: {e.reason}") from e
            except Exception as e:
                last_exc = e
                if attempt == 1:
                    continue
                raise WebhookWriteError(f"Webhook POST failed: {e}") from e

        # No debería llegar aquí
        raise WebhookWriteError(f"Webhook POST failed: {last_exc}")

    # ------------------------------------------------------------------
    # Push batch
    # ------------------------------------------------------------------
    def push(self, cases: List[Case]) -> Dict[str, Any]:
        """
        Envía un batch de casos al webhook.

        Returns:
            Dict con: total, pushed, response, errors
        """
        if not cases:
            return {
                "operation": "push_cases",
                "target": "webhook",
                "total": 0,
                "pushed": 0,
                "response": "NO_CASES",
                "errors": [],
            }

        payload = {"cases": [self._case_to_payload(c) for c in cases]}

        try:
            response = self._post(payload)
        except WebhookWriteError as e:
            self._log_audit("webhook_push", "error",
                             details={"error": str(e), "total": len(cases)})
            return {
                "operation": "push_cases",
                "target": "webhook",
                "webhook_url": self.webhook_url,
                "total": len(cases),
                "pushed": 0,
                "response": "",
                "errors": [{"error": str(e)}],
            }

        # Interpretar respuesta del Apps Script
        response_clean = response.strip()
        pushed = len(cases) if response_clean == "OK" else 0

        # Log por caso (glm_instruction_block: ALWAYS log case_id after write)
        if pushed:
            for case in cases:
                self._log_audit("webhook_push", "appended",
                                 entity_id=case.case_id,
                                 details={"score": case.score})
        else:
            self._log_audit("webhook_push", "failed",
                             details={"response": response_clean, "total": len(cases)})

        return {
            "operation": "push_cases",
            "target": "webhook",
            "webhook_url": self.webhook_url,
            "total": len(cases),
            "pushed": pushed,
            "response": response_clean,
            "errors": [] if pushed else [{"error": f"Unexpected response: {response_clean}"}],
        }

    def _log_audit(
        self,
        action: str,
        result: str,
        entity_type: str = "case",
        entity_id: str = "",
        details: Optional[Dict[str, Any]] = None,
    ) -> None:
        if self.audit is None:
            return
        self.audit.append(
            actor="system:webhook_uploader",
            action=action,
            entity_type=entity_type,
            entity_id=entity_id,
            details={"result": result, **(details or {})},
        )


# ---------------------------------------------------------------------------
# Smoke test (spec-only): verifica el contrato de error, NO hace HTTP real
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    import sys

    print("=" * 70)
    print("  SMOKE TEST webhook_uploader.py (SPEC-ONLY, no hace HTTP real)")
    print("=" * 70)

    # 1. Sin env var → Missing webhook URL
    saved = os.environ.pop("RADAR_WEBHOOK_URL", None)
    try:
        try:
            uploader = WebhookUploader()
            print(f"  ✗ FAIL: debería haber lanzado MissingWebhookURLError")
            sys.exit(1)
        except MissingWebhookURLError as e:
            assert "Missing webhook URL" in str(e), f"Mensaje incorrecto: {e}"
            print(f"  ✓ Sin URL → '{e}'")
    finally:
        if saved is not None:
            os.environ["RADAR_WEBHOOK_URL"] = saved

    # 2. URL con esquema inválido → Missing webhook URL
    os.environ["RADAR_WEBHOOK_URL"] = "ftp://example.com/script"
    try:
        try:
            uploader = WebhookUploader()
            print(f"  ✗ FAIL: debería haber lanzado MissingWebhookURLError")
            sys.exit(1)
        except MissingWebhookURLError as e:
            assert "invalid scheme" in str(e), f"Mensaje incorrecto: {e}"
            print(f"  ✓ Esquema inválido → '{e}'")
    finally:
        os.environ.pop("RADAR_WEBHOOK_URL", None)
        if saved is not None:
            os.environ["RADAR_WEBHOOK_URL"] = saved

    # 3. URL válida → constructor OK (no hace HTTP hasta llamar a push())
    test_url = "https://script.google.com/macros/s/AKfycbyTest/exec"
    os.environ["RADAR_WEBHOOK_URL"] = test_url
    try:
        uploader = WebhookUploader()
        assert uploader.webhook_url == test_url
        print(f"  ✓ URL válida → constructor OK (sin HTTP)")
        print(f"    webhook_url = {uploader.webhook_url}")

        # 4. _case_to_payload genera exactamente los 15 campos esperados por el script
        from models import Case
        case = Case(
            case_id="case-test",
            signal_id="sig-test",
            source_id="facebook_public_groups",
            source_url="https://example.com/post/abc",
            profile_url="https://example.com/user/1",
            timestamp="2026-06-30T10:00:00-03:00",
            name_or_alias="Test User",
            vehicle_type="auto",
            patent="ABC123",
            jurisdiction="CABA",
            locality="Caballito",
            problem_type="fotomulta",
            year=2020,
            amount=18500.0,
            evidence_text="Test evidence text",
            score=82,
            score_band="critical",
            whatsapp_number="541155551234",
        )
        payload = uploader._case_to_payload(case)
        expected_keys = {
            "case_id", "timestamp", "name_or_alias", "profile_url", "patent",
            "vehicle_type", "jurisdiction", "locality", "problem_type", "year",
            "amount", "score", "source_name", "source_url", "evidence_text",
            "whatsapp_number",
        }
        assert set(payload.keys()) == expected_keys, \
            f"Payload keys mismatch: {set(payload.keys())} vs {expected_keys}"
        print(f"  ✓ _case_to_payload genera {len(payload)} campos esperados por el script")
        print(f"    keys = {sorted(payload.keys())}")

        # 5. push([]) retorna NO_CASES sin hacer HTTP
        empty_result = uploader.push([])
        assert empty_result["response"] == "NO_CASES"
        assert empty_result["pushed"] == 0
        print(f"  ✓ push([]) → 'NO_CASES' (sin HTTP)")
    finally:
        os.environ.pop("RADAR_WEBHOOK_URL", None)
        if saved is not None:
            os.environ["RADAR_WEBHOOK_URL"] = saved

    print("\n" + "=" * 70)
    print("  ✓ Contrato spec-only verificado. No se ejecutaron POSTs HTTP.")
    print("=" * 70)
    print("""
  Para ejecutar push real (en máquina del operador con Web App desplegada):

      # 1. En Apps Script: Implementar > Implementar > Nueva implementación
      #    Tipo: App web
      #    Ejecutar como: Yo
      #    Quién puede acceder: Cualquiera (o solo dominio)
      #    → Copiar URL de implementación
      #
      # 2. Setear env var:
      export RADAR_WEBHOOK_URL=https://script.google.com/macros/s/<DEPLOY_ID>/exec
      #
      # 3. Ejecutar:
      python main.py --sheet-push-webhook

  Si la URL no está seteada, el uploader lanza:
      Missing webhook URL (env var RADAR_WEBHOOK_URL is empty)
""")
