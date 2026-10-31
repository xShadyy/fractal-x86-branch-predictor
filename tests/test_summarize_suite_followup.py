"""Portable archive series checks, including failed studies and frozen code."""

from __future__ import annotations

from hashlib import sha256
import json
import ntpath
from pathlib import Path
import struct
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch
from zipfile import ZipFile

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import summarize_suite_followup as series  # noqa: E402


def _pe(code: bytes = b"\x90" * 32) -> bytes:
    """Small PE32+ fixture with a real executable .text section table."""
    data = bytearray(0x300)
    data[:2] = b"MZ"
    struct.pack_into("<I", data, 0x3c, 0x80)
    data[0x80:0x84] = b"PE\0\0"
    struct.pack_into("<H", data, 0x86, 1)
    struct.pack_into("<H", data, 0x94, 0xf0)
    struct.pack_into("<H", data, 0x98, 0x20b)
    table = 0x80 + 24 + 0xf0
    data[table:table + 5] = b".text"
    struct.pack_into("<II", data, table + 16, len(code), 0x200)
    struct.pack_into("<I", data, table + 36, 0x20000000)
    data[0x200:0x200 + len(code)] = code
    return bytes(data)


def _record(name: str, contents: bytes) -> dict[str, str]:
    return {"path": "C:\\research\\out\\" + name,
            "sha256": sha256(contents).hexdigest()}


def _host(stamp: str) -> bytes:
    return json.dumps({
        "captured_utc": stamp,
        "os": {"Caption": "Windows Test", "Version": "10.0.26200",
               "BuildNumber": "26200", "OSArchitecture": "64-bit"},
        "processor": {"Name": "Fixture CPU", "NumberOfCores": 8,
                      "NumberOfLogicalProcessors": 16},
        "baseboard": {"Manufacturer": "Example", "Product": "Board", "Version": "1"},
        "bios": {"Manufacturer": "Example", "SMBIOSBIOSVersion": "2",
                 "ReleaseDate": "today"},
        "hypervisor": {"HypervisorPresent": True},
        "active_power_plan": "Balanced",
    }).encode()


def _parse_fake(text: str) -> SimpleNamespace:
    rows = text.splitlines()
    spec = dict(field.split("=", 1) for field in rows[0][5:].split(","))
    digest = rows[1].split("sha256=", 1)[1]
    return SimpleNamespace(run={"seed": spec["seed"]},
                           host={"run_utc": spec["stamp"],
                                 "windows_build": "26200"},
                           affinity_cpu=0, binary_sha256=digest,
                           estimate=float(spec["estimate"]),
                           gate=spec["gate"] == "1",
                           random_gate=spec.get("random_gate", spec["gate"]) == "1")


def _summary_a(trace: SimpleNamespace) -> dict[str, object]:
    return {"contrasts": {"primary_interaction":
                          {"paired_trimmed_mean_ticks_per_iteration": trace.estimate}},
            "timer_control": {"passes": trace.gate},
            "negative_controls_within_tolerance": {"fixed": trace.gate},
            "controls_pass": trace.gate}


def _summary_c(trace: SimpleNamespace) -> dict[str, object]:
    return {"profile": {
        "p2_minus_p32": {"contrasts": {"adjusted":
                            {"paired_trimmed_mean_ticks_per_iteration": trace.estimate}},
                           "fixed_within_tolerance": trace.gate,
                           "branchless_within_tolerance": trace.gate},
        "random_minus_p32": {"contrasts": {"adjusted":
                              {"paired_trimmed_mean_ticks_per_iteration":
                               trace.estimate + 18}},
                             "fixed_within_tolerance": trace.random_gate,
                             "branchless_within_tolerance": trace.random_gate}},
            "timer_control": {"passes": trace.gate},
            "controls_pass": trace.gate}


class SuiteSeriesTests(unittest.TestCase):
    def setUp(self) -> None:
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.root = Path(folder.name)
        self.patches = [
            patch.object(series, "parse_decision", _parse_fake),
            patch.object(series, "parse_pattern", _parse_fake),
            patch.object(series, "summarize_decision", _summary_a),
            patch.object(series, "summarize_pattern", _summary_c),
        ]
        # STUDIES stores callables at module import time.
        for key, summary in (("decision_source_a", _summary_a),
                             ("pattern_complexity", _summary_c)):
            self.patches.append(patch.dict(series.STUDIES[key],
                                           {"parse": _parse_fake,
                                            "summarize": summary}))
        for item in self.patches:
            item.start()
            self.addCleanup(item.stop)

    def archive(self, day: str, suite_seed: int, a_seed: int, c_seed: int, *,
                a_estimate: float, c_estimate: float, c_gate: bool = True,
                source_drift: bool = False, code: bytes = b"\x90" * 32,
                corrupt: bool = False, phase: str = "Followup",
                study_set: str = "Focus", failed_other: bool = False,
                c_candidate_gate: bool = True) -> Path:
        stamp = day + f"T{12 + suite_seed:02d}0000Z"
        prefix = {"decision_source_a": "decision-source-windows-",
                  "pattern_complexity": "pattern-complexity-windows-"}
        host_name = "host-windows-" + stamp + ".json"
        host_bytes = _host(stamp)
        sources = {name: ("1" if source_drift else "0") * 64
                   for protocol in series.STUDIES.values()
                   for name in protocol["sources"]}
        entries: dict[str, bytes] = {host_name: host_bytes}
        runs = []
        for key, seed, estimate, gate in (
                ("decision_source_a", a_seed, a_estimate, True),
                ("pattern_complexity", c_seed, c_estimate, c_gate)):
            name = prefix[key] + stamp
            exe = _pe(code)
            marker = "DECISION" if key == "decision_source_a" else "PATTERN"
            trace = (f"DATA,seed={seed},stamp={stamp},estimate={estimate},gate={int(gate)},"
                     f"random_gate={int(c_candidate_gate)}\n"
                     f"{marker}_BINARY,sha256={sha256(exe).hexdigest()}\n").encode()
            entries[name + ".exe"] = exe if not (corrupt and key == "pattern_complexity") else exe + b"bad"
            entries[name + ".log"] = trace
            runs.append({"stage": "exploratory", "round": 1, "position": len(runs) + 1,
                         "study": key, "seed": seed,
                         "status": (series.PASS_STATUS if gate else "failed_preserved"),
                         "traces": [_record(name + ".log", trace)],
                         "exes": [_record(name + ".exe", exe)],
                         "sidecars": [], "new_artifacts": []})
        for key in sorted(series.FOCUS_STUDIES - {"decision_source_a",
                                                        "pattern_complexity"}):
            name = key + "-" + stamp
            exe = _pe(code)
            trace = ("EXAMPLE_BINARY,sha256=" + sha256(exe).hexdigest() + "\n").encode()
            entries[name + ".exe"] = exe
            entries[name + ".log"] = trace
            failed = failed_other and key == "history_b2"
            runs.append({"stage": "exploratory", "round": 1,
                         "position": len(runs) + 1, "study": key,
                         "seed": 1000 + len(runs),
                         "status": "failed_preserved" if failed else series.PASS_STATUS,
                         "error": "small-work gate failed" if failed else None,
                         "traces": [_record(name + ".log", trace)],
                         "exes": [_record(name + ".exe", exe)],
                         "sidecars": [], "new_artifacts": []})
        session = {"schema": 1, "started_utc": stamp, "suite_seed": suite_seed,
                   "phase": phase, "study_set": study_set,
                   "git_head": "f" * 40,
                   "host_snapshot": _record(host_name, host_bytes),
                   "source_sha256": sources, "runs": runs}
        entries["session.json"] = json.dumps(session).encode()
        path = self.root / (day + "-" + str(suite_seed) + ".zip")
        with ZipFile(path, "w") as archive:
            for name, data in entries.items():
                archive.writestr(name, data)
        return path

    def test_failed_controls_remain_visible_and_days_are_descriptive(self) -> None:
        first = self.archive("20261030", 1, 101, 201,
                             a_estimate=16, c_estimate=0)
        second = self.archive("20261031", 2, 102, 202,
                              a_estimate=18, c_estimate=1, c_gate=False,
                              failed_other=True)
        result = series.summarize_suite_archives([first, second])
        self.assertEqual(result["studies"]["decision_source_a"]["distinct_utc_days"], 2)
        a = result["studies"]["decision_source_a"]["focus_descriptive_if_comparable"]
        self.assertEqual(a["mean_of_all_run_estimates"]["primary_interaction"], 17)
        c = result["studies"]["pattern_complexity"]["focus_descriptive_if_comparable"]
        self.assertEqual(c["control_failed_run_count"], 1)
        self.assertEqual(c["mean_of_all_run_estimates"]["random_minus_p32"], 18.5)
        self.assertEqual(len(result["sessions"][1]["runs"]), 9)
        failed = next(run for run in result["sessions"][1]["runs"]
                      if run["study"] == "history_b2")
        self.assertEqual(failed["error"], "small-work gate failed")
        self.assertIn("no across-day CI", c["uncertainty_scope"])
        self.assertFalse(result["followup_complete"])

    def test_modified_executable_is_rejected_by_archive_hash_audit(self) -> None:
        path = self.archive("20261030", 1, 101, 201,
                            a_estimate=16, c_estimate=0, corrupt=True)
        with self.assertRaisesRegex(ValueError, "integrity failed"):
            series.summarize_suite_archives([path])

    def test_source_or_code_drift_disables_cross_session_description(self) -> None:
        first = self.archive("20261030", 1, 101, 201,
                             a_estimate=16, c_estimate=0)
        second = self.archive("20261031", 2, 102, 202,
                              a_estimate=18, c_estimate=1, source_drift=True,
                              code=b"\xcc" * 32)
        result = series.summarize_suite_archives([first, second])
        self.assertFalse(result["studies"]["pattern_complexity"]["comparable"])
        self.assertIsNone(result["studies"]["pattern_complexity"]["focus_descriptive_if_comparable"])
        self.assertEqual(len(result["sessions"]), 2)

    def test_duplicate_seed_is_reported_without_erasing_runs(self) -> None:
        first = self.archive("20261030", 1, 101, 201,
                             a_estimate=16, c_estimate=0)
        second = self.archive("20261031", 2, 101, 202,
                              a_estimate=18, c_estimate=1)
        result = series.summarize_suite_archives([first, second])
        self.assertFalse(result["studies"]["decision_source_a"]["comparable"])
        self.assertTrue(any("duplicate run seed" in warning for warning in
                            result["warnings"]))
        self.assertEqual(result["studies"]["decision_source_a"]["measured_run_count"], 2)

    def test_six_focus_sessions_two_days_complete_and_pilot_excluded(self) -> None:
        pilot = self.archive("20261029", 0, 10, 20, a_estimate=100,
                             c_estimate=100, phase="Pilot", study_set="Full")
        focus = [self.archive("20261030" if index < 3 else "20261031",
                              index + 1, 100 + index, 200 + index,
                              a_estimate=16 + index, c_estimate=0)
                 for index in range(6)]
        result = series.summarize_suite_archives([pilot, *focus])
        self.assertTrue(result["followup_complete"])
        self.assertEqual(result["focus_sessions_per_utc_day"],
                         {"2026-10-30": 3, "2026-10-31": 3})
        a = result["studies"]["decision_source_a"]
        self.assertEqual(a["pilot_measured_run_count"], 1)
        self.assertEqual(a["focus_descriptive_if_comparable"]["mean_of_all_run_estimates"]
                         ["primary_interaction"], 18.5)

    def test_pilot_only_keeps_counts_without_followup_summary(self) -> None:
        pilot = self.archive("20261029", 1, 10, 20, a_estimate=17,
                             c_estimate=0, phase="Pilot", study_set="Full")
        result = series.summarize_suite_archives([pilot])
        self.assertFalse(result["followup_complete"])
        self.assertEqual(result["focus_session_count"], 0)
        a = result["studies"]["decision_source_a"]
        self.assertEqual(a["pilot_measured_run_count"], 1)
        self.assertEqual(a["focus_measured_run_count"], 0)
        self.assertIsNone(a["focus_descriptive_if_comparable"])

    def test_new_c_candidate_gate_is_separate_from_original_c_primary(self) -> None:
        archives = [self.archive("20261030" if index < 3 else "20261031",
                                 index + 1, 100 + index, 200 + index,
                                 a_estimate=16, c_estimate=0,
                                 c_candidate_gate=index != 0)
                    for index in range(6)]
        result = series.summarize_suite_archives(archives)
        self.assertFalse(result["followup_complete"])
        first_c = next(run["analysis"] for run in result["sessions"][0]["runs"]
                       if run["study"] == "pattern_complexity")
        self.assertTrue(first_c["controls_pass"])
        self.assertFalse(first_c["new_primary_eligible"])
        self.assertEqual(result["studies"]["pattern_complexity"]
                         ["focus_descriptive_if_comparable"]
                         ["new_primary_eligible_run_count"], 5)

    def test_missing_focus_study_prevents_complete_protocol(self) -> None:
        archives = [self.archive("20261030" if index < 3 else "20261031",
                                 index + 1, 100 + index, 200 + index,
                                 a_estimate=16, c_estimate=0)
                    for index in range(6)]
        with ZipFile(archives[0]) as archive:
            files = {name: archive.read(name) for name in archive.namelist()}
        session = json.loads(files["session.json"])
        missing = next(run for run in session["runs"]
                       if run["study"] == "history_probe_b1")
        session["runs"].remove(missing)
        for item in missing["traces"] + missing["exes"]:
            files.pop(ntpath.basename(item["path"]))
        files["session.json"] = json.dumps(session).encode()
        with ZipFile(archives[0], "w") as archive:
            for name, data in files.items():
                archive.writestr(name, data)
        result = series.summarize_suite_archives(archives)
        self.assertFalse(result["followup_complete"])
        self.assertTrue(any("Focus study set incomplete" in reason
                            for reason in result["followup_completion_reasons"]))


if __name__ == "__main__":
    unittest.main()
