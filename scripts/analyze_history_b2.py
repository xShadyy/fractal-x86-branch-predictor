#!/usr/bin/env python3
"""Replay and analyze the exploratory same-site B2 history-probe trace."""

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


LENGTHS = (1, 16)
ARMS = ("r", "f", "s")
TIMERS = ("fast", "small", "pause")
KINDS = tuple(
    label
    for n in LENGTHS
    for label in (
        *(f"{arm}_t{t}_p{p}_n{n}"
          for arm in ARMS for t in (0, 1) for p in (0, 1)),
        *(f"{timer}_p{p}_n{n}" for timer in TIMERS for p in (0, 1)),
    )
)
KIND_INDEX = {name: index for index, name in enumerate(KINDS)}
EXPECTED_BLOCKS = 720
EPISODES = 128
RESET_CALLS = 256
TRAIN_CALLS = 256
WARMUP_BLOCKS = 36
MAX_U32 = (1 << 32) - 1
FNV_OFFSET = 14695981039346656037
FNV_PRIME = 1099511628211
PROTOCOL = "history_same_site_fixed_probe_length"
TIMER = "lfence_rdtsc_lfence"
COMPILER = "msvc_O2"


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
    """Recreate the C xorshift32 shuffle and complete position rotations."""
    state = seed
    base: list[int] = []
    orders: list[tuple[str, ...]] = []
    schedule_hash = FNV_OFFSET

    def random32() -> int:
        nonlocal state
        state ^= (state << 13) & MAX_U32
        state ^= state >> 17
        state ^= (state << 5) & MAX_U32
        state &= MAX_U32
        return state

    # Warm-up and recorded blocks each start at zero for their rotation.
    # Their RNG state, however, is continuous.
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
                    schedule_hash = ((schedule_hash ^ KIND_INDEX[kind]) * FNV_PRIME) & MAX_U64
    return orders, schedule_hash


def replay_pattern_hash(calls: int = RESET_CALLS) -> int:
    """Hash the same 0011 prelude and fixed-decision byte streams in order."""
    value = FNV_OFFSET
    for _ in range(2):
        for index in range(calls):
            value = ((value ^ ((index >> 1) & 1)) * FNV_PRIME) & MAX_U64
    return value


def _address(value: str, label: str) -> int:
    if re.fullmatch(r"0x[0-9a-fA-F]+", value) is None or int(value, 16) == 0:
        raise ValueError(f"invalid {label}")
    return int(value, 16)


def parse_trace(content: str) -> Trace:
    cpu: dict[str, str] | None = None
    run: dict[str, str] | None = None
    end: dict[str, str] | None = None
    host: dict[str, str] | None = None
    sha: str | None = None
    affinity: int | None = None
    raw: list[tuple[int, int, str, int]] = []
    checksum = 0
    for original in content.splitlines():
        row = original.strip()
        if row.startswith("HOST_AFFINITY_CPU="):
            if affinity is not None or cpu is not None:
                raise ValueError("duplicate or late affinity record")
            affinity = unsigned(row.split("=", 1)[1], "affinity CPU")
        elif row.startswith("B2_CPU,"):
            if cpu is not None or run is not None or affinity is None:
                raise ValueError("duplicate or late B2_CPU")
            cpu = fields(row, "B2_CPU")
        elif row.startswith("B2_RUN,"):
            if cpu is None or run is not None:
                raise ValueError("missing B2_CPU or duplicate B2_RUN")
            run = fields(row, "B2_RUN")
        elif row.startswith("B2_SAMPLE,"):
            if run is None or end is not None:
                raise ValueError("sample outside open run")
            parts = row.split(",")
            if len(parts) != 6:
                raise ValueError("malformed B2_SAMPLE")
            index, block, position = (unsigned(v, name) for v, name in zip(
                parts[1:4], ("sample index", "block", "position")))
            kind = parts[4]
            ticks = unsigned(parts[5], "ticks")
            if index != len(raw) or kind not in KIND_INDEX:
                raise ValueError("sample index or condition mismatch")
            if block != index // len(KINDS) or position != index % len(KINDS):
                raise ValueError("sample block or position mismatch")
            if ticks == 0:
                raise ValueError("zero probe duration")
            checksum = (checksum + (index + 1) * ticks + block + position +
                        KIND_INDEX[kind]) & MAX_U64
            raw.append((block, position, kind, ticks))
        elif row.startswith("B2_END,"):
            if run is None or end is not None:
                raise ValueError("duplicate or premature B2_END")
            end = fields(row, "B2_END")
        elif row.startswith("B2_HOST,"):
            if end is None or host is not None or sha is not None:
                raise ValueError("duplicate or premature B2_HOST")
            host = fields(row, "B2_HOST")
        elif row.startswith("B2_BINARY,"):
            if host is None or sha is not None:
                raise ValueError("duplicate or premature B2_BINARY")
            binary = fields(row, "B2_BINARY")
            if set(binary) != {"sha256"} or not re.fullmatch(r"[a-f0-9]{64}",
                                                             binary["sha256"]):
                raise ValueError("invalid binary SHA-256")
            sha = binary["sha256"]
        else:
            raise ValueError(f"unexpected trace line: {row[:60]}")

    if any(value is None for value in (cpu, run, end, host, sha, affinity)):
        raise ValueError("incomplete B2 trace")
    assert cpu is not None and run is not None and end is not None
    assert host is not None and sha is not None and affinity is not None
    if set(cpu) != {"vendor", "signature", "invariant_tsc", "hypervisor"} or not cpu["vendor"]:
        raise ValueError("invalid CPU metadata")
    if unsigned(cpu["invariant_tsc"], "invariant TSC") != 1 or \
       unsigned(cpu["hypervisor"], "hypervisor") not in (0, 1):
        raise ValueError("invalid CPU flags")
    _address(cpu["signature"], "CPU signature")
    expected_run = {"version", "blocks", "episodes", "reset_calls",
                    "train_calls", "probe_lengths", "warmup_blocks", "seed",
                    "branch_addr", "sham_addr", "live_addr", "fixed_addr",
                    "mode_addr", "probe_addr", "prelude_addr", "timer", "protocol",
                    "compiler", "schedule_hash", "pattern_hash"}
    if set(run) != expected_run or run["version"] != "1":
        raise ValueError("invalid B2 run version or fields")
    addresses = [_address(run[name], name) for name in
                 ("branch_addr", "sham_addr", "live_addr", "fixed_addr",
                  "mode_addr", "probe_addr", "prelude_addr")]
    if len(set(addresses)) != len(addresses):
        raise ValueError("B2 code or data addresses coincide")
    if run["timer"] != TIMER or run["protocol"] != PROTOCOL or run["compiler"] != COMPILER:
        raise ValueError("unexpected timer, protocol or compiler")
    if (unsigned(run["blocks"], "blocks") != EXPECTED_BLOCKS or
        unsigned(run["episodes"], "episodes") != EPISODES or
        unsigned(run["reset_calls"], "reset calls") != RESET_CALLS or
        unsigned(run["train_calls"], "train calls") != TRAIN_CALLS or
        run["probe_lengths"] != "1:16" or
        unsigned(run["warmup_blocks"], "warm-up blocks") != WARMUP_BLOCKS):
        raise ValueError("unexpected protocol dimensions")
    seed = unsigned(run["seed"], "seed")
    if not 0 < seed <= MAX_U32:
        raise ValueError("invalid nonzero 32-bit seed")
    if unsigned(run["pattern_hash"], "pattern hash") != replay_pattern_hash(RESET_CALLS):
        raise ValueError("pattern hash does not match fixed streams")
    if set(end) != {"count", "checksum", "sink"} or \
       unsigned(end["count"], "sample count") != len(raw) or \
       unsigned(end["checksum"], "checksum") != checksum or \
       unsigned(end["sink"], "sink") == 0:
        raise ValueError("sample count, checksum or sink mismatch")
    if set(host) != {"windows_build", "run_utc"} or \
       unsigned(host["windows_build"], "Windows build") == 0 or \
       not re.fullmatch(r"\d{8}T\d{6}Z", host["run_utc"]):
        raise ValueError("invalid host metadata")
    try:
        datetime.strptime(host["run_utc"], "%Y%m%dT%H%M%SZ")
    except ValueError as exc:
        raise ValueError("invalid UTC timestamp") from exc
    if len(raw) != EXPECTED_BLOCKS * len(KINDS):
        raise ValueError("missing or extra B2 samples")
    expected, schedule_hash = replay_schedule(EXPECTED_BLOCKS, seed)
    if unsigned(run["schedule_hash"], "schedule hash") != schedule_hash:
        raise ValueError("schedule hash does not match seed")
    positions = {kind: [0] * len(KINDS) for kind in KINDS}
    blocks: list[dict[str, int]] = []
    for block in range(EXPECTED_BLOCKS):
        rows = raw[block * len(KINDS):(block + 1) * len(KINDS)]
        order = tuple(kind for _, _, kind, _ in rows)
        if set(order) != set(KINDS) or order != expected[block]:
            raise ValueError(f"condition order does not match seed in block {block}")
        for _, position, kind, _ in rows:
            positions[kind][position] += 1
        blocks.append({kind: ticks for _, _, kind, ticks in rows})
    if any(count != EXPECTED_BLOCKS // len(KINDS) for row in positions.values()
           for count in row):
        raise ValueError("unbalanced condition positions")
    return Trace(cpu, run, host, sha, affinity, blocks)


def _stats(values: list[int], seed: int) -> dict[str, object]:
    low, high = interval(values, seed=seed, cycle_size=len(KINDS))
    middle = len(values) // 2
    return {
        "paired_median_ticks_per_probe": median(values) / EPISODES,
        "paired_trimmed_mean_ticks_per_probe": trimmed_mean(values) / EPISODES,
        "within_run_cycle_bootstrap_95_ticks_per_probe":
            (low / EPISODES, high / EPISODES),
        "first_second_half_ticks_per_probe":
            (trimmed_mean(values[:middle]) / EPISODES,
             trimmed_mean(values[middle:]) / EPISODES),
        "exploratory_20pct_trim_ticks_per_probe":
            trimmed_mean(values, 0.20) / EPISODES,
        "positive_blocks": sum(x > 0 for x in values),
        "total_blocks": len(values),
    }


def summarize(trace: Trace) -> dict[str, object]:
    contrasts: dict[str, dict[str, object]] = {}
    controls: dict[str, dict[str, object]] = {}
    point_series: dict[str, list[int]] = {}
    for n in LENGTHS:
        for p in (0, 1):
            suffix = f"p{p}_n{n}"
            mismatch, match = 1 - p, p
            for arm in ARMS:
                key = f"D_{arm}_{suffix}"
                point_series[key] = [
                    row[f"{arm}_t{mismatch}_{suffix}"] -
                    row[f"{arm}_t{match}_{suffix}"] for row in trace.blocks]
            point_series[f"F_{suffix}"] = [a - b for a, b in zip(
                point_series[f"D_r_{suffix}"], point_series[f"D_f_{suffix}"])]
            point_series[f"S_{suffix}"] = [a - b for a, b in zip(
                point_series[f"D_r_{suffix}"], point_series[f"D_s_{suffix}"])]
    for p in (0, 1):
        point_series[f"interaction_p{p}"] = [a - b for a, b in zip(
            point_series[f"F_p{p}_n1"], point_series[f"F_p{p}_n16"])]
    for index, (name, values) in enumerate(point_series.items()):
        contrasts[name] = _stats(values, 0xB200 + index)
        if name.endswith("_n16") and name.startswith(("F_", "S_")):
            contrasts[name]["descriptive_ticks_per_call"] = (
                contrasts[name]["paired_trimmed_mean_ticks_per_probe"] / 16)
    for n in LENGTHS:
        for p in (0, 1):
            suffix = f"p{p}_n{n}"
            controls[suffix] = {}
            fast = f"fast_{suffix}"
            for index, name in enumerate(("pause", "small")):
                values = [row[f"{name}_{suffix}"] - row[fast]
                          for row in trace.blocks]
                result = _stats(values, 0xB300 + 8 * n + 2 * p + index)
                low, high = result["within_run_cycle_bootstrap_95_ticks_per_probe"]
                point = result["paired_trimmed_mean_ticks_per_probe"]
                fraction = result["positive_blocks"] / result["total_blocks"]
                result["positive_fraction"] = fraction
                if name == "pause":
                    result["passes"] = low > 0 and fraction >= 0.95
                else:
                    result["passes"] = low > 0 and high < 8 and 1 <= point <= 8
                controls[suffix][name] = result
            fixed_low, fixed_high = contrasts[f"D_f_{suffix}"][
                "within_run_cycle_bootstrap_95_ticks_per_probe"]
            controls[suffix]["fixed_neutral"] = {
                "interval": (fixed_low, fixed_high),
                "passes": fixed_low > -1 and fixed_high < 1,
            }
    all_pass = all(control[gate]["passes"] for control in controls.values()
                   for gate in ("pause", "small", "fixed_neutral"))
    return {
        "contrasts": contrasts,
        "controls": controls,
        "statistical_control_gates_pass": all_pass,
        "observed_tick_gcd": reduce(gcd, (x for block in trace.blocks
                                           for x in block.values())),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("trace", type=Path)
    parser.add_argument("--strict", action="store_true",
                        help="fail if timer or fixed neutral control gates fail")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    try:
        trace = parse_trace(args.trace.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        parser.exit(2, f"Invalid B2 trace: {exc}\n")
    result = summarize(trace)
    if args.json:
        print(json.dumps({"cpu": trace.cpu, "run": trace.run, "host": trace.host,
                          "binary_sha256": trace.binary_sha256, **result},
                         sort_keys=True))
    else:
        print(f"B2 exploratory trace: {len(trace.blocks)} complete blocks; "
              f"{EPISODES} episodes/condition; binary SHA256 {trace.binary_sha256}")
        print(f"CPU {trace.cpu['vendor']} {trace.cpu['signature']}; "
              f"hypervisor={trace.cpu['hypervisor']}; "
              f"GCD of batch totals {result['observed_tick_gcd']} ticks")
        for suffix, control in result["controls"].items():
            for gate in ("pause", "small"):
                value = control[gate]
                low, high = value["within_run_cycle_bootstrap_95_ticks_per_probe"]
                print(f"{suffix} {gate:5s}: {value['paired_trimmed_mean_ticks_per_probe']:+.3f} "
                      f"[{low:+.3f},{high:+.3f}] ticks/probe; "
                      f"positive {value['positive_fraction']:.1%}; "
                      f"{'PASS' if value['passes'] else 'INCONCLUSIVE'}")
            print(f"{suffix} fixed neutral: "
                  f"{'PASS' if control['fixed_neutral']['passes'] else 'INCONCLUSIVE'}")
        for name, value in result["contrasts"].items():
            low, high = value["within_run_cycle_bootstrap_95_ticks_per_probe"]
            print(f"{name:20s} {value['paired_trimmed_mean_ticks_per_probe']:+.3f} "
                  f"[{low:+.3f},{high:+.3f}] ticks/complete probe")
        print("Exploratory within-run estimates only. Timing does not count branch "
              "mispredictions or establish cross-privilege sharing.")
    return int(args.strict and not result["statistical_control_gates_pass"])


if __name__ == "__main__":
    raise SystemExit(main())
