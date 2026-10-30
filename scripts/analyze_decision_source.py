#!/usr/bin/env python3
"""Validate one-site Windows decision-source intervention traces."""

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


KINDS = ("live_periodic", "live_random", "fixed_periodic", "fixed_random",
         "branchless_periodic", "branchless_random", "timer_fast", "timer_slow")
KIND_INDEX = {kind: index for index, kind in enumerate(KINDS)}
BLOCKS = 144
ITERATIONS = 8192
WARMUP_BLOCKS = 8
TIMER = "lfence_rdtsc_lfence"
PATTERN = "periodic0011_vs_fresh_balanced_shuffle"
DECISION = "runtime_cmov_live_vs_fixed_periodic"
COMPILER = "msvc_O2"
# Predeclared within-run equivalence tolerance for fixed input, branchless
# input, and live-vs-fixed periodic decisions, in TSC ticks/call.
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
        elif row.startswith("DECISION_CPU,"):
            if affinity is None or cpu is not None:
                raise ValueError("missing affinity or duplicate DECISION_CPU")
            cpu = fields(row, "DECISION_CPU")
        elif row.startswith("DECISION_RUN,"):
            if cpu is None or run is not None:
                raise ValueError("missing CPU or duplicate DECISION_RUN")
            run = fields(row, "DECISION_RUN")
            if run.get("version") != "1":
                raise ValueError("unsupported decision trace version")
        elif row.startswith("DECISION_SAMPLE,"):
            if run is None or end is not None:
                raise ValueError("sample outside open decision run")
            parts = row.split(",")
            if len(parts) != 6:
                raise ValueError("malformed DECISION_SAMPLE")
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
        elif row.startswith("DECISION_END,"):
            if run is None or end is not None:
                raise ValueError("unexpected DECISION_END")
            end = fields(row, "DECISION_END")
        elif row.startswith("DECISION_HOST,"):
            if end is None or host is not None or binary_sha256 is not None:
                raise ValueError("unexpected DECISION_HOST")
            host = fields(row, "DECISION_HOST")
            if set(host) != {"windows_build", "run_utc"} or \
               unsigned(host["windows_build"], "Windows build") == 0 or \
               not re.fullmatch(r"\d{8}T\d{6}Z", host["run_utc"]):
                raise ValueError("invalid DECISION_HOST")
            try:
                datetime.strptime(host["run_utc"], "%Y%m%dT%H%M%SZ")
            except ValueError as exc:
                raise ValueError("invalid run timestamp") from exc
        elif row.startswith("DECISION_BINARY,"):
            if host is None or binary_sha256 is not None:
                raise ValueError("missing DECISION_HOST or duplicate DECISION_BINARY")
            binary = fields(row, "DECISION_BINARY")
            if set(binary) != {"sha256"} or not re.fullmatch(
                    r"[0-9a-f]{64}", binary["sha256"]):
                raise ValueError("invalid binary SHA256")
            binary_sha256 = binary["sha256"]
        else:
            raise ValueError(f"unexpected trace line: {row[:60]}")

    if affinity is None or cpu is None or run is None or end is None or \
       host is None or binary_sha256 is None:
        raise ValueError("incomplete decision trace")
    if not {"vendor", "signature", "invariant_tsc", "hypervisor"} <= cpu.keys():
        raise ValueError("missing CPU metadata")
    if not {"version", "blocks", "iterations", "warmup_blocks", "seed",
            "branch_addr", "branchless_addr", "input_addr", "control_addr",
            "mode_addr", "timer", "pattern", "decision", "compiler",
            "pattern_hash"} <= run.keys():
        raise ValueError("missing decision metadata")
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
        raise ValueError("missing or extra decision samples")
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
    live = [b["live_random"] - b["live_periodic"] for b in trace.blocks]
    fixed = [b["fixed_random"] - b["fixed_periodic"] for b in trace.blocks]
    branchless = [b["branchless_random"] - b["branchless_periodic"]
                  for b in trace.blocks]
    primary = [a - b for a, b in zip(live, fixed)]
    periodic_mode = [b["live_periodic"] - b["fixed_periodic"]
                     for b in trace.blocks]
    timer = [b["timer_slow"] - b["timer_fast"] for b in trace.blocks]
    contrasts = {}
    for name, values in (("primary_interaction", primary),
                         ("live_pattern", live), ("fixed_pattern", fixed),
                         ("branchless_pattern", branchless),
                         ("periodic_mode", periodic_mode)):
        low, high = interval(values, seed=0xD315 + len(contrasts),
                             cycle_size=len(KINDS))
        contrasts[name] = {
            "paired_trimmed_mean_ticks_per_iteration":
                trimmed_mean(values) / iterations,
            "paired_median_ticks_per_iteration": median(values) / iterations,
            "within_run_eight_block_bootstrap_95_ticks_per_iteration":
                (low / iterations, high / iterations),
            "positive_blocks": sum(value > 0 for value in values),
            "total_blocks": len(values),
        }
    timer_low, timer_high = interval(timer, seed=0xD31F,
                                     cycle_size=len(KINDS))
    timer_pass = (sum(value > 0 for value in timer) / len(timer) >= 0.95
                  and timer_low > 0)
    negative_controls = {}
    for name in ("fixed_pattern", "branchless_pattern", "periodic_mode"):
        low, high = contrasts[name][
            "within_run_eight_block_bootstrap_95_ticks_per_iteration"]
        negative_controls[name] = -CONTROL_TOLERANCE <= low and \
            high <= CONTROL_TOLERANCE
    half = len(primary) // 2
    return {
        "contrasts": contrasts,
        "primary_split_halves_ticks_per_iteration": (
            trimmed_mean(primary[:half]) / iterations,
            trimmed_mean(primary[half:]) / iterations,
        ),
        "timer_control": {
            "paired_trimmed_mean_ticks": trimmed_mean(timer),
            "paired_median_ticks": median(timer),
            "positive_blocks": sum(value > 0 for value in timer),
            "total_blocks": len(timer),
            "within_run_eight_block_bootstrap_95_ticks":
                (timer_low, timer_high),
            "passes": timer_pass,
        },
        "negative_control_tolerance_ticks_per_iteration": CONTROL_TOLERANCE,
        "negative_controls_within_tolerance": negative_controls,
        "controls_pass": timer_pass and all(negative_controls.values()),
        "primary_positive_within_run": contrasts["primary_interaction"][
            "within_run_eight_block_bootstrap_95_ticks_per_iteration"][0] > 0,
        "observed_tick_gcd": reduce(gcd, (value for b in trace.blocks
                                           for value in b.values())),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("trace", type=Path)
    parser.add_argument("--strict", action="store_true",
                        help="exit nonzero on failed timer or negative controls")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    try:
        trace = parse_trace(args.trace.read_text(encoding="utf-8"))
    except (OSError, ValueError, KeyError) as exc:
        parser.exit(2, f"Invalid decision trace: {exc}\n")
    result = summarize(trace)
    if args.json:
        print(json.dumps({"cpu": trace.cpu, "run": trace.run,
                          "host": trace.host, "binary_sha256": trace.binary_sha256,
                          **result}, sort_keys=True))
    else:
        print(f"CPU: {trace.cpu['vendor']} {trace.cpu['signature']}; "
              f"hypervisor={trace.cpu['hypervisor']}")
        print(f"Validated {len(trace.blocks)} complete randomized blocks, "
              f"{trace.run['iterations']} iterations per condition; "
              f"seed {trace.run['seed']}; Windows build "
              f"{trace.host['windows_build']}")
        print(f"Branch site: {trace.run['branch_addr']}; "
              f"control tolerance ±{CONTROL_TOLERANCE:g} TSC ticks/iteration")
        print(f"Binary SHA256: {trace.binary_sha256}")
        print(f"Observed GCD of batch totals: {result['observed_tick_gcd']} TSC ticks")
        timer_control = result["timer_control"]
        print(f"Added-work timer control: {timer_control['paired_trimmed_mean_ticks']:+.1f} "
              f"ticks/batch, positive {timer_control['positive_blocks']}/"
              f"{timer_control['total_blocks']} "
              f"({'PASS' if timer_control['passes'] else 'INCONCLUSIVE'})")
        for name in ("primary_interaction", "live_pattern", "fixed_pattern",
                     "branchless_pattern", "periodic_mode"):
            value = result["contrasts"][name]
            low, high = value[
                "within_run_eight_block_bootstrap_95_ticks_per_iteration"]
            print(f"{name:20s} {value['paired_trimmed_mean_ticks_per_iteration']:+.6f} "
                  f"TSC ticks/iteration [within-run 8-block bootstrap 95%: "
                  f"{low:+.6f}, {high:+.6f}]; "
                  f"positive {value['positive_blocks']}/{value['total_blocks']}")
        print("Negative control intervals within predeclared tolerance: " + ", ".join(
            f"{name}={'PASS' if passes else 'INCONCLUSIVE'}"
            for name, passes in result["negative_controls_within_tolerance"].items()))
        first, second = result["primary_split_halves_ticks_per_iteration"]
        print(f"Primary interaction first/second half: {first:+.3f}, "
              f"{second:+.3f} ticks/iteration")
        print("A timing contrast is not a count of branch mispredictions.")
    return 1 if args.strict and not result["controls_pass"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
