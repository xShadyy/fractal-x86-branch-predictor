#!/usr/bin/env python3
"""Check internal consistency of a Windows evidence ZIP without extraction.

The session's file hashes and embedded executable hashes detect mismatches,
but are not an external signature. A successful check does not validate
controls, PE layout or a microarchitectural mechanism.
"""

from __future__ import annotations

import argparse
from collections import Counter
from hashlib import sha256
import json
import ntpath
from pathlib import Path
import re
from zipfile import ZipFile, BadZipFile


BINARY_MARKER = re.compile(rb"(?:^|\n)[A-Z0-9_]+_BINARY,sha256=([a-f0-9]{64})(?:\r?\n|$)")
PASS_STATUS = "validated_trace_pending_binary_audit"


def audit(path: Path) -> dict[str, object]:
    problems: list[str] = []
    checked: dict[str, str] = {}
    try:
        with ZipFile(path) as archive:
            entries = {ntpath.basename(item.filename.rstrip("/")): item.filename
                       for item in archive.infolist() if not item.is_dir()}
            names = [ntpath.basename(item.filename.rstrip("/"))
                     for item in archive.infolist() if not item.is_dir()]
            if len(entries) != len(names):
                raise ValueError("duplicate filenames in evidence ZIP")
            if "session.json" not in entries:
                raise ValueError("session.json is absent")
            session = json.loads(archive.read(entries["session.json"]).decode("utf-8-sig"))
            if not isinstance(session, dict) or session.get("schema") != 1 or \
               not isinstance(session.get("runs"), list):
                raise ValueError("unknown session record")
            if not session["runs"]:
                raise ValueError("empty session record")

            def check(record: object, label: str) -> bytes | None:
                if not isinstance(record, dict):
                    problems.append(f"{label}: malformed file record")
                    return None
                original, expected = record.get("path"), record.get("sha256")
                if not isinstance(original, str) or not isinstance(expected, str) or \
                   not re.fullmatch(r"[a-fA-F0-9]{64}", expected):
                    problems.append(f"{label}: missing path or SHA-256")
                    return None
                name = ntpath.basename(original)
                if name not in entries:
                    problems.append(f"{label}: missing {name}")
                    return None
                if name in checked and checked[name] != expected.lower():
                    problems.append(f"{label}: inconsistent recorded hashes for {name}")
                    return None
                data = archive.read(entries[name])
                if sha256(data).hexdigest() != expected.lower():
                    problems.append(f"{label}: SHA-256 mismatch for {name}")
                    return None
                checked[name] = expected.lower()
                return data

            if session.get("host_snapshot"):
                check(session["host_snapshot"], "host snapshot")
            statuses: Counter[str] = Counter()
            studies: list[str] = []
            for number, run in enumerate(session["runs"]):
                if not isinstance(run, dict) or not isinstance(run.get("study"), str):
                    problems.append(f"run {number}: missing study identity")
                    continue
                study = run["study"]
                studies.append(study)
                statuses[str(run.get("status", "missing"))] += 1
                if run.get("transcript_path"):
                    check({"path": run["transcript_path"],
                           "sha256": run.get("transcript_sha256")}, study + " transcript")
                for field in ("new_artifacts", "traces", "exes", "sidecars"):
                    collection = run.get(field, [])
                    if not isinstance(collection, list):
                        problems.append(f"{study}: malformed {field} array")
                        continue
                    for item in collection:
                        check(item, f"{study} {field}")
                if run.get("disassembly"):
                    check(run["disassembly"], study + " disassembly")
                traces = run.get("traces", [])
                exes = run.get("exes", [])
                if not isinstance(traces, list):
                    traces = []
                if not isinstance(exes, list):
                    exes = []
                if run.get("status") == PASS_STATUS and (len(traces) != 1 or len(exes) != 1):
                    problems.append(f"{study}: successful run lacks a unique trace/EXE pair")
                for trace in traces:
                    if not isinstance(trace, dict):
                        continue
                    trace_data = check(trace, study + " paired trace")
                    paired = [exe for exe in exes if isinstance(exe, dict) and
                              ntpath.splitext(ntpath.basename(str(exe.get("path", ""))))[0] ==
                              ntpath.splitext(ntpath.basename(str(trace.get("path", ""))))[0]]
                    if len(paired) != 1:
                        problems.append(f"{study}: trace has no uniquely paired EXE")
                        continue
                    exe_data = check(paired[0], study + " paired EXE")
                    if trace_data is not None and exe_data is not None:
                        hashes = BINARY_MARKER.findall(trace_data)
                        if len(hashes) > 1 or (hashes and hashes[0].decode() != sha256(exe_data).hexdigest()):
                            problems.append(f"{study}: embedded binary SHA-256 mismatch")
            extra = set(entries) - set(checked) - {"session.json", "session.previous.json"}
            if extra:
                problems.append("unreferenced archive members: " + ", ".join(sorted(extra)))
            return {"integrity_ok": not problems, "problems": problems,
                    "session_git_head": session.get("git_head"),
                    "recorded_runs": len(session["runs"]), "studies": studies,
                    "run_statuses": dict(statuses), "verified_files": len(checked),
                    "validated_runs_pending_pe_audit": statuses[PASS_STATUS],
                    "terminal_record": bool(statuses) and all(
                        s in (PASS_STATUS, "failed_preserved") for s in statuses),
                    "scientific_status": "physical instruction and control audit still required"}
    except (OSError, BadZipFile, json.JSONDecodeError, ValueError,
            TypeError, AttributeError) as exc:
        return {"integrity_ok": False, "problems": [str(exc)],
                "recorded_runs": 0, "verified_files": 0,
                "scientific_status": "unverified archive"}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("zip", type=Path)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    result = audit(args.zip)
    if args.json:
        print(json.dumps(result, sort_keys=True))
    else:
        status = "PASS" if result["integrity_ok"] else "FAIL"
        print(f"Archive integrity: {status}; {result['recorded_runs']} runs; "
              f"{result['verified_files']} SHA-256 verified files")
        for problem in result["problems"]:
            print(f"  {problem}")
        print(f"Scientific status: {result['scientific_status']}")
    return 0 if result["integrity_ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
