"""Artifact-only command line entrypoint for the Fotomultas laboratory."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from .pipeline import run_batch


def _load_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def _candidate_from_legacy(lead: dict[str, Any]) -> dict[str, Any]:
    """Map the existing radar payload into the strict laboratory contract."""

    return {
        "id": lead.get("id"),
        "vertical": lead.get("vertical"),
        "entity_name": lead.get("persona") or lead.get("name") or lead.get("problem_summary"),
        "source_url": lead.get("source_url"),
        "source_type": lead.get("platform"),
        "contact_public": lead.get("contacto_publico") is True,
        "email_publico": lead.get("email_publico"),
        "telefono_publico": lead.get("telefono_publico") or lead.get("telefono_e164"),
        "whatsapp_publico": lead.get("whatsapp_publico"),
    }


def load_candidates(path: Path) -> list[dict[str, Any]]:
    payload = _load_json(path)
    if isinstance(payload, list):
        candidates = payload
    elif isinstance(payload, dict) and isinstance(payload.get("candidates"), list):
        candidates = payload["candidates"]
    elif isinstance(payload, dict) and isinstance(payload.get("leads_all"), list):
        candidates = [_candidate_from_legacy(item) for item in payload["leads_all"] if isinstance(item, dict)]
    else:
        raise ValueError("unsupported_candidate_payload")
    return candidates


def load_verifications(path: Path | None) -> list[dict[str, Any]]:
    if path is None:
        return []
    payload = _load_json(path)
    if isinstance(payload, list):
        return payload
    if isinstance(payload, dict) and isinstance(payload.get("verifications"), list):
        return payload["verifications"]
    raise ValueError("unsupported_verification_payload")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--candidates", required=True, type=Path)
    parser.add_argument("--verifications", type=Path)
    parser.add_argument("--output", type=Path, help="Omit to emit JSON on stdout.")
    args = parser.parse_args(argv)

    try:
        result = run_batch(load_candidates(args.candidates), load_verifications(args.verifications))
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(json.dumps({"status": "BLOCKED", "reason": str(exc)}, sort_keys=True), file=sys.stderr)
        return 2

    rendered = json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        temporary = args.output.with_suffix(args.output.suffix + ".tmp")
        temporary.write_text(rendered, encoding="utf-8")
        temporary.replace(args.output)
    else:
        sys.stdout.write(rendered)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
