#!/usr/bin/env python3
"""Validate and summarize balanced native Windows branch timing batches."""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from datetime import datetime
from functools import reduce
import json
from math import gcd
from pathlib import Path
import random
import re
from statistics import median

from analyze_cache_probe import MAX_U64, fields, unsigned


KINDS_V1 = (
    "branch_periodic", "branch_random", "branchless_periodic",
    "branchless_random", "timer_fast", "timer_slow",
)
KINDS_V2 = (
    "branch_periodic", "branch_random",
    "branch_no_load_periodic", "branch_no_load_random",
    "branchless_periodic", "branchless_random", "timer_fast", "timer_slow",
)
KINDS_BY_VERSION = {"1": KINDS_V1, "2": KINDS_V2}
# Keep the version 1 aliases so historical trace fixtures remain readable.
KINDS = KINDS_V1
KIND_INDEX = {kind: index for index, kind in enumerate(KINDS)}
TIMER = "lfence_rdtsc_lfence"
PATTERN = "periodic0011_vs_fresh_balanced_shuffle"
COMPILER = "msvc_O2"
EXPECTED_SEED = 0x3127F49B
EXPECTED_BLOCKS = 144
EXPECTED_ITERATIONS = 8192
WARMUP_BLOCKS = 6
WARMUP_BLOCKS_V2 = 8
FNV_OFFSET = 14695981039346656037
FNV_PRIME = 1099511628211
MAX_U32 = (1 << 32) - 1


@dataclass(frozen=True)
class Trace:
    cpu: dict[str, str]
    run: dict[str, str]
    blocks: list[dict[str, int]]
    affinity_cpu: int | None
    binary_sha256: str
    kinds: tuple[str, ...] = KINDS_V1
    host: dict[str, str] | None = None


def _address(value: str, name: str) -> int:
    if not re.fullmatch(r"0x[0-9a-fA-F]+", value):
        raise ValueError(f"invalid {name}")
    address = int(value, 16)
    if address == 0:
        raise ValueError(f"zero {name}")
    return address


def replay_patterns(iterations: int, blocks: int, seed: int,
                    kinds: tuple[str, ...] = KINDS_V1,
                    warmup_blocks: int = WARMUP_BLOCKS) -> tuple[list[tuple[str, ...]], int]:
    """Reproduce both C xorshift shuffles and the FNV64 pattern commitment."""
    state = seed
    periodic = bytearray((i >> 1) & 1 for i in range(iterations))
    pattern_hash = FNV_OFFSET
    orders: list[tuple[str, ...]] = []

    def random32() -> int:
        nonlocal state
        value = state
        value ^= (value << 13) & MAX_U32
        value ^= value >> 17
        value ^= (value << 5) & MAX_U32
        state = value & MAX_U32
        return state

    def one_block(block: int, record: bool) -> None:
        nonlocal pattern_hash, base
        shuffled = periodic.copy()
        for index in range(iterations - 1, 0, -1):
            other = random32() % (index + 1)
            shuffled[index], shuffled[other] = shuffled[other], shuffled[index]
        if record:
            for value in shuffled:
                pattern_hash = ((pattern_hash ^ value) * FNV_PRIME) & MAX_U64
        if block % len(kinds) == 0:
            base = list(range(len(kinds)))
            for index in range(len(kinds) - 1, 0, -1):
                other = random32() % (index + 1)
                base[index], base[other] = base[other], base[index]
        if record:
            orders.append(tuple(kinds[base[(position + block % len(kinds)) %
                                        len(kinds)]]
                                for position in range(len(kinds))))

    base: list[int] = []
    for block in range(warmup_blocks):
        one_block(block, False)
    for block in range(blocks):
        one_block(block, True)
    return orders, pattern_hash


def parse_trace(content: str) -> Trace:
    cpu: dict[str, str] | None = None
    run: dict[str, str] | None = None
    end: dict[str, str] | None = None
    host: dict[str, str] | None = None
    binary_sha256: str | None = None
    affinity_cpu: int | None = None
    raw: list[tuple[int, int, str, int]] = []
    checksum = 0
    kinds: tuple[str, ...] | None = None
    kind_index: dict[str, int] = {}

    for line in content.splitlines():
        row = line.strip()
        if row.startswith("HOST_AFFINITY_CPU="):
            if affinity_cpu is not None or cpu is not None:
                raise ValueError("duplicate or late affinity record")
            affinity_cpu = unsigned(row.split("=", 1)[1], "affinity CPU")
        elif row.startswith("BATCH_CPU,"):
            if cpu is not None or run is not None:
                raise ValueError("duplicate or late BATCH_CPU")
            cpu = fields(row, "BATCH_CPU")
        elif row.startswith("BATCH_RUN,"):
            if cpu is None or run is not None:
                raise ValueError("missing BATCH_CPU or duplicate BATCH_RUN")
            run = fields(row, "BATCH_RUN")
            kinds = KINDS_BY_VERSION.get(run.get("version", ""))
            if kinds is None:
                raise ValueError("unsupported trace version")
            kind_index = {kind: index for index, kind in enumerate(kinds)}
        elif row.startswith("BATCH_SAMPLE,"):
            if run is None or end is not None:
                raise ValueError("sample outside an open run")
            parts = row.split(",")
            if len(parts) != 6:
                raise ValueError("malformed BATCH_SAMPLE")
            index = unsigned(parts[1], "index")
            block = unsigned(parts[2], "block")
            position = unsigned(parts[3], "position")
            kind = parts[4]
            ticks = unsigned(parts[5], "ticks")
            if ticks == 0:
                raise ValueError("zero batch duration")
            if kind not in kind_index or index != len(raw):
                raise ValueError("sample order or class mismatch")
            if block != index // len(kinds) or position != index % len(kinds):
                raise ValueError("invalid sample block or position")
            raw.append((block, position, kind, ticks))
            checksum = (checksum + (index + 1) * ticks + block + position +
                        kind_index[kind]) & MAX_U64
        elif row.startswith("BATCH_END,"):
            if run is None or end is not None or binary_sha256 is not None:
                raise ValueError("unexpected BATCH_END")
            end = fields(row, "BATCH_END")
        elif row.startswith("BATCH_HOST,"):
            if end is None or host is not None or binary_sha256 is not None or \
               run is None or run["version"] != "2":
                raise ValueError("unexpected BATCH_HOST")
            host = fields(row, "BATCH_HOST")
            if set(host) != {"windows_build", "run_utc"} or \
               unsigned(host["windows_build"], "Windows build") == 0 or \
               not re.fullmatch(r"\d{8}T\d{6}Z", host["run_utc"]):
                raise ValueError("invalid BATCH_HOST")
            try:
                datetime.strptime(host["run_utc"], "%Y%m%dT%H%M%SZ")
            except ValueError as exc:
                raise ValueError("invalid BATCH_HOST timestamp") from exc
        elif row.startswith("BATCH_BINARY,"):
            if end is None or binary_sha256 is not None:
                raise ValueError("missing BATCH_END or duplicate BATCH_BINARY")
            if run is not None and run["version"] == "2" and host is None:
                raise ValueError("missing BATCH_HOST")
            binary = fields(row, "BATCH_BINARY")
            if set(binary) != {"sha256"} or not re.fullmatch(
                    r"[0-9a-f]{64}", binary["sha256"]):
                raise ValueError("invalid binary SHA256")
            binary_sha256 = binary["sha256"]
        else:
            raise ValueError(f"unexpected trace line: {row[:60]}")

    if cpu is None or run is None or end is None or affinity_cpu is None or \
       binary_sha256 is None or kinds is None or \
       (run is not None and run["version"] == "2" and host is None):
        raise ValueError("incomplete batch trace")
    if not {"vendor", "signature", "invariant_tsc", "hypervisor"} <= cpu.keys():
        raise ValueError("missing CPU metadata")
    if not {"version", "blocks", "iterations", "warmup_blocks", "seed",
            "branch_addr", "branchless_addr", "timer", "pattern",
            "compiler", "pattern_hash"} <= run.keys():
        raise ValueError("missing run metadata")
    if unsigned(cpu["invariant_tsc"], "invariant TSC") not in (0, 1):
        raise ValueError("invalid invariant TSC flag")
    if unsigned(cpu["hypervisor"], "hypervisor") not in (0, 1):
        raise ValueError("invalid hypervisor flag")
    _address(cpu["signature"], "CPU signature")
    branch = _address(run["branch_addr"], "branch address")
    branchless = _address(run["branchless_addr"], "branchless address")
    if branch == branchless:
        raise ValueError("branch and branchless address coincide")
    if run["version"] == "2":
        if "branch_no_load_addr" not in run:
            raise ValueError("missing no-load branch address")
        no_load = _address(run["branch_no_load_addr"], "no-load branch address")
        if no_load in (branch, branchless):
            raise ValueError("branch addresses coincide")
    if run["timer"] != TIMER or run["pattern"] != PATTERN or \
       run["compiler"] != COMPILER:
        raise ValueError("unexpected timer, pattern or build settings")
    recorded_pattern_hash = unsigned(run["pattern_hash"], "pattern hash")
    expected_warmup = WARMUP_BLOCKS if run["version"] == "1" else WARMUP_BLOCKS_V2
    if unsigned(run["warmup_blocks"], "warmup blocks") != expected_warmup:
        raise ValueError("unexpected warmup block count")
    iterations = unsigned(run["iterations"], "iterations")
    blocks = unsigned(run["blocks"], "blocks")
    seed = unsigned(run["seed"], "seed")
    if iterations != EXPECTED_ITERATIONS or blocks != EXPECTED_BLOCKS:
        raise ValueError("unexpected iteration or block setting")
    if run["version"] == "1" and seed != EXPECTED_SEED:
        raise ValueError("unexpected version 1 iteration, block or seed setting")
    if run["version"] == "2" and not 0 < seed <= MAX_U32:
        raise ValueError("invalid version 2 seed")
    if len(raw) != blocks * len(kinds):
        raise ValueError("missing or extra samples")
    if unsigned(end["count"], "sample count") != len(raw) or \
       unsigned(end["checksum"], "checksum") != checksum:
        raise ValueError("sample count or checksum mismatch")
    unsigned(end["sink"], "sink")

    expected_orders, expected_hash = replay_patterns(
        iterations, blocks, seed, kinds, expected_warmup)
    if recorded_pattern_hash != expected_hash:
        raise ValueError("pattern hash does not match seed and shuffle")
    parsed: list[dict[str, int]] = []
    positions = {kind: [0] * len(kinds) for kind in kinds}
    for block in range(blocks):
        rows = raw[block * len(kinds):(block + 1) * len(kinds)]
        if {kind for _, _, kind, _ in rows} != set(kinds):
            raise ValueError(f"unbalanced conditions in block {block}")
        if tuple(kind for _, _, kind, _ in rows) != expected_orders[block]:
            raise ValueError(f"class order does not match seed in block {block}")
        for _, position, kind, _ in rows:
            positions[kind][position] += 1
        parsed.append({kind: ticks for _, _, kind, ticks in rows})
    if any(count != blocks // len(kinds) for counts in positions.values()
           for count in counts):
        raise ValueError("unbalanced class positions across blocks")
    return Trace(cpu, run, parsed, affinity_cpu, binary_sha256, kinds, host)


def trimmed_mean(values: list[int], fraction: float = 0.10) -> float:
    ordered = sorted(values)
    cut = int(len(ordered) * fraction)
    middle = ordered[cut:len(ordered) - cut] if cut else ordered
    return sum(middle) / len(middle)


def interval(differences: list[int], iterations: int = 2000,
             seed: int = 0x723a,
             cycle_size: int = len(KINDS_V1)) -> tuple[float, float]:
    """Resample whole position cycles, not individual observations."""
    rng = random.Random(seed)
    cycles = [differences[i:i + cycle_size]
              for i in range(0, len(differences), cycle_size)]
    if not cycles or any(len(cycle) != cycle_size for cycle in cycles):
        raise ValueError("incomplete position cycle")
    estimates = sorted(trimmed_mean([value
                                     for _ in cycles
                                     for value in cycles[rng.randrange(len(cycles))]])
                       for _ in range(iterations))
    return estimates[int(iterations * 0.025)], estimates[int(iterations * 0.975)]


def summarize(trace: Trace) -> dict[str, object]:
    iterations = int(trace.run["iterations"])
    cycle_size = len(trace.kinds)
    measured = [b["branch_random"] - b["branch_periodic"]
                for b in trace.blocks]
    baseline = [b["branchless_random"] - b["branchless_periodic"]
                for b in trace.blocks]
    interaction = [a - b for a, b in zip(measured, baseline)]
    timer = [b["timer_slow"] - b["timer_fast"] for b in trace.blocks]
    comparisons = [("branch", measured), ("branchless", baseline),
                   ("adjusted", interaction)]
    no_load: list[int] | None = None
    if trace.run["version"] == "2":
        no_load = [b["branch_no_load_random"] - b["branch_no_load_periodic"]
                   for b in trace.blocks]
        comparisons.extend((
            ("branch_no_load", no_load),
            ("no_load_adjusted", [a - b for a, b in zip(no_load, baseline)]),
            ("load_minus_no_load", [a - b for a, b in zip(measured, no_load)]),
        ))
    contrasts = {}
    for label, differences in comparisons:
        ci = interval(differences, seed=0x723a + len(contrasts),
                      cycle_size=cycle_size)
        contrasts[label] = {
            "paired_median_ticks_per_iteration": median(differences) / iterations,
            "paired_trimmed_mean_ticks_per_iteration":
                trimmed_mean(differences) / iterations,
            "within_run_cycle_bootstrap_95_ticks_per_iteration":
                (ci[0] / iterations, ci[1] / iterations),
            "positive_blocks": sum(value > 0 for value in differences),
            "total_blocks": len(differences),
        }
    timer_ci = interval(timer, seed=0x723d, cycle_size=cycle_size)
    positive_count = sum(value > 0 for value in timer)
    timer_pass = (positive_count / len(timer) >= 0.95 and timer_ci[0] > 0)
    branchless_low, branchless_high = contrasts["branchless"][
        "within_run_cycle_bootstrap_95_ticks_per_iteration"]
    half = len(trace.blocks) // 2
    result = {
        "class_median_ticks_per_iteration": {
            kind: median(b[kind] for b in trace.blocks) / iterations
            for kind in trace.kinds[:-2]
        },
        "contrasts": contrasts,
        "split_half_adjusted_trimmed_mean_ticks_per_iteration": (
            trimmed_mean(interaction[:half]) / iterations,
            trimmed_mean(interaction[half:]) / iterations,
        ),
        "timer_control": {
            "positive_fraction": positive_count / len(timer),
            "paired_median_ticks": median(timer),
            "paired_trimmed_mean_ticks": trimmed_mean(timer),
            "within_run_cycle_bootstrap_95_ticks": timer_ci,
            "passes": timer_pass,
        },
        "branchless_contrast_detectable": not (branchless_low <= 0 <= branchless_high),
        "observed_tick_gcd": reduce(gcd, (value for block in trace.blocks
                                           for value in block.values())),
    }
    if no_load is not None:
        result["split_half_no_load_trimmed_mean_ticks_per_iteration"] = (
            trimmed_mean(no_load[:half]) / iterations,
            trimmed_mean(no_load[half:]) / iterations,
        )
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("trace", type=Path)
    parser.add_argument("--strict", action="store_true",
                        help="fail if the timer positive control fails")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    try:
        trace = parse_trace(args.trace.read_text(encoding="utf-8"))
    except (OSError, ValueError, KeyError) as exc:
        parser.exit(2, f"Invalid batch trace: {exc}\n")
    result = summarize(trace)
    if args.json:
        print(json.dumps({"cpu": trace.cpu, "run": trace.run, "host": trace.host,
                          "binary_sha256": trace.binary_sha256, **result},
                         sort_keys=True))
    else:
        print(f"CPU: {trace.cpu['vendor']} signature {trace.cpu['signature']}; "
              f"hypervisor={trace.cpu['hypervisor']}")
        if trace.host is not None:
            print(f"Windows build {trace.host['windows_build']}; "
                  f"run start UTC {trace.host['run_utc']}")
        print(f"Validated {len(trace.blocks)} randomized complete blocks, "
              f"{trace.run['iterations']} iterations per condition; "
              f"trace version {trace.run['version']}; seed {trace.run['seed']}")
        print(f"Binary SHA256: {trace.binary_sha256}")
        print(f"Observed GCD of batch totals: {result['observed_tick_gcd']} TSC ticks")
        timer = result["timer_control"]
        timer_low, timer_high = timer["within_run_cycle_bootstrap_95_ticks"]
        cycle_size = len(trace.kinds)
        print(f"Timer positive control: slow - fast trimmed mean "
              f"{timer['paired_trimmed_mean_ticks']:+.1f} ticks "
              f"[within-run {cycle_size}-block cycle bootstrap 95%: "
              f"{timer_low:+.1f}, {timer_high:+.1f}]; "
              f"paired median {timer['paired_median_ticks']:+.1f}; "
              f"positive in {timer['positive_fraction']:.1%} of blocks "
              f"({'PASS' if timer['passes'] else 'INCONCLUSIVE'})")
        labels = ["branch", "branchless", "adjusted"]
        if trace.run["version"] == "2":
            labels = ["branch", "branch_no_load", "branchless", "adjusted",
                      "no_load_adjusted", "load_minus_no_load"]
        for label in labels:
            value = result["contrasts"][label]
            low, high = value["within_run_cycle_bootstrap_95_ticks_per_iteration"]
            comparison = ("loaded - no-load effect:" if label == "load_minus_no_load"
                          else "random - periodic:")
            precision = 6 if label == "branchless" else 3
            print(f"{label:19s} {comparison} "
                  f"{value['paired_trimmed_mean_ticks_per_iteration']:+.{precision}f} "
                  f"TSC ticks/iteration [within-run {cycle_size}-block cycle bootstrap 95%: "
                  f"{low:+.{precision}f}, {high:+.{precision}f}]")
        first, second = result["split_half_adjusted_trimmed_mean_ticks_per_iteration"]
        print(f"Adjusted contrast first/second half: {first:+.3f}, "
              f"{second:+.3f} ticks/iteration")
        if trace.run["version"] == "2":
            print("Positive block contrasts: " + ", ".join(
                f"{label} {result['contrasts'][label]['positive_blocks']}/"
                f"{result['contrasts'][label]['total_blocks']}"
                for label in ("branch", "branch_no_load", "adjusted")))
            first, second = result[
                "split_half_no_load_trimmed_mean_ticks_per_iteration"]
            print(f"No-load branch first/second half: {first:+.3f}, "
                  f"{second:+.3f} ticks/iteration")
            print("No-load and loaded branches occupy different addresses; "
                  "their contrast is an ablation, not isolated target-load cost.")
        if result["branchless_contrast_detectable"]:
            branch = abs(result["contrasts"]["branch"][
                "paired_trimmed_mean_ticks_per_iteration"])
            branchless = abs(result["contrasts"]["branchless"][
                "paired_trimmed_mean_ticks_per_iteration"])
            ratio = f"; absolute point-estimate ratio to branch contrast: {branchless / branch:.2%}" \
                if branch else ""
            print("Branchless comparator difference is statistically detectable "
                  "within this run; inspect its magnitude and repeat runs" + ratio + ".")
        print("A timing contrast is not a count of branch mispredictions.")
    return 1 if args.strict and not result["timer_control"]["passes"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
