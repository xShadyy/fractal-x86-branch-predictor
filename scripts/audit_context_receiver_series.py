#!/usr/bin/env python3
"""Audit the K4 Windows pilot and the three sessions selected in chat.

The count and seeds were specified after the pilot, before follow-up collection.
This script records repeated per-run signatures, not a new pooled test or a
proof of transient execution. Archived executables and source are never run.
"""
from __future__ import annotations

import argparse
import csv
from io import StringIO
import json
from pathlib import Path
import random
import struct
import tempfile
from zipfile import BadZipFile

import analyze_context_receiver as k4
from audit_fresh_receiver_archive import check_disassembly, digest, json_bytes, members

PILOT_SEED = 888890949
SESSION_SEEDS = (830217184, 4108945320, 3039835034)
SOURCE_REVISION = "ee8422ffe6d466c4f51b1b550224ac63e30c96b4"


def text_section_hash(image: bytes) -> str:
    pe = struct.unpack_from("<I", image, 0x3c)[0]
    optional_size = struct.unpack_from("<H", image, pe+20)[0]
    section_count = struct.unpack_from("<H", image, pe+6)[0]
    for i in range(section_count):
        offset = pe+24+optional_size+40*i
        if image[offset:offset+8].rstrip(b"\0") == b".text":
            size, start = struct.unpack_from("<II", image, offset+16)
            if start+size > len(image):
                raise ValueError("truncated linked code section")
            return digest(image[start:start+size])
    raise ValueError("linked .text section missing")


def independent_primary(content: str, thresholds: dict, blocks: int) -> dict:
    """Recompute the primary from raw CSV, independently of K4's summarizer."""
    half = blocks//2
    counts = {}
    names = ("candidate_t0_p0", "candidate_t1_p0", "no_probe_t0_p0", "no_probe_t1_p0")
    for row in csv.reader(StringIO(content)):
        if not row or row[0] != "K4_SAMPLE" or int(row[2]) < half or row[5] not in names:
            continue
        key = (int(row[2]), row[3], row[5])
        hits, count = counts.get(key, (0, 0))
        counts[key] = hits+int(int(row[11]) <= thresholds["p0"]), count+1
    values = []
    for block in range(half, blocks):
        contrasts = {}
        for mode in ("nop", "cpuid"):
            rates = [counts[block, mode, name][0]/counts[block, mode, name][1] for name in names]
            contrasts[mode] = (rates[1]-rates[0])-(rates[3]-rates[2])
        values.append(contrasts["nop"]-contrasts["cpuid"])
    cycles = [sum(values[i:i+16])/16 for i in range(0, len(values), 16)]
    rng = random.Random(20261102)
    boot = sorted(sum(rng.choices(cycles, k=len(cycles)))/len(cycles) for _ in range(10000))
    return {"hit_rate_difference": sum(values)/len(values), "ci95": [boot[249], boot[9749]],
            "cycle_differences": cycles, "interval_scope": "within_run_16_block_cycles"}


def audit_run(path: Path) -> dict:
    content = path.read_bytes()
    files = members(content)
    manifests = [name for name in files if name.endswith(".manifest.json")]
    if len(manifests) != 1:
        raise ValueError("one evidence manifest required")
    name = manifests[0]
    prefix = name.removesuffix(".manifest.json")
    manifest = json_bytes(files[name])
    if set(files)-{name} != set(manifest["files_sha256"]):
        raise ValueError("manifest inventory mismatch")
    for member, expected in manifest["files_sha256"].items():
        if digest(files[member]) != expected:
            raise ValueError(f"manifest hash mismatch: {member}")
    build = json_bytes(files[prefix+".build.json"])
    source = members(files[prefix+".sources.zip"])
    if set(source) != set(build["source_sha256"]):
        raise ValueError("source inventory mismatch")
    for member, expected in build["source_sha256"].items():
        if digest(source[member]) != expected:
            raise ValueError(f"source hash mismatch: {member}")
    # Reanalysis uses this repository's frozen analyzer and its dependencies.
    root = Path(__file__).resolve().parents[1]
    for member in ("scripts/analyze_context_receiver.py", "scripts/analyze_cache_probe.py",
                   "scripts/context_receiver_contract.py", "scripts/fresh_receiver_contract.py"):
        if source[member] != (root/member).read_bytes():
            raise ValueError(f"historical analysis dependency differs: {member}")
    raw = files[prefix+".log"].decode("utf-8-sig")
    trace = k4.parse_trace(raw)
    result = k4.summarize(trace)
    if result["sample_count"] != 262144 or not result["windows_collection"]:
        raise ValueError("complete frozen Windows collection required")
    with tempfile.TemporaryDirectory() as temporary:
        artifacts = []
        for suffix in (".exe", ".nop.bin", ".cpuid.bin"):
            target = Path(temporary)/("image"+suffix)
            target.write_bytes(files[prefix+suffix])
            artifacts.append(target)
        result["artifact_audit"] = k4.audit_files(trace, *artifacts)
    if result != json_bytes(files[prefix+".analysis.json"]):
        raise ValueError("archived analysis does not reproduce exactly")
    primary = independent_primary(raw, result["thresholds"], int(trace.run["blocks"]))
    if primary != result["outcomes"]["p0"]["interaction"]:
        raise ValueError("independent raw-row primary disagrees")
    host = json_bytes(files[prefix+".host.json"])
    if str(host["os"]["BuildNumber"]) != trace.host["windows_build"] or \
            host["virtualization"]["HypervisorPresent"] != (trace.cpu["hypervisor"] == "1"):
        raise ValueError("host/trace metadata mismatch")
    if build["seed"] != int(trace.run["seed"]) or build["binary_sha256"] != trace.binary_sha256:
        raise ValueError("build/trace provenance mismatch")
    for key in ("git_head", "control_status", "build_runtime_status"):
        if build[key] != manifest[key]:
            raise ValueError(f"build/manifest {key} mismatch")
    expected_status = "passed" if result["apparatus_controls_pass"] else "inconclusive"
    if build["control_status"] != expected_status or build["execution_exit_code"] != 0:
        raise ValueError("build/analysis completion status mismatch")
    listing = check_disassembly(files[prefix+".exe"], files[prefix+".disasm.txt"].decode("utf-8-sig"))
    return {"archive_name": path.name, "archive_sha256": digest(content),
            "trace_sha256": digest(files[prefix+".log"]), "seed": int(trace.run["seed"]),
            "git_head": build["git_head"], "source_sha256": build["source_sha256"],
            "toolchain": build["tools"], "reported_host_inventory": host,
            "git_clean_reported": build["git_clean"],
            "linked_text_raw_sha256": text_section_hash(files[prefix+".exe"]),
            "manifest_files_verified": len(manifest["files_sha256"]),
            "source_files_verified": len(source), "linked_listing_audit": listing,
            "archived_analysis_reproduced_exactly": True,
            "independent_primary_reproduced_exactly": True, "analysis": result}


def summarize_series(pilot: dict, sessions: list[dict]) -> dict:
    if pilot["seed"] != PILOT_SEED or len(sessions) != 3 or \
            sorted(s["seed"] for s in sessions) != sorted(SESSION_SEEDS):
        raise ValueError("pilot or follow-up seeds disagree with the three-session chat plan")
    runs = [pilot]+sessions
    for field in ("archive_sha256", "trace_sha256"):
        if len({r[field] for r in runs}) != 4:
            raise ValueError("duplicate evidence cannot count as a separate session")
    comparable_fields = ("git_head", "source_sha256", "toolchain", "linked_text_raw_sha256",
                         "reported_host_inventory")
    comparison = {field: all(r[field] == pilot[field] for r in sessions) for field in comparable_fields}
    comparable = all(comparison.values()) and all(r["git_head"] == SOURCE_REVISION and
                                                  r["git_clean_reported"] for r in runs)
    repeated = comparable and pilot["analysis"]["numerical_signature_detected"] and \
        all(s["analysis"]["numerical_signature_detected"] for s in sessions)
    ordered = [next(s for s in sessions if s["seed"] == seed) for seed in SESSION_SEEDS]
    points = [s["analysis"]["outcomes"]["p0"]["interaction"]["hit_rate_difference"] for s in ordered]
    return {"study": "context_marker_k4_v1", "pilot": pilot, "planned_sessions": ordered,
            "comparison_with_pilot": comparison, "comparable_recorded_conditions": comparable,
            "three_planned_session_signatures_repeated": bool(repeated),
            "followup_recorded_samples": sum(s["analysis"]["sample_count"] for s in ordered),
            "all_four_recorded_samples": sum(s["analysis"]["sample_count"] for s in runs),
            "followup_primary_descriptive_mean": sum(points)/3,
            "followup_primary_descriptive_range": [min(points), max(points)],
            "pooled_confidence_interval": None, "physical_mechanism_proven": False,
            "privilege_boundary_tested": False,
            "scope": "one reported host; separate processes within minutes; no independent days, boots or hosts",
            "plan_record": "count and seeds specified in chat after the pilot and before these sessions; no new pooled test is claimed"}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pilot", type=Path, required=True)
    parser.add_argument("sessions", nargs=3, type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    try:
        result = summarize_series(audit_run(args.pilot), [audit_run(path) for path in args.sessions])
        text = json.dumps(result, indent=2, sort_keys=True)+"\n"
        if args.output:
            args.output.write_text(text, encoding="utf-8")
        else:
            print(text, end="")
    except (OSError, ValueError, KeyError, TypeError, struct.error, BadZipFile) as exc:
        parser.exit(2, f"Invalid K4 series: {exc}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
