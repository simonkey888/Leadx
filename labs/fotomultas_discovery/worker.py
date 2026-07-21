"""Unattended file-queue worker with no network or production side effects."""

from __future__ import annotations

import argparse
import json
import shutil
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .pipeline import run_batch


def _atomic_json_write(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    temporary.replace(path)


def process_job(job_path: Path, outbox: Path, processed: Path, dead_letter: Path) -> str:
    processing_path = job_path.with_suffix(job_path.suffix + ".processing")
    job_path.replace(processing_path)
    try:
        payload = json.loads(processing_path.read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            raise ValueError("job_must_be_object")
        candidates = payload.get("candidates")
        verifications = payload.get("verifications", [])
        result = run_batch(candidates, verifications)
        result["job_id"] = str(payload.get("job_id") or processing_path.stem)
        result["processed_at"] = datetime.now(timezone.utc).isoformat()
        _atomic_json_write(outbox / f"{result['job_id']}.result.json", result)
        processed.mkdir(parents=True, exist_ok=True)
        shutil.move(str(processing_path), str(processed / processing_path.name.removesuffix(".processing")))
        return "processed"
    except Exception as exc:  # fail closed: malformed jobs never re-enter the queue automatically
        error = {
            "status": "DEAD_LETTER",
            "reason": type(exc).__name__,
            "detail": str(exc),
            "source_file": processing_path.name,
            "failed_at": datetime.now(timezone.utc).isoformat(),
        }
        dead_letter.mkdir(parents=True, exist_ok=True)
        _atomic_json_write(dead_letter / f"{processing_path.stem}.error.json", error)
        shutil.move(str(processing_path), str(dead_letter / processing_path.name.removesuffix(".processing")))
        return "dead_letter"


def run_once(inbox: Path, outbox: Path, processed: Path, dead_letter: Path) -> dict[str, int]:
    inbox.mkdir(parents=True, exist_ok=True)
    counts = {"processed": 0, "dead_letter": 0}
    for job_path in sorted(inbox.glob("*.json")):
        outcome = process_job(job_path, outbox, processed, dead_letter)
        counts[outcome] += 1
    return counts


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--inbox", required=True, type=Path)
    parser.add_argument("--outbox", required=True, type=Path)
    parser.add_argument("--processed", required=True, type=Path)
    parser.add_argument("--dead-letter", required=True, type=Path)
    parser.add_argument("--watch", action="store_true")
    parser.add_argument("--interval-seconds", type=float, default=30.0)
    args = parser.parse_args(argv)

    if args.interval_seconds < 1:
        print("interval_seconds_must_be_at_least_1", file=sys.stderr)
        return 2

    while True:
        counts = run_once(args.inbox, args.outbox, args.processed, args.dead_letter)
        print(json.dumps({"worker": "fotomultas_discovery", **counts}, sort_keys=True), flush=True)
        if not args.watch:
            return 0
        time.sleep(args.interval_seconds)


if __name__ == "__main__":
    raise SystemExit(main())
