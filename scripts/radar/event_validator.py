"""
event_validator.py — Validación de eventos contra el data_contract v2.0.

Regla del spec: `requires_event_validation: true`

Cada evento debe pasar por validate() antes de ser dispatchado por el bus.
Si falla, se emite un EventRejected y el original no se procesa.

Data_contract:
    case_id: string (no vacío)
    patent: string (puede estar vacío)
    jurisdiction: string (puede estar vacío)
    score: number (0-100)
    source: string (no vacío)
    evidence: string (no vacío)
    timestamp: iso8601 (parseable)
"""
from __future__ import annotations
from dataclasses import dataclass
from datetime import datetime
from typing import List, Tuple, Optional

from event_types import Event


@dataclass
class ValidationResult:
    valid: bool
    errors: List[str]
    warnings: List[str]


# ---------------------------------------------------------------------------
# Validators por tipo de dato
# ---------------------------------------------------------------------------
def _is_string(v) -> bool:
    return isinstance(v, str)


def _is_number(v) -> bool:
    return isinstance(v, (int, float)) and not isinstance(v, bool)


def _is_iso8601(v) -> bool:
    if not isinstance(v, str) or not v:
        return False
    try:
        # fromisoformat soporta tz offsets desde 3.11+; para 3.10 fallback
        datetime.fromisoformat(v.replace("Z", "+00:00"))
        return True
    except (ValueError, TypeError):
        return False


# ---------------------------------------------------------------------------
# Validator principal
# ---------------------------------------------------------------------------
def validate_event(event) -> ValidationResult:
    """
    Valida un evento contra el data_contract.

    Cada tipo de evento tiene campos obligatorios distintos:
        - SignalCollected: requiere signal con raw_text + source_id + source_url + detected_at
        - EntitiesExtracted: requiere case_partial con case_id + source_id + evidence_text + timestamp
        - CaseScored: requiere case con case_id + score + source_id + evidence_text + timestamp
        - CaseDeduplicated: requiere case + is_canonical
        - CasePublished: requiere case_id + sinks_result
        - EventRejected: siempre válido (es el fallback)
    """
    errors: List[str] = []
    warnings: List[str] = []

    # Campos base (todos los eventos concretos los tienen)
    if not getattr(event, "event_id", ""):
        errors.append("event_id is empty")
    if not getattr(event, "event_type", ""):
        errors.append("event_type is empty")
    if not _is_iso8601(getattr(event, "timestamp", "")):
        errors.append(f"timestamp is not iso8601: {getattr(event, 'timestamp', '')!r}")
    if not isinstance(getattr(event, "payload", None), dict):
        errors.append("payload is not a dict")
        return ValidationResult(False, errors, warnings)

    event_type = event.event_type
    payload = event.payload

    # Validación por tipo
    if event_type == "signal_collected":
        sig = payload.get("signal")
        if not isinstance(sig, dict):
            errors.append("payload.signal must be a dict")
        else:
            for f in ("source_id", "source_url", "raw_text", "detected_at"):
                if not sig.get(f):
                    errors.append(f"signal.{f} is empty")
            if sig.get("detected_at") and not _is_iso8601(sig["detected_at"]):
                errors.append(f"signal.detected_at is not iso8601: {sig.get('detected_at')!r}")

    elif event_type == "entities_extracted":
        cp = payload.get("case_partial")
        if not isinstance(cp, dict):
            errors.append("payload.case_partial must be a dict")
        else:
            for f in ("case_id", "source_id", "evidence_text", "timestamp"):
                if not cp.get(f):
                    errors.append(f"case_partial.{f} is empty")
            if cp.get("timestamp") and not _is_iso8601(cp["timestamp"]):
                errors.append(f"case_partial.timestamp is not iso8601")
            if "score" in cp and not _is_number(cp["score"]):
                errors.append(f"case_partial.score is not a number: {cp.get('score')!r}")

    elif event_type == "case_scored":
        c = payload.get("case")
        if not isinstance(c, dict):
            errors.append("payload.case must be a dict")
        else:
            errors.extend(_validate_case_contract(c))
            # Corrección B: score_version recomendado (warning si falta)
            if not c.get("score_version"):
                warnings.append("case.score_version is empty (recommended: v1.0_weighted_sum)")

    elif event_type == "case_deduplicated":
        c = payload.get("case")
        if not isinstance(c, dict):
            errors.append("payload.case must be a dict")
        else:
            errors.extend(_validate_case_contract(c))
            if not c.get("score_version"):
                warnings.append("case.score_version is empty (recommended: v1.0_weighted_sum)")
        if "is_canonical" not in payload:
            errors.append("payload.is_canonical is missing")

    elif event_type == "case_published":
        if not payload.get("case_id"):
            errors.append("payload.case_id is empty")
        if "sinks_result" not in payload:
            errors.append("payload.sinks_result is missing")

    elif event_type == "event_rejected":
        pass  # siempre válido

    elif event_type == "policy_evaluated":
        if not payload.get("case_id"):
            errors.append("payload.case_id is empty")
        decision = payload.get("decision")
        if not isinstance(decision, dict):
            errors.append("payload.decision must be a dict")
        else:
            if not isinstance(decision.get("actions"), list):
                errors.append("decision.actions must be a list")
            if not isinstance(decision.get("reasons"), list):
                errors.append("decision.reasons must be a list")
            if not isinstance(decision.get("boost_delta"), int):
                errors.append(f"decision.boost_delta must be int: {decision.get('boost_delta')!r}")

    else:
        warnings.append(f"unknown event_type: {event_type}")

    return ValidationResult(valid=len(errors) == 0, errors=errors, warnings=warnings)


def _validate_case_contract(c: dict) -> List[str]:
    """
    Valida un case contra el data_contract del spec v2.0:
        case_id: string (no vacío)
        patent: string
        jurisdiction: string
        score: number (0-100)
        source: string (no vacío)  → en nuestro modelo es source_id
        evidence: string (no vacío) → en nuestro modelo es evidence_text
        timestamp: iso8601
    """
    errors: List[str] = []

    if not _is_string(c.get("case_id")) or not c["case_id"]:
        errors.append("case.case_id must be non-empty string")
    if not _is_string(c.get("patent")):
        errors.append("case.patent must be string (can be empty)")
    if not _is_string(c.get("jurisdiction")):
        errors.append("case.jurisdiction must be string (can be empty)")
    if not _is_number(c.get("score")):
        errors.append(f"case.score must be number: {c.get('score')!r}")
    elif not (0 <= c["score"] <= 100):
        errors.append(f"case.score out of range [0,100]: {c['score']}")
    if not _is_string(c.get("source_id")) or not c["source_id"]:
        errors.append("case.source_id must be non-empty string (data_contract: source)")
    if not _is_string(c.get("evidence_text")) or not c["evidence_text"]:
        errors.append("case.evidence_text must be non-empty string (data_contract: evidence)")
    if not _is_iso8601(c.get("timestamp", "")):
        errors.append(f"case.timestamp must be iso8601: {c.get('timestamp')!r}")

    return errors


# ---------------------------------------------------------------------------
# Smoke test
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    from event_types import SignalCollected, CaseScored, make_event_id
    from models import Signal, Case, now_iso
    from mock_sources import generate_mock_signals

    print("=== Smoke test event_validator ===\n")

    sigs = generate_mock_signals()
    sig = sigs[0]
    sig_dict = sig.to_dict()

    # 1. SignalCollected válido
    evt = SignalCollected(
        event_id=make_event_id("sig", sig.signal_id),
        event_type="signal_collected",
        timestamp=now_iso(),
        payload={"signal": sig_dict},
    )
    r = validate_event(evt)
    assert r.valid, f"Should be valid: {r.errors}"
    print(f"  ✓ SignalCollected válido ({len(r.warnings)} warnings)")

    # 2. SignalCollected inválido (sin source_id)
    bad_sig = dict(sig_dict)
    bad_sig["source_id"] = ""
    evt2 = SignalCollected(
        event_id=make_event_id("sig-bad", "x"),
        event_type="signal_collected",
        timestamp=now_iso(),
        payload={"signal": bad_sig},
    )
    r2 = validate_event(evt2)
    assert not r2.valid, "Should be invalid"
    assert any("source_id" in e for e in r2.errors)
    print(f"  ✓ SignalCollected inválido detectado: {r2.errors[0]}")

    # 3. CaseScored válido
    case = Case(
        case_id="case-test",
        signal_id="sig-test",
        source_id="facebook_public_groups",
        source_url="https://example.com/p/1",
        profile_url="",
        timestamp=now_iso(),
        name_or_alias="Test",
        evidence_text="Test evidence",
        score=75,
    )
    evt3 = CaseScored(
        event_id=make_event_id("case", case.case_id),
        event_type="case_scored",
        timestamp=now_iso(),
        payload={"case": case.to_dict()},
    )
    r3 = validate_event(evt3)
    assert r3.valid, f"Should be valid: {r3.errors}"
    print(f"  ✓ CaseScored válido (data_contract OK)")

    # 4. CaseScored inválido (score fuera de rango)
    bad_case = case.to_dict()
    bad_case["score"] = 150
    evt4 = CaseScored(
        event_id=make_event_id("case-bad", "x"),
        event_type="case_scored",
        timestamp=now_iso(),
        payload={"case": bad_case},
    )
    r4 = validate_event(evt4)
    assert not r4.valid
    assert any("out of range" in e for e in r4.errors)
    print(f"  ✓ CaseScored inválido detectado: {r4.errors[0]}")

    # 5. Timestamp inválido
    bad_case2 = case.to_dict()
    bad_case2["timestamp"] = "not-a-date"
    evt5 = CaseScored(
        event_id=make_event_id("case-bad2", "x"),
        event_type="case_scored",
        timestamp=now_iso(),
        payload={"case": bad_case2},
    )
    r5 = validate_event(evt5)
    assert not r5.valid
    assert any("iso8601" in e for e in r5.errors)
    print(f"  ✓ Timestamp inválido detectado: {r5.errors[0]}")

    print("\n=== Todos los smoke tests OK ===")
