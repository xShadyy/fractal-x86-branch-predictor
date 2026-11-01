#!/usr/bin/env python3
"""Read-only triage of failed runs in a canonical Windows suite evidence ZIP.

This classifies *why the recorded run could not be accepted*, not whether a
microarchitectural hypothesis is true. The archive must first pass the suite
integrity auditor; only archived traces are replayed, never archived binaries.
"""

from __future__ import annotations

import argparse
from collections import Counter
import json
import ntpath
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory
from zipfile import ZipFile

from audit_suite_evidence import audit


ANALYZERS = {
    "history_b2": "analyze_history_b2.py",
    "address_sensitivity": "analyze_address_sensitivity.py",
    "branch_batch": "analyze_branch_batch.py",
}
SCRIPT_DIR = Path(__file__).resolve().parent


class IncompleteAnalyzerResult(ValueError):
    """The analyzer returned JSON without a consistent declared control gate."""


def _boolean(value: object, label: str) -> bool:
    if type(value) is not bool:
        raise IncompleteAnalyzerResult(f"missing or non-boolean gate {label}")
    return value


def _object(value: object, label: str) -> dict:
    if not isinstance(value, dict):
        raise IncompleteAnalyzerResult(f"missing object {label}")
    return value


def failed_control_gates(study: str, result: dict) -> list[str]:
    """Compare each declared overall gate to its concrete constituent gates."""
    gates: dict[str, bool] = {}
    if study == "history_b2":
        controls = _object(result.get("controls"), "controls")
        for suffix in ("p0_n1", "p1_n1", "p0_n16", "p1_n16"):
            control = _object(controls.get(suffix), f"controls.{suffix}")
            for name in ("pause", "small", "fixed_neutral"):
                detail = _object(control.get(name), f"controls.{suffix}.{name}")
                label = f"{suffix}.{name}"
                gates[label] = _boolean(detail.get("passes"), label)
        overall = _boolean(result.get("statistical_control_gates_pass"),
                           "statistical_control_gates_pass")
    elif study == "address_sensitivity":
        controls = _object(result.get("timer_controls"), "timer_controls")
        timer: dict[str, bool] = {}
        for suffix in ("p0", "p1"):
            control = _object(controls.get(suffix), f"timer_controls.{suffix}")
            for name in ("small_pass", "pause_pass"):
                label = f"timer_controls.{suffix}.{name}"
                timer[label] = _boolean(control.get(name), label)
        fixed = _object(result.get("fixed_within_tolerance"),
                        "fixed_within_tolerance")
        fixed_gates: dict[str, bool] = {}
        for suffix in (f"{site}_p{probe}"
                       for site in ("target", "same4k", "offset128")
                       for probe in (0, 1)):
            label = f"fixed_within_tolerance.{suffix}"
            fixed_gates[label] = _boolean(fixed.get(suffix), label)
        timer_overall = _boolean(result.get("timer_controls_pass"),
                                 "timer_controls_pass")
        fixed_overall = _boolean(result.get("fixed_all_within_tolerance"),
                                 "fixed_all_within_tolerance")
        if timer_overall != all(timer.values()) or fixed_overall != all(fixed_gates.values()):
            raise IncompleteAnalyzerResult("overall and detailed gates disagree")
        gates.update(timer)
        gates.update(fixed_gates)
        overall = timer_overall and fixed_overall
    elif study == "branch_batch":
        control = _object(result.get("timer_control"), "timer_control")
        gates["timer_control.passes"] = _boolean(control.get("passes"),
                                                  "timer_control.passes")
        overall = gates["timer_control.passes"]
    else:
        raise IncompleteAnalyzerResult(f"unsupported study {study}")

    if overall != all(gates.values()):
        raise IncompleteAnalyzerResult("overall and detailed gates disagree")
    return [label for label, passes in gates.items() if not passes]


def _pair(run: dict) -> tuple[str | None, str | None]:
    traces, exes = run.get("traces", []), run.get("exes", [])
    if not isinstance(traces, list) or not isinstance(exes, list) or \
       len(traces) != 1 or len(exes) != 1 or \
       not isinstance(traces[0], dict) or not isinstance(exes[0], dict):
        return None, None
    trace, exe = traces[0].get("path"), exes[0].get("path")
    if not isinstance(trace, str) or not isinstance(exe, str):
        return None, None
    trace_name, exe_name = ntpath.basename(trace), ntpath.basename(exe)
    if ntpath.splitext(trace_name)[0] != ntpath.splitext(exe_name)[0] or \
       ntpath.splitext(trace_name)[1].lower() != ".log" or \
       ntpath.splitext(exe_name)[1].lower() != ".exe":
        return None, None
    return trace_name, exe_name


def classify_archive(path: Path) -> dict:
    """Verify the ZIP and replay supported failed traces without writing results."""
    inspection = audit(path)
    answer: dict = {
        "schema": 1,
        "archive": str(path),
        "archive_integrity_ok": inspection["integrity_ok"],
        "audit_problems": inspection["problems"],
        "recorded_runs": inspection["recorded_runs"],
        "failed_runs": [],
        "category_counts": {},
        "scientific_status": "failure triage only; no mechanism or replication claim",
    }
    if not inspection["integrity_ok"]:
        return answer

    with ZipFile(path) as archive, TemporaryDirectory(prefix="suite-failures-") as folder:
        entries = {ntpath.basename(item.filename.rstrip("/")): item.filename
                   for item in archive.infolist() if not item.is_dir()}
        session = json.loads(archive.read(entries["session.json"]).decode("utf-8-sig"))
        for index, run in enumerate(session["runs"]):
            if run.get("status") != "failed_preserved":
                continue
            study = run["study"]
            entry = {"index": index, "study": study,
                     "stage": run.get("stage"), "round": run.get("round"),
                     "position": run.get("position"),
                     "status": run["status"], "error": run.get("error"),
                     "category": "", "failed_gates": []}
            answer["failed_runs"].append(entry)
            if study not in ANALYZERS:
                entry["category"] = "unsupported_study"
                continue
            trace_name, exe_name = _pair(run)
            if trace_name is None or trace_name not in entries or exe_name not in entries:
                entry["category"] = "missing_build_or_run_pair"
                continue
            entry["trace"] = trace_name
            entry["executable"] = exe_name
            # A temporary copy is the only write. Neither the ZIP nor its EXE
            # is modified or executed, and the copy disappears on return.
            trace_path = Path(folder) / f"{index}-{trace_name}"
            trace_path.write_bytes(archive.read(entries[trace_name]))
            command = [sys.executable, str(SCRIPT_DIR / ANALYZERS[study]),
                       str(trace_path), "--json"]  # Deliberately no --strict.
            try:
                replay = subprocess.run(command, text=True, capture_output=True,
                                        timeout=180, check=False)
            except (OSError, subprocess.TimeoutExpired) as exc:
                entry["category"] = "analyzer_replay_requires_review"
                entry["replay_error"] = str(exc)
                continue
            if replay.returncode != 0:
                if replay.returncode == 2 and replay.stderr.startswith("Invalid "):
                    entry["category"] = "invalid_trace"
                else:
                    entry["category"] = "analyzer_replay_requires_review"
                entry["replay_error"] = replay.stderr.strip()[:1000]
                continue
            try:
                result = json.loads(replay.stdout)
                if not isinstance(result, dict):
                    raise IncompleteAnalyzerResult("analyzer returned non-object JSON")
                failures = failed_control_gates(study, result)
            except (json.JSONDecodeError, IncompleteAnalyzerResult) as exc:
                entry["category"] = "analyzer_result_requires_review"
                entry["replay_error"] = str(exc)
                continue
            entry["failed_gates"] = failures
            entry["category"] = ("completed_control_inconclusive" if failures else
                                 "inconsistent_record_requires_review")
    answer["category_counts"] = dict(Counter(run["category"]
                                             for run in answer["failed_runs"]))
    return answer


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("zip", type=Path, help="canonical suite evidence ZIP")
    parser.add_argument("--json", action="store_true", help="machine-readable result")
    args = parser.parse_args()
    result = classify_archive(args.zip)
    if args.json:
        print(json.dumps(result, sort_keys=True))
    elif not result["archive_integrity_ok"]:
        print("Archive integrity: FAIL")
        for problem in result["audit_problems"]:
            print(f"  {problem}")
    else:
        print(f"Archive integrity: PASS; {result['recorded_runs']} recorded runs; "
              f"{len(result['failed_runs'])} failed runs classified")
        for run in result["failed_runs"]:
            gates = ", ".join(run["failed_gates"])
            print(f"  #{run['index']} {run['study']}: {run['category']}" +
                  (f" [{gates}]" if gates else ""))
        print(f"Scientific status: {result['scientific_status']}")
    return 0 if result["archive_integrity_ok"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
