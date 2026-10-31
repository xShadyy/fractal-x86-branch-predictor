#!/usr/bin/env python3
"""Validate a balanced run-length sweep at one Windows branch site."""

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

from analyze_branch_batch import interval, replay_patterns, trimmed_mean
from analyze_cache_probe import MAX_U64, fields, unsigned


KINDS = (
    "live_p2", "live_p4", "live_p8", "live_p16", "live_p32", "live_random",
    "fixed_p2", "fixed_p4", "fixed_p8", "fixed_p16", "fixed_p32", "fixed_random",
    "branchless_p2", "branchless_p4", "branchless_p8", "branchless_p16",
    "branchless_p32", "branchless_random", "timer_fast", "timer_slow",
)
KIND_INDEX = {kind: index for index, kind in enumerate(KINDS)}
BLOCKS = 400
ITERATIONS = 8192
WARMUP_BLOCKS = 20
TIMER = "lfence_rdtsc_lfence"
PATTERN = "balanced_periods_2_4_8_16_32_and_block_shuffle"
DECISION = "runtime_cmov_live_vs_fixed_p4"
COMPILER = "msvc_O2"
# Practical tolerance for the two primary input-order controls, ticks/call.
CONTROL_TOLERANCE = 0.5


@dataclass(frozen=True)
class Trace:
    cpu: dict[str, str]
    run: dict[str, str]
    host: dict[str, str]
    affinity_cpu: int
    blocks: list[dict[str, int]]
    binary_sha256: str


def _address(value: str, label: str) -> int:
    if not re.fullmatch(r"0x[0-9a-fA-F]+", value) or int(value, 16) == 0:
        raise ValueError(f"invalid {label}")
    return int(value, 16)


def parse_trace(content: str) -> Trace:
    affinity: int | None = None
    cpu: dict[str, str] | None = None
    run: dict[str, str] | None = None
    end: dict[str, str] | None = None
    host: dict[str, str] | None = None
    binary_sha256: str | None = None
    raw: list[tuple[int, int, str, int]] = []
    checksum = 0
    for line in content.splitlines():
        row = line.strip()
        if row.startswith("HOST_AFFINITY_CPU="):
            if affinity is not None or cpu is not None:
                raise ValueError("duplicate or late affinity")
            affinity = unsigned(row.split("=", 1)[1], "affinity CPU")
        elif row.startswith("PATTERN_CPU,"):
            if affinity is None or cpu is not None:
                raise ValueError("missing affinity or duplicate PATTERN_CPU")
            cpu = fields(row, "PATTERN_CPU")
        elif row.startswith("PATTERN_RUN,"):
            if cpu is None or run is not None:
                raise ValueError("missing CPU or duplicate PATTERN_RUN")
            run = fields(row, "PATTERN_RUN")
            if run.get("version") != "1":
                raise ValueError("unsupported pattern trace version")
        elif row.startswith("PATTERN_SAMPLE,"):
            if run is None or end is not None:
                raise ValueError("sample outside open pattern run")
            parts = row.split(",")
            if len(parts) != 6:
                raise ValueError("malformed PATTERN_SAMPLE")
            index = unsigned(parts[1], "sample index")
            block = unsigned(parts[2], "block")
            position = unsigned(parts[3], "position")
            kind = parts[4]
            ticks = unsigned(parts[5], "ticks")
            if kind not in KIND_INDEX or index != len(raw):
                raise ValueError("sample order or class mismatch")
            if block != index // len(KINDS) or position != index % len(KINDS):
                raise ValueError("invalid sample block or position")
            if ticks == 0:
                raise ValueError("zero batch duration")
            raw.append((block, position, kind, ticks))
            checksum = (checksum + (index + 1) * ticks + block + position +
                        KIND_INDEX[kind]) & MAX_U64
        elif row.startswith("PATTERN_END,"):
            if run is None or end is not None:
                raise ValueError("unexpected PATTERN_END")
            end = fields(row, "PATTERN_END")
        elif row.startswith("PATTERN_HOST,"):
            if end is None or host is not None or binary_sha256 is not None:
                raise ValueError("unexpected PATTERN_HOST")
            host = fields(row, "PATTERN_HOST")
            if set(host) != {"windows_build", "run_utc"} or \
               unsigned(host["windows_build"], "Windows build") == 0 or \
               not re.fullmatch(r"\d{8}T\d{6}Z", host["run_utc"]):
                raise ValueError("invalid PATTERN_HOST")
            try:
                datetime.strptime(host["run_utc"], "%Y%m%dT%H%M%SZ")
            except ValueError as exc:
                raise ValueError("invalid run timestamp") from exc
        elif row.startswith("PATTERN_BINARY,"):
            if host is None or binary_sha256 is not None:
                raise ValueError("missing PATTERN_HOST or duplicate PATTERN_BINARY")
            binary = fields(row, "PATTERN_BINARY")
            if set(binary) != {"sha256"} or not re.fullmatch(
                    r"[0-9a-f]{64}", binary["sha256"]):
                raise ValueError("invalid binary SHA256")
            binary_sha256 = binary["sha256"]
        else:
            raise ValueError(f"unexpected trace line: {row[:60]}")

    if affinity is None or cpu is None or run is None or end is None or \
       host is None or binary_sha256 is None:
        raise ValueError("incomplete pattern trace")
    if not {"vendor", "signature", "invariant_tsc", "hypervisor"} <= cpu.keys():
        raise ValueError("missing CPU metadata")
    if not {"version", "blocks", "iterations", "warmup_blocks", "seed",
            "branch_addr", "branchless_addr", "input_addr", "control_addr",
            "mode_addr", "timer", "pattern", "decision", "compiler",
            "pattern_hash"} <= run.keys():
        raise ValueError("missing pattern metadata")
    _address(cpu["signature"], "CPU signature")
    if cpu["invariant_tsc"] != "1" or cpu["hypervisor"] not in ("0", "1"):
        raise ValueError("invalid CPU feature flags")
    addresses = [_address(run[label], label) for label in
                 ("branch_addr", "branchless_addr", "input_addr",
                  "control_addr", "mode_addr")]
    if len(set(addresses)) != len(addresses):
        raise ValueError("branch or data addresses coincide")
    if (run["timer"], run["pattern"], run["decision"], run["compiler"]) != \
       (TIMER, PATTERN, DECISION, COMPILER):
        raise ValueError("unexpected timer, pattern, decision or compiler")
    blocks = unsigned(run["blocks"], "blocks")
    iterations = unsigned(run["iterations"], "iterations")
    warmup = unsigned(run["warmup_blocks"], "warmup blocks")
    seed = unsigned(run["seed"], "seed")
    if blocks != BLOCKS or iterations != ITERATIONS or warmup != WARMUP_BLOCKS:
        raise ValueError("unexpected experiment dimensions")
    if not 0 < seed <= (1 << 32) - 1:
        raise ValueError("invalid run seed")
    if len(raw) != blocks * len(KINDS):
        raise ValueError("missing or extra pattern samples")
    if unsigned(end["count"], "count") != len(raw) or \
       unsigned(end["checksum"], "checksum") != checksum:
        raise ValueError("sample count or checksum mismatch")
    unsigned(end["sink"], "sink")
    orders, pattern_hash = replay_patterns(iterations, blocks, seed,
                                           KINDS, WARMUP_BLOCKS)
    if unsigned(run["pattern_hash"], "pattern hash") != pattern_hash:
        raise ValueError("pattern hash does not match seed and shuffle")
    positions = {kind: [0] * len(KINDS) for kind in KINDS}
    parsed: list[dict[str, int]] = []
    for block in range(blocks):
        rows = raw[block * len(KINDS):(block + 1) * len(KINDS)]
        if {kind for _, _, kind, _ in rows} != set(KINDS):
            raise ValueError(f"unbalanced classes in block {block}")
        if tuple(kind for _, _, kind, _ in rows) != orders[block]:
            raise ValueError(f"class order does not match seed in block {block}")
        for _, position, kind, _ in rows:
            positions[kind][position] += 1
        parsed.append({kind: ticks for _, _, kind, ticks in rows})
    if any(count != blocks // len(KINDS) for counts in positions.values()
           for count in counts):
        raise ValueError("unbalanced class positions")
    return Trace(cpu, run, host, affinity, parsed, binary_sha256)


def summarize(trace: Trace) -> dict[str, object]:
    iterations = int(trace.run["iterations"])
    baseline = "p32"
    alternatives = ("p2", "p4", "p8", "p16", "random")
    profile: dict[str, object] = {}
    for alternative in alternatives:
        contrasts = {}
        blockwise = {
            mode: [block[f"{mode}_{alternative}"] - block[f"{mode}_{baseline}"]
                   for block in trace.blocks]
            for mode in ("live", "fixed", "branchless")
        }
        blockwise["adjusted"] = [a - b for a, b in zip(
            blockwise["live"], blockwise["fixed"])]
        for index, (mode, differences) in enumerate(blockwise.items()):
            low, high = interval(differences, seed=0xC300 +
                                 KIND_INDEX[f"live_{alternative}"] * 4 + index,
                                 cycle_size=len(KINDS))
            contrasts[mode] = {
                "paired_trimmed_mean_ticks_per_iteration":
                    trimmed_mean(differences) / iterations,
                "paired_median_ticks_per_iteration": median(differences) / iterations,
                "within_run_20_block_bootstrap_95_ticks_per_iteration":
                    (low / iterations, high / iterations),
                "positive_blocks": sum(value > 0 for value in differences),
                "total_blocks": len(differences),
            }
        profile[f"{alternative}_minus_{baseline}"] = {
            "contrasts": contrasts,
            "fixed_within_tolerance": all(
                -CONTROL_TOLERANCE <= v <= CONTROL_TOLERANCE for v in
                contrasts["fixed"]["within_run_20_block_bootstrap_95_ticks_per_iteration"]),
            "branchless_within_tolerance": all(
                -CONTROL_TOLERANCE <= v <= CONTROL_TOLERANCE for v in
                contrasts["branchless"]["within_run_20_block_bootstrap_95_ticks_per_iteration"]),
        }
    prior_a_anchor = {}
    for index, mode in enumerate(("live", "fixed", "branchless")):
        values = [block[f"{mode}_random"] - block[f"{mode}_p4"]
                  for block in trace.blocks]
        low, high = interval(values, seed=0xC3A0 + index, cycle_size=len(KINDS))
        prior_a_anchor[mode] = {
            "paired_trimmed_mean_ticks_per_iteration": trimmed_mean(values) / iterations,
            "within_run_20_block_bootstrap_95_ticks_per_iteration":
                (low / iterations, high / iterations),
        }
    anchor_adjusted = [
        (block["live_random"] - block["live_p4"]) -
        (block["fixed_random"] - block["fixed_p4"])
        for block in trace.blocks
    ]
    anchor_low, anchor_high = interval(anchor_adjusted, seed=0xC3A3,
                                       cycle_size=len(KINDS))
    prior_a_anchor["adjusted"] = {
        "paired_trimmed_mean_ticks_per_iteration":
            trimmed_mean(anchor_adjusted) / iterations,
        "within_run_20_block_bootstrap_95_ticks_per_iteration":
            (anchor_low / iterations, anchor_high / iterations),
    }
    primary_values = [
        (block["live_p2"] - block["live_p32"]) -
        (block["fixed_p2"] - block["fixed_p32"])
        for block in trace.blocks
    ]
    primary = profile["p2_minus_p32"]
    timer = [block["timer_slow"] - block["timer_fast"]
             for block in trace.blocks]
    timer_low, timer_high = interval(timer, seed=0xC3FF, cycle_size=len(KINDS))
    timer_pass = (sum(value > 0 for value in timer) / len(timer) >= 0.95 and
                  timer_low > 0)
    half = len(primary_values) // 2
    return {
        "profile": profile,
        "primary": "p2_minus_p32",
        "primary_split_halves_ticks_per_iteration": (
            trimmed_mean(primary_values[:half]) / iterations,
            trimmed_mean(primary_values[half:]) / iterations,
        ),
        "prior_a_random_minus_p4_anchor": prior_a_anchor,
        "timer_control": {
            "paired_trimmed_mean_ticks": trimmed_mean(timer),
            "paired_median_ticks": median(timer),
            "positive_blocks": sum(value > 0 for value in timer),
            "total_blocks": len(timer),
            "within_run_20_block_bootstrap_95_ticks": (timer_low, timer_high),
            "passes": timer_pass,
        },
        "negative_control_tolerance_ticks_per_iteration": CONTROL_TOLERANCE,
        "controls_pass": timer_pass and primary["fixed_within_tolerance"] and
                         primary["branchless_within_tolerance"],
        "primary_positive_within_run": primary["contrasts"]["adjusted"][
            "within_run_20_block_bootstrap_95_ticks_per_iteration"][0] > 0,
        "observed_tick_gcd": reduce(gcd, (value for block in trace.blocks
                                           for value in block.values())),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("trace", type=Path)
    parser.add_argument("--strict", action="store_true",
                        help="exit nonzero on failed timer or primary negative controls")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    try:
        trace = parse_trace(args.trace.read_text(encoding="utf-8"))
    except (OSError, ValueError, KeyError) as exc:
        parser.exit(2, f"Invalid pattern trace: {exc}\n")
    result = summarize(trace)
    if args.json:
        print(json.dumps({"cpu": trace.cpu, "run": trace.run,
                          "host": trace.host, "binary_sha256": trace.binary_sha256,
                          **result}, sort_keys=True))
    else:
        print(f"CPU: {trace.cpu['vendor']} {trace.cpu['signature']}; "
              f"hypervisor={trace.cpu['hypervisor']}")
        print(f"Validated {len(trace.blocks)} randomized complete 20-condition "
              f"blocks, {trace.run['iterations']} iterations/condition; "
              f"seed {trace.run['seed']}; Windows build {trace.host['windows_build']}")
        print(f"Branch site: {trace.run['branch_addr']}; "
              f"binary SHA256: {trace.binary_sha256}")
        print(f"Observed GCD of batch totals: {result['observed_tick_gcd']} TSC ticks")
        control = result["timer_control"]
        print(f"Added-work timer: {control['paired_trimmed_mean_ticks']:+.1f} "
              f"ticks/batch; positive {control['positive_blocks']}/"
              f"{control['total_blocks']} "
              f"({'PASS' if control['passes'] else 'INCONCLUSIVE'})")
        print("Each contrast is alternative minus p32, ticks/iteration; "
              "all 20-block bootstrap intervals are within-run only:")
        for name, entry in result["profile"].items():
            print(name + ":")
            for mode, values in entry["contrasts"].items():
                low, high = values[
                    "within_run_20_block_bootstrap_95_ticks_per_iteration"]
                print(f"  {mode:10s} {values['paired_trimmed_mean_ticks_per_iteration']:+.6f} "
                      f"[95%: {low:+.6f}, {high:+.6f}]")
            print("  fixed/branchless controls within ±0.5 ticks/iteration: "
                  f"{entry['fixed_within_tolerance']}/"
                  f"{entry['branchless_within_tolerance']}")
        anchor = result["prior_a_random_minus_p4_anchor"]["adjusted"]
        anchor_low, anchor_high = anchor[
            "within_run_20_block_bootstrap_95_ticks_per_iteration"]
        print(f"Earlier A comparison, adjusted shuffle - p4: "
              f"{anchor['paired_trimmed_mean_ticks_per_iteration']:+.6f} "
              f"[within-run 95%: {anchor_low:+.6f}, {anchor_high:+.6f}]")
        first, second = result["primary_split_halves_ticks_per_iteration"]
        print(f"Primary p2 - p32 adjusted first/second half: {first:+.3f}, "
              f"{second:+.3f} ticks/iteration")
        print(f"Primary negative controls and timer: "
              f"{'PASS' if result['controls_pass'] else 'INCONCLUSIVE'}")
        print("Balanced run length changes transition frequency; timing does not "
              "identify predictor capacity or count mispredictions.")
    return 1 if args.strict and not result["controls_pass"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
