"""Integrity checks for a preserved multi-run Windows timing series."""

import json
from pathlib import Path
import shutil
import struct
import sys
import tempfile
import unittest
from unittest.mock import patch

PROJECT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT / "scripts"))
import summarize_branch_batch_series as series  # noqa: E402

PILOT = PROJECT / "results" / "2026-10-30-windows-v2-pilot"
REPLICATION = PROJECT / "results" / "2026-10-30-windows-v2-replication"


def pilot_manifest(root):
    trace = "branch-batch-windows-20261030T130133Z.log"
    exe = "branch-batch-windows-20261030T130133Z.exe"
    host = "host-windows-20261030T125908Z.json"
    for name in (trace, exe, host):
        shutil.copyfile(PILOT / name, root / name)
    manifest = {"schema": 1, "sessions": [{
        "id": "pilot", "host": host, "runs": [{"trace": trace, "exe": exe}],
    }]}
    path = root / "manifest.json"
    path.write_text(json.dumps(manifest), encoding="utf-8")
    return path, manifest


class SeriesTests(unittest.TestCase):
    def test_all_archived_replication_runs_are_accounted_for(self):
        result = series.summarize_series(REPLICATION / "manifest.json")
        self.assertEqual(result["all_runs_descriptive"]["run_count"], 6)
        self.assertEqual(result["all_runs_descriptive"]["timer_control_passed_runs"], 6)
        self.assertEqual(len({run["seed"] for session in result["sessions"]
                              for run in session["runs"]}), 6)
        self.assertEqual([session["descriptive"]["run_count"]
                          for session in result["sessions"]], [3, 3])
        self.assertEqual(result["text_sha256"],
                         "7ecae6f5ee8c9114e750f30c9c196b1c0685d9f0f0f302fb8d752296baa0d469")
        self.assertNotIn("across_run_confidence_interval", result)

    def test_mismatched_binary_is_rejected(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            path, manifest = pilot_manifest(root)
            exe = root / manifest["sessions"][0]["runs"][0]["exe"]
            data = bytearray(exe.read_bytes())
            data[-1] ^= 1
            exe.write_bytes(data)
            with self.assertRaisesRegex(ValueError, "EXE SHA-256 differs"):
                series.summarize_series(path)

    def test_path_traversal_and_stale_host_are_rejected(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            path, manifest = pilot_manifest(root)
            manifest["sessions"][0]["runs"][0]["trace"] = "../outside.log"
            path.write_text(json.dumps(manifest), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "must stay under"):
                series.summarize_series(path)
            manifest["sessions"][0]["runs"][0]["trace"] = \
                "branch-batch-windows-20261030T130133Z.log"
            path.write_text(json.dumps(manifest), encoding="utf-8")
            host = root / manifest["sessions"][0]["host"]
            record = json.loads(host.read_text(encoding="utf-8-sig"))
            record["captured_utc"] = "20261029T125908Z"
            host.write_text(json.dumps(record), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "precede the run by at most"):
                series.summarize_series(path)

    def test_duplicate_seed_is_rejected_even_for_separate_paths(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            path, manifest = pilot_manifest(root)
            first = manifest["sessions"][0]["runs"][0]
            second = {key: value.replace("Z.", "Z-copy.")
                      for key, value in first.items()}
            for key in ("trace", "exe"):
                shutil.copyfile(root / first[key], root / second[key])
            manifest["sessions"][0]["runs"].append(second)
            path.write_text(json.dumps(manifest), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "duplicate run seed"):
                series.summarize_series(path)

    def test_code_section_change_is_rejected_even_with_matching_exe_hash(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            names = ("20261030T131602Z", "20261030T131612Z")
            runs = []
            for stamp in names:
                item = {"trace": f"branch-batch-windows-{stamp}.log",
                        "exe": f"branch-batch-windows-{stamp}.exe"}
                for name in item.values():
                    shutil.copyfile(REPLICATION / "session-1" / name, root / name)
                runs.append(item)
            host = "host-windows-20261030T131525Z.json"
            shutil.copyfile(REPLICATION / "session-1" / host, root / host)
            second_exe = root / runs[1]["exe"]
            data = bytearray(second_exe.read_bytes())
            pe = struct.unpack_from("<I", data, 0x3c)[0]
            table = pe + 24 + struct.unpack_from("<H", data, pe + 20)[0]
            sections = struct.unpack_from("<H", data, pe + 6)[0]
            text = next(table + 40 * i for i in range(sections)
                        if data[table + 40 * i:table + 40 * i + 8].rstrip(b"\0") == b".text")
            offset = struct.unpack_from("<I", data, text + 20)[0]
            data[offset] ^= 1
            second_exe.write_bytes(data)
            import hashlib
            new_hash = hashlib.sha256(data).hexdigest()
            second_log = root / runs[1]["trace"]
            content = second_log.read_text(encoding="utf-8")
            content = content.rsplit("BATCH_BINARY,sha256=", 1)[0] + \
                "BATCH_BINARY,sha256=" + new_hash + "\n"
            second_log.write_text(content, encoding="utf-8")
            path = root / "manifest.json"
            path.write_text(json.dumps({"schema": 1, "sessions": [{
                "id": "session-1", "host": host, "runs": runs,
            }]}), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "EXE .text differs"):
                series.summarize_series(path)

    def test_failed_timer_control_remains_in_summary(self):
        with tempfile.TemporaryDirectory() as temporary:
            path, _ = pilot_manifest(Path(temporary))
            original = series.summarize

            def failing_control(trace):
                analysis = original(trace)
                analysis["timer_control"]["passes"] = False
                return analysis

            with patch.object(series, "summarize", side_effect=failing_control):
                result = series.summarize_series(path)
            self.assertEqual(result["all_runs_descriptive"]["run_count"], 1)
            self.assertEqual(result["all_runs_descriptive"]["timer_control_failed_runs"], 1)
            self.assertFalse(result["sessions"][0]["runs"][0]["timer_control"]["passes"])


if __name__ == "__main__":
    unittest.main()
