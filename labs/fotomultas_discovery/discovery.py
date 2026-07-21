"""Opt-in public-web discovery runner isolated from LeadX production."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

_SAFELY_INHERITED_ENV = {
    "HOME",
    "LANG",
    "LC_ALL",
    "PATH",
    "PYTHONPATH",
    "SSL_CERT_DIR",
    "SSL_CERT_FILE",
    "TMPDIR",
}


def build_sanitized_environment(source: dict[str, str] | None = None) -> dict[str, str]:
    """Build an environment that cannot authenticate to LeadX or Cloudflare."""

    source_env = source or dict(os.environ)
    env = {key: value for key, value in source_env.items() if key in _SAFELY_INHERITED_ENV}
    env.update(
        {
            "INGEST_SECRET": "",
            "WORKER_URL": "",
            "CLOUDFLARE_API_TOKEN": "",
            "CLOUDFLARE_ACCOUNT_ID": "",
            "DASHBOARD_PASSWORD": "",
            "SESSION_SECRET": "",
            "LEADX_DISCOVERY_LAB": "1",
            "PYTHONUNBUFFERED": "1",
        }
    )
    return env


def _legacy_candidate(lead: dict[str, Any]) -> dict[str, Any]:
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
        "discovered_at": lead.get("discovery_timestamp") or lead.get("fecha_iso"),
    }


def sanitize_legacy_payload(payload: Any) -> dict[str, Any]:
    """Remove raw text, plates and unrelated verticals from the radar output."""

    if not isinstance(payload, dict) or not isinstance(payload.get("leads_all"), list):
        raise ValueError("invalid_legacy_payload")
    candidates: list[dict[str, Any]] = []
    seen: set[str] = set()
    for lead in payload["leads_all"]:
        if not isinstance(lead, dict) or lead.get("vertical") != "fotomultas":
            continue
        candidate = _legacy_candidate(lead)
        candidate_id = str(candidate.get("id") or "").strip()
        if not candidate_id or candidate_id in seen:
            continue
        seen.add(candidate_id)
        candidates.append(candidate)
    return {
        "mode": "public_discovery_only",
        "source": "existing_generate_payload_radar",
        "target_vertical": "fotomultas",
        "production_access": False,
        "cloudflare_access": False,
        "kv_access": False,
        "ingest_enabled": False,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "candidate_count": len(candidates),
        "candidates": candidates,
    }


def _atomic_write(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    temporary.replace(path)


def run_discovery(repo_root: Path, output: Path, *, timeout_seconds: int = 260) -> dict[str, Any]:
    script = repo_root.resolve() / "generate_payload.py"
    if not script.is_file():
        raise FileNotFoundError("generate_payload.py_not_found")
    if timeout_seconds < 30 or timeout_seconds > 900:
        raise ValueError("invalid_timeout_seconds")

    lock_path = output.with_suffix(output.suffix + ".lock")
    output.parent.mkdir(parents=True, exist_ok=True)
    try:
        lock_fd = os.open(lock_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    except FileExistsError as exc:
        raise RuntimeError("discovery_already_running") from exc

    try:
        os.write(lock_fd, f"pid={os.getpid()}\n".encode("ascii"))
        os.close(lock_fd)
        with tempfile.TemporaryDirectory(prefix="leadx-fotomultas-discovery-") as directory:
            sandbox = Path(directory)
            completed = subprocess.run(
                [sys.executable, str(script)],
                cwd=sandbox,
                env=build_sanitized_environment(),
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=timeout_seconds,
                check=False,
            )
            if completed.returncode != 0:
                raise RuntimeError(f"legacy_radar_failed_exit_{completed.returncode}")
            payload_path = sandbox / "data" / "dashboard_payload.json"
            if not payload_path.is_file():
                raise RuntimeError("legacy_radar_payload_missing")
            payload = json.loads(payload_path.read_text(encoding="utf-8"))
            sanitized = sanitize_legacy_payload(payload)
            _atomic_write(output, sanitized)
            return sanitized
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError("legacy_radar_timeout") from exc
    finally:
        try:
            lock_path.unlink()
        except FileNotFoundError:
            pass


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", type=Path, default=Path.cwd())
    parser.add_argument("--output", required=True, type=Path)
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
            result = run_discovery(args.repo_root, args.output, timeout_seconds=args.timeout_seconds)
            print(json.dumps({"status": "PASS", "candidate_count": result["candidate_count"]}, sort_keys=True), flush=True)
        except Exception as exc:
            print(json.dumps({"status": "BLOCKED", "reason": str(exc)}, sort_keys=True), file=sys.stderr, flush=True)
            if not args.watch:
                return 1
        if not args.watch:
            return 0
        time.sleep(args.interval_minutes * 60)


if __name__ == "__main__":
    raise SystemExit(main())
