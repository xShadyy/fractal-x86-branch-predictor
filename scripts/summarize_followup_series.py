#!/usr/bin/env python3
"""Validate and summarize the Windows decision-source and history series.

Manifest paths are relative to the JSON file. Example:
{"schema":1,"sessions":[{"id":"day-1","host":"day-1/host.json",
 "runs":[{"study":"decision_source","trace":"day-1/decision-source.log",
          "exe":"day-1/decision-source.exe"}]}]}

All supplied runs remain in the output, including runs with failed controls.
Reported intervals come from the individual run analyzers. Means across runs
and sessions are descriptive; they do not create an across-day confidence interval.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from statistics import fmean
import struct

from analyze_branch_batch import trimmed_mean
from analyze_decision_source import parse_trace as parse_decision
from analyze_decision_source import summarize as summarize_decision
from analyze_history_probe import parse_trace as parse_history
from analyze_history_probe import summarize as summarize_history
from summarize_branch_batch_series import (
    MAX_HOST_AGE_SECONDS, _host_configuration, _path, _require, _stamp,
    _text_digest,
)


STUDIES = {
    "decision_source": ("decision-source-windows-", parse_decision,
                        summarize_decision, "branchless_addr"),
    "history_probe": ("history-probe-windows-", parse_history,
                      summarize_history, "sham_addr"),
}


def _estimate(run: dict[str, object], label: str) -> float:
    contrast = run["contrasts"][label]
    unit = ("paired_trimmed_mean_ticks_per_iteration" if
            run["study"] == "decision_source" else
            "paired_trimmed_mean_ticks_per_probe")
    return contrast[unit]


def _descriptive(runs: list[dict[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for study, keys in (("decision_source", ("primary_interaction",)),
                        ("history_probe", ("adjusted0", "adjusted1"))):
        selected = [run for run in runs if run["study"] == study]
        if not selected:
            continue
        values = {label: [_estimate(run, label) for run in selected]
                  for label in keys}
        result[study] = {
            "run_count": len(selected),
            "mean_of_run_estimates": {
                key: fmean(numbers) for key, numbers in values.items()
            },
            "run_estimate_ranges": {
                key: [min(numbers), max(numbers)]
                for key, numbers in values.items()
            },
            "predeclared_control_gate_passed_runs": sum(
                bool(run["control_gate_passes"]) for run in selected),
            "predeclared_control_gate_failed_runs": sum(
                not run["control_gate_passes"] for run in selected),
            "control_gate": ("timer and three practical negative controls"
                             if study == "decision_source" else "timer only"),
            "units": ("TSC ticks per iteration" if study == "decision_source"
                      else "TSC ticks per fixed 16-call probe"),
        }
    return result


def _sensitivity(study: str, trace: object) -> dict[str, float]:
    blocks = trace.blocks
    if study == "decision_source":
        differences = [
            (b["live_random"] - b["live_periodic"]) -
            (b["fixed_random"] - b["fixed_periodic"])
            for b in blocks
        ]
        return {"exploratory_20_percent_trim_primary_ticks_per_iteration":
                trimmed_mean(differences, 0.20) / int(trace.run["iterations"])}
    zero = [
        (b["b_t1_p0"] - b["b_t0_p0"]) -
        (b["s_t1_p0"] - b["s_t0_p0"])
        for b in blocks
    ]
    one = [
        (b["b_t0_p1"] - b["b_t1_p1"]) -
        (b["s_t0_p1"] - b["s_t1_p1"])
        for b in blocks
    ]
    return {
        "exploratory_20_percent_trim_adjusted0_ticks_per_probe":
            trimmed_mean(zero, 0.20) / int(trace.run["episodes"]),
        "exploratory_20_percent_trim_adjusted1_ticks_per_probe":
            trimmed_mean(one, 0.20) / int(trace.run["episodes"]),
    }


def summarize_series(manifest_path: Path) -> dict[str, object]:
    root = manifest_path.parent
    manifest = json.loads(manifest_path.read_text(encoding="utf-8-sig"))
    _require(isinstance(manifest, dict) and set(manifest) == {"schema", "sessions"}
             and type(manifest["schema"]) is int and manifest["schema"] == 1
             and isinstance(manifest["sessions"], list) and manifest["sessions"],
             "invalid follow-up series manifest")
    seen_sessions: set[str] = set()
    seen_files: set[Path] = set()
    seen_seeds: set[int] = set()
    seen_starts: set[str] = set()
    expected_code: dict[str, str] = {}
    expected_offsets: dict[str, int] = {}
    cpu_identity: tuple[str, ...] | None = None
    host_config: dict[str, object] | None = None
    sessions: list[dict[str, object]] = []
    all_runs: list[dict[str, object]] = []
    for session in manifest["sessions"]:
        _require(isinstance(session, dict) and set(session) == {"id", "host", "runs"}
                 and isinstance(session["id"], str) and session["id"]
                 and session["id"] not in seen_sessions
                 and isinstance(session["runs"], list) and session["runs"],
                 "invalid or duplicate session")
        seen_sessions.add(session["id"])
        host_path = _path(root, session["host"], "host")
        _require(host_path.resolve() not in seen_files,
                 "duplicate host or run path")
        seen_files.add(host_path.resolve())
        host = json.loads(host_path.read_text(encoding="utf-8-sig"))
        _require(isinstance(host, dict), "invalid host snapshot")
        capture = _stamp(host["captured_utc"], "host capture timestamp")
        config = _host_configuration(host)
        if host_config is None:
            host_config = config
        else:
            _require(config == host_config,
                     "machine, OS, firmware, hypervisor or power settings changed")
        runs: list[dict[str, object]] = []
        for item in session["runs"]:
            _require(isinstance(item, dict) and
                     set(item) == {"study", "trace", "exe"} and
                     item["study"] in STUDIES,
                     "invalid run manifest entry")
            study = item["study"]
            prefix, parse, summarize, other_site = STUDIES[study]
            trace_path = _path(root, item["trace"], "trace")
            exe_path = _path(root, item["exe"], "exe")
            _require(trace_path.name.startswith(prefix) and
                     trace_path.name.endswith(".log") and
                     exe_path.name.startswith(prefix) and
                     exe_path.name.endswith(".exe"),
                     "study, trace and EXE names do not match")
            _require(trace_path.parent.resolve() == host_path.parent.resolve()
                     and exe_path.parent.resolve() == host_path.parent.resolve(),
                     "run files and host must be in the same session directory")
            for path in (trace_path, exe_path):
                _require(path.resolve() not in seen_files,
                         "duplicate host, trace or EXE path")
                seen_files.add(path.resolve())
            trace = parse(trace_path.read_text(encoding="utf-8-sig"))
            seed = int(trace.run["seed"])
            _require(seed not in seen_seeds, "duplicate run seed")
            seen_seeds.add(seed)
            started = _stamp(trace.host["run_utc"], "run start timestamp")
            stamp = trace.host["run_utc"]
            _require(stamp not in seen_starts, "duplicate run timestamp")
            seen_starts.add(stamp)
            age = (started - capture).total_seconds()
            _require(0 <= age <= MAX_HOST_AGE_SECONDS,
                     "host snapshot must precede each run by at most two hours")
            _require(trace_path.stem == prefix + stamp and
                     exe_path.stem == prefix + stamp,
                     "trace/EXE filename timestamp differs from recorded start")
            _require(trace.host["windows_build"] == str(config["os"][2]),
                     "trace and host Windows builds differ")
            _require(trace.cpu["hypervisor"] ==
                     str(int(config["hypervisor"][0])),
                     "trace and host hypervisor flags differ")
            identity = (trace.cpu["vendor"], trace.cpu["signature"],
                        trace.cpu["invariant_tsc"], trace.cpu["hypervisor"],
                        str(trace.affinity_cpu))
            if cpu_identity is None:
                cpu_identity = identity
            else:
                _require(identity == cpu_identity,
                         "trace CPU or affinity changed")
            branch = int(trace.run["branch_addr"], 16)
            offset = int(trace.run[other_site], 16) - branch
            if study not in expected_offsets:
                expected_offsets[study] = offset
            else:
                _require(offset == expected_offsets[study],
                         f"{study} branch site offset changed")
            binary = exe_path.read_bytes()
            digest = hashlib.sha256(binary).hexdigest()
            _require(digest == trace.binary_sha256,
                     f"{study} EXE SHA-256 differs from trace")
            code_digest = _text_digest(binary)
            if study not in expected_code:
                expected_code[study] = code_digest
            else:
                _require(code_digest == expected_code[study],
                         f"{study} EXE .text differs across runs")
            analysis = summarize(trace)
            controls = (analysis["controls_pass"] if study == "decision_source"
                        else analysis["timer_control"]["passes"])
            run = {
                "study": study, "trace": item["trace"], "exe": item["exe"],
                "seed": seed, "run_utc": stamp,
                "host_snapshot_age_minutes": age / 60,
                "binary_sha256": digest, "text_sha256": code_digest,
                "contrasts": analysis["contrasts"],
                "timer_control": analysis["timer_control"],
                "control_gate_passes": controls,
                "negative_controls_within_tolerance": analysis.get(
                    "negative_controls_within_tolerance"),
                "observed_tick_gcd": analysis["observed_tick_gcd"],
                "sensitivity": _sensitivity(study, trace),
            }
            runs.append(run)
            all_runs.append(run)
        # Detect omitted files in the archive directory; this does not prove
        # that the user never ran additional experiments elsewhere.
        listed = {(_path(root, item[key], key)).resolve()
                  for item in session["runs"] for key in ("trace", "exe")}
        present = {path.resolve() for prefix in ("decision-source-windows-",
                                                 "history-probe-windows-")
                   for suffix in (".log", ".exe")
                   for path in host_path.parent.glob(prefix + "*" + suffix)}
        _require(present == listed,
                 "unlisted or missing trace/EXE in session directory")
        _require(len(listed) == 2 * len(session["runs"]),
                 "duplicate trace/EXE in session")
        order = [{"study": run["study"], "run_utc": run["run_utc"]}
                 for run in sorted(runs, key=lambda run: run["run_utc"])]
        sessions.append({
            "id": session["id"], "host": session["host"],
            "captured_utc": host["captured_utc"],
            "utc_date": capture.date().isoformat(),
            "recorded_run_order": order,
            "descriptive": _descriptive(runs), "runs": runs,
        })
    return {
        "schema": 1,
        "interpretation": ("Run-level estimates; bootstrap intervals are within each "
                           "run, and means across runs/sessions are descriptive."),
        "machine_configuration": host_config,
        "cpu_identity": cpu_identity,
        "site_offsets_from_branch_entry": expected_offsets,
        "text_sha256_by_study": expected_code,
        "sessions_on_distinct_utc_dates": len({s["utc_date"] for s in sessions})
                                         == len(sessions),
        "sessions": sessions,
        "all_runs_descriptive": _descriptive(all_runs),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("manifest", type=Path,
                        help="JSON manifest with paths relative to itself")
    parser.add_argument("--output", type=Path,
                        help="write summary JSON instead of printing it")
    args = parser.parse_args()
    try:
        result = summarize_series(args.manifest)
    except (OSError, ValueError, KeyError, TypeError, struct.error,
            json.JSONDecodeError, UnicodeDecodeError) as exc:
        parser.exit(2, f"Invalid follow-up series: {exc}\n")
    payload = json.dumps(result, sort_keys=True, indent=2) + "\n"
    if args.output:
        args.output.write_text(payload, encoding="utf-8")
    else:
        print(payload, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
