"""A repeated numerical signature is not a pooled test or mechanism approval."""
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/"scripts"))
from audit_context_receiver_series import (PILOT_SEED, SESSION_SEEDS, SOURCE_REVISION,
                                           independent_primary, summarize_series)
from test_analyze_context_receiver import fixture


def record(seed):
    return {"seed": seed, "archive_sha256": f"archive-{seed}", "trace_sha256": f"trace-{seed}",
            "git_head": SOURCE_REVISION, "git_clean_reported": True, "source_sha256": {},
            "toolchain": {}, "linked_text_raw_sha256": "code", "reported_host_inventory": {},
            "analysis": {"numerical_signature_detected": True, "sample_count": 262144,
                         "outcomes": {"p0": {"interaction": {"hit_rate_difference": .99}}}}}


class ContextSeriesAuditTests(unittest.TestCase):
    def test_three_signatures_never_approve_mechanism_or_pool_episodes(self):
        result = summarize_series(record(PILOT_SEED), [record(s) for s in SESSION_SEEDS])
        self.assertTrue(result["three_planned_session_signatures_repeated"])
        self.assertFalse(result["physical_mechanism_proven"])
        self.assertFalse(result["privilege_boundary_tested"])
        self.assertIsNone(result["pooled_confidence_interval"])
        self.assertEqual(result["followup_recorded_samples"], 786432)

    def test_null_is_retained_and_prevents_all_session_signature_claim(self):
        sessions = [record(s) for s in SESSION_SEEDS]
        sessions[1]["analysis"]["numerical_signature_detected"] = False
        result = summarize_series(record(PILOT_SEED), sessions)
        self.assertFalse(result["three_planned_session_signatures_repeated"])
        self.assertEqual(len(result["planned_sessions"]), 3)

    def test_wrong_seeds_and_duplicate_traces_cannot_be_replications(self):
        pilot = record(PILOT_SEED)
        sessions = [record(s) for s in SESSION_SEEDS]
        with self.assertRaisesRegex(ValueError, "seeds"):
            summarize_series(pilot, [sessions[0]]*3)
        sessions[1]["trace_sha256"] = sessions[0]["trace_sha256"]
        with self.assertRaisesRegex(ValueError, "duplicate"):
            summarize_series(pilot, sessions)

    def test_changed_code_is_retained_without_comparable_replication_claim(self):
        sessions = [record(s) for s in SESSION_SEEDS]
        sessions[2]["linked_text_raw_sha256"] = "changed code"
        result = summarize_series(record(PILOT_SEED), sessions)
        self.assertFalse(result["comparable_recorded_conditions"])
        self.assertFalse(result["three_planned_session_signatures_repeated"])
        self.assertEqual(len(result["planned_sessions"]), 3)

    def test_independent_raw_csv_calculation_distinguishes_training_from_entry_heat(self):
        for pattern, expected in (("signature", 1), ("entry_heat", 0)):
            result = independent_primary(fixture(pattern), {"p0": 100}, 32)
            self.assertEqual(result["hit_rate_difference"], expected)
            self.assertEqual(result["ci95"], [expected, expected])


if __name__ == "__main__":
    unittest.main()
