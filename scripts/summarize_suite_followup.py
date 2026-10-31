#!/usr/bin/env python3
"""Summarize verified Windows suite ZIPs without extracting or running binaries.

This is a descriptive A/C follow-up ledger. Every attempted study and failed
control stays visible. Within-run bootstrap intervals remain within-run; the
program never turns them into uncertainty across independent days or hosts.
"""

from __future__ import annotations

import argparse
from collections import defaultdict
from datetime import datetime
import json
import ntpath
from pathlib import Path
import re
from statistics import fmean, median
from zipfile import ZipFile

from analyze_decision_source import parse_trace as parse_decision
from analyze_decision_source import summarize as summarize_decision
from analyze_pattern_complexity import parse_trace as parse_pattern
from analyze_pattern_complexity import summarize as summarize_pattern
from audit_suite_evidence import PASS_STATUS, audit
from summarize_branch_batch_series import _host_configuration, _text_digest


STUDIES = {
    "decision_source_a": {
        "prefix": "decision-source-windows-", "parse": parse_decision,
        "summarize": summarize_decision,
        "sources": ("programs/decision_source_windows.c",
                    "programs/decision_source_windows.asm",
                    "scripts/check_decision_source_windows.ps1",
                    "scripts/analyze_decision_source.py"),
    },
    "pattern_complexity": {
        "prefix": "pattern-complexity-windows-", "parse": parse_pattern,
        "summarize": summarize_pattern,
        "sources": ("programs/pattern_complexity_windows.c",
                    "programs/pattern_complexity_windows.asm",
                    "scripts/check_pattern_complexity_windows.ps1",
                    "scripts/analyze_pattern_complexity.py"),
    },
}
STAMP = re.compile(r"^\d{8}T\d{6}Z$")
FOCUS_STUDIES = {
    "cache_controls", "branch_batch", "decision_source_a", "history_probe_b1",
    "pattern_complexity", "history_b2", "history_decay",
    "address_sensitivity", "indirect_cache",
}


def _utc_date(value: str) -> str:
    if not STAMP.fullmatch(value):
        raise ValueError(f"invalid UTC timestamp: {value!r}")
    try:
        return datetime.strptime(value, "%Y%m%dT%H%M%SZ").date().isoformat()
    except ValueError as exc:
        raise ValueError(f"invalid UTC timestamp: {value!r}") from exc


def _entry_name(record: dict[str, object]) -> str:
    return ntpath.basename(str(record["path"]))


def _estimate(run: dict[str, object], key: str) -> float:
    return float(run["estimates"][key]["paired_trimmed_mean_ticks_per_iteration"])


def _description(runs: list[dict[str, object]], keys: tuple[str, ...]) -> dict[str, object]:
    days: dict[str, list[dict[str, object]]] = defaultdict(list)
    for run in runs:
        days[str(run["utc_date"])].append(run)
    return {
        "measured_run_count": len(runs),
        "control_passed_run_count": sum(bool(r["controls_pass"]) for r in runs),
        "control_failed_run_count": sum(not r["controls_pass"] for r in runs),
        "new_primary_eligible_run_count": sum(bool(r["new_primary_eligible"])
                                              for r in runs),
        "distinct_utc_days": len(days),
        "mean_of_all_run_estimates": {
            key: fmean(_estimate(run, key) for run in runs) for key in keys
        },
        "median_of_all_run_estimates": {
            key: median(_estimate(run, key) for run in runs) for key in keys
        },
        "ranges_of_all_run_estimates": {
            key: [min(_estimate(run, key) for run in runs),
                  max(_estimate(run, key) for run in runs)] for key in keys
        },
        "utc_day_descriptions": [{
            "date": day, "run_count": len(selected),
            "control_passed": sum(bool(r["controls_pass"]) for r in selected),
            "new_primary_eligible": sum(bool(r["new_primary_eligible"])
                                        for r in selected),
            "mean_of_run_estimates": {
                key: fmean(_estimate(run, key) for run in selected)
                for key in keys
            },
            "median_of_run_estimates": {
                key: median(_estimate(run, key) for run in selected)
                for key in keys
            },
            "range_of_run_estimates": {
                key: [min(_estimate(run, key) for run in selected),
                      max(_estimate(run, key) for run in selected)]
                for key in keys
            },
        } for day, selected in sorted(days.items())],
        "uncertainty_scope": "run intervals are within-run only; no across-day CI",
    }


def summarize_suite_archives(paths: list[Path]) -> dict[str, object]:
    if not paths:
        raise ValueError("provide at least one suite evidence ZIP")
    sessions: list[dict[str, object]] = []
    study_runs: dict[str, list[dict[str, object]]] = {name: [] for name in STUDIES}
    seen_sessions: set[tuple[str, int]] = set()
    host_configurations: list[dict[str, object]] = []
    warnings: list[str] = []
    for path in paths:
        integrity = audit(path)
        if not integrity["integrity_ok"]:
            raise ValueError(f"{path}: evidence integrity failed: " +
                             "; ".join(integrity["problems"]))
        with ZipFile(path) as archive:
            members = {ntpath.basename(item.filename): item.filename
                       for item in archive.infolist() if not item.is_dir()}
            session = json.loads(archive.read(members["session.json"]).decode("utf-8-sig"))
            session_id = (str(session["started_utc"]), int(session["suite_seed"]))
            if session_id in seen_sessions:
                raise ValueError(f"duplicate suite session {session_id}")
            seen_sessions.add(session_id)
            day = _utc_date(session_id[0])
            host_record = session.get("host_snapshot")
            if not isinstance(host_record, dict):
                raise ValueError(f"{path}: missing host snapshot")
            host = json.loads(archive.read(members[_entry_name(host_record)]).decode("utf-8-sig"))
            host_config = _host_configuration(host)
            host_configurations.append(host_config)
            snapshot_day = _utc_date(host["captured_utc"])
            if snapshot_day != day:
                warnings.append(f"{session_id}: host snapshot and session have different UTC dates")
            files = session.get("source_sha256", {})
            if not isinstance(files, dict):
                raise ValueError(f"{path}: missing source hash ledger")
            record = {
                "archive": str(path), "session_started_utc": session_id[0],
                "suite_seed": session_id[1], "phase": session.get("phase"),
                "study_set": session.get("study_set"),
                "git_head": session.get("git_head"), "utc_date": day,
                "host_configuration": host_config,
                "archive_integrity": integrity,
                "runs": [],
            }
            for item in session["runs"]:
                study = item["study"]
                status = item.get("status")
                attempt = {
                    "study": study, "stage": item.get("stage"),
                    "round": item.get("round"), "position": item.get("position"),
                    "seed": item.get("seed"), "status": status,
                    "error": item.get("error"),
                    "trace_names": [_entry_name(trace) for trace in item.get("traces", [])],
                    "exe_names": [_entry_name(exe) for exe in item.get("exes", [])],
                }
                record["runs"].append(attempt)
                if study not in STUDIES or len(item.get("traces", [])) != 1 or \
                   len(item.get("exes", [])) != 1:
                    continue
                protocol = STUDIES[study]
                trace_record, exe_record = item["traces"][0], item["exes"][0]
                trace_name, exe_name = _entry_name(trace_record), _entry_name(exe_record)
                prefix = protocol["prefix"]
                if not (trace_name.startswith(prefix) and
                        trace_name.endswith(".log") and
                        exe_name == trace_name[:-4] + ".exe"):
                    raise ValueError(f"{path}: {study} has wrong trace/EXE names")
                trace = protocol["parse"](archive.read(members[trace_name]).decode("utf-8-sig"))
                binary = archive.read(members[exe_name])
                analysis = protocol["summarize"](trace)
                stamp = trace.host["run_utc"]
                if trace_name != prefix + stamp + ".log" or \
                   trace.host["windows_build"] != str(host_config["os"][2]):
                    raise ValueError(f"{path}: {study} run timestamp or Windows build differs")
                if int(trace.run["seed"]) != int(item["seed"]):
                    raise ValueError(f"{path}: {study} session/trace seed differs")
                if trace.binary_sha256 != exe_record["sha256"].lower():
                    raise ValueError(f"{path}: {study} trace/EXE hash differs")
                source_hashes = {name: files.get(name) for name in protocol["sources"]}
                if any(value is None for value in source_hashes.values()):
                    warnings.append(f"{session_id}: {study} source hash missing")
                if study == "decision_source_a":
                    estimates = {"primary_interaction":
                                 analysis["contrasts"]["primary_interaction"]}
                    controls = {"timer": analysis["timer_control"],
                                "negative": analysis["negative_controls_within_tolerance"]}
                    new_primary_eligible = bool(analysis["controls_pass"])
                else:
                    estimates = {
                        "p2_minus_p32": analysis["profile"]["p2_minus_p32"]["contrasts"]["adjusted"],
                        "random_minus_p32": analysis["profile"]["random_minus_p32"]["contrasts"]["adjusted"],
                    }
                    controls = {"timer": analysis["timer_control"],
                                "primary_fixed_within_tolerance":
                                analysis["profile"]["p2_minus_p32"]["fixed_within_tolerance"],
                                "primary_branchless_within_tolerance":
                                analysis["profile"]["p2_minus_p32"]["branchless_within_tolerance"],
                                "candidate_random_fixed_within_tolerance":
                                analysis["profile"]["random_minus_p32"]["fixed_within_tolerance"],
                                "candidate_random_branchless_within_tolerance":
                                analysis["profile"]["random_minus_p32"]["branchless_within_tolerance"]}
                    new_primary_eligible = bool(
                        analysis["controls_pass"] and
                        controls["candidate_random_fixed_within_tolerance"] and
                        controls["candidate_random_branchless_within_tolerance"])
                measured = {
                    "session_started_utc": session_id[0], "utc_date": _utc_date(stamp),
                    "phase": session.get("phase"),
                    "study_set": session.get("study_set"),
                    "study": study, "seed": int(trace.run["seed"]),
                    "status": status, "controls_pass": bool(analysis["controls_pass"]),
                    "new_primary_eligible": new_primary_eligible,
                    "source_sha256": source_hashes, "text_sha256": _text_digest(binary),
                    "binary_sha256": trace.binary_sha256,
                    "affinity_cpu": trace.affinity_cpu,
                    "estimates": estimates, "controls": controls,
                }
                if measured["utc_date"] != day:
                    warnings.append(f"{session_id}: {study} run/session UTC dates differ")
                if (status == PASS_STATUS) != measured["controls_pass"]:
                    warnings.append(f"{session_id}: {study} session status and analyzer gate disagree")
                attempt["analysis"] = measured
                study_runs[study].append(measured)
            sessions.append(record)
    def is_focus(item: dict[str, object]) -> bool:
        return item["phase"] == "Followup" and item["study_set"] == "Focus"

    focus_sessions = [session for session in sessions if is_focus(session)]
    focus_configs = [session["host_configuration"] for session in focus_sessions]
    focus_host_stable = bool(focus_configs) and all(
        config == focus_configs[0] for config in focus_configs)
    if focus_configs and not focus_host_stable:
        warnings.append("host configuration changed between Focus sessions")
    summaries: dict[str, object] = {}
    for study, all_runs in study_runs.items():
        runs = [run for run in all_runs if is_focus(run)]
        if not runs:
            summaries[study] = {"measured_run_count": len(all_runs),
                                "pilot_measured_run_count": sum(
                                    r["phase"] == "Pilot" for r in all_runs),
                                "focus_measured_run_count": 0,
                                "distinct_utc_days": 0,
                                "comparable": False,
                                "focus_descriptive_if_comparable": None}
            continue
        seeds = [run["seed"] for run in runs]
        if len(set(seeds)) != len(seeds):
            warnings.append(f"{study}: duplicate run seed")
        source_fingerprints = [run["source_sha256"] for run in runs]
        text_fingerprints = [run["text_sha256"] for run in runs]
        affinities = [run["affinity_cpu"] for run in runs]
        comparable = (all(all(isinstance(v, str) and
                              re.fullmatch(r"[0-9a-fA-F]{64}", v)
                              for v in source.values())
                          for source in source_fingerprints)
                      and all(source_fingerprints[0] == source for source in source_fingerprints)
                      and all(text_fingerprints[0] == text for text in text_fingerprints)
                      and all(affinities[0] == cpu for cpu in affinities)
                      and len(set(seeds)) == len(seeds)
                      and focus_host_stable)
        if not comparable:
            warnings.append(f"{study}: source, executable .text, affinity, host, or seeds changed")
        keys = (("primary_interaction",) if study == "decision_source_a" else
                ("p2_minus_p32", "random_minus_p32"))
        summaries[study] = {
            "measured_run_count": len(all_runs),
            "pilot_measured_run_count": sum(r["phase"] == "Pilot" for r in all_runs),
            "focus_measured_run_count": len(runs), "comparable": comparable,
            "unique_seed_count": len(set(seeds)),
            "distinct_utc_days": len({r["utc_date"] for r in runs}),
            "focus_descriptive_if_comparable": _description(runs, keys) if comparable else None,
            "within_run_intervals_are_not_across_day_intervals": True,
        }
    reasons: list[str] = []
    if len(focus_sessions) < 6:
        reasons.append("fewer than six distinct Focus sessions")
    by_day: dict[str, set[tuple[str, int]]] = defaultdict(set)
    for session in focus_sessions:
        by_day[session["utc_date"]].add((session["session_started_utc"],
                                         session["suite_seed"]))
    if sum(len(ids) >= 3 for ids in by_day.values()) < 2:
        reasons.append("need at least three Focus sessions on each of two UTC days")
    for session in focus_sessions:
        actual = [run["study"] for run in session["runs"]]
        if len(actual) != len(FOCUS_STUDIES) or set(actual) != FOCUS_STUDIES:
            reasons.append(f"{session['session_started_utc']}: Focus study set incomplete or duplicated")
    focus_runs = [run for study in study_runs.values() for run in study
                  if is_focus(run)]
    if len(set(run["seed"] for run in focus_runs)) != len(focus_runs):
        reasons.append("Focus run seeds are not unique across A and C")
    for study in STUDIES:
        current = summaries[study]
        if any(sum(run["study"] == study and "analysis" in run
                   for run in session["runs"]) != 1
               for session in focus_sessions):
            reasons.append(f"{study}: need exactly one measured run in every Focus session")
        if not current["comparable"]:
            reasons.append(f"{study}: frozen source/.text/affinity/host condition failed")
        if any(not run["new_primary_eligible"] or run["status"] != PASS_STATUS
               for run in study_runs[study] if is_focus(run)):
            reasons.append(f"{study}: one or more Focus control gates failed")
    return {
        "schema": 1, "archives": len(paths), "sessions": sessions,
        "studies": summaries, "warnings": warnings,
        "followup_complete": not reasons,
        "followup_completion_reasons": reasons,
        "focus_session_count": len(focus_sessions),
        "focus_sessions_per_utc_day": {day: len(ids) for day, ids in
                                       sorted(by_day.items())},
        "interpretation": "A/C timing summaries only; all attempted runs retained. "
                          "No predictor miss counts, transient-execution, domain-sharing "
                          "or Fractal OS result follows from these values."
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("archives", nargs="+", type=Path)
    parser.add_argument("--output", type=Path, help="write JSON report to a file")
    args = parser.parse_args()
    try:
        result = summarize_suite_archives(args.archives)
    except (OSError, KeyError, TypeError, ValueError) as exc:
        parser.exit(2, f"Invalid follow-up evidence: {exc}\n")
    content = json.dumps(result, sort_keys=True, indent=2) + "\n"
    if args.output:
        args.output.write_text(content, encoding="utf-8")
        print(f"Saved descriptive suite summary: {args.output}")
    else:
        print(content, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
