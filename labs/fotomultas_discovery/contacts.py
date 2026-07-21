"""Public-contact normalization with conservative Argentina defaults."""

from __future__ import annotations

import re
from collections.abc import Iterable
from typing import Any

_EMAIL_RE = re.compile(r"^[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,63}$", re.IGNORECASE)


def _values(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [value]
    if isinstance(value, Iterable) and not isinstance(value, (bytes, bytearray, dict)):
        return [str(item) for item in value if item is not None]
    return [str(value)]


def normalize_email(value: str) -> str:
    email = str(value or "").strip().lower()
    if len(email) > 254 or not _EMAIL_RE.fullmatch(email):
        return ""
    local, domain = email.rsplit("@", 1)
    if local.startswith(".") or local.endswith(".") or ".." in local or ".." in domain:
        return ""
    return email


def normalize_argentina_phone(value: str, *, mobile_hint: bool = False) -> str:
    """Return conservative E.164 output or an empty string.

    The function does not guess short/local numbers. It accepts an Argentine
    national number only when ten digits remain after removing international,
    trunk and mobile prefixes.
    """

    digits = re.sub(r"\D", "", str(value or ""))
    if digits.startswith("00"):
        digits = digits[2:]
    if digits.startswith("54"):
        digits = digits[2:]
    if digits.startswith("9") and len(digits) == 11:
        mobile_hint = True
        digits = digits[1:]
    if digits.startswith("0") and len(digits) == 11:
        digits = digits[1:]

    # Remove the legacy domestic mobile marker in common 2/3/4 digit area-code forms.
    for position in (2, 3, 4):
        if len(digits) == 12 and digits[position : position + 2] == "15":
            digits = digits[:position] + digits[position + 2 :]
            mobile_hint = True
            break

    if len(digits) != 10 or digits.startswith("0") or digits[0] not in "123456789":
        return ""
    return f"+549{digits}" if mobile_hint else f"+54{digits}"


def extract_public_contacts(candidate: dict[str, Any]) -> dict[str, list[str]]:
    """Extract only explicitly public contact fields.

    Arbitrary page text is intentionally not regex-mined here. The discovery
    adapter must provide explicit fields plus contact_public=true and provenance.
    """

    if candidate.get("contact_public") is not True:
        return {"emails": [], "phones": [], "whatsapp": []}

    emails: set[str] = set()
    phones: set[str] = set()
    whatsapp: set[str] = set()

    for key in ("email", "email_publico", "emails"):
        for raw in _values(candidate.get(key)):
            normalized = normalize_email(raw)
            if normalized:
                emails.add(normalized)

    for key in ("phone", "telefono_publico", "telefono_e164", "phones"):
        for raw in _values(candidate.get(key)):
            normalized = normalize_argentina_phone(raw)
            if normalized:
                phones.add(normalized)

    for key in ("whatsapp_publico", "whatsapp", "whatsapp_numbers"):
        for raw in _values(candidate.get(key)):
            normalized = normalize_argentina_phone(raw, mobile_hint=True)
            if normalized:
                whatsapp.add(normalized)

    return {
        "emails": sorted(emails),
        "phones": sorted(phones),
        "whatsapp": sorted(whatsapp),
    }


def has_contact(contacts: dict[str, list[str]]) -> bool:
    return any(contacts.get(key) for key in ("emails", "phones", "whatsapp"))
