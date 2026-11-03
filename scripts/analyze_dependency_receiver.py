#!/usr/bin/env python3
"""Replay K5 resolved-condition dependency-control traces, audit runtime bytes, and apply frozen rules.

Numerical eligibility never substitutes for linked harness review or host
replication. Native development runs cannot become Windows physical evidence.
"""
from __future__ import annotations

import argparse
from dataclasses import dataclass
from datetime import datetime
import hashlib
import json
from pathlib import Path
import random
import re
from statistics import mean

from analyze_cache_probe import fields, select_threshold, unsigned
from dependency_receiver_contract import CODE, BRANCH, code_for

BLOCKS, EPISODES, WARMUP = 512, 16, 16
PRELUDE, TRAIN, PAGES, STRIDE = 128, 256, 64, 4096
MASK32, MASK64 = (1 << 32) - 1, (1 << 64) - 1
FNV_OFFSET, FNV_PRIME = 14695981039346656037, 1099511628211
MODES = ("plain", "mask", "cpuid")
MEMBERS = ("candidate_t0", "candidate_t1", "no_probe_t0", "no_probe_t1",
           "hot", "cold", "arch_load", "warm_mismatch")
KINDS = tuple(f"{member}_p{p}" for p in (0, 1) for member in MEMBERS)
PRIMARY = "p0_adjusted_training_contrast_plain_minus_dependency"
MARGIN = .05


def next32(state: int) -> int:
    state ^= (state << 13) & MASK32
    state ^= state >> 17
    state ^= (state << 5) & MASK32
    return state & MASK32


def mix(value: int, tag: int) -> int:
    return ((value ^ tag) * FNV_PRIME) & MASK64


def replay(blocks: int, episodes: int, seed: int):
    """Shuffle each interleaved round; replay both RNG streams including warmup."""
    schedule = seed
    tags = (seed ^ 0xa5f1523d) or 1
    for count, keep in ((WARMUP, False), (blocks, True)):
        for block in range(count):
            mode_order = list(range(3))
            for i in range(2, 0, -1):
                schedule = next32(schedule)
                j = schedule % (i+1)
                mode_order[i], mode_order[j] = mode_order[j], mode_order[i]
            for mode in mode_order:
                for occurrence in range(episodes):
                    order = list(range(16))
                    for i in range(15, 0, -1):
                        schedule = next32(schedule)
                        j = schedule % (i + 1)
                        order[i], order[j] = order[j], order[i]
                    for position, kind in enumerate(order):
                        p = kind // 8
                        tags = next32(tags); tag0 = 1 + tags % 63
                        tags = next32(tags); tag1 = 1 + tags % 63
                        wanted = tag0 if p else tag1
                        tags = next32(tags); decoy = 1 + tags % 62
                        if decoy >= wanted:
                            decoy += 1
                        tags = next32(tags); first = tags & 1
                        if keep:
                            yield (block, MODES[mode], position, KINDS[kind],
                                   occurrence, tag0, tag1, decoy, first)


@dataclass(frozen=True)
class Sample:
    block: int
    mode: str
    kind: str
    occurrence: int
    order: int
    wanted: int
    decoy: int


@dataclass(frozen=True)
class Trace:
    cpu: dict[str, str]
    run: dict[str, str]
    host: dict[str, str]
    binary_sha256: str | None
    samples: list[Sample]


def _validate_run(run: dict[str, str], development: bool) -> None:
    fixed = dict(version="1", protocol="dependency_marker_k5_v1", conditions="16",
                 modes="3", warmup_blocks="16", prelude_calls="128", train_calls="256",
                 pages="64", stride="4096", history_prefix_branches="256",
                 schedule="interleaved_modes_and_rounds", mask="resolved_condition_index_zero", timer="cpuid_outside_rdtscp_load_rdtscp")
    if any(run.get(k) != v for k, v in fixed.items()):
        raise ValueError("run disagrees with K5 protocol")
    blocks = unsigned(run["blocks"], "blocks")
    episodes = unsigned(run["episodes"], "episodes")
    seed = unsigned(run["seed"], "seed")
    if not 0 < seed <= MASK32 or blocks < 32 or blocks % 32 or blocks > BLOCKS:
        raise ValueError("invalid seed or balanced block dimensions")
    if not 1 <= episodes <= EPISODES:
        raise ValueError("invalid episode count")
    if run.get("platform") == "windows":
        if blocks != BLOCKS or episodes != EPISODES:
            raise ValueError("Windows collection dimensions changed")
    elif run.get("platform") != "native_dev" or not development:
        raise ValueError("native development requires --development; not Windows evidence")
    if unsigned(run["affinity_cpu"], "affinity") > 4095:
        raise ValueError("invalid affinity CPU")
    regions = []
    for key in ("code", "condition", "token0", "token1", "bank0", "bank1"):
        text = run[f"{key}_addr"]
        if re.fullmatch(r"0x[0-9a-fA-F]+", text) is None:
            raise ValueError("invalid address")
        address = int(text, 16)
        length = STRIDE * (PAGES if key.startswith("bank") else 1)
        if not address or address % STRIDE or address + length > MASK64:
            raise ValueError("misaligned or invalid memory region")
        regions.append((address, address + length))
    regions.sort()
    if any(a[1] > b[0] for a, b in zip(regions, regions[1:])):
        raise ValueError("condition, tokens, banks or code overlap")


def parse_trace(content: str, *, development: bool = False) -> Trace:
    cpu = run = end = host = None
    codes: set[str] = set()
    binary = None
    expected = None
    samples = []
    checksum, event_hash = 0, FNV_OFFSET
    for line in content.splitlines():
        row = line.strip()
        if not row:
            continue
        if row.startswith("K5_CPU,"):
            if cpu is not None or run is not None:
                raise ValueError("duplicate or late CPU record")
            cpu = fields(row, "K5_CPU")
            if cpu.get("vendor") != "AuthenticAMD" or cpu.get("rdtscp") != "1" or \
                    cpu.get("clflush_bytes") != "64" or cpu.get("invariant_tsc") != "1" or \
                    cpu.get("hypervisor") not in ("0", "1") or \
                    re.fullmatch(r"0x[0-9a-fA-F]{8}", cpu.get("signature", "")) is None:
                raise ValueError("invalid or unsupported CPU metadata")
        elif row.startswith("K5_RUN,"):
            if cpu is None or run is not None:
                raise ValueError("missing CPU or duplicate run")
            run = fields(row, "K5_RUN")
            _validate_run(run, development)
            expected = iter(replay(int(run["blocks"]), int(run["episodes"]), int(run["seed"])))
        elif row.startswith("K5_CODE,"):
            if run is None or samples or end is not None:
                raise ValueError("late runtime code snapshot")
            record = fields(row, "K5_CODE")
            mode = record["mode"]
            if mode in codes or record["hex"] != code_for(mode).hex():
                raise ValueError("unexpected runtime code bytes or duplicate mode")
            codes.add(mode)
        elif row.startswith("K5_SAMPLE,"):
            if expected is None or codes != set(MODES) or end is not None:
                raise ValueError("sample outside complete code-audited run")
            columns = row.split(",")
            if len(columns) != 20 or unsigned(columns[1], "index") != len(samples):
                raise ValueError("malformed or reordered sample")
            try:
                plan = next(expected)
            except StopIteration:
                raise ValueError("extra sample") from None
            actual = (unsigned(columns[2], "block"), columns[3], unsigned(columns[4], "position"),
                      columns[5], *(unsigned(c, "episode or token") for c in columns[6:11]))
            if actual != plan:
                raise ValueError("schedule, episode or context-token replay mismatch")
            block, mode, position, kind, occurrence, tag0, tag1, decoy, order = plan
            wanted_ticks, decoy_ticks, prelude, train, probe = (
                unsigned(c, "ticks or architectural return") for c in columns[11:16])
            if not wanted_ticks or not decoy_ticks:
                raise ValueError("zero timer delta")
            kind_id = KINDS.index(kind)
            p, member = divmod(kind_id, 8)
            t = member & 1 if member < 4 else (1 - p if member == 7 else p)
            expected_probe = 1 + p if member in (0, 1, 7) else (2 - p if member == 6 else 0)
            if (prelude, train, probe) != (PRELUDE * 3 // 2, TRAIN * (1 + t), expected_probe):
                raise ValueError("architectural path disagrees with intended probe")
            training_cpl, probe_cpl = (unsigned(c, "CPL") for c in columns[16:18])
            training_pc, probe_pc = (int(c,16) for c in columns[18:20])
            expected_pc = int(run["code_addr"],16)+BRANCH
            probed = member in (0,1,6,7)
            if training_cpl != 3 or training_pc != expected_pc or \
                    probe_cpl != (3 if probed else 255) or probe_pc != (expected_pc if probed else 0):
                raise ValueError("actual privilege or measured-site address mismatch")
            samples.append(Sample(block, mode, kind, occurrence, order, wanted_ticks, decoy_ticks))
            checksum = mix(mix(mix(checksum, len(samples)), wanted_ticks), decoy_ticks)
            event_hash = mix(event_hash, MODES.index(mode) * 256 + kind_id * 16 + occurrence)
            event_hash = mix(event_hash, tag0 * 65536 + tag1 * 256 + decoy * 2 + order)
        elif row.startswith("K5_END,"):
            if run is None or end is not None:
                raise ValueError("unexpected end record")
            end = fields(row, "K5_END")
            count = int(run["blocks"]) * 3 * 16 * int(run["episodes"])
            if len(samples) != count or unsigned(end["count"], "count") != count or \
                    unsigned(end["checksum"], "checksum") != checksum or \
                    unsigned(end["event_hash"], "event hash") != event_hash or \
                    end.get("architecture_errors") != "0":
                raise ValueError("incomplete trace, checksum, event hash or architectural error")
        elif row.startswith("K5_HOST,"):
            if end is None or host is not None or binary is not None:
                raise ValueError("unexpected host record")
            host = fields(row, "K5_HOST")
            unsigned(host["windows_build"], "Windows build")
            datetime.strptime(host["run_utc"], "%Y%m%dT%H%M%SZ")
        elif row.startswith("K5_BINARY,"):
            if end is None or host is None or binary is not None:
                raise ValueError("unexpected binary record")
            binary = fields(row, "K5_BINARY")["sha256"]
            if re.fullmatch(r"[0-9a-f]{64}", binary) is None:
                raise ValueError("invalid executable hash")
        else:
            raise ValueError(f"unexpected trace row: {row[:100]}")
    if cpu is None or run is None or end is None or codes != set(MODES):
        raise ValueError("missing run records")
    if run["platform"] == "windows" and (host is None or binary is None):
        raise ValueError("missing Windows host or executable provenance")
    return Trace(cpu, run, host or {}, binary, samples)


def cycle_interval(values: list[float]) -> dict[str, object]:
    cycles = [mean(values[i:i + 16]) for i in range(0, len(values), 16)]
    rng = random.Random(20261102)
    boot = sorted(mean(rng.choices(cycles, k=len(cycles))) for _ in range(10000))
    return dict(hit_rate_difference=mean(values), ci95=[boot[249], boot[9749]],
                cycle_differences=cycles, interval_scope="within_run_16_block_cycles")


def summarize(trace: Trace) -> dict[str, object]:
    blocks, episodes = int(trace.run["blocks"]), int(trace.run["episodes"])
    half = blocks // 2
    threshold = {}
    for p in (0, 1):
        hot = [s.wanted for s in trace.samples if s.block < half and s.kind == f"hot_p{p}"]
        cold = [s.wanted for s in trace.samples if s.block < half and s.kind == f"cold_p{p}"]
        threshold[p] = select_threshold(hot, cold)
    per_block = {(b, m, k): [] for b in range(half, blocks) for m in MODES for k in KINDS}
    decoys = {(m, k): [] for m in MODES for k in KINDS}
    order_hits = {(m, k, o): [] for m in MODES for k in KINDS for o in (0, 1)}
    occurrence_hits = {(m, k, e): [] for m in MODES for k in KINDS for e in range(episodes)}
    for s in trace.samples:
        if s.block < half:
            continue
        hit = int(s.wanted <= threshold[int(s.kind[-1])])
        per_block[s.block, s.mode, s.kind].append(hit)
        decoys[s.mode, s.kind].append(int(s.decoy <= threshold[int(s.kind[-1])]))
        order_hits[s.mode, s.kind, s.order].append(hit)
        occurrence_hits[s.mode, s.kind, s.occurrence].append(hit)
    rates = {m: {k: mean(mean(per_block[b, m, k]) for b in range(half, blocks))
                 for k in KINDS} for m in MODES}
    decoy_rates = {m: {k: mean(decoys[m, k]) for k in KINDS} for m in MODES}
    gates = {}
    for m in MODES:
        for p in (0, 1):
            for member in ("hot", "cold", "arch_load", "no_probe_t0", "no_probe_t1", f"candidate_t{p}"):
                k = f"{member}_p{p}"
                minimum = member in ("hot", "arch_load")
                gates[f"{m}/{k}"] = rates[m][k] >= .95 if minimum else rates[m][k] <= .05
            if m in ("mask", "cpuid"):
                k = f"candidate_t{1 - p}_p{p}"
                gates[f"{m}/{k}"] = rates[m][k] <= .05
        for k in KINDS:
            gates[f"{m}/{k}/decoy"] = decoy_rates[m][k] <= .05
    outcomes = {}
    for p in (0, 1):
        adjusted, components = {}, {}
        for m in MODES:
            c, n = [], []
            for b in range(half, blocks):
                c.append(mean(per_block[b, m, f"candidate_t{1-p}_p{p}"]) -
                         mean(per_block[b, m, f"candidate_t{p}_p{p}"]))
                n.append(mean(per_block[b, m, f"no_probe_t{1-p}_p{p}"]) -
                         mean(per_block[b, m, f"no_probe_t{p}_p{p}"]))
            adjusted[m] = [x - y for x, y in zip(c, n)]
            components[m] = dict(candidate=cycle_interval(c), no_probe=cycle_interval(n))
        outcomes[f"p{p}"] = dict(
            components=components, plain_adjusted=cycle_interval(adjusted["plain"]),
            mask_adjusted=cycle_interval(adjusted["mask"]),
            cpuid_adjusted=cycle_interval(adjusted["cpuid"]),
            interaction=cycle_interval([x - y for x, y in zip(adjusted["plain"], adjusted["mask"])]))
    primary = outcomes["p0"]
    equivalent = all(-MARGIN <= x <= MARGIN for x in primary["cpuid_adjusted"]["ci95"])
    mask_equivalent = all(-MARGIN <= x <= MARGIN for x in primary["mask_adjusted"]["ci95"])
    numerical = (all(gates.values()) and primary["plain_adjusted"]["ci95"][0] > MARGIN and
                 primary["interaction"]["ci95"][0] > MARGIN and equivalent and mask_equivalent)
    return dict(study="dependency_marker_k5_v1", cpu=trace.cpu, run=trace.run,
                host=trace.host, binary_sha256=trace.binary_sha256, sample_count=len(trace.samples),
                runtime_bytes_match_contract=True, thresholds={f"p{p}": threshold[p] for p in (0, 1)},
                apparatus_controls_pass=all(gates.values()), gates=gates,
                heldout_hit_rates=rates, heldout_decoy_hit_rates=decoy_rates,
                receiver_order_hit_rates={m: {k: {str(o): mean(order_hits[m, k, o])
                    if order_hits[m, k, o] else None for o in (0, 1)} for k in KINDS} for m in MODES},
                occurrence_hit_rates={m: {k: [mean(occurrence_hits[m, k, e]) for e in range(episodes)]
                    for k in KINDS} for m in MODES},
                primary_endpoint=PRIMARY, practical_margin=MARGIN, outcomes=outcomes,
                cpuid_primary_equivalence=equivalent, mask_primary_equivalence=mask_equivalent, numerical_signature_detected=numerical,
                windows_collection=trace.run["platform"] == "windows",
                mechanism_conclusion=("not_established_failed_controls" if not all(gates.values()) else
                    "not_established_no_numerical_signature" if not numerical else
                    "withheld_pending_k5_pilot_review_and_independent_sessions"),
                limitation="The resolved-condition address dependency is a distinct control; hardware attribution and user-to-kernel behavior require separate evidence.")


def audit_files(trace: Trace, binary: Path, plain: Path, mask: Path, cpuid: Path) -> dict[str, object]:
    image = binary.read_bytes()
    if trace.binary_sha256 is None or hashlib.sha256(image).hexdigest() != trace.binary_sha256:
        raise ValueError("executed binary SHA256 mismatch or absent provenance")
    hashes = {}
    for mode, path in (("plain", plain), ("mask", mask), ("cpuid", cpuid)):
        content = path.read_bytes()
        if content != code_for(mode):
            raise ValueError("archived runtime bytes disagree with observed code")
        hashes[mode] = hashlib.sha256(content).hexdigest()
    return dict(executable_hash_verified=True, runtime_snapshots_verified=True,
                runtime_code_sha256=hashes, template_present_in_linked_image=CODE in image,
                linked_harness_review="pending")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("trace", type=Path)
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--strict", action="store_true", help="fail invalid apparatus, not an eligible null")
    parser.add_argument("--development", action="store_true")
    parser.add_argument("--binary", type=Path)
    parser.add_argument("--plain-code", type=Path)
    parser.add_argument("--mask-code", type=Path)
    parser.add_argument("--cpuid-code", type=Path)
    args = parser.parse_args()
    try:
        trace = parse_trace(args.trace.read_text(encoding="utf-8-sig"), development=args.development)
        supplied = (args.binary, args.plain_code, args.mask_code, args.cpuid_code)
        if any(supplied) and not all(supplied):
            raise ValueError("provide the executable and all three runtime snapshots together")
        audited = audit_files(trace, *supplied) if all(supplied) else None
        result = summarize(trace)
        result["artifact_audit"] = audited
    except (OSError, ValueError, KeyError, TypeError) as exc:
        parser.exit(2, f"Invalid K5 evidence: {exc}\n")
    if args.json:
        print(json.dumps(result, sort_keys=True))
    else:
        print(f"K5 complete: {result['sample_count']} samples; platform={trace.run['platform']}")
        print(f"Apparatus gates: {sum(result['gates'].values())}/{len(result['gates'])}")
        for name in ("plain_adjusted", "mask_adjusted", "cpuid_adjusted", "interaction"):
            metric = result["outcomes"]["p0"][name]
            print(f"p0 {name}: {100*metric['hit_rate_difference']:+.3f} pp; "
                  f"95% within-run CI [{100*metric['ci95'][0]:+.3f},{100*metric['ci95'][1]:+.3f}]")
        print(f"Frozen numerical signature: {result['numerical_signature_detected']}")
        print(f"Mechanism claim: {result['mechanism_conclusion']}")
        for name, passed in result["gates"].items():
            if not passed:
                print(f"FAILED CONTROL: {name}")
    return 1 if args.strict and not result["apparatus_controls_pass"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
