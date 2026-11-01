"""Independent-session provenance and no-pooling tests for B2 replication."""

import hashlib
from io import BytesIO
import json
from pathlib import Path
import sys
from types import SimpleNamespace
import unittest
from unittest.mock import patch
from zipfile import ZipFile

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import summarize_b2_outcome_replicates as replication


HEAD = "a" * 40
BASE = "b2-outcome-windows-20261101T000000001Z"


def encode(value):
    return json.dumps(value).encode("utf-8")


def pack(files):
    buffer = BytesIO()
    with ZipFile(buffer, "w") as archive:
        for name, data in files.items():
            archive.writestr(name, data)
    return buffer.getvalue()


def tiny_pe():
    data = bytearray(0x204)
    data[0x3c:0x40] = (0x80).to_bytes(4, "little")
    data[0x80:0x84] = b"PE\0\0"
    data[0x86:0x88] = (1).to_bytes(2, "little")
    data[0x94:0x96] = (0).to_bytes(2, "little")
    data[0x98:0xa0] = b".text\0\0\0"
    data[0xa8:0xac] = (4).to_bytes(4, "little")
    data[0xac:0xb0] = (0x200).to_bytes(4, "little")
    data[0x200:] = b"ABCD"
    return bytes(data)


def expected_analysis(seed, controls=True):
    outcomes = {key: {"F": {
        "paired_trimmed_mean_ticks_per_probe": seed / 100,
        "within_run_cycle_bootstrap_95_ticks_per_probe": [seed / 100 - .1,
                                                            seed / 100 + .1]}}
                for key in ("p0_n1", "p1_n1", "p0_n16", "p1_n16")}
    return {"cpu": {"vendor": "AuthenticAMD", "signature": "0x00b40f40",
                    "hypervisor": "1"}, "run": {"seed": str(seed)},
            "host": {"run_utc": "20261101T120000Z", "windows_build": "26200"},
            "binary_sha256": replication._digest(tiny_pe()), "affinity_cpu": 0,
            "outcomes": outcomes, "apparatus_controls_pass": controls,
            "primary_practical_association": False if controls else None,
            "primary_direction": "none" if controls else None}


def inner(seed, controls=True, partial=False, early=False):
    files = {}
    pe = tiny_pe()
    build = {"study": replication.INNER_STUDY, "seed": seed,
             "git_head": HEAD, "git_clean": True,
             "build_runtime_status": "failed_at_compilation" if partial else "analyzed",
             "control_status": "not_evaluated" if partial else
                               "passed" if controls else "inconclusive",
             "source_sha256": {"programs/b2_outcome_windows.c": "b" * 64},
             "text_section_sha256": replication._text_sha(pe),
             "binary_sha256": replication._digest(pe),
             "strict_analyzer_exit_code": 0 if controls else 1,
             "primary_practical_association": False if controls else None,
             "primary_direction": "none" if controls else None}
    if partial:
        build["failure"] = "compiler rejected source"
        if early:
            build["git_head"] = None
            build["git_clean"] = None
    else:
        files[BASE + ".exe"] = pe
        files[BASE + ".log"] = str(seed).encode("ascii")
        files[BASE + ".analysis.json"] = encode(expected_analysis(seed, controls))
        files[BASE + ".strict.log"] = b"control verdict"
    files[BASE + ".build.json"] = encode(build)
    manifest = {"study": replication.INNER_STUDY, "git_head": HEAD,
                "git_clean": True, "build_runtime_status": build["build_runtime_status"],
                "control_status": build["control_status"],
                "files_sha256": {name: replication._digest(data)
                                 for name, data in files.items()}}
    if early:
        manifest["git_head"] = None
        manifest["git_clean"] = None
    files[BASE + ".manifest.json"] = encode(manifest)
    return pack(files)


def fixture(controls=(True, True, True), partial=None):
    archives, transcripts, attempts = {}, {}, []
    for ordinal, seed in enumerate((1, 2, 3), 1):
        archive = f"run-{ordinal}.zip"
        transcript = f"replication.attempt-{ordinal}.transcript.log"
        transcripts[transcript] = f"seed {seed}".encode()
        archives[archive] = inner(seed, controls[ordinal-1], partial == ordinal)
        attempts.append({"ordinal": ordinal, "seed": seed,
                         "exit_code": 1 if partial == ordinal or not controls[ordinal-1] else 0,
                         "archive": archive, "archive_sha256": replication._digest(archives[archive]),
                         "transcript": transcript,
                         "transcript_sha256": replication._digest(transcripts[transcript])})
    session = {"schema": 1, "study": replication.STUDY, "git_head": HEAD,
               "git_clean": True, "preselected_seeds": [1, 2, 3],
               "attempts": attempts}
    return session, archives, transcripts


def fake_parse(raw):
    seed = int(raw)
    expected = expected_analysis(seed)
    return SimpleNamespace(cpu=expected["cpu"], run=expected["run"],
                           host=expected["host"], binary_sha256=expected["binary_sha256"],
                           affinity_cpu=0, seed=seed)


def fake_summarize(trace):
    expected = expected_analysis(trace.seed, trace.seed != 3 or not getattr(
        fake_summarize, "third_failed", False))
    return {key: value for key, value in expected.items()
            if key not in ("cpu", "run", "host", "binary_sha256", "affinity_cpu")}


class ReplicationSessionTests(unittest.TestCase):
    def setUp(self):
        self.parse_patch = patch.object(replication, "parse_trace", fake_parse)
        self.summary_patch = patch.object(replication, "summarize", fake_summarize)
        self.parse_patch.start()
        self.summary_patch.start()
        fake_summarize.third_failed = False
        self.addCleanup(self.parse_patch.stop)
        self.addCleanup(self.summary_patch.stop)

    def test_three_distinct_run_units_and_no_block_pooling(self):
        session, archives, transcripts = fixture()
        result = replication.summarize_session(session, archives, transcripts)
        self.assertEqual(result["analyzed_run_count"], 3)
        self.assertEqual(result["control_passed_run_count"], 3)
        self.assertEqual(result["eligible_primary_point_median"], .02)
        self.assertEqual(result["eligible_primary_point_range"], [.01, .03])
        self.assertTrue(result["single_utc_date"])
        self.assertNotIn("pooled_blocks", result)

    def test_failed_control_retained_but_excluded_from_eligible_summary(self):
        fake_summarize.third_failed = True
        session, archives, transcripts = fixture(controls=(True, True, False))
        result = replication.summarize_session(session, archives, transcripts)
        self.assertEqual(result["analyzed_run_count"], 3)
        self.assertEqual(result["control_passed_run_count"], 2)
        self.assertFalse(result["runs"][2]["eligible"])
        self.assertEqual(result["eligible_primary_point_range"], [.01, .02])

    def test_partial_build_preserved_as_attempt(self):
        session, archives, transcripts = fixture(partial=2)
        result = replication.summarize_session(session, archives, transcripts)
        self.assertEqual(result["attempt_count"], 3)
        self.assertEqual(result["analyzed_run_count"], 2)
        self.assertIn("compiler rejected", result["runs"][1]["diagnostic"])

    def test_early_diagnostic_without_git_capture_is_preserved_in_outer(self):
        session, archives, transcripts = fixture()
        archives["run-2.zip"] = inner(2, partial=True, early=True)
        session["attempts"][1]["archive_sha256"] = replication._digest(archives["run-2.zip"])
        session["attempts"][1]["exit_code"] = 1
        result = replication.summarize_session(session, archives, transcripts)
        self.assertEqual(result["analyzed_run_count"], 2)
        self.assertIsNone(result["runs"][1]["git_head_recorded"])
        self.assertFalse(result["runs"][1]["eligible"])
        files = {"b2-repl.session.json": encode(session), "b2-repl.summary.json": encode(result),
                 **archives, **transcripts}
        files["b2-repl.manifest.json"] = encode({"study": replication.STUDY,
            "git_head": HEAD, "files_sha256": {
                name: replication._digest(data) for name, data in files.items()}})
        from tempfile import TemporaryDirectory
        with TemporaryDirectory() as directory:
            path = Path(directory) / "session.zip"
            path.write_bytes(pack(files))
            self.assertEqual(replication.summarize_outer(path), result)

    def test_one_complete_run_has_unknown_comparability(self):
        session, archives, transcripts = fixture(partial=2)
        archives["run-3.zip"] = inner(3, partial=True)
        session["attempts"][2]["archive_sha256"] = replication._digest(archives["run-3.zip"])
        session["attempts"][2]["exit_code"] = 1
        result = replication.summarize_session(session, archives, transcripts)
        self.assertIsNone(result["same_text_section"])
        self.assertIsNone(result["single_utc_date"])

    def test_duplicate_seed_rejected_before_analysis(self):
        session, archives, transcripts = fixture()
        session["preselected_seeds"][2] = 2
        with self.assertRaisesRegex(ValueError, "three-seed"):
            replication.summarize_session(session, archives, transcripts)

    def test_nested_member_mutation_rejected(self):
        session, archives, transcripts = fixture()
        with ZipFile(BytesIO(archives["run-2.zip"])) as source:
            files = {name: source.read(name) for name in source.namelist()}
        files[BASE + ".log"] = b"changed"
        archives["run-2.zip"] = pack(files)
        session["attempts"][1]["archive_sha256"] = replication._digest(archives["run-2.zip"])
        with self.assertRaisesRegex(ValueError, "member hash mismatch"):
            replication.summarize_session(session, archives, transcripts)

    def test_corrupt_inner_zip_and_mismatched_stem_rejected(self):
        session, archives, transcripts = fixture()
        archives["run-1.zip"] = b"not a ZIP"
        session["attempts"][0]["archive_sha256"] = replication._digest(archives["run-1.zip"])
        with self.assertRaisesRegex(ValueError, "invalid run ZIP"):
            replication.summarize_session(session, archives, transcripts)
        archives["run-1.zip"] = inner(1)
        with ZipFile(BytesIO(archives["run-1.zip"])) as source:
            files = {name: source.read(name) for name in source.namelist()}
        files["other.build.json"] = files.pop(BASE + ".build.json")
        manifest = json.loads(files[BASE + ".manifest.json"])
        manifest["files_sha256"]["other.build.json"] = manifest["files_sha256"].pop(BASE + ".build.json")
        files[BASE + ".manifest.json"] = encode(manifest)
        archives["run-1.zip"] = pack(files)
        session["attempts"][0]["archive_sha256"] = replication._digest(archives["run-1.zip"])
        with self.assertRaisesRegex(ValueError, "stems differ"):
            replication.summarize_session(session, archives, transcripts)

    def test_analysis_mutation_rejected_even_with_updated_manifest(self):
        session, archives, transcripts = fixture()
        with ZipFile(BytesIO(archives["run-1.zip"])) as source:
            files = {name: source.read(name) for name in source.namelist()}
        analysis = json.loads(files[BASE + ".analysis.json"])
        analysis["outcomes"]["p0_n1"]["F"]["paired_trimmed_mean_ticks_per_probe"] = 100
        files[BASE + ".analysis.json"] = encode(analysis)
        manifest = json.loads(files[BASE + ".manifest.json"])
        manifest["files_sha256"][BASE + ".analysis.json"] = replication._digest(files[BASE + ".analysis.json"])
        files[BASE + ".manifest.json"] = encode(manifest)
        archives["run-1.zip"] = pack(files)
        session["attempts"][0]["archive_sha256"] = replication._digest(archives["run-1.zip"])
        with self.assertRaisesRegex(ValueError, "does not replay"):
            replication.summarize_session(session, archives, transcripts)

    def test_missing_archive_keeps_preselected_attempt(self):
        session, archives, transcripts = fixture()
        session["attempts"][1]["archive"] = None
        session["attempts"][1]["archive_sha256"] = None
        result = replication.summarize_session(session, archives, transcripts)
        self.assertEqual(result["attempt_count"], 3)
        self.assertEqual(result["analyzed_run_count"], 2)
        self.assertIn("no evidence ZIP", result["runs"][1]["diagnostic"])

    def test_outer_manifest_and_summary_replay(self):
        session, archives, transcripts = fixture()
        summary = replication.summarize_session(session, archives, transcripts)
        files = {"b2-repl.session.json": encode(session), "b2-repl.summary.json": encode(summary),
                 **archives, **transcripts}
        files["b2-repl.manifest.json"] = encode({"study": replication.STUDY,
            "git_head": HEAD, "files_sha256": {
            name: replication._digest(data) for name, data in files.items()}})
        from tempfile import TemporaryDirectory
        with TemporaryDirectory() as directory:
            path = Path(directory) / "session.zip"
            path.write_bytes(pack(files))
            self.assertEqual(replication.summarize_outer(path), summary)
            files["b2-repl.summary.json"] = encode({"fake": True})
            files["b2-repl.manifest.json"] = encode({"study": replication.STUDY,
                "git_head": HEAD, "files_sha256": {
                name: replication._digest(data) for name, data in files.items()
                if name != "b2-repl.manifest.json"}})
            path.write_bytes(pack(files))
            with self.assertRaisesRegex(ValueError, "summary does not replay"):
                replication.summarize_outer(path)


if __name__ == "__main__":
    unittest.main()
