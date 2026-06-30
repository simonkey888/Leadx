"""
sinks.py — Sinks del pipeline event-driven v2.0 (corrección A: rol congelado).

================================================================================
ROL DE SINKS (corrección A — capa congelada)
================================================================================

Sinks son EJECUCIÓN PURA. 0 lógica de negocio.

    Input  : Case + PolicyDecision
    Output : resultado de ejecución (ok/skipped/error)

Lo que un Sink puede hacer:
    - Ejecutar la acción indicada por PolicyDecision.actions
    - Loguear al audit trail
    - Retornar el resultado de la ejecución

Lo que un Sink NO puede hacer:
    - Decidir si ejecutar o no (eso lo hace PolicyEngine)
    - Evaluar triggers (eso lo hace PolicyEngine)
    - Mutar el case más allá de lo estrictamente necesario para su acción
      (ej: WhatsAppLinkSink setea case.whatsapp_link, eso es su acción)
    - Llamar a otros sinks
    - Publicar eventos al bus (eso lo hace el orquestador)

Sinks definidos (spec v2.0):
    1. WhatsAppLinkSink    : genera link wa.me si action="generate_whatsapp_intent"
    2. GoogleSheetsWebhookSink: encola case si action="publish_to_sheets"

Cada sink expone:
    - write_with_decision(case, decision)  ← API recomendada (v2.0)
    - write(case)                          ← legacy backward-compat (v1)
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
    """
    Interfaz común para todos los sinks.

    Corrección A: Sinks = ejecución pura. La decisión de qué ejecutar
    vive en PolicyEngine, no acá.
    """

    sink_id: str = "abstract"

    def __init__(self, audit: Optional[AuditTrail] = None):
        self.audit = audit

    @abstractmethod
    def write_with_decision(self, case: Case, decision) -> Dict[str, Any]:
        """
        Ejecuta el sink según PolicyDecision (API v2.0).

        Args:
            case: el case a procesar
            decision: PolicyDecision del PolicyEngine.evaluate(case)

        Returns:
            Dict con: sink_id, status (ok|skipped|error), details
        """
        ...

    def write(self, case: Case) -> Dict[str, Any]:
        """
        Legacy backward-compat (v1). No usar en pipeline v2.0.

        Implementación default: llama a write_with_decision con una
        PolicyDecision sintética. Deprecado.
        """
        from policy_engine import PolicyDecision
        synthetic = PolicyDecision(
            case_id=case.case_id,
            actions=["generate_whatsapp_intent", "publish_to_sheets"],
            reasons=["legacy_write_call"],
            boost_delta=0,
            metadata={"legacy": True},
            decision_id="dec-legacy",
            ruleset_version="legacy",
            timestamp=now_iso(),
        )
        return self.write_with_decision(case, synthetic)

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
    Sink que genera links de WhatsApp.

    Corrección A: ejecución pura. La trigger logic vive en PolicyEngine.

    Comportamiento:
        - Si decision.should_suppress() → skip
        - Si decision.should_generate_whatsapp() → genera link
        - Sino → skip

    No consulta score, no consulta jurisdiction, no consulta status.
    Sólo ejecuta lo que la PolicyDecision dice.
    """

    sink_id = "whatsapp"

    def __init__(
        self,
        audit: Optional[AuditTrail] = None,
        default_message: Optional[str] = None,
        # Parámetros legacy ignorados en v2.0 (sólo para no romper constructor viejo)
        score_threshold: int = 80,
    ):
        super().__init__(audit=audit)
        self.default_message = default_message or config.WHATSAPP_DEFAULT_MESSAGE
        self._legacy_score_threshold = score_threshold  # ignorado en v2.0

    def write_with_decision(self, case: Case, decision) -> Dict[str, Any]:
        """Ejecuta el sink según la decisión del PolicyEngine."""
        # Si la policy dice suprimir, no hacer nada
        if decision.should_suppress():
            self._log("skipped", case.case_id, {
                "reason": "policy_suppress",
                "decision_id": decision.decision_id,
            })
            return {
                "sink_id": self.sink_id,
                "status": "skipped",
                "reason": "policy_suppress",
                "decision_id": decision.decision_id,
            }

        # Si la policy NO dice generar whatsapp intent → skip
        if not decision.should_generate_whatsapp():
            self._log("skipped", case.case_id, {
                "reason": "policy_no_whatsapp_action",
                "decision_id": decision.decision_id,
                "actions": decision.actions,
            })
            return {
                "sink_id": self.sink_id,
                "status": "skipped",
                "reason": "policy_no_whatsapp_action",
                "actions": decision.actions,
                "decision_id": decision.decision_id,
            }

        # Ejecutar: generar link
        link = self.generate_link(case.whatsapp_number)
        case.whatsapp_link = link
        case.updated_at = now_iso()

        # Identificar trigger source desde la decisión (para auditoría)
        trigger_source = "policy_decision"
        if "score >= " in " ".join(decision.reasons):
            trigger_source = "score_threshold"
        elif "manual whatsapp_number present" in " ".join(decision.reasons):
            trigger_source = "manual_number"
        elif "approved by human review" in " ".join(decision.reasons):
            trigger_source = "approved_review"

        self._log("ok" if link else "skipped", case.case_id, {
            "link_generated": bool(link),
            "whatsapp_number_present": bool(case.whatsapp_number),
            "trigger_source": trigger_source,
            "decision_id": decision.decision_id,
            "policy_actions": decision.actions,
            "ruleset_version": decision.ruleset_version,
        })

        if not link:
            return {
                "sink_id": self.sink_id,
                "status": "skipped",
                "reason": "no_whatsapp_number",
                "link": "",
                "decision_id": decision.decision_id,
            }

        return {
            "sink_id": self.sink_id,
            "status": "ok",
            "link": link,
            "trigger": trigger_source,
            "decision_id": decision.decision_id,
            "ruleset_version": decision.ruleset_version,
        }

    def generate_link(self, whatsapp_number: str, message: Optional[str] = None) -> str:
        """Construye https://wa.me/{num}?text={encoded_msg}."""
        if not whatsapp_number:
            return ""
        normalized = "".join(c for c in str(whatsapp_number) if c.isdigit())
        if not normalized:
            return ""
        msg = message or self.default_message
        encoded = quote(msg)
        return f"https://wa.me/{normalized}?text={encoded}"


# ---------------------------------------------------------------------------
# Google Sheets Webhook Sink
# ---------------------------------------------------------------------------
class GoogleSheetsWebhookSink(Sink):
    """
    Sink que escribe casos a Google Sheet vía Apps Script Webhook.

    Corrección A: ejecución pura. Decide si encolar o no basándose en
    PolicyDecision, no en lógica propia.

    Batch: acumula casos y los envía en un único POST al flush().
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
            raise MissingWebhookURLError(
                f"Sink google_sheets no puede inicializar: {e}"
            ) from e

    def write_with_decision(self, case: Case, decision) -> Dict[str, Any]:
        """
        Corrección A: ejecuta según PolicyDecision.

        Si decision.should_suppress() → NO encola (duplicate, etc.)
        Si decision.should_publish_to_sheets() → encola
        Sino → skip
        """
        if decision.should_suppress():
            self._log("skipped", case.case_id, {
                "reason": "policy_suppress",
                "decision_id": decision.decision_id,
            })
            return {
                "sink_id": self.sink_id,
                "status": "skipped",
                "reason": "policy_suppress",
                "decision_id": decision.decision_id,
            }

        if not decision.should_publish_to_sheets():
            self._log("skipped", case.case_id, {
                "reason": "policy_no_publish_action",
                "decision_id": decision.decision_id,
                "actions": decision.actions,
            })
            return {
                "sink_id": self.sink_id,
                "status": "skipped",
                "reason": "policy_no_publish_action",
                "actions": decision.actions,
                "decision_id": decision.decision_id,
            }

        # Encolar para batch
        self._batch.append(case)

        result = {
            "sink_id": self.sink_id,
            "status": "queued",
            "batch_size": len(self._batch),
            "case_id": case.case_id,
            "decision_id": decision.decision_id,
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
    """
    Ejecuta una lista de sinks sobre cada case.

    Corrección A: el fan-out sólo itera y delega. 0 lógica de negocio.
    """

    def __init__(self, sinks: List[Sink]):
        self.sinks = sinks

    def write_with_decision(self, case: Case, decision) -> Dict[str, Any]:
        """
        Ejecuta todos los sinks con PolicyDecision (API v2.0).

        Cada sink decide si ejecutar según decision.actions.
        Si decision.should_suppress() → todos los sinks se saltan.
        """
        results = {}
        for sink in self.sinks:
            try:
                results[sink.sink_id] = sink.write_with_decision(case, decision)
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

    def write(self, case: Case) -> Dict[str, Any]:
        """Legacy backward-compat (v1). No usar en pipeline v2.0."""
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
# Smoke test (spec-only)
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    import sys

    print("=" * 70)
    print("  SMOKE TEST sinks.py (corrección A: ejecución pura)")
    print("=" * 70)

    from models import Case, now_iso
    from policy_engine import PolicyEngine, PolicyDecision, POLICY_RULESET_VERSION

    engine = PolicyEngine()
    wa_sink = WhatsAppLinkSink(score_threshold=80)  # legacy param, ignored in v2.0

    # 1. Caso crítico con whatsapp_number → decision genera action
    case1 = Case(
        case_id="case-crit",
        signal_id="sig-1",
        source_id="facebook_public_groups",
        source_url="https://example.com/p/1", profile_url="",
        timestamp=now_iso(), name_or_alias="Test", evidence_text="Test",
        score=85, jurisdiction="CABA", is_canonical=True,
        whatsapp_number="541155551234",
    )
    decision1 = engine.evaluate(case1)
    result1 = wa_sink.write_with_decision(case1, decision1)
    assert result1["status"] == "ok"
    assert "wa.me/541155551234" in case1.whatsapp_link
    assert result1["ruleset_version"] == POLICY_RULESET_VERSION
    print(f"  ✓ Caso crítico: sink ejecuta según decision (status={result1['status']})")
    print(f"    decision_id = {result1['decision_id']}")
    print(f"    ruleset_version = {result1['ruleset_version']}")

    # 2. Caso sin whatsapp action → sink skip
    case2 = Case(
        case_id="case-low",
        signal_id="sig-2",
        source_id="x_search",
        source_url="https://example.com/p/2", profile_url="",
        timestamp=now_iso(), name_or_alias="Test2", evidence_text="Test2",
        score=42, jurisdiction="MENDOZA", is_canonical=True,
    )
    decision2 = engine.evaluate(case2)
    result2 = wa_sink.write_with_decision(case2, decision2)
    assert result2["status"] == "skipped"
    assert result2["reason"] == "policy_no_whatsapp_action"
    print(f"  ✓ Caso sin action: sink skip (reason={result2['reason']})")

    # 3. Duplicate → suppress → sink skip
    case3 = Case(
        case_id="case-dup",
        signal_id="sig-3",
        source_id="x_search",
        source_url="https://example.com/p/3", profile_url="",
        timestamp=now_iso(), name_or_alias="Test3", evidence_text="Test3",
        score=85, jurisdiction="CABA", is_canonical=False,
        duplicate_of="case-crit",
    )
    decision3 = engine.evaluate(case3)
    result3 = wa_sink.write_with_decision(case3, decision3)
    assert result3["status"] == "skipped"
    assert result3["reason"] == "policy_suppress"
    print(f"  ✓ Duplicate: sink skip (reason={result3['reason']})")

    # 4. GoogleSheetsWebhookSink sin URL → error explícito al flush
    os.environ.pop("RADAR_WEBHOOK_URL", None)
    sheets_sink = GoogleSheetsWebhookSink(batch_size=10)
    # Sin URL, no podemos encolar (write_with_decision debería pasar, pero flush falla)
    # Actually: write_with_decision encola sin validar URL (lazy init en flush)
    # Esto es intencional: el batch se arma aunque no haya URL; el flush falla claro
    sheets_sink.write_with_decision(case1, decision1)
    try:
        sheets_sink.flush()
        print(f"  ✗ FAIL: debería fallar sin URL")
        sys.exit(1)
    except Exception as e:
        assert "Missing webhook URL" in str(e)
        print(f"  ✓ Sheets sink sin URL → '{e}'")

    # 5. FanOut
    fanout = SinkFanOut([wa_sink])
    fanout_result = fanout.write_with_decision(case1, decision1)
    assert "whatsapp" in fanout_result
    assert fanout_result["whatsapp"]["status"] == "ok"
    print(f"  ✓ SinkFanOut ejecuta N sinks con decision")

    # 6. Corrección A: sinks NO consultan triggers internos
    # Verificamos que WhatsAppLinkSink NO tiene should_trigger (eliminado en v2.0)
    assert not hasattr(wa_sink, "should_trigger"), "should_trigger should be removed in v2.0"
    print(f"  ✓ Corrección A: WhatsAppLinkSink NO tiene should_trigger (eliminado)")

    print("\n" + "=" * 70)
    print("  ✓ Corrección A verificada: sinks = ejecución pura, 0 lógica de negocio")
    print("=" * 70)
