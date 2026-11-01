#!/usr/bin/env python3
"""Audit three preselected B2 v4 ZIPs and describe independent run estimates.

No block pooling, across-day interval, or post-hoc success selection is made.
The input is either a session JSON plus its three sibling evidence ZIPs or
the single outer session ZIP produced by check_b2_outcome_replicates_windows.
"""

from __future__ import annotations

import argparse
from datetime import datetime
import hashlib
from io import BytesIO
import json
from pathlib import Path
import re
from statistics import median
from zipfile import BadZipFile, ZipFile

from analyze_b2_outcome import parse_trace, summarize

STUDY = "b2_v4_same_site_replication"
INNER_STUDY = "b2_v4_same_site_outcome"
SHA = re.compile(r"[0-9a-f]{64}\Z")


def _json(data: bytes, label: str) -> dict:
    try:
        value = json.loads(data.decode("utf-8-sig"))
    except (UnicodeError, ValueError) as exc:
        raise ValueError(f"{label}: invalid JSON") from exc
    if not isinstance(value, dict):
        raise ValueError(f"{label}: expected JSON object")
    return value


def _digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _basename(value: str, label: str) -> str:
    if (not isinstance(value, str) or not value or value in (".", "..") or
            "/" in value or "\\" in value or ":" in value):
        raise ValueError(f"unsafe {label} filename")
    return value


def _hex(value: object, label: str) -> str:
    if not isinstance(value, str) or SHA.fullmatch(value) is None:
        raise ValueError(f"invalid {label} SHA256")
    return value


def _text_sha(binary: bytes) -> str:
    if len(binary) < 64:
        raise ValueError("truncated PE")
    offset = int.from_bytes(binary[0x3c:0x40], "little")
    if offset + 24 > len(binary) or binary[offset:offset + 4] != b"PE\0\0":
        raise ValueError("invalid PE signature")
    count = int.from_bytes(binary[offset + 6:offset + 8], "little")
    optional = int.from_bytes(binary[offset + 20:offset + 22], "little")
    table = offset + 24 + optional
    if count < 1 or count > 96 or table + 40 * count > len(binary):
        raise ValueError("invalid PE section table")
    for i in range(count):
        row = binary[table + i * 40:table + (i + 1) * 40]
        if row[:8].rstrip(b"\0") == b".text":
            size = int.from_bytes(row[16:20], "little")
            start = int.from_bytes(row[20:24], "little")
            if not size or start + size > len(binary):
                raise ValueError("invalid PE .text bounds")
            return _digest(binary[start:start + size])
    raise ValueError("PE .text section absent")


def _members(archive: ZipFile, label: str) -> dict[str, bytes]:
    names = archive.namelist()
    if len(names) != len(set(names)) or any(
        _basename(name, label) != name for name in names
    ):
        raise ValueError(f"{label}: duplicate or unsafe ZIP entry")
    corrupt = archive.testzip()
    if corrupt:
        raise ValueError(f"{label}: corrupt ZIP member {corrupt}")
    return {name: archive.read(name) for name in names}


def audit_inner(data: bytes, seed: int, git_head: str) -> dict:
    try:
        with ZipFile(BytesIO(data)) as zip_file:
            files = _members(zip_file, "run ZIP")
    except (OSError, BadZipFile) as exc:
        raise ValueError("invalid run ZIP") from exc
    manifests = [name for name in files if name.endswith(".manifest.json")]
    builds = [name for name in files if name.endswith(".build.json")]
    if len(manifests) != 1 or len(builds) != 1:
        raise ValueError("run ZIP requires one manifest and one build sidecar")
    manifest = _json(files[manifests[0]], "run manifest")
    base = manifests[0][:-len(".manifest.json")]
    if builds[0] != base + ".build.json":
        raise ValueError("run build and manifest stems differ")
    declared = manifest.get("files_sha256")
    if (manifest.get("study") != INNER_STUDY or not isinstance(declared, dict) or
            set(files) != set(declared) | set(manifests)):
        raise ValueError("run ZIP manifest membership/study mismatch")
    for name, expected in declared.items():
        if _basename(name, "run member") != name or _digest(files[name]) != _hex(expected, name):
            raise ValueError(f"run ZIP member hash mismatch: {name}")
    build = _json(files[builds[0]], "run build")
    if (build.get("study") != INNER_STUDY or build.get("seed") != seed or
            manifest.get("build_runtime_status") != build.get("build_runtime_status") or
            manifest.get("control_status") != build.get("control_status")):
        raise ValueError("run seed, revision, or state mismatch")
    status = build.get("build_runtime_status")
    row = {"seed": seed, "run_name": base, "build_runtime_status": status,
           "control_status": build.get("control_status"),
           "source_sha256": build.get("source_sha256"),
           "text_section_sha256": build.get("text_section_sha256")}
    if status != "analyzed":
        row["eligible"] = False
        row["diagnostic"] = build.get("failure", "incomplete run")
        row["git_head_recorded"] = build.get("git_head")
        row["git_clean_recorded"] = build.get("git_clean")
        return row
    if (build.get("git_head") != git_head or build.get("git_clean") is not True or
            manifest.get("git_head") != git_head or manifest.get("git_clean") is not True):
        raise ValueError("analyzed run revision or clean state mismatch")
    names = {ext: base + ext for ext in
             (".exe", ".log", ".analysis.json", ".strict.log")}
    if any(name not in files for name in names.values()):
        raise ValueError("analyzed run lacks executable, trace, or analysis")
    binary = files[names[".exe"]]
    binary_sha = _digest(binary)
    if binary_sha != build.get("binary_sha256") or _text_sha(binary) != build.get("text_section_sha256"):
        raise ValueError("run executable or PE text hash mismatch")
    try:
        trace = parse_trace(files[names[".log"]].decode("ascii"))
    except (UnicodeError, ValueError) as exc:
        raise ValueError(f"run trace invalid: {exc}") from exc
    if trace.binary_sha256 != binary_sha or int(trace.run["seed"]) != seed:
        raise ValueError("run trace binary or seed mismatch")
    expected = {"cpu": trace.cpu, "run": trace.run, "host": trace.host,
                "binary_sha256": trace.binary_sha256,
                "affinity_cpu": trace.affinity_cpu, **summarize(trace)}
    # The analyzer writes JSON arrays from Python tuples. Normalize this
    # representation before comparing the archived JSON object.
    expected = json.loads(json.dumps(expected))
    archived = _json(files[names[".analysis.json"]], "run analysis")
    if archived != expected:
        raise ValueError("run analysis does not replay from trace")
    controls = expected["apparatus_controls_pass"]
    if (build.get("control_status") != ("passed" if controls else "inconclusive") or
            build.get("strict_analyzer_exit_code") != (0 if controls else 1) or
            build.get("primary_practical_association") != expected["primary_practical_association"] or
            build.get("primary_direction") != expected["primary_direction"]):
        raise ValueError("run control/strict/practical verdict mismatch")
    f_values = {name: {"point": outcome["F"]["paired_trimmed_mean_ticks_per_probe"],
                       "within_run_95": outcome["F"]["within_run_cycle_bootstrap_95_ticks_per_probe"]}
                for name, outcome in expected["outcomes"].items()}
    row.update({"eligible": bool(controls), "utc_date": datetime.strptime(
        trace.host["run_utc"], "%Y%m%dT%H%M%SZ").date().isoformat(),
        "cpu": trace.cpu, "windows_build": trace.host["windows_build"],
        "affinity_cpu": trace.affinity_cpu, "binary_sha256": binary_sha,
        "outcome_F_ticks_per_episode": f_values,
        "primary_practical_association": expected["primary_practical_association"],
        "primary_direction": expected["primary_direction"]})
    return row


def summarize_session(session: dict, archives: dict[str, bytes],
                      transcripts: dict[str, bytes]) -> dict:
    if session.get("schema") != 1 or session.get("study") != STUDY:
        raise ValueError("invalid session schema or study")
    seeds = session.get("preselected_seeds")
    attempts = session.get("attempts")
    if (not isinstance(seeds, list) or len(seeds) != 3 or
            any(type(x) is not int or x < 1 or x > 0xffffffff for x in seeds) or
            len(set(seeds)) != 3 or not isinstance(attempts, list) or
            len(attempts) != 3 or
            not isinstance(session.get("git_head"), str) or
            re.fullmatch(r"[0-9a-f]{40}", session["git_head"]) is None or
            session.get("git_clean") is not True):
        raise ValueError("invalid or incomplete three-seed preselection")
    rows = []
    for ordinal, (seed, attempt) in enumerate(zip(seeds, attempts), 1):
        if (not isinstance(attempt, dict) or attempt.get("ordinal") != ordinal or
                attempt.get("seed") != seed or type(attempt.get("exit_code")) is not int):
            raise ValueError("attempt order, seed, or exit code mismatch")
        transcript = _basename(attempt.get("transcript"), "transcript")
        if transcript not in transcripts or _digest(transcripts[transcript]) != _hex(
                attempt.get("transcript_sha256"), "transcript"):
            raise ValueError("missing or modified attempt transcript")
        name = attempt.get("archive")
        if name is None:
            if attempt.get("archive_sha256") is not None:
                raise ValueError("archive hash without archive")
            rows.append({"ordinal": ordinal, "seed": seed, "exit_code": attempt["exit_code"],
                         "eligible": False, "diagnostic": "no evidence ZIP produced"})
            continue
        name = _basename(name, "run archive")
        if name not in archives or _digest(archives[name]) != _hex(
                attempt.get("archive_sha256"), "run archive"):
            raise ValueError("missing or modified run evidence ZIP")
        row = audit_inner(archives[name], seed, session["git_head"])
        if row["eligible"] and attempt["exit_code"] != 0:
            raise ValueError("passing run had nonzero runner exit")
        if row["build_runtime_status"] != "analyzed" and attempt["exit_code"] == 0:
            raise ValueError("incomplete run had zero runner exit")
        if row["control_status"] == "inconclusive" and attempt["exit_code"] == 0:
            raise ValueError("failed-control run had zero runner exit")
        row.update({"ordinal": ordinal, "exit_code": attempt["exit_code"],
                    "archive": name, "archive_sha256": attempt["archive_sha256"]})
        rows.append(row)
    complete = [row for row in rows if "outcome_F_ticks_per_episode" in row]
    eligible = [row for row in complete if row["eligible"]]
    text_hashes = {row["text_section_sha256"] for row in complete}
    sources = {json.dumps(row["source_sha256"], sort_keys=True) for row in complete}
    dates = {row["utc_date"] for row in complete}
    host = {(row["cpu"]["vendor"], row["cpu"]["signature"], row["cpu"]["hypervisor"],
             row["windows_build"], row["affinity_cpu"]) for row in complete}
    primary_points = [row["outcome_F_ticks_per_episode"]["p0_n1"]["point"]
                      for row in eligible]
    return {"schema": 1, "study": STUDY, "git_head": session["git_head"],
            "preselected_seeds": seeds, "attempt_count": 3, "runs": rows,
            "analyzed_run_count": len(complete), "control_passed_run_count": len(eligible),
            "primary_practical_association_count": sum(
                row["primary_practical_association"] is True for row in eligible),
            "same_text_section": len(text_hashes) == 1 if len(complete) >= 2 else None,
            "same_source_hashes": len(sources) == 1 if len(complete) >= 2 else None,
            "same_host_configuration": len(host) == 1 if len(complete) >= 2 else None,
            "single_utc_date": len(dates) == 1 if len(complete) >= 2 else None,
            "eligible_primary_point_median": median(primary_points) if primary_points else None,
            "eligible_primary_point_range": [min(primary_points), max(primary_points)]
            if primary_points else None,
            "uncertainty_scope": "Run intervals are within-run only. No pooled-block or across-run CI. "
                                 "One UTC date cannot establish day-to-day robustness."}


def summarize_files(session_path: Path) -> dict:
    session = _json(session_path.read_bytes(), "session")
    archives, transcripts = {}, {}
    for attempt in session.get("attempts", []):
        for field, target in (("archive", archives), ("transcript", transcripts)):
            if isinstance(attempt, dict) and attempt.get(field) is not None:
                name = _basename(attempt[field], field)
                target[name] = (session_path.parent / name).read_bytes()
    return summarize_session(session, archives, transcripts)


def summarize_outer(path: Path) -> dict:
    try:
        with ZipFile(path) as archive:
            files = _members(archive, "session ZIP")
    except BadZipFile as exc:
        raise ValueError("invalid session ZIP") from exc
    sessions = [name for name in files if name.endswith(".session.json")]
    manifests = [name for name in files if name.endswith(".manifest.json")]
    if len(sessions) != 1 or len(manifests) != 1:
        raise ValueError("session ZIP needs one session and one manifest")
    manifest = _json(files[manifests[0]], "session manifest")
    declared = manifest.get("files_sha256")
    if (manifest.get("study") != STUDY or not isinstance(declared, dict) or
            set(files) != set(declared) | set(manifests)):
        raise ValueError("session ZIP manifest membership mismatch")
    for name, expected in declared.items():
        if _digest(files[name]) != _hex(expected, name):
            raise ValueError(f"session ZIP member hash mismatch: {name}")
    session = _json(files[sessions[0]], "session")
    if manifest.get("git_head") != session.get("git_head"):
        raise ValueError("session ZIP revision mismatch")
    result = summarize_session(session,
                               {name: data for name, data in files.items() if name.endswith(".zip")},
                               {name: data for name, data in files.items() if name.endswith(".transcript.log")})
    summaries = [name for name in files if name.endswith(".summary.json")]
    if len(summaries) == 1 and _json(files[summaries[0]], "summary") != result:
        raise ValueError("archived session summary does not replay")
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path, help="session.json or completed outer ZIP")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    try:
        result = (summarize_outer(args.input) if args.input.suffix.lower() == ".zip"
                  else summarize_files(args.input))
    except (OSError, ValueError) as exc:
        parser.exit(2, f"Invalid B2 replication: {exc}\n")
    if args.json:
        print(json.dumps(result, sort_keys=True))
    else:
        print(f"B2 v4 replication: {result['analyzed_run_count']}/3 analyzed, "
              f"{result['control_passed_run_count']}/3 controls pass")
        for row in result["runs"]:
            if "outcome_F_ticks_per_episode" in row:
                value = row["outcome_F_ticks_per_episode"]["p0_n1"]
                print(f"seed {row['seed']}: F_p0_n1 {value['point']:+.3f} "
                      f"{value['within_run_95']}; controls {row['control_status']}")
            else:
                print(f"seed {row['seed']}: {row['diagnostic']}")
        print(result["uncertainty_scope"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
