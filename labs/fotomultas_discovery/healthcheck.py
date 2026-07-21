"""Container health probe for matching, recent private cycle outputs."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def _read_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("output_must_be_object")
    return payload


def _parse_cycle_id(value: Any) -> datetime:
    text = str(value or "")
    try:
        parsed = datetime.strptime(text, "%Y%m%dT%H%M%S.%fZ")
    except ValueError as exc:
        raise ValueError("invalid_cycle_id") from exc
    return parsed.replace(tzinfo=timezone.utc)


def check_outputs(
    candidates_path: Path,
    decisions_path: Path,
    *,
    max_age_minutes: int,
    now: datetime | None = None,
) -> dict[str, Any]:
    if max_age_minutes < 5:
        raise ValueError("max_age_minutes_too_small")
    if not candidates_path.is_file() or not decisions_path.is_file():
        raise ValueError("cycle_outputs_missing")

    candidates = _read_json(candidates_path)
    decisions = _read_json(decisions_path)
    candidate_cycle = str(candidates.get("cycle_id") or "")
    decision_cycle = str(decisions.get("cycle_id") or "")
    if not candidate_cycle or candidate_cycle != decision_cycle:
        raise ValueError("cycle_id_mismatch")
    if candidates.get("target_vertical") != "fotomultas":
        raise ValueError("candidate_vertical_mismatch")
    if decisions.get("target_vertical") != "fotomultas":
        raise ValueError("decision_vertical_mismatch")
    if decisions.get("production_access") is not False:
        raise ValueError("production_access_not_false")

    checked_at = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    cycle_at = _parse_cycle_id(candidate_cycle)
    age_seconds = (checked_at - cycle_at).total_seconds()
    if age_seconds < -300:
        raise ValueError("cycle_from_future")
    if age_seconds > max_age_minutes * 60:
        raise ValueError("cycle_stale")

    return {
        "status": "PASS",
        "cycle_id": candidate_cycle,
        "age_seconds": int(max(age_seconds, 0)),
        "candidate_count": int(candidates.get("candidate_count") or len(candidates.get("candidates") or [])),
        "counts": decisions.get("counts") or {},
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--candidates", required=True, type=Path)
    parser.add_argument("--decisions", required=True, type=Path)
    parser.add_argument("--max-age-minutes", type=int, default=240)
    args = parser.parse_args(argv)

    try:
        result = check_outputs(
            args.candidates,
            args.decisions,
            max_age_minutes=args.max_age_minutes,
        )
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(json.dumps({"status": "BLOCKED", "reason": str(exc)}, sort_keys=True), file=sys.stderr)
        return 1
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
