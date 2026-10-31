"""Check that follow-up series analysis preserves both studies and bad runs."""

import json
from pathlib import Path
import shutil
import sys
import tempfile
import unittest
from unittest.mock import patch


PROJECT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT / "scripts"))
import summarize_followup_series as series  # noqa: E402

PILOT = PROJECT / "results" / "2026-10-30-windows-followup-pilots"
REPLICATION = PROJECT / "results" / "2026-10-30-31-windows-followup-replication"
HOST = "host-windows-20261030T163650Z.json"
DECISION = "decision-source-windows-20261030T163709Z"
HISTORY = "history-probe-windows-20261030T163724Z"


def copied_pilots(root):
    day = root / "session-1"
    day.mkdir()
    for name in (HOST, DECISION + ".log", DECISION + ".exe",
                 HISTORY + ".log", HISTORY + ".exe"):
        shutil.copyfile(PILOT / name, day / name)
    manifest = {"schema": 1, "sessions": [{
        "id": "session-1", "host": f"session-1/{HOST}",
        "runs": [
            {"study": "decision_source", "trace": f"session-1/{DECISION}.log",
             "exe": f"session-1/{DECISION}.exe"},
            {"study": "history_probe", "trace": f"session-1/{HISTORY}.log",
             "exe": f"session-1/{HISTORY}.exe"},
        ],
    }]}
    path = root / "manifest.json"
    path.write_text(json.dumps(manifest), encoding="utf-8")
    return path, manifest


class FollowupSeriesTests(unittest.TestCase):
    def test_archived_two_day_series_accounts_for_every_supplied_run(self):
        result = series.summarize_series(REPLICATION / "manifest.json")
        self.assertEqual([s["utc_date"] for s in result["sessions"]],
                         ["2026-10-30", "2026-10-31"])
        self.assertTrue(result["sessions_on_distinct_utc_dates"])
        for session in result["sessions"]:
            self.assertEqual(len(session["runs"]), 6)
            for study in ("decision_source", "history_probe"):
                self.assertEqual(session["descriptive"][study]["run_count"], 3)
                self.assertEqual(session["descriptive"][study]
                                 ["predeclared_control_gate_passed_runs"], 3)
        self.assertEqual(len({run["seed"] for session in result["sessions"]
                              for run in session["runs"]}), 12)
        self.assertEqual(result["text_sha256_by_study"], {
            "decision_source":
                "0f302df7d38b2c1e1eb840104cd4c51da4d0d802a8e540ee74fd8d20a11ec1e9",
            "history_probe":
                "b7ee4707628ac45f621ffd281066efd0cff3652717324fe3baa7c592c8289e3b",
        })

    def test_both_real_pilot_traces_are_replayed_in_separate_units(self):
        with tempfile.TemporaryDirectory() as temporary:
            result = series.summarize_series(copied_pilots(Path(temporary))[0])
        runs = result["sessions"][0]["runs"]
        self.assertEqual([run["study"] for run in runs],
                         ["decision_source", "history_probe"])
        self.assertEqual([run["control_gate_passes"] for run in runs],
                         [True, True])
        self.assertEqual(result["all_runs_descriptive"]["history_probe"]
                         ["control_gate"], "timer only")
        self.assertAlmostEqual(
            result["all_runs_descriptive"]["decision_source"]
            ["mean_of_run_estimates"]["primary_interaction"], 17.08257740941541)
        self.assertAlmostEqual(
            result["all_runs_descriptive"]["history_probe"]
            ["mean_of_run_estimates"]["adjusted0"], 0.919403076171875)
        self.assertEqual(result["sessions_on_distinct_utc_dates"], True)
        self.assertNotIn("across_day_confidence_interval", result)

    def test_mismatched_executable_is_rejected(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            path, _ = copied_pilots(root)
            exe = root / "session-1" / (HISTORY + ".exe")
            data = bytearray(exe.read_bytes())
            data[-1] ^= 1
            exe.write_bytes(data)
            with self.assertRaisesRegex(ValueError, "EXE SHA-256 differs"):
                series.summarize_series(path)

    def test_omitted_run_file_and_stale_host_are_rejected(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            path, manifest = copied_pilots(root)
            manifest["sessions"][0]["runs"].pop()
            path.write_text(json.dumps(manifest), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "unlisted or missing"):
                series.summarize_series(path)

            manifest["sessions"][0]["runs"][0]["trace"] = "../outside.log"
            path.write_text(json.dumps(manifest), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "must stay under"):
                series.summarize_series(path)

            manifest["sessions"][0]["runs"][0]["trace"] = \
                f"session-1/{DECISION}.log"
            manifest["sessions"][0]["runs"].append({
                "study": "history_probe", "trace": f"session-1/{HISTORY}.log",
                "exe": f"session-1/{HISTORY}.exe",
            })
            path.write_text(json.dumps(manifest), encoding="utf-8")
            host_path = root / "session-1" / HOST
            host = json.loads(host_path.read_text(encoding="utf-8-sig"))
            host["captured_utc"] = "20261029T163650Z"
            host_path.write_text(json.dumps(host), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "precede each run by at most"):
                series.summarize_series(path)

    def test_failed_control_run_remains_in_output(self):
        with tempfile.TemporaryDirectory() as temporary:
            path, _ = copied_pilots(Path(temporary))
            original = series.summarize_decision

            def failed_control(trace):
                analysis = original(trace)
                analysis["controls_pass"] = False
                return analysis

            prefix, parser, _, other_site = series.STUDIES["decision_source"]
            with patch.dict(series.STUDIES, {
                "decision_source": (prefix, parser, failed_control, other_site)
            }):
                result = series.summarize_series(path)
        counts = result["sessions"][0]["descriptive"]["decision_source"]
        self.assertEqual(counts["run_count"], 1)
        self.assertEqual(counts["predeclared_control_gate_failed_runs"], 1)
        self.assertFalse(result["sessions"][0]["runs"][0]
                         ["control_gate_passes"])


if __name__ == "__main__":
    unittest.main()
