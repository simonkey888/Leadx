from __future__ import annotations

import json
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from labs.fotomultas_discovery.healthcheck import check_outputs


def cycle_id(value: datetime) -> str:
    return value.astimezone(timezone.utc).strftime("%Y%m%dT%H%M%S.%fZ")


class HealthcheckTests(unittest.TestCase):
    def test_matching_recent_outputs_are_healthy(self):
        now = datetime(2026, 7, 21, 15, 0, tzinfo=timezone.utc)
        current_cycle = cycle_id(now - timedelta(minutes=5))
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            candidates = root / "candidates.json"
            decisions = root / "decisions.json"
            candidates.write_text(
                json.dumps(
                    {
                        "cycle_id": current_cycle,
                        "target_vertical": "fotomultas",
                        "candidate_count": 2,
                        "candidates": [],
                    }
                ),
                encoding="utf-8",
            )
            decisions.write_text(
                json.dumps(
                    {
                        "cycle_id": current_cycle,
                        "target_vertical": "fotomultas",
                        "production_access": False,
                        "counts": {"PENDING_VERIFICATION": 2},
                    }
                ),
                encoding="utf-8",
            )
            result = check_outputs(candidates, decisions, max_age_minutes=240, now=now)
            self.assertEqual(result["status"], "PASS")
            self.assertEqual(result["candidate_count"], 2)

    def test_mismatched_cycle_is_unhealthy(self):
        now = datetime(2026, 7, 21, 15, 0, tzinfo=timezone.utc)
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            candidates = root / "candidates.json"
            decisions = root / "decisions.json"
            candidates.write_text(
                json.dumps({"cycle_id": cycle_id(now), "target_vertical": "fotomultas"}),
                encoding="utf-8",
            )
            decisions.write_text(
                json.dumps(
                    {
                        "cycle_id": cycle_id(now - timedelta(minutes=1)),
                        "target_vertical": "fotomultas",
                        "production_access": False,
                    }
                ),
                encoding="utf-8",
            )
            with self.assertRaisesRegex(ValueError, "cycle_id_mismatch"):
                check_outputs(candidates, decisions, max_age_minutes=240, now=now)

    def test_stale_cycle_is_unhealthy(self):
        now = datetime(2026, 7, 21, 15, 0, tzinfo=timezone.utc)
        stale_cycle = cycle_id(now - timedelta(minutes=241))
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            candidates = root / "candidates.json"
            decisions = root / "decisions.json"
            candidates.write_text(
                json.dumps({"cycle_id": stale_cycle, "target_vertical": "fotomultas"}),
                encoding="utf-8",
            )
            decisions.write_text(
                json.dumps(
                    {
                        "cycle_id": stale_cycle,
                        "target_vertical": "fotomultas",
                        "production_access": False,
                    }
                ),
                encoding="utf-8",
            )
            with self.assertRaisesRegex(ValueError, "cycle_stale"):
                check_outputs(candidates, decisions, max_age_minutes=240, now=now)

    def test_production_access_must_be_explicitly_false(self):
        now = datetime(2026, 7, 21, 15, 0, tzinfo=timezone.utc)
        current_cycle = cycle_id(now)
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            candidates = root / "candidates.json"
            decisions = root / "decisions.json"
            candidates.write_text(
                json.dumps({"cycle_id": current_cycle, "target_vertical": "fotomultas"}),
                encoding="utf-8",
            )
            decisions.write_text(
                json.dumps({"cycle_id": current_cycle, "target_vertical": "fotomultas"}),
                encoding="utf-8",
            )
            with self.assertRaisesRegex(ValueError, "production_access_not_false"):
                check_outputs(candidates, decisions, max_age_minutes=240, now=now)


if __name__ == "__main__":
    unittest.main()
