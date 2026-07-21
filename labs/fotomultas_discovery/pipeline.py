"""Fail-closed candidate evaluation and batch orchestration."""

from __future__ import annotations

import hashlib
import json
import re
import unicodedata
from datetime import datetime, timezone
from typing import Any
from urllib.parse import urlparse

from .constants import (
    ALLOWED_AUTHORIZATION_BASES,
    DEBT_THRESHOLD_ARS,
    MAX_VERIFICATION_AGE_DAYS,
    RAW_IDENTIFIER_FIELDS,
    SINAI_HOST,
    SINAI_PROVIDER,
    TARGET_VERTICAL,
)
from .contacts import extract_public_contacts, has_contact
from .debt import summarize_active_debt

_ID_RE = re.compile(r"^[A-Za-z0-9:_-]{1,120}$")
_SHA256_RE = re.compile(r"^[a-f0-9]{64}$")


def _decision(candidate_id: str, status: str, reason: str, **extra: Any) -> dict[str, Any]:
    return {"candidate_id": candidate_id, "status": status, "reason": reason, **extra}


def _public_https_url(value: Any) -> bool:
    try:
        parsed = urlparse(str(value or ""))
        return parsed.scheme == "https" and bool(parsed.hostname)
    except ValueError:
        return False


def _sinai_url(value: Any) -> bool:
    try:
        parsed = urlparse(str(value or ""))
        return parsed.scheme == "https" and parsed.hostname == SINAI_HOST
    except ValueError:
        return False


def _parse_datetime(value: Any) -> datetime | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _normalize_text(value: Any) -> str:
    text = unicodedata.normalize("NFKD", str(value or "").strip().lower())
    text = text.encode("ascii", "ignore").decode("ascii")
    return " ".join(re.sub(r"[^a-z0-9]+", " ", text).split())


def _contains_raw_identifier(value: Any) -> bool:
    if isinstance(value, dict):
        for key, nested in value.items():
            if _normalize_text(key).replace(" ", "_") in RAW_IDENTIFIER_FIELDS and nested not in (None, "", [], {}):
                return True
            if _contains_raw_identifier(nested):
                return True
    elif isinstance(value, list):
        return any(_contains_raw_identifier(item) for item in value)
    return False


def _entity_fingerprint(candidate: dict[str, Any], contacts: dict[str, list[str]]) -> str:
    material = {
        "entity_key": _normalize_text(candidate.get("entity_key")),
        "entity_name": _normalize_text(candidate.get("entity_name") or candidate.get("persona") or candidate.get("name")),
        "source_host": urlparse(str(candidate.get("source_url") or "")).hostname or "",
        "emails": contacts["emails"],
        "phones": contacts["phones"],
        "whatsapp": contacts["whatsapp"],
    }
    encoded = json.dumps(material, ensure_ascii=True, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _evidence_hash(candidate_id: str, verification: dict[str, Any], debt: dict[str, Any]) -> str:
    material = {
        "candidate_id": candidate_id,
        "checked_at": verification.get("checked_at"),
        "provider": verification.get("provider"),
        "source_url": verification.get("source_url"),
        "subject_ref_hash": verification.get("subject_ref_hash"),
        "active_count": debt["active_count"],
        "active_total_ars": debt["active_total_ars"],
        "infraction_fingerprints": debt["infraction_fingerprints"],
    }
    encoded = json.dumps(material, ensure_ascii=True, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def evaluate_candidate(
    candidate: dict[str, Any],
    verification: dict[str, Any] | None,
    *,
    now: datetime | None = None,
) -> dict[str, Any]:
    now_utc = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    candidate_id = str(candidate.get("id") or candidate.get("candidate_id") or "").strip()
    if not _ID_RE.fullmatch(candidate_id):
        return _decision(candidate_id or "invalid", "REJECTED", "invalid_candidate_id")
    if candidate.get("vertical") != TARGET_VERTICAL:
        return _decision(candidate_id, "REJECTED", "vertical_not_allowed")
    if not _public_https_url(candidate.get("source_url")):
        return _decision(candidate_id, "REJECTED", "invalid_public_source")

    contacts = extract_public_contacts(candidate)
    if not has_contact(contacts):
        return _decision(candidate_id, "REJECTED", "public_contact_required")

    entity_fingerprint = _entity_fingerprint(candidate, contacts)
    if verification is None:
        return _decision(
            candidate_id,
            "PENDING_VERIFICATION",
            "official_verification_missing",
            contacts=contacts,
            entity_fingerprint=entity_fingerprint,
        )
    if not isinstance(verification, dict):
        return _decision(candidate_id, "REJECTED", "invalid_verification")
    if _contains_raw_identifier(verification):
        return _decision(candidate_id, "REJECTED", "raw_identifier_forbidden")
    if verification.get("candidate_id") != candidate_id:
        return _decision(candidate_id, "REJECTED", "verification_candidate_mismatch")
    if verification.get("provider") != SINAI_PROVIDER or not _sinai_url(verification.get("source_url")):
        return _decision(candidate_id, "REJECTED", "official_source_required")
    if verification.get("authorization_basis") not in ALLOWED_AUTHORIZATION_BASES:
        return _decision(candidate_id, "REJECTED", "authorization_basis_required")
    if verification.get("result_complete") is not True:
        return _decision(candidate_id, "REJECTED", "incomplete_official_result")

    subject_ref_hash = str(verification.get("subject_ref_hash") or "").strip().lower()
    if not _SHA256_RE.fullmatch(subject_ref_hash):
        return _decision(candidate_id, "REJECTED", "subject_reference_hash_required")

    checked_at = _parse_datetime(verification.get("checked_at"))
    if checked_at is None:
        return _decision(candidate_id, "REJECTED", "invalid_checked_at")
    age_seconds = (now_utc - checked_at).total_seconds()
    if age_seconds < -300:
        return _decision(candidate_id, "REJECTED", "verification_from_future")
    if age_seconds > MAX_VERIFICATION_AGE_DAYS * 86400:
        return _decision(candidate_id, "REJECTED", "verification_expired")

    try:
        debt = summarize_active_debt(verification.get("infractions"))
    except ValueError as exc:
        return _decision(candidate_id, "REJECTED", str(exc))
    if debt["unknown_statuses"]:
        return _decision(
            candidate_id,
            "REJECTED",
            "ambiguous_infraction_status",
            unknown_statuses=debt["unknown_statuses"],
        )

    evidence_hash = _evidence_hash(candidate_id, verification, debt)
    common = {
        "contacts": contacts,
        "entity_fingerprint": entity_fingerprint,
        "verification": {
            "provider": SINAI_PROVIDER,
            "checked_at": checked_at.isoformat(),
            "active_infractions_count": debt["active_count"],
            "active_debt_total_ars": debt["active_total_ars"],
            "duplicate_infractions_ignored": debt["duplicate_count"],
            "inactive_infractions_ignored": debt["inactive_count"],
            "threshold_ars": DEBT_THRESHOLD_ARS,
            "evidence_hash": evidence_hash,
        },
    }
    if debt["active_total_ars"] < DEBT_THRESHOLD_ARS:
        return _decision(candidate_id, "REJECTED", "debt_below_threshold", **common)
    return _decision(candidate_id, "ELIGIBLE_VERIFIED", "all_gates_passed", **common)


def run_batch(
    candidates: list[dict[str, Any]],
    verifications: list[dict[str, Any]] | None = None,
    *,
    now: datetime | None = None,
) -> dict[str, Any]:
    if not isinstance(candidates, list):
        raise ValueError("candidates_must_be_list")
    if verifications is not None and not isinstance(verifications, list):
        raise ValueError("verifications_must_be_list")

    verification_by_candidate: dict[str, dict[str, Any]] = {}
    duplicate_verifications: set[str] = set()
    for verification in verifications or []:
        candidate_id = str(verification.get("candidate_id") or "") if isinstance(verification, dict) else ""
        if candidate_id in verification_by_candidate:
            duplicate_verifications.add(candidate_id)
        elif candidate_id:
            verification_by_candidate[candidate_id] = verification

    decisions: list[dict[str, Any]] = []
    seen_candidate_ids: set[str] = set()
    seen_entities: set[str] = set()
    for candidate in candidates:
        if not isinstance(candidate, dict):
            decisions.append(_decision("invalid", "REJECTED", "invalid_candidate"))
            continue
        candidate_id = str(candidate.get("id") or candidate.get("candidate_id") or "").strip()
        if candidate_id in seen_candidate_ids:
            decisions.append(_decision(candidate_id or "invalid", "REJECTED", "duplicate_candidate_id"))
            continue
        seen_candidate_ids.add(candidate_id)
        if candidate_id in duplicate_verifications:
            decisions.append(_decision(candidate_id, "REJECTED", "duplicate_verification"))
            continue

        decision = evaluate_candidate(candidate, verification_by_candidate.get(candidate_id), now=now)
        fingerprint = decision.get("entity_fingerprint")
        if fingerprint and fingerprint in seen_entities:
            decision = _decision(candidate_id, "REJECTED", "duplicate_entity")
        elif fingerprint:
            seen_entities.add(fingerprint)
        decisions.append(decision)

    counts: dict[str, int] = {}
    for decision in decisions:
        counts[decision["status"]] = counts.get(decision["status"], 0) + 1
    return {
        "mode": "artifact_only",
        "network_access": False,
        "production_access": False,
        "target_vertical": TARGET_VERTICAL,
        "threshold_ars": DEBT_THRESHOLD_ARS,
        "counts": counts,
        "decisions": decisions,
    }
