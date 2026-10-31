#!/usr/bin/env python3
"""Validate the pre-training prelude-pattern sweep and report paired interactions.

This user-mode latency assay cannot identify a physical PHR length, branch
misprediction count, or cross-domain predictor behavior.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from datetime import datetime
from functools import reduce
import json
from math import gcd
from pathlib import Path
import re
from statistics import median

from analyze_branch_batch import interval, trimmed_mean
from analyze_cache_probe import MAX_U64, fields, unsigned


LENGTHS = (128, 256)
PATTERNS = ("p4", "p32", "c0", "c1")
ARMS = ("real", "fixed", "sham")
KINDS = tuple(
    f"n{length}_{pattern}_{arm}_t{train}_p{probe}"
    for length in LENGTHS for pattern in PATTERNS for arm in ARMS
    for train in (0, 1) for probe in (0, 1)
) + tuple(
    f"n{length}_p4_timer_{timer}_p{probe}"
    for length in LENGTHS for probe in (0, 1)
    for timer in ("fast", "small", "pause")
)
KIND_INDEX = {kind: index for index, kind in enumerate(KINDS)}
BLOCKS = 864
WARMUP_BLOCKS = 108
EPISODES = 32
TRAIN_CALLS = 32
PROBE_CALLS = 1
FNV_OFFSET = 14695981039346656037
FNV_PRIME = 1099511628211
MAX_U32 = (1 << 32) - 1
PROTOCOL = "prelude_pattern_by_length"
FIXED_TOLERANCE = 1.0


@dataclass(frozen=True)
class Trace:
    cpu: dict[str, str]
    run: dict[str, str]
    host: dict[str, str]
    binary_sha256: str
    affinity_cpu: int
    blocks: list[dict[str, int]]


def replay_schedule(blocks: int, seed: int,
                    warmup_blocks: int = WARMUP_BLOCKS
                    ) -> tuple[list[tuple[str, ...]], int]:
    """Replay warmup plus recorded seeded shuffle and position rotation."""
    state = seed
    base: list[int] = []
    orders: list[tuple[str, ...]] = []
    hash_value = FNV_OFFSET

    def random32() -> int:
        nonlocal state
        state ^= (state << 13) & MAX_U32
        state ^= state >> 17
        state ^= (state << 5) & MAX_U32
        state &= MAX_U32
        return state

    for count, store in ((warmup_blocks, False), (blocks, True)):
        for block in range(count):
            if block % len(KINDS) == 0:
                base = list(range(len(KINDS)))
                for index in range(len(KINDS) - 1, 0, -1):
                    other = random32() % (index + 1)
                    base[index], base[other] = base[other], base[index]
            if store:
                order = tuple(KINDS[base[(position + block % len(KINDS)) %
                                         len(KINDS)]] for position in range(len(KINDS)))
                orders.append(order)
                for kind in order:
                    hash_value = ((hash_value ^ KIND_INDEX[kind]) *
                                  FNV_PRIME) & MAX_U64
    return orders, hash_value


def _features(kind: str) -> tuple[int, str, str, int, int]:
    parts = kind.split("_")
    length = int(parts[0][1:])
    pattern = parts[1]
    if parts[2] == "timer":
        return length, pattern, parts[3], 0, int(parts[4][1:])
    return length, pattern, parts[2], int(parts[3][1:]), int(parts[4][1:])


def expected_sink(blocks: int = BLOCKS, warmup: int = WARMUP_BLOCKS,
                  episodes: int = EPISODES, train_calls: int = TRAIN_CALLS
                  ) -> int:
    total = 0
    for kind in KINDS:
        length, pattern, arm, train, probe = _features(kind)
        prelude = 0 if pattern == "c0" else length if pattern == "c1" else length // 2
        small_work = 8 if arm == "small" and probe == 1 else 0
        total += episodes * (prelude + train_calls * train + probe + small_work)
    return total * (blocks + warmup) & MAX_U32


def _address(value: str) -> int:
    if re.fullmatch(r"0x[0-9a-fA-F]+", value) is None or int(value, 16) == 0:
        raise ValueError("invalid code address")
    return int(value, 16)


def parse_trace(content: str) -> Trace:
    cpu = run = end = host = None
    binary_hash = None
    affinity = None
    rows: list[tuple[int, int, str, int]] = []
    checksum = 0
    for original in content.splitlines():
        row = original.strip()
        if row.startswith("HOST_AFFINITY_CPU="):
            if affinity is not None or cpu is not None:
                raise ValueError("duplicate or late affinity")
            affinity = unsigned(row.split("=", 1)[1], "affinity")
        elif row.startswith("PRELUDE_CPU,"):
            if cpu is not None or run is not None or affinity is None:
                raise ValueError("duplicate, late or unpinned CPU")
            cpu = fields(row, "PRELUDE_CPU")
        elif row.startswith("PRELUDE_RUN,"):
            if run is not None or cpu is None:
                raise ValueError("duplicate or premature RUN")
            run = fields(row, "PRELUDE_RUN")
        elif row.startswith("PRELUDE_SAMPLE,"):
            if run is None or end is not None:
                raise ValueError("sample outside run")
            parts = row.split(",")
            if len(parts) != 6:
                raise ValueError("malformed sample")
            index = unsigned(parts[1], "index")
            block = unsigned(parts[2], "block")
            position = unsigned(parts[3], "position")
            kind = parts[4]
            ticks = unsigned(parts[5], "ticks")
            if index != len(rows) or kind not in KIND_INDEX:
                raise ValueError("unexpected index or kind")
            if block != index // len(KINDS) or position != index % len(KINDS) or not ticks:
                raise ValueError("invalid sample position or ticks")
            rows.append((block, position, kind, ticks))
            checksum = (checksum + (index + 1) * ticks + block + position +
                        KIND_INDEX[kind]) & MAX_U64
        elif row.startswith("PRELUDE_END,"):
            if end is not None or run is None:
                raise ValueError("duplicate or premature END")
            end = fields(row, "PRELUDE_END")
        elif row.startswith("PRELUDE_HOST,"):
            if end is None or host is not None or binary_hash is not None:
                raise ValueError("duplicate or premature HOST")
            host = fields(row, "PRELUDE_HOST")
        elif row.startswith("PRELUDE_BINARY,"):
            if host is None or binary_hash is not None:
                raise ValueError("duplicate or premature BINARY")
            binary = fields(row, "PRELUDE_BINARY")
            if set(binary) != {"sha256"} or re.fullmatch(
                    r"[a-f0-9]{64}", binary["sha256"]) is None:
                raise ValueError("invalid binary SHA256")
            binary_hash = binary["sha256"]
        else:
            raise ValueError(f"unexpected trace row: {row[:60]}")

    if any(value is None for value in (cpu, run, end, host, binary_hash, affinity)):
        raise ValueError("incomplete prelude trace")
    assert cpu is not None and run is not None and end is not None and host is not None
    assert binary_hash is not None and affinity is not None
    if set(cpu) != {"vendor", "signature", "invariant_tsc", "hypervisor"} or \
       not cpu["vendor"] or cpu["invariant_tsc"] != "1" or \
       cpu["hypervisor"] not in ("0", "1"):
        raise ValueError("invalid CPU metadata")
    _address(cpu["signature"])
    required = {"version", "blocks", "conditions", "episodes", "prelude_lengths",
                "patterns", "train_calls", "probe_calls", "warmup_blocks", "seed",
                "branch_addr", "sham_addr", "small_addr", "timer", "protocol",
                "compiler", "schedule_hash"}
    if set(run) != required or run["version"] != "1" or \
       run["prelude_lengths"] != "128_256" or \
       run["patterns"] != "p4_p32_c0_c1" or run["protocol"] != PROTOCOL or \
       run["timer"] != "lfence_rdtsc_lfence" or run["compiler"] != "msvc_O2":
        raise ValueError("unsupported run protocol or metadata")
    if len({_address(run[x]) for x in ("branch_addr", "sham_addr", "small_addr")}) != 3:
        raise ValueError("site address collision")
    for label, expected in (
        ("blocks", BLOCKS), ("conditions", len(KINDS)), ("episodes", EPISODES),
        ("train_calls", TRAIN_CALLS), ("probe_calls", PROBE_CALLS),
        ("warmup_blocks", WARMUP_BLOCKS),
    ):
        if unsigned(run[label], label) != expected:
            raise ValueError(f"invalid dimension {label}")
    seed = unsigned(run["seed"], "seed")
    if not 0 < seed <= MAX_U32:
        raise ValueError("invalid seed")
    if set(end) != {"count", "checksum", "sink"} or \
       len(rows) != BLOCKS * len(KINDS) or \
       unsigned(end["count"], "count") != len(rows) or \
       unsigned(end["checksum"], "checksum") != checksum:
        raise ValueError("sample count or checksum mismatch")
    if unsigned(end["sink"], "sink") != expected_sink():
        raise ValueError("architectural sink mismatch")
    if set(host) != {"windows_build", "run_utc"} or \
       unsigned(host["windows_build"], "build") == 0:
        raise ValueError("invalid host metadata")
    try:
        datetime.strptime(host["run_utc"], "%Y%m%dT%H%M%SZ")
    except ValueError as exc:
        raise ValueError("invalid UTC timestamp") from exc
    orders, expected_hash = replay_schedule(BLOCKS, seed)
    if unsigned(run["schedule_hash"], "schedule hash") != expected_hash:
        raise ValueError("schedule hash mismatch")
    counts = {kind: [0] * len(KINDS) for kind in KINDS}
    blocks: list[dict[str, int]] = []
    for block in range(BLOCKS):
        subset = rows[block * len(KINDS):(block + 1) * len(KINDS)]
        order = tuple(kind for _, _, kind, _ in subset)
        if order != orders[block] or len(set(order)) != len(KINDS):
            raise ValueError(f"condition order mismatch at block {block}")
        for _, position, kind, _ in subset:
            counts[kind][position] += 1
        blocks.append({kind: ticks for _, _, kind, ticks in subset})
    if any(count != BLOCKS // len(KINDS)
           for item in counts.values() for count in item):
        raise ValueError("condition-position balance mismatch")
    return Trace(cpu, run, host, binary_hash, affinity, blocks)


def _summary(values: list[int], seed: int) -> dict[str, object]:
    low, high = interval(values, seed=seed, cycle_size=len(KINDS))
    return {
        "paired_trimmed_mean_ticks_per_probe": trimmed_mean(values) / EPISODES,
        "paired_median_ticks_per_probe": median(values) / EPISODES,
        "within_run_cycle_bootstrap_95_ticks_per_probe": (low / EPISODES,
                                                          high / EPISODES),
        "positive_blocks": sum(x > 0 for x in values),
        "total_blocks": len(values),
    }


def summarize(trace: Trace) -> dict[str, object]:
    outcomes: dict[str, dict[str, object]] = {}
    adjusted: dict[tuple[int, str, int], list[int]] = {}
    fixed_gates: dict[str, bool] = {}
    for length in LENGTHS:
        for pattern in PATTERNS:
            for probe in (0, 1):
                key = f"n{length}_{pattern}_p{probe}"
                components = {}
                for arm in ARMS:
                    values = [
                        b[f"n{length}_{pattern}_{arm}_t{1 - probe}_p{probe}"] -
                        b[f"n{length}_{pattern}_{arm}_t{probe}_p{probe}"]
                        for b in trace.blocks
                    ]
                    components[arm] = values
                real, fixed, sham = (components[arm] for arm in ARMS)
                adj = [a - b for a, b in zip(real, fixed)]
                adjusted[(length, pattern, probe)] = adj
                fixed_summary = _summary(fixed, 0x401 + length + probe)
                fixed_low, fixed_high = fixed_summary[
                    "within_run_cycle_bootstrap_95_ticks_per_probe"]
                fixed_gates[key] = (-FIXED_TOLERANCE <= fixed_low and
                                    fixed_high <= FIXED_TOLERANCE)
                outcomes[key] = {
                    "real_mismatch_minus_match": _summary(real, 0x101 + length + probe),
                    "fixed_mismatch_minus_match": fixed_summary,
                    "sham_mismatch_minus_match": _summary(sham, 0x501 + length + probe),
                    "real_minus_fixed": _summary(adj, 0x201 + length + probe),
                    "real_minus_sham": _summary(
                        [a - b for a, b in zip(real, sham)], 0x601 + length + probe),
                }
    interactions: dict[str, dict[str, object]] = {}
    for probe in (0, 1):
        for length in LENGTHS:
            for a, b in (("p32", "p4"), ("c1", "c0")):
                values = [x - y for x, y in zip(adjusted[(length, a, probe)],
                                                 adjusted[(length, b, probe)])]
                name = f"n{length}_{a}_minus_{b}_p{probe}"
                interactions[name] = _summary(values, 0x900 + length + probe)
        for pattern in PATTERNS:
            values = [x - y for x, y in zip(adjusted[(256, pattern, probe)],
                                             adjusted[(128, pattern, probe)])]
            interactions[f"n256_minus_n128_{pattern}_p{probe}"] = _summary(
                values, 0xA00 + PATTERNS.index(pattern) + probe)
    controls: dict[str, dict[str, object]] = {}
    all_timer = True
    for length in LENGTHS:
        for probe in (0, 1):
            base = f"n{length}_p4_timer_"
            fast = base + f"fast_p{probe}"
            small = _summary([b[base + f"small_p{probe}"] - b[fast]
                              for b in trace.blocks], 0xB00 + length + probe)
            pause = _summary([b[base + f"pause_p{probe}"] - b[fast]
                              for b in trace.blocks], 0xC00 + length + probe)
            small_low, small_high = small[
                "within_run_cycle_bootstrap_95_ticks_per_probe"]
            pause_low, _ = pause[
                "within_run_cycle_bootstrap_95_ticks_per_probe"]
            point = small["paired_trimmed_mean_ticks_per_probe"]
            few_tick = small_low > 0 and small_high < 8 and 1 <= point <= 8
            coarse = pause_low > 0 and pause["positive_blocks"] >= .95 * BLOCKS
            controls[f"n{length}_p{probe}"] = {
                "small_minus_fast": small, "pause_minus_fast": pause,
                "few_tick_pass": few_tick, "coarse_pass": coarse,
            }
            all_timer &= few_tick and coarse
    recorded_calls = BLOCKS * EPISODES * sum(
        _features(kind)[0] + TRAIN_CALLS + PROBE_CALLS for kind in KINDS
    )
    return {
        "outcomes": outcomes, "interactions": interactions,
        "timer_controls": controls, "timer_controls_pass": all_timer,
        "fixed_tolerance_ticks_per_probe": FIXED_TOLERANCE,
        "fixed_trainer_within_tolerance": fixed_gates,
        "fixed_trainer_all_within_tolerance": all(fixed_gates.values()),
        "observed_tick_gcd": reduce(gcd, (
            ticks for block in trace.blocks for ticks in block.values())),
        "total_recorded_site_or_sham_calls": recorded_calls,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("trace", type=Path)
    parser.add_argument("--strict", action="store_true")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    try:
        trace = parse_trace(args.trace.read_text(encoding="utf-8-sig"))
        result = summarize(trace)
    except (OSError, ValueError, KeyError) as exc:
        parser.exit(2, f"Invalid prelude trace: {exc}\n")
    if args.json:
        print(json.dumps({"cpu": trace.cpu, "run": trace.run, "host": trace.host,
                          "affinity_cpu": trace.affinity_cpu,
                          "binary_sha256": trace.binary_sha256, **result},
                         sort_keys=True))
    else:
        print(f"CPU: {trace.cpu['vendor']} {trace.cpu['signature']}; "
              f"hypervisor={trace.cpu['hypervisor']}; logical CPU {trace.affinity_cpu}")
        print(f"Validated {len(trace.blocks)} complete blocks, "
              f"{trace.run['episodes']} episodes per condition; "
              f"seed {trace.run['seed']}; TSC GCD {result['observed_tick_gcd']}")
        for label, control in result["timer_controls"].items():
            small = control["small_minus_fast"]["paired_trimmed_mean_ticks_per_probe"]
            print(f"Timer {label}: small {small:+.2f} ticks, "
                  f"few-tick {'PASS' if control['few_tick_pass'] else 'INCONCLUSIVE'}, "
                  f"PAUSE {'PASS' if control['coarse_pass'] else 'INCONCLUSIVE'}")
        for probe in (0, 1):
            key = f"n128_p32_minus_p4_p{probe}"
            value = result["interactions"][key]
            low, high = value["within_run_cycle_bootstrap_95_ticks_per_probe"]
            print(f"Predeclared balanced-history interaction {key}: "
                  f"{value['paired_trimmed_mean_ticks_per_probe']:+.3f} "
                  f"[within-run 108-block cycle bootstrap 95%: "
                  f"{low:+.3f},{high:+.3f}] ticks/probe")
            for length in LENGTHS:
                for pattern in PATTERNS:
                    label = f"n{length}_{pattern}_p{probe}"
                    row = result["outcomes"][label]["real_minus_fixed"]
                    print(f"  {label}: {row['paired_trimmed_mean_ticks_per_probe']:+.3f} "
                          f"ticks/probe; fixed diagnostic "
                          f"{'within' if result['fixed_trainer_within_tolerance'][label] else 'outside'} "
                          f"±{FIXED_TOLERANCE:g}")
        print("No physical PHR length, misprediction count, transient target "
              "execution, or cross-domain sharing follows from latency alone.")
        print(f"Binary SHA256: {trace.binary_sha256}")
    return 1 if args.strict and (
        not result["timer_controls_pass"] or
        not result["fixed_trainer_all_within_tolerance"]) else 0


if __name__ == "__main__":
    raise SystemExit(main())
