"""Failure triage exercises canonical ZIP integrity and analyzer replay decisions."""

from __future__ import annotations

from hashlib import sha256
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
from zipfile import ZipFile

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import classify_suite_failures as classifier  # noqa: E402


def file_record(name: str, contents: bytes) -> dict[str, str]:
    return {"path": rf"C:\research\out\{name}",
            "sha256": sha256(contents).hexdigest()}


def analyzer_result(study: str, *, failed: bool) -> dict:
    if study == "branch_batch":
        return {"timer_control": {"passes": not failed}}
    if study == "history_b2":
        controls = {f"p{probe}_n{n}": {
            gate: {"passes": not (failed and probe == 1 and n == 16 and
                                   gate == "fixed_neutral")}
            for gate in ("pause", "small", "fixed_neutral")}
            for probe in (0, 1) for n in (1, 16)}
        return {"controls": controls, "statistical_control_gates_pass": not failed}
    if study == "address_sensitivity":
        timer = {f"p{p}": {"small_pass": not (failed and p == 0),
                           "pause_pass": True} for p in (0, 1)}
        fixed = {f"{site}_p{p}": True
                 for site in ("target", "same4k", "offset128") for p in (0, 1)}
        return {"timer_controls": timer, "timer_controls_pass": not failed,
                "fixed_within_tolerance": fixed,
                "fixed_all_within_tolerance": True}
    raise AssertionError(study)


class FailureClassifierTests(unittest.TestCase):
    def setUp(self) -> None:
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.path = Path(folder.name) / "suite.zip"
        self.exe = b"MZ" + bytes(62)
        self.trace = (b"EXAMPLE_BINARY,sha256=" + sha256(self.exe).hexdigest().encode()
                      + b"\nmalformed test trace\n")

    def make_zip(self, specifications: list[tuple[str, bool]], *,
                 omit_exe: bool = False) -> None:
        runs = []
        files = {}
        for index, (study, paired) in enumerate(specifications):
            stem = f"{study}-{index}"
            run = {"stage": "focus", "round": 2, "position": index,
                   "study": study, "status": "failed_preserved",
                   "error": f"original error for {study} at {index}",
                   "new_artifacts": [], "sidecars": [], "traces": [], "exes": []}
            if paired:
                log, exe = f"{stem}.log", f"{stem}.exe"
                run["traces"] = [file_record(log, self.trace)]
                run["exes"] = [file_record(exe, self.exe)]
                files[log] = self.trace
                if not omit_exe:
                    files[exe] = self.exe
            runs.append(run)
        with ZipFile(self.path, "w") as archive:
            archive.writestr("session.json", json.dumps({"schema": 1, "runs": runs}))
            for name, data in files.items():
                archive.writestr(name, data)

    def test_failed_controls_require_audited_pair_and_explicit_gate(self) -> None:
        studies = ["branch_batch", "history_b2", "address_sensitivity"]
        self.make_zip([(study, True) for study in studies])

        def replay(command: list[str], **kwargs: object):
            study = next(name for name, script in classifier.ANALYZERS.items()
                         if script == Path(command[1]).name)
            self.assertEqual(command[-1], "--json")
            self.assertNotIn("--strict", command)
            return classifier.subprocess.CompletedProcess(
                command, 0, json.dumps(analyzer_result(study, failed=True)), "")

        with patch.object(classifier.subprocess, "run", side_effect=replay) as process:
            result = classifier.classify_archive(self.path)
        self.assertTrue(result["archive_integrity_ok"])
        self.assertEqual(process.call_count, 3)
        for run in result["failed_runs"]:
            self.assertEqual(run["category"], "completed_control_inconclusive")
            self.assertTrue(run["failed_gates"])
            self.assertEqual(run["status"], "failed_preserved")
            self.assertEqual(run["error"],
                             f"original error for {run['study']} at {run['position']}")

    def test_malformed_trace_is_not_a_completed_control_run(self) -> None:
        self.make_zip([("branch_batch", True)])
        # Exercise the real non-strict parser; the ZIP itself is hash-consistent.
        result = classifier.classify_archive(self.path)
        self.assertTrue(result["archive_integrity_ok"])
        self.assertEqual(result["failed_runs"][0]["category"], "invalid_trace")
        self.assertEqual(result["failed_runs"][0]["failed_gates"], [])

    def test_missing_pair_and_unsupported_study(self) -> None:
        self.make_zip([("history_b2", False), ("unknown_study", False)])
        with patch.object(classifier.subprocess, "run") as process:
            result = classifier.classify_archive(self.path)
        process.assert_not_called()
        self.assertTrue(result["archive_integrity_ok"])
        self.assertEqual([r["category"] for r in result["failed_runs"]],
                         ["missing_build_or_run_pair", "unsupported_study"])

    def test_archive_with_missing_declared_exe_is_not_replayed(self) -> None:
        self.make_zip([("branch_batch", True)], omit_exe=True)
        with patch.object(classifier.subprocess, "run") as process:
            result = classifier.classify_archive(self.path)
        process.assert_not_called()
        self.assertFalse(result["archive_integrity_ok"])
        self.assertEqual(result["failed_runs"], [])
        self.assertTrue(any("missing" in problem for problem in result["audit_problems"]))

    def test_passed_gates_in_failed_record_require_review(self) -> None:
        self.make_zip([("branch_batch", True)])
        replay = classifier.subprocess.CompletedProcess(
            [], 0, json.dumps(analyzer_result("branch_batch", failed=False)), "")
        with patch.object(classifier.subprocess, "run", return_value=replay):
            result = classifier.classify_archive(self.path)
        self.assertEqual(result["failed_runs"][0]["category"],
                         "inconsistent_record_requires_review")

    def test_missing_or_contradictory_gates_require_review(self) -> None:
        self.make_zip([("history_b2", True)])
        contradictory = analyzer_result("history_b2", failed=True)
        contradictory["statistical_control_gates_pass"] = True
        for payload in ({"statistical_control_gates_pass": False}, contradictory):
            with self.subTest(payload=payload):
                replay = classifier.subprocess.CompletedProcess([], 0,
                                                                 json.dumps(payload), "")
                with patch.object(classifier.subprocess, "run", return_value=replay):
                    result = classifier.classify_archive(self.path)
                self.assertEqual(result["failed_runs"][0]["category"],
                                 "analyzer_result_requires_review")


if __name__ == "__main__":
    unittest.main()
