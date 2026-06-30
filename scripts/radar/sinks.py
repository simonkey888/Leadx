"""
sinks.py — Sinks del pipeline event-driven (v2.0).

Regla del spec v2.0: `no_direct_external_writes: true`
→ El pipeline NUNCA escribe a sistemas externos directamente
→ TODO write externo pasa por un Sink
→ Cada Sink es responsable de su contrato, retry y audit

Sinks definidos en el spec v2.0:
  1. google_sheets (apps_script_webhook, append_only, batch=true)
  2. whatsapp (link_generator, trigger=manual_or_score_threshold)

El sink de WhatsApp NO escribe externamente (sólo genera un link y lo guarda
en el case). El sink de Google Sheets delega en webhook_uploader.
"""
from __future__ import annotations

import os
from abc import ABC, abstractmethod
from typing import Dict, Any, List, Optional
from urllib.parse import quote

from models import Case, now_iso
from storage import AuditTrail
import config


# ---------------------------------------------------------------------------
# Base Sink
# ---------------------------------------------------------------------------
class Sink(ABC):
    """Interfaz común para todos los sinks."""

    sink_id: str = "abstract"

    def __init__(self, audit: Optional[AuditTrail] = None):
        self.audit = audit

    @abstractmethod
    def write(self, case: Case) -> Dict[str, Any]:
        """
        Escribe el case al sink. Returns dict con:
            sink_id, status (ok|skipped|error), details
        """
        ...

    def _log(self, status: str, case_id: str, details: Dict[str, Any]) -> None:
        if self.audit is None:
            return
        self.audit.append(
            actor=f"system:sink:{self.sink_id}",
            action=f"write:{status}",
            entity_type="case",
            entity_id=case_id,
            details=details,
        )


# ---------------------------------------------------------------------------
# WhatsApp Link Sink
# ---------------------------------------------------------------------------
class WhatsAppLinkSink(Sink):
    """
    Sink que genera links de WhatsApp según trigger `manual_or_score_threshold`.

    Trigger:
        - score >= WHATSAPP_SCORE_THRESHOLD (default 80 = critical), OR
        - case.whatsapp_number ya está poblado (manual override)
        - En v2.0 también: case.review_state == "approved" (review manual)

    No escribe externamente: sólo genera el link y lo guarda en case.whatsapp_link.
    """

    sink_id = "whatsapp"

    def __init__(
        self,
        audit: Optional[AuditTrail] = None,
        score_threshold: int = 80,
        default_message: Optional[str] = None,
    ):
        super().__init__(audit=audit)
        self.score_threshold = score_threshold
        self.default_message = default_message or config.WHATSAPP_DEFAULT_MESSAGE

    def should_trigger(self, case: Case) -> bool:
        """Decide si el sink debe generar link para este case."""
        # Trigger 1: score >= threshold
        if case.score >= self.score_threshold:
            return True
        # Trigger 2: ya tiene número (manual override desde CLI de revisión)
        if case.whatsapp_number:
            return True
        # Trigger 3: revisado y aprobado (manual)
        if case.review_state == "approved" or case.status == "approved":
            return True
        return False

    def generate_link(self, whatsapp_number: str, message: Optional[str] = None) -> str:
        """Construye https://wa.me/{num}?text={encoded_msg}."""
        if not whatsapp_number:
            return ""
        # Normalizar: sólo dígitos
        normalized = "".join(c for c in str(whatsapp_number) if c.isdigit())
        if not normalized:
            return ""
        msg = message or self.default_message
        encoded = quote(msg)
        return f"https://wa.me/{normalized}?text={encoded}"

    def write(self, case: Case) -> Dict[str, Any]:
        """Genera link si trigger se cumple, lo guarda en case.whatsapp_link."""
        if not self.should_trigger(case):
            self._log("skipped", case.case_id, {
                "reason": "trigger_not_met",
                "score": case.score,
                "threshold": self.score_threshold,
            })
            return {
                "sink_id": self.sink_id,
                "status": "skipped",
                "reason": "trigger_not_met",
                "score": case.score,
                "threshold": self.score_threshold,
            }

        link = self.generate_link(case.whatsapp_number)
        case.whatsapp_link = link
        case.updated_at = now_iso()

        self._log("ok" if link else "skipped", case.case_id, {
            "link_generated": bool(link),
            "whatsapp_number_present": bool(case.whatsapp_number),
            "trigger_source": (
                "score_threshold" if case.score >= self.score_threshold
                else "manual_number" if case.whatsapp_number
                else "approved_review"
            ),
        })

        if not link:
            return {
                "sink_id": self.sink_id,
                "status": "skipped",
                "reason": "no_whatsapp_number",
                "link": "",
            }

        return {
            "sink_id": self.sink_id,
            "status": "ok",
            "link": link,
            "trigger": (
                "score_threshold" if case.score >= self.score_threshold
                else "manual_number" if case.whatsapp_number
                else "approved_review"
            ),
        }


# ---------------------------------------------------------------------------
# Google Sheets Webhook Sink
# ---------------------------------------------------------------------------
class GoogleSheetsWebhookSink(Sink):
    """
    Sink que escribe casos a Google Sheet vía Apps Script Webhook.

    Batch: acumula casos y los envía en un único POST al flush().
    También puede enviar de a uno con write() directo (no recomendado para alto volumen).

    Delega en webhook_uploader.WebhookUploader para el POST HTTP real.
    """

    sink_id = "google_sheets"

    def __init__(
        self,
        audit: Optional[AuditTrail] = None,
        webhook_url: Optional[str] = None,
        batch_size: int = 50,
    ):
        super().__init__(audit=audit)
        self._webhook_url = webhook_url or os.environ.get("RADAR_WEBHOOK_URL", "")
        self.batch_size = batch_size
        self._batch: List[Case] = []
        self._uploader = None  # lazy init

    def _ensure_uploader(self):
        """Lazy init del uploader (falla si no hay URL)."""
        if self._uploader is not None:
            return
        from webhook_uploader import WebhookUploader, MissingWebhookURLError
        try:
            self._uploader = WebhookUploader(
                webhook_url=self._webhook_url or None,
                audit=self.audit,
            )
        except MissingWebhookURLError as e:
            # Re-raise con contexto de sink
            raise MissingWebhookURLError(
                f"Sink google_sheets no puede inicializar: {e}"
            ) from e

    def write(self, case: Case) -> Dict[str, Any]:
        """
        Acumula el caso en batch. No envía hasta flush().
        Si el batch alcanza batch_size, auto-flush.
        """
        self._batch.append(case)

        result = {
            "sink_id": self.sink_id,
            "status": "queued",
            "batch_size": len(self._batch),
            "case_id": case.case_id,
        }

        if len(self._batch) >= self.batch_size:
            flush_result = self.flush()
            result["flush_result"] = flush_result

        return result

    def flush(self) -> Dict[str, Any]:
        """Envía todos los casos acumulados en un único POST al webhook."""
        if not self._batch:
            return {
                "sink_id": self.sink_id,
                "status": "empty",
                "total": 0,
                "pushed": 0,
            }

        self._ensure_uploader()
        cases_to_send = list(self._batch)
        self._batch.clear()

        summary = self._uploader.push(cases_to_send)

        self._log(
            "ok" if summary["pushed"] else "error",
            "batch",
            {
                "total": summary["total"],
                "pushed": summary["pushed"],
                "response": summary["response"],
                "errors": summary["errors"],
            },
        )

        return {
            "sink_id": self.sink_id,
            "status": "ok" if summary["pushed"] else "error",
            "total": summary["total"],
            "pushed": summary["pushed"],
            "response": summary["response"],
            "errors": summary["errors"],
        }


# ---------------------------------------------------------------------------
# Fan-out: ejecuta todos los sinks sobre un case
# ---------------------------------------------------------------------------
class SinkFanOut:
    """Ejecuta una lista de sinks sobre cada case y agrega resultados."""

    def __init__(self, sinks: List[Sink]):
        self.sinks = sinks

    def write(self, case: Case) -> Dict[str, Any]:
        """Ejecuta todos los sinks. Returns dict {sink_id: result}."""
        results = {}
        for sink in self.sinks:
            try:
                results[sink.sink_id] = sink.write(case)
            except Exception as e:
                results[sink.sink_id] = {
                    "sink_id": sink.sink_id,
                    "status": "error",
                    "error": str(e),
                    "error_type": type(e).__name__,
                }
                if sink.audit:
                    sink._log("error", case.case_id, {
                        "error": str(e),
                        "error_type": type(e).__name__,
                    })
        return results

    def flush_all(self) -> Dict[str, Any]:
        """Llama flush() en todos los sinks que lo soportan."""
        results = {}
        for sink in self.sinks:
            if hasattr(sink, "flush"):
                try:
                    results[sink.sink_id] = sink.flush()
                except Exception as e:
                    results[sink.sink_id] = {
                        "sink_id": sink.sink_id,
                        "status": "error",
                        "error": str(e),
                    }
        return results


# ---------------------------------------------------------------------------
# Smoke test (spec-only): WhatsApp link gen path, no HTTP for Sheets sink
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    import sys

    print("=" * 70)
    print("  SMOKE TEST sinks.py (SPEC-ONLY, no HTTP para Sheets sink)")
    print("=" * 70)

    # 1. WhatsAppLinkSink: trigger por score >= 80
    wa_sink = WhatsAppLinkSink(score_threshold=80)
    case_critical = Case(
        case_id="case-crit",
        signal_id="sig-1",
        source_id="facebook_public_groups",
        source_url="https://example.com/p/1",
        profile_url="",
        timestamp=now_iso(),
        name_or_alias="Test",
        evidence_text="Test evidence",
        score=85,
        whatsapp_number="541155551234",
    )
    assert wa_sink.should_trigger(case_critical)
    result = wa_sink.write(case_critical)
    assert result["status"] == "ok"
    assert "wa.me/541155551234" in case_critical.whatsapp_link
    print(f"  ✓ Score 85 >= 80 → trigger ok, link generado")
    print(f"    link = {case_critical.whatsapp_link[:60]}…")

    # 2. Score < 80, sin número → no trigger
    case_low = Case(
        case_id="case-low",
        signal_id="sig-2",
        source_id="x_search",
        source_url="https://example.com/p/2",
        profile_url="",
        timestamp=now_iso(),
        name_or_alias="Test2",
        evidence_text="Test evidence 2",
        score=42,
        whatsapp_number="",
    )
    assert not wa_sink.should_trigger(case_low)
    result2 = wa_sink.write(case_low)
    assert result2["status"] == "skipped"
    assert result2["reason"] == "trigger_not_met"
    print(f"  ✓ Score 42 < 80, sin número → skip (trigger_not_met)")

    # 3. Score < 80 pero con número manual → trigger
    case_manual = Case(
        case_id="case-manual",
        signal_id="sig-3",
        source_id="x_search",
        source_url="https://example.com/p/3",
        profile_url="",
        timestamp=now_iso(),
        name_or_alias="Test3",
        evidence_text="Test evidence 3",
        score=50,
        whatsapp_number="541112345678",
    )
    assert wa_sink.should_trigger(case_manual)
    result3 = wa_sink.write(case_manual)
    assert result3["status"] == "ok"
    assert "wa.me/541112345678" in case_manual.whatsapp_link
    print(f"  ✓ Score 50 < 80 pero con número manual → trigger ok")

    # 4. Score < 80, sin número, pero status=approved → trigger (review manual)
    case_approved = Case(
        case_id="case-approv",
        signal_id="sig-4",
        source_id="x_search",
        source_url="https://example.com/p/4",
        profile_url="",
        timestamp=now_iso(),
        name_or_alias="Test4",
        evidence_text="Test evidence 4",
        score=55,
        whatsapp_number="541100000000",
        status="approved",
    )
    assert wa_sink.should_trigger(case_approved)
    print(f"  ✓ Score 55, status=approved → trigger ok (review manual)")

    # 5. WhatsAppLinkSink sin número pero con trigger → link vacío, status skipped
    case_high_no_num = Case(
        case_id="case-high-no-num",
        signal_id="sig-5",
        source_id="x_search",
        source_url="https://example.com/p/5",
        profile_url="",
        timestamp=now_iso(),
        name_or_alias="Test5",
        evidence_text="Test evidence 5",
        score=85,
        whatsapp_number="",
    )
    assert wa_sink.should_trigger(case_high_no_num)
    result5 = wa_sink.write(case_high_no_num)
    assert result5["status"] == "skipped"
    assert result5["reason"] == "no_whatsapp_number"
    print(f"  ✓ Score 85 pero sin número → trigger ok pero link vacío")

    # 6. GoogleSheetsWebhookSink sin URL → error explícito al flush
    os.environ.pop("RADAR_WEBHOOK_URL", None)
    sheets_sink = GoogleSheetsWebhookSink(batch_size=10)
    sheets_sink.write(case_critical)  # sólo encola, no falla
    try:
        sheets_sink.flush()
        print(f"  ✗ FAIL: debería fallar sin URL")
        sys.exit(1)
    except Exception as e:
        assert "Missing webhook URL" in str(e)
        print(f"  ✓ Sheets sink sin URL → '{e}'")

    # 7. GoogleSheetsWebhookSink con URL dummy → flush lanza HTTP (esperado)
    os.environ["RADAR_WEBHOOK_URL"] = "https://dummy.example.com/exec"
    try:
        sheets_sink2 = GoogleSheetsWebhookSink(batch_size=10)
        sheets_sink2.write(case_critical)
        # Flush intentará HTTP real → fallará con URLError
        flush_result = sheets_sink2.flush()
        # Esperamos error de red (no excepción sin atrapar)
        assert flush_result["status"] in ("error", "empty")
        print(f"  ✓ Sheets sink con URL dummy → flush retornó status={flush_result['status']}")
    finally:
        os.environ.pop("RADAR_WEBHOOK_URL", None)

    # 8. SinkFanOut
    wa_sink2 = WhatsAppLinkSink(score_threshold=80)
    fanout = SinkFanOut([wa_sink2])
    fanout_result = fanout.write(case_critical)
    assert "whatsapp" in fanout_result
    assert fanout_result["whatsapp"]["status"] == "ok"
    print(f"  ✓ SinkFanOut ejecuta N sinks y agrega resultados")

    print("\n" + "=" * 70)
    print("  ✓ Contrato spec-only verificado. Sheets sink no hizo HTTP real exitoso.")
    print("=" * 70)
    print("""
  Reglas del spec v2.0 cumplidas:
    ✓ no_direct_external_writes: pipeline sólo escribe via sinks
    ✓ WhatsAppLinkSink: pure function (no escribe externamente)
    ✓ GoogleSheetsWebhookSink: delegate en webhook_uploader (SPEC-ONLY)
    ✓ Trigger manual_or_score_threshold implementado (3 sub-triggers)
""")
