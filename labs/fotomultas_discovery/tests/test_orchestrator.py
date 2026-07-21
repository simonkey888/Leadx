from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from labs.fotomultas_discovery.orchestrator import run_cycle


def fake_discovery(_repo_root: Path, output: Path, *, timeout_seconds: int = 260):
    assert timeout_seconds == 260
    payload = {
        "mode": "public_discovery_only",
        "target_vertical": "fotomultas",
        "production_access": False,
        "generated_at": "2026-07-21T11:00:00+00:00",
        "candidates": [
            {
                "id": "synthetic:cycle:1",
                "vertical": "fotomultas",
                "entity_name": "Ciclo Sintetico SA",
                "source_url": "https://example.org/cycle/1",
                "contact_public": True,
                "email_publico": "cycle@example.org",
            }
        ],
    }
    output.write_text(json.dumps(payload), encoding="utf-8")
    return payload


class OrchestratorTests(unittest.TestCase):
    def test_cycle_publishes_matching_candidate_and_decision_versions(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            verifications = root / "verifications.json"
            verifications.write_text(
                json.dumps(
                    {
                        "verifications": [
                            {
                                "candidate_id": "synthetic:cycle:1",
                                "provider": "sinai_official",
                                "source_url": "https://consultainfracciones.seguridadvial.gob.ar/",
                                "authorization_basis": "synthetic_test",
                                "subject_ref_hash": "c" * 64,
                                "checked_at": "2026-07-21T11:00:00+00:00",
                                "result_complete": True,
                                "infractions": [
                                    {"id": "a", "status": "Vigente", "amount_ars": 600000},
                                    {"id": "b", "status": "Pendiente", "amount_ars": 400000},
                                ],
                            }
                        ]
                    }
                ),
                encoding="utf-8",
            )
            candidates_output = root / "private" / "candidates.json"
            decisions_output = root / "private" / "decisions.json"
            summary = run_cycle(
                root,
                candidates_output,
                decisions_output,
                verifications,
                discovery_function=fake_discovery,
            )
            self.assertEqual(summary["candidate_count"], 1)
            self.assertEqual(summary["counts"]["ELIGIBLE_VERIFIED"], 1)
            candidates = json.loads(candidates_output.read_text(encoding="utf-8"))
            decisions = json.loads(decisions_output.read_text(encoding="utf-8"))
            self.assertEqual(decisions["counts"]["ELIGIBLE_VERIFIED"], 1)
            self.assertTrue(decisions["verification_file_present"])
            self.assertEqual(candidates["cycle_id"], decisions["cycle_id"])
            self.assertEqual(summary["cycle_id"], decisions["cycle_id"])

    def test_missing_verification_produces_pending_queue(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            decisions_output = root / "decisions.json"
            summary = run_cycle(
                root,
                root / "candidates.json",
                decisions_output,
                root / "missing-verifications.json",
                discovery_function=fake_discovery,
            )
            self.assertEqual(summary["counts"]["PENDING_VERIFICATION"], 1)
            decisions = json.loads(decisions_output.read_text(encoding="utf-8"))
            self.assertFalse(decisions["verification_file_present"])

    def test_failed_cycle_preserves_previous_outputs(self):
        def failing_discovery(*_args, **_kwargs):
            raise RuntimeError("synthetic_discovery_failure")

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            candidates_output = root / "candidates.json"
            decisions_output = root / "decisions.json"
            candidates_output.write_text("old-candidates", encoding="utf-8")
            decisions_output.write_text("old-decisions", encoding="utf-8")
            with self.assertRaisesRegex(RuntimeError, "synthetic_discovery_failure"):
                run_cycle(
                    root,
                    candidates_output,
                    decisions_output,
                    None,
                    discovery_function=failing_discovery,
                )
            self.assertEqual(candidates_output.read_text(encoding="utf-8"), "old-candidates")
            self.assertEqual(decisions_output.read_text(encoding="utf-8"), "old-decisions")
            self.assertFalse(decisions_output.with_suffix(".json.cycle.lock").exists())


if __name__ == "__main__":
    unittest.main()
