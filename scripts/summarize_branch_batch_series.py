#!/usr/bin/env python3
"""Audit and describe a Windows branch-batch v2 replication series.

Manifest example (all paths relative to this JSON file):
{"schema":1,"sessions":[{"id":"session-1","host":"session-1/host.json",
 "runs":[{"trace":"session-1/run.log","exe":"session-1/run.exe"}]}]}

Run: python3 scripts/summarize_branch_batch_series.py results/series/manifest.json
The printed JSON contains descriptive run and session estimates, not an
across-run confidence interval. Every listed run, including failed controls,
is retained. A host snapshot must precede its runs by at most two hours.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
from statistics import fmean
import struct

from analyze_branch_batch import parse_trace, summarize, trimmed_mean


MAX_HOST_AGE_SECONDS = 2 * 60 * 60
UTC_STAMP = re.compile(r"\d{8}T\d{6}Z\Z")
CONTRASTS = ("branch", "branch_no_load", "branchless", "adjusted",
             "no_load_adjusted", "load_minus_no_load")


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def _stamp(value: object, label: str) -> datetime:
    _require(isinstance(value, str) and UTC_STAMP.fullmatch(value) is not None,
             f"invalid {label}")
    try:
        return datetime.strptime(value, "%Y%m%dT%H%M%SZ").replace(tzinfo=timezone.utc)
    except ValueError as exc:
        raise ValueError(f"invalid {label}") from exc


def _path(root: Path, value: object, label: str) -> Path:
    _require(isinstance(value, str) and value != "" and
             not Path(value).is_absolute() and "\\" not in value and
             ".." not in Path(value).parts,
             f"{label} must stay under the manifest directory")
    path = root / value
    _require(path.resolve().is_relative_to(root.resolve()),
             f"{label} escapes the manifest directory")
    return path


def _text_digest(data: bytes) -> str:
    """Hash .text's raw section bytes from a bounded PE32+ section table."""
    _require(len(data) >= 0x40 and data[:2] == b"MZ", "invalid PE DOS header")
    pe = struct.unpack_from("<I", data, 0x3c)[0]
    _require(pe + 24 <= len(data) and data[pe:pe + 4] == b"PE\0\0",
             "invalid PE signature")
    sections = struct.unpack_from("<H", data, pe + 6)[0]
    optional_size = struct.unpack_from("<H", data, pe + 20)[0]
    optional = pe + 24
    table = optional + optional_size
    _require(0 < sections <= 96 and optional_size >= 2 and
             table + 40 * sections <= len(data) and
             struct.unpack_from("<H", data, optional)[0] == 0x20b,
             "invalid PE32+ section table")
    matching: list[bytes] = []
    for index in range(sections):
        entry = table + 40 * index
        if data[entry:entry + 8].rstrip(b"\0") != b".text":
            continue
        size, offset = struct.unpack_from("<II", data, entry + 16)
        flags = struct.unpack_from("<I", data, entry + 36)[0]
        _require(size > 0 and offset + size <= len(data) and
                 bool(flags & 0x20000000), "invalid executable .text section")
        matching.append(data[offset:offset + size])
    _require(len(matching) == 1, "expected exactly one executable .text section")
    return hashlib.sha256(matching[0]).hexdigest()


def _host_configuration(host: dict[str, object]) -> dict[str, object]:
    """Compare documented hardware, OS, hypervisor and power settings exactly."""
    def pick(group: str, names: tuple[str, ...]) -> tuple[object, ...]:
        value = host[group]
        _require(isinstance(value, dict), f"invalid host {group}")
        fields = tuple(value[name] for name in names)
        _require(all(field is not None and field != "" for field in fields),
                 f"incomplete host {group}")
        return fields

    config = {
        "os": pick("os", ("Caption", "Version", "BuildNumber", "OSArchitecture")),
        "processor": pick("processor", ("Name", "NumberOfCores",
                                        "NumberOfLogicalProcessors")),
        "baseboard": pick("baseboard", ("Manufacturer", "Product", "Version")),
        "bios": pick("bios", ("Manufacturer", "SMBIOSBIOSVersion", "ReleaseDate")),
        "hypervisor": pick("hypervisor", ("HypervisorPresent",)),
        "active_power_plan": host["active_power_plan"],
    }
    for group in ("os", "baseboard", "bios"):
        _require(all(isinstance(value, str) and value.strip()
                     for value in config[group]), f"invalid host {group}")
    cpu = config["processor"]
    _require(isinstance(cpu[0], str) and cpu[0].strip() and
             all(type(value) is int and value > 0 for value in cpu[1:]),
             "invalid host processor")
    _require(type(config["hypervisor"][0]) is bool, "invalid host hypervisor")
    _require(isinstance(config["active_power_plan"], str) and
             config["active_power_plan"].strip(), "invalid host power plan")
    _require(config["os"][2].isdigit(), "invalid host Windows build")
    return config


def _descriptive(runs: list[dict[str, object]]) -> dict[str, object]:
    estimates = {
        label: [run["contrasts"][label]["paired_trimmed_mean_ticks_per_iteration"]
                for run in runs]
        for label in CONTRASTS
    }
    return {
        "run_count": len(runs),
        "mean_of_run_estimates_ticks_per_iteration": {
            label: fmean(values) for label, values in estimates.items()
        },
        "run_estimate_ranges_ticks_per_iteration": {
            label: [min(values), max(values)] for label, values in estimates.items()
        },
        "timer_control_passed_runs": sum(run["timer_control"]["passes"]
                                         for run in runs),
        "timer_control_failed_runs": sum(not run["timer_control"]["passes"]
                                         for run in runs),
    }


def summarize_series(manifest_path: Path) -> dict[str, object]:
    root = manifest_path.parent
    manifest = json.loads(manifest_path.read_text(encoding="utf-8-sig"))
    _require(isinstance(manifest, dict) and set(manifest) == {"schema", "sessions"}
             and manifest["schema"] == 1 and
             isinstance(manifest["sessions"], list) and manifest["sessions"],
             "invalid series manifest schema")
    seen_sessions: set[str] = set()
    seen_paths: set[Path] = set()
    seen_seeds: set[int] = set()
    configuration: dict[str, object] | None = None
    cpu_identity: tuple[str, ...] | None = None
    site_offsets: tuple[int, int] | None = None
    text_sha256: str | None = None
    sessions: list[dict[str, object]] = []
    all_runs: list[dict[str, object]] = []
    for session in manifest["sessions"]:
        _require(isinstance(session, dict) and set(session) == {"id", "host", "runs"}
                 and isinstance(session["id"], str) and session["id"] and
                 session["id"] not in seen_sessions and
                 isinstance(session["runs"], list) and session["runs"],
                 "invalid or duplicate session")
        seen_sessions.add(session["id"])
        host_path = _path(root, session["host"], "host")
        host = json.loads(host_path.read_text(encoding="utf-8-sig"))
        _require(isinstance(host, dict), "invalid host snapshot")
        captured = _stamp(host["captured_utc"], "host capture timestamp")
        current = _host_configuration(host)
        if configuration is None:
            configuration = current
        else:
            _require(current == configuration,
                     "machine, OS, firmware, hypervisor or power settings changed")
        runs: list[dict[str, object]] = []
        for item in session["runs"]:
            _require(isinstance(item, dict) and set(item) == {"trace", "exe"},
                     "invalid run manifest entry")
            trace_path = _path(root, item["trace"], "trace")
            exe_path = _path(root, item["exe"], "exe")
            for path in (trace_path, exe_path):
                resolved = path.resolve()
                _require(resolved not in seen_paths, "duplicate trace or EXE path")
                seen_paths.add(resolved)
            trace = parse_trace(trace_path.read_text(encoding="utf-8-sig"))
            _require(trace.run["version"] == "2" and trace.host is not None,
                     "series requires complete version 2 traces")
            seed = int(trace.run["seed"])
            _require(seed not in seen_seeds, "duplicate run seed")
            seen_seeds.add(seed)
            started = _stamp(trace.host["run_utc"], "run start timestamp")
            age = (started - captured).total_seconds()
            _require(0 <= age <= MAX_HOST_AGE_SECONDS,
                     "host snapshot must precede the run by at most two hours")
            _require(trace.host["windows_build"] == str(host["os"]["BuildNumber"]),
                     "trace and host Windows builds differ")
            _require(trace.cpu["hypervisor"] ==
                     str(int(host["hypervisor"]["HypervisorPresent"])),
                     "trace and host hypervisor flags differ")
            _require(started.strftime("%Y%m%dT%H%M%SZ") in trace_path.name and
                     started.strftime("%Y%m%dT%H%M%SZ") in exe_path.name,
                     "trace/EXE filename timestamp differs from the run")
            cpu = (trace.cpu["vendor"], trace.cpu["signature"],
                   trace.cpu["invariant_tsc"], trace.cpu["hypervisor"],
                   str(trace.affinity_cpu))
            if cpu_identity is None:
                cpu_identity = cpu
            else:
                _require(cpu == cpu_identity, "trace CPU or affinity changed")
            branch = int(trace.run["branch_addr"], 16)
            offsets = (int(trace.run["branch_no_load_addr"], 16) - branch,
                       int(trace.run["branchless_addr"], 16) - branch)
            if site_offsets is None:
                site_offsets = offsets
            else:
                _require(offsets == site_offsets, "branch site offsets changed")
            binary = exe_path.read_bytes()
            digest = hashlib.sha256(binary).hexdigest()
            _require(digest == trace.binary_sha256, "EXE SHA-256 differs from trace")
            code_digest = _text_digest(binary)
            if text_sha256 is None:
                text_sha256 = code_digest
            else:
                _require(text_sha256 == code_digest, "EXE .text differs across runs")
            analysis = summarize(trace)
            adjusted = [(b["branch_random"] - b["branch_periodic"]) -
                        (b["branchless_random"] - b["branchless_periodic"])
                        for b in trace.blocks]
            run = {
                "trace": item["trace"], "exe": item["exe"],
                "seed": seed, "run_utc": trace.host["run_utc"],
                "host_snapshot_age_minutes": age / 60,
                "binary_sha256": digest, "text_sha256": code_digest,
                "contrasts": analysis["contrasts"],
                "timer_control": analysis["timer_control"],
                "observed_tick_gcd": analysis["observed_tick_gcd"],
                "adjusted_sensitivity_ticks_per_iteration": {
                    "paired_median": analysis["contrasts"]["adjusted"][
                        "paired_median_ticks_per_iteration"],
                    "exploratory_20_percent_trimmed_mean":
                        trimmed_mean(adjusted, 0.20) / int(trace.run["iterations"]),
                },
            }
            runs.append(run)
            all_runs.append(run)
        sessions.append({
            "id": session["id"], "host": session["host"],
            "captured_utc": host["captured_utc"],
            "descriptive": _descriptive(runs), "runs": runs,
        })
    return {
        "schema": 1,
        "interpretation": "Descriptive run-level summaries only; within-run intervals do not measure between-run uncertainty.",
        "machine_configuration": configuration,
        "cpu_identity": cpu_identity,
        "site_offsets_from_loaded_branch": site_offsets,
        "text_sha256": text_sha256,
        "sessions": sessions,
        "all_runs_descriptive": _descriptive(all_runs),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("manifest", type=Path, help="JSON manifest; paths relative to it")
    parser.add_argument("--output", type=Path, help="write JSON to this path instead of stdout")
    args = parser.parse_args()
    try:
        result = summarize_series(args.manifest)
    except (OSError, ValueError, KeyError, TypeError, struct.error,
            json.JSONDecodeError) as exc:
        parser.exit(2, f"Invalid series: {exc}\n")
    payload = json.dumps(result, sort_keys=True, indent=2) + "\n"
    if args.output:
        args.output.write_text(payload, encoding="utf-8")
    else:
        print(payload, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
