"""Deterministic, fail-closed national-infraction debt aggregation."""

from __future__ import annotations

import hashlib
import json
import math
import re
import unicodedata
from decimal import Decimal, InvalidOperation
from typing import Any

from .constants import ACTIVE_STATUSES, INACTIVE_STATUSES


def normalize_status(value: Any) -> str:
    text = unicodedata.normalize("NFKD", str(value or "").strip().lower())
    return " ".join(text.encode("ascii", "ignore").decode("ascii").split())


def parse_amount_ars(value: Any) -> int:
    """Parse Argentine currency formats into whole pesos.

    Accepted examples: 1250000, "1.250.000", "$ 1.250.000,00".
    Negative, non-finite and ambiguous values are rejected.
    """

    if isinstance(value, bool) or value is None:
        raise ValueError("invalid_amount")
    if isinstance(value, int):
        amount = Decimal(value)
    elif isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError("invalid_amount")
        amount = Decimal(str(value))
    else:
        text = re.sub(r"[^0-9,.-]", "", str(value))
        if not text or text.count("-") > 1 or ("-" in text and not text.startswith("-")):
            raise ValueError("invalid_amount")

        if "," in text and "." in text:
            if text.rfind(",") > text.rfind("."):
                text = text.replace(".", "").replace(",", ".")
            else:
                text = text.replace(",", "")
        elif "," in text:
            tail = text.rsplit(",", 1)[1]
            text = text.replace(".", "")
            text = text.replace(",", "." if len(tail) <= 2 else "")
        elif "." in text:
            groups = text.split(".")
            if len(groups) > 2 or len(groups[-1]) == 3:
                text = "".join(groups)

        try:
            amount = Decimal(text)
        except InvalidOperation as exc:
            raise ValueError("invalid_amount") from exc

    if not amount.is_finite() or amount < 0 or amount != amount.to_integral_value():
        raise ValueError("invalid_amount")
    return int(amount)


def _fingerprint(infraction: dict[str, Any], amount: int) -> str:
    explicit = str(infraction.get("id") or "").strip()
    if explicit:
        material = {"id": explicit}
    else:
        material = {
            "act_number": str(infraction.get("act_number") or infraccion_value(infraction, "acta") or "").strip(),
            "amount": amount,
            "date": str(infraction.get("date") or infraccion_value(infraction, "fecha") or "").strip(),
            "jurisdiction": str(infraction.get("jurisdiction") or infraccion_value(infraction, "jurisdiccion") or "").strip().lower(),
        }
    encoded = json.dumps(material, ensure_ascii=True, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def infraccion_value(infraction: dict[str, Any], key: str) -> Any:
    return infraction.get(key)


def summarize_active_debt(infractions: Any) -> dict[str, Any]:
    if not isinstance(infractions, list):
        raise ValueError("invalid_infractions")

    total = 0
    active_count = 0
    inactive_count = 0
    duplicate_count = 0
    unknown_statuses: set[str] = set()
    fingerprints: list[str] = []
    seen: set[str] = set()

    for item in infractions:
        if not isinstance(item, dict):
            raise ValueError("invalid_infraction")
        status = normalize_status(item.get("status") or item.get("estado"))
        if status in INACTIVE_STATUSES:
            inactive_count += 1
            continue
        if status not in ACTIVE_STATUSES:
            unknown_statuses.add(status or "missing")
            continue

        amount = parse_amount_ars(item.get("amount_ars", item.get("importe")))
        fingerprint = _fingerprint(item, amount)
        if fingerprint in seen:
            duplicate_count += 1
            continue
        seen.add(fingerprint)
        fingerprints.append(fingerprint)
        total += amount
        active_count += 1

    return {
        "active_count": active_count,
        "active_total_ars": total,
        "duplicate_count": duplicate_count,
        "inactive_count": inactive_count,
        "unknown_statuses": sorted(unknown_statuses),
        "infraction_fingerprints": sorted(fingerprints),
    }
