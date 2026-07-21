from __future__ import annotations

import json
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from labs.fotomultas_discovery.cli import load_candidates
from labs.fotomultas_discovery.pipeline import evaluate_candidate, run_batch
from labs.fotomultas_discovery.worker import run_once

NOW = datetime(2026, 7, 21, 12, 0, tzinfo=timezone.utc)


def candidate(**overrides):
    base = {
        "id": "synthetic:lead:1",
        "vertical": "fotomultas",
        "entity_name": "Transporte Sintetico SA",
        "source_url": "https://example.org/publicacion/1",
        "contact_public": True,
        "email_publico": "ventas@example.org",
        "telefono_publico": "342 456 7890",
    }
    base.update(overrides)
    return base


def verification(**overrides):
    base = {
        "candidate_id": "synthetic:lead:1",
        "provider": "sinai_official",
        "source_url": "https://consultainfracciones.seguridadvial.gob.ar/",
        "authorization_basis": "synthetic_test",
        "subject_ref_hash": "a" * 64,
        "checked_at": "2026-07-21T11:00:00+00:00",
        "result_complete": True,
        "infractions": [
            {"id": "acta-1", "status": "Vigente", "amount_ars": "$ 350.000"},
            {"id": "acta-2", "status": "Pendiente", "amount_ars": "420.000"},
            {"id": "acta-3", "status": "Impaga", "amount_ars": "310000"},
            {"id": "acta-3", "status": "Impaga", "amount_ars": "310000"},
            {"id": "acta-4", "status": "Pagada", "amount_ars": "900000"},
        ],
    }
    base.update(overrides)
    return base


class PipelineTests(unittest.TestCase):
    def test_sum_of_multiple_active_fines_meets_threshold(self):
        decision = evaluate_candidate(candidate(), verification(), now=NOW)
        self.assertEqual(decision["status"], "ELIGIBLE_VERIFIED")
        self.assertEqual(decision["verification"]["active_debt_total_ars"], 1_080_000)
        self.assertEqual(decision["verification"]["active_infractions_count"], 3)
        self.assertEqual(decision["verification"]["duplicate_infractions_ignored"], 1)
        self.assertEqual(decision["verification"]["inactive_infractions_ignored"], 1)

    def test_single_fine_is_not_required(self):
        data = verification(
            infractions=[
                {"id": "a", "status": "vigente", "amount_ars": 500_000},
                {"id": "b", "status": "vigente", "amount_ars": 500_000},
            ]
        )
        decision = evaluate_candidate(candidate(), data, now=NOW)
        self.assertEqual(decision["status"], "ELIGIBLE_VERIFIED")
        self.assertEqual(decision["verification"]["active_debt_total_ars"], 1_000_000)

    def test_below_threshold_is_rejected(self):
        data = verification(infractions=[{"id": "a", "status": "vigente", "amount_ars": 999_999}])
        decision = evaluate_candidate(candidate(), data, now=NOW)
        self.assertEqual(decision["reason"], "debt_below_threshold")

    def test_contact_is_mandatory(self):
        decision = evaluate_candidate(
            candidate(contact_public=False, email_publico="", telefono_publico=""),
            verification(),
            now=NOW,
        )
        self.assertEqual(decision["reason"], "public_contact_required")

    def test_repuestos_vertical_is_blocked(self):
        decision = evaluate_candidate(candidate(vertical="repuestos_agricolas"), verification(), now=NOW)
        self.assertEqual(decision["reason"], "vertical_not_allowed")

    def test_raw_identifier_is_forbidden_in_verification_artifact(self):
        data = verification(dominio="AA000AA")
        decision = evaluate_candidate(candidate(), data, now=NOW)
        self.assertEqual(decision["reason"], "raw_identifier_forbidden")

    def test_unknown_infraction_status_fails_closed(self):
        data = verification(infractions=[{"id": "a", "status": "en revision", "amount_ars": 1_500_000}])
        decision = evaluate_candidate(candidate(), data, now=NOW)
        self.assertEqual(decision["reason"], "ambiguous_infraction_status")

    def test_missing_verification_stays_pending(self):
        decision = evaluate_candidate(candidate(), None, now=NOW)
        self.assertEqual(decision["status"], "PENDING_VERIFICATION")

    def test_duplicate_entity_is_rejected(self):
        first = candidate(id="synthetic:lead:1")
        second = candidate(id="synthetic:lead:2")
        second_verification = verification(candidate_id="synthetic:lead:2", subject_ref_hash="b" * 64)
        result = run_batch([first, second], [verification(), second_verification], now=NOW)
        self.assertEqual(result["counts"]["ELIGIBLE_VERIFIED"], 1)
        self.assertEqual(result["counts"]["REJECTED"], 1)
        self.assertEqual(result["decisions"][1]["reason"], "duplicate_entity")

    def test_legacy_payload_maps_without_network(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "dashboard_payload.json"
            path.write_text(
                json.dumps(
                    {
                        "leads_all": [
                            {
                                "id": "legacy:1",
                                "vertical": "fotomultas",
                                "persona": "Caso sintetico",
                                "source_url": "https://example.org/caso",
                                "contacto_publico": True,
                                "email_publico": "caso@example.org",
                            }
                        ]
                    }
                ),
                encoding="utf-8",
            )
            mapped = load_candidates(path)
            result = run_batch(mapped, [], now=NOW)
            self.assertFalse(result["network_access"])
            self.assertEqual(result["decisions"][0]["status"], "PENDING_VERIFICATION")

    def test_background_worker_processes_and_dead_letters(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            inbox = root / "inbox"
            outbox = root / "outbox"
            processed = root / "processed"
            dead = root / "dead"
            inbox.mkdir()
            (inbox / "ok.json").write_text(
                json.dumps({"job_id": "job-ok", "candidates": [candidate()], "verifications": [verification()]}),
                encoding="utf-8",
            )
            (inbox / "bad.json").write_text("not-json", encoding="utf-8")
            counts = run_once(inbox, outbox, processed, dead)
            self.assertEqual(counts, {"processed": 1, "dead_letter": 1})
            result = json.loads((outbox / "job-ok.result.json").read_text(encoding="utf-8"))
            self.assertEqual(result["counts"]["ELIGIBLE_VERIFIED"], 1)
            self.assertTrue(any(dead.glob("*.error.json")))


if __name__ == "__main__":
    unittest.main()
