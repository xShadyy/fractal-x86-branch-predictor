"""Cross-file integrity checks for portable Windows pilot evidence archives."""

from __future__ import annotations

from hashlib import sha256
import json
from pathlib import Path
import sys
import tempfile
import unittest
from zipfile import ZipFile

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from audit_suite_evidence import audit  # noqa: E402


def record(name: str, contents: bytes) -> dict[str, str]:
    return {"path": rf"C:\research\out\{name}",
            "sha256": sha256(contents).hexdigest()}


class EvidenceAuditTests(unittest.TestCase):
    def setUp(self) -> None:
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.path = Path(self.folder.name) / "evidence.zip"
        self.exe = b"MZ" + b"\x00" * 62
        self.trace = (b"EXAMPLE_BINARY,sha256=" + sha256(self.exe).hexdigest().encode()
                      + b"\n")
        self.host = b'{"cpu":"test"}'
        self.transcript = b"build and analyze complete\n"

    def make_zip(self, *, omit_exe: bool = False, fail_run: bool = False) -> None:
        run = {"stage": "exploratory", "study": "example",
               "status": "failed_preserved" if fail_run else
               "validated_trace_pending_binary_audit",
               "transcript_path": record("round-1-example.txt", self.transcript)["path"],
               "transcript_sha256": sha256(self.transcript).hexdigest(),
               "traces": [] if fail_run else [record("example-20261031T120000Z.log", self.trace)],
               "exes": [] if fail_run else [record("example-20261031T120000Z.exe", self.exe)],
               "new_artifacts": [], "sidecars": []}
        session = {"schema": 1, "git_head": "f" * 40,
                   "host_snapshot": record("host-windows-test.json", self.host),
                   "runs": [run]}
        with ZipFile(self.path, "w") as archive:
            archive.writestr("session.json", json.dumps(session))
            archive.writestr("host-windows-test.json", self.host)
            archive.writestr("round-1-example.txt", self.transcript)
            if not fail_run:
                archive.writestr("example-20261031T120000Z.log", self.trace)
                if not omit_exe:
                    archive.writestr("example-20261031T120000Z.exe", self.exe)

    def test_matching_archive_and_preserved_failed_run(self) -> None:
        self.make_zip()
        result = audit(self.path)
        self.assertTrue(result["integrity_ok"])
        self.assertEqual(result["recorded_runs"], 1)
        self.assertIn("instruction and control audit still required",
                      result["scientific_status"])
        self.make_zip(fail_run=True)
        self.assertTrue(audit(self.path)["integrity_ok"])

    def test_missing_executable_is_rejected(self) -> None:
        self.make_zip(omit_exe=True)
        result = audit(self.path)
        self.assertFalse(result["integrity_ok"])
        self.assertTrue(any("missing" in p or "no uniquely paired" in p
                            for p in result["problems"]))

    def test_embedded_binary_hash_disagrees_with_manifest(self) -> None:
        self.trace = b"EXAMPLE_BINARY,sha256=" + b"0" * 64 + b"\n"
        self.make_zip()
        result = audit(self.path)
        self.assertFalse(result["integrity_ok"])
        self.assertTrue(any("embedded binary" in p for p in result["problems"]))

    def test_unreferenced_file_is_reported(self) -> None:
        self.make_zip()
        with ZipFile(self.path, "a") as archive:
            archive.writestr("unrecorded.txt", b"unexpected")
        self.assertTrue(any("unreferenced" in problem for problem in
                            audit(self.path)["problems"]))

    def test_malformed_artifact_array_fails_cleanly(self) -> None:
        self.make_zip()
        with ZipFile(self.path) as archive:
            files = {name: archive.read(name) for name in archive.namelist()}
        session = json.loads(files["session.json"])
        session["runs"][0]["traces"] = None
        files["session.json"] = json.dumps(session).encode()
        with ZipFile(self.path, "w") as archive:
            for name, data in files.items():
                archive.writestr(name, data)
        result = audit(self.path)
        self.assertFalse(result["integrity_ok"])
        self.assertTrue(any("malformed traces array" in problem for problem in
                            result["problems"]))


if __name__ == "__main__":
    unittest.main()
