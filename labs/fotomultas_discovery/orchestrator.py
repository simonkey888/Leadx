"""Single-command autonomous cycle for public discovery and private decisions."""

from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from .cli import load_verifications
from .discovery import run_discovery
from .pipeline import run_batch


def _atomic_write(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    temporary.replace(path)


def run_cycle(
    repo_root: Path,
    candidates_output: Path,
    decisions_output: Path,
    verifications_path: Path | None,
    *,
    timeout_seconds: int = 260,
    discovery_function: Callable[..., dict[str, Any]] = run_discovery,
) -> dict[str, Any]:
    """Run one fail-closed cycle.

    Discovery and evaluation complete before publication. Each output is replaced
    atomically and both carry the same cycle_id, so consumers can reject a
    mismatched pair after an interrupted filesystem operation.
    """

    lock_path = decisions_output.with_suffix(decisions_output.suffix + ".cycle.lock")
    decisions_output.parent.mkdir(parents=True, exist_ok=True)
    try:
        lock_fd = os.open(lock_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    except FileExistsError as exc:
        raise RuntimeError("orchestrator_already_running") from exc

    try:
        os.write(lock_fd, f"pid={os.getpid()}\n".encode("ascii"))
        os.close(lock_fd)
        with tempfile.TemporaryDirectory(prefix="leadx-fotomultas-cycle-") as directory:
            staging = Path(directory)
            staged_candidates_path = staging / "candidates.json"
            discovery_result = discovery_function(
                repo_root,
                staged_candidates_path,
                timeout_seconds=timeout_seconds,
            )
            candidates = discovery_result.get("candidates")
            if not isinstance(candidates, list):
                raise ValueError("discovery_candidates_missing")

            verifications = []
            if verifications_path is not None and verifications_path.exists():
                verifications = load_verifications(verifications_path)

            decisions = run_batch(candidates, verifications)
            cycle_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S.%fZ")
            discovery_result = {
                **discovery_result,
                "cycle_id": cycle_id,
            }
            decisions.update(
                {
                    "cycle_id": cycle_id,
                    "discovery_generated_at": discovery_result.get("generated_at"),
                    "verification_file_present": bool(verifications_path and verifications_path.exists()),
                }
            )

            # Publish only after the complete cycle succeeds. Cross-file consumers
            # must require matching cycle_id values.
            _atomic_write(candidates_output, discovery_result)
            _atomic_write(decisions_output, decisions)
            return {
                "cycle_id": cycle_id,
                "candidate_count": len(candidates),
                "counts": decisions["counts"],
            }
    finally:
        try:
            lock_path.unlink()
        except FileNotFoundError:
            pass


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", type=Path, default=Path.cwd())
    parser.add_argument("--candidates-output", required=True, type=Path)
    parser.add_argument("--decisions-output", required=True, type=Path)
    parser.add_argument("--verifications", type=Path)
    parser.add_argument("--allow-public-network", action="store_true")
    parser.add_argument("--watch", action="store_true")
    parser.add_argument("--interval-minutes", type=float, default=180.0)
    parser.add_argument("--timeout-seconds", type=int, default=260)
    args = parser.parse_args(argv)

    if not args.allow_public_network:
        print("public_network_discovery_requires_explicit_flag", file=sys.stderr)
        return 2
    if args.interval_minutes < 5:
        print("interval_minutes_must_be_at_least_5", file=sys.stderr)
        return 2

    while True:
        try:
            summary = run_cycle(
                args.repo_root,
                args.candidates_output,
                args.decisions_output,
                args.verifications,
                timeout_seconds=args.timeout_seconds,
            )
            print(json.dumps({"status": "PASS", **summary}, sort_keys=True), flush=True)
        except Exception as exc:
            print(json.dumps({"status": "BLOCKED", "reason": str(exc)}, sort_keys=True), file=sys.stderr, flush=True)
            if not args.watch:
                return 1
        if not args.watch:
            return 0
        time.sleep(args.interval_minutes * 60)


if __name__ == "__main__":
    raise SystemExit(main())
