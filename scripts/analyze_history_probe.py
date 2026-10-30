#!/usr/bin/env python3
"""Validate user-mode branch-history crossover traces and paired controls."""

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


KINDS = (
    "b_t0_p0", "b_t1_p0", "b_t0_p1", "b_t1_p1",
    "s_t0_p0", "s_t1_p0", "s_t0_p1", "s_t1_p1",
    "timer_fast", "timer_slow",
)
KIND_INDEX = {kind: index for index, kind in enumerate(KINDS)}
EXPECTED_BLOCKS = 320
EPISODES = 128
RESET_CALLS = 256
TRAIN_CALLS = 256
PROBE_CALLS = 16
WARMUP_BLOCKS = 10
TIMER = "lfence_rdtsc_lfence"
PROTOCOL = "reset_train_fixed_probe_crossover"
COMPILER = "msvc_O2"
MAX_U32 = (1 << 32) - 1
FNV_OFFSET = 14695981039346656037
FNV_PRIME = 1099511628211


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
    """Replay the C xorshift permutation and complete position rotation."""
    state = seed
    base: list[int] = []
    orders: list[tuple[str, ...]] = []
    schedule_hash = FNV_OFFSET

    def random32() -> int:
        nonlocal state
        value = state
        value ^= (value << 13) & MAX_U32
        value ^= value >> 17
        value ^= (value << 5) & MAX_U32
        state = value & MAX_U32
        return state

    def one_block(block: int, store: bool) -> None:
        nonlocal base, schedule_hash
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

    for block in range(warmup_blocks):
        one_block(block, False)
    for block in range(blocks):
        one_block(block, True)
    return orders, schedule_hash


def _address(value: str, label: str) -> int:
    if not re.fullmatch(r"0x[0-9a-fA-F]+", value):
        raise ValueError(f"invalid {label}")
    address = int(value, 16)
    if not address:
        raise ValueError(f"zero {label}")
    return address


def parse_trace(content: str) -> Trace:
    cpu: dict[str, str] | None = None
    run: dict[str, str] | None = None
    end: dict[str, str] | None = None
    host: dict[str, str] | None = None
    binary_sha256: str | None = None
    affinity_cpu: int | None = None
    raw: list[tuple[int, int, str, int]] = []
    checksum = 0

    for original in content.splitlines():
        row = original.strip()
        if row.startswith("HOST_AFFINITY_CPU="):
            if affinity_cpu is not None or cpu is not None:
                raise ValueError("duplicate or late affinity record")
            affinity_cpu = unsigned(row.split("=", 1)[1], "affinity CPU")
        elif row.startswith("HISTORY_CPU,"):
            if cpu is not None or run is not None or affinity_cpu is None:
                raise ValueError("duplicate or late HISTORY_CPU")
            cpu = fields(row, "HISTORY_CPU")
        elif row.startswith("HISTORY_RUN,"):
            if cpu is None or run is not None:
                raise ValueError("missing HISTORY_CPU or duplicate HISTORY_RUN")
            run = fields(row, "HISTORY_RUN")
        elif row.startswith("HISTORY_SAMPLE,"):
            if run is None or end is not None:
                raise ValueError("sample outside an open run")
            parts = row.split(",")
            if len(parts) != 6:
                raise ValueError("malformed HISTORY_SAMPLE")
            index = unsigned(parts[1], "index")
            block = unsigned(parts[2], "block")
            position = unsigned(parts[3], "position")
            kind = parts[4]
            ticks = unsigned(parts[5], "ticks")
            if kind not in KIND_INDEX or index != len(raw):
                raise ValueError("sample order or class mismatch")
            if block != index // len(KINDS) or position != index % len(KINDS):
                raise ValueError("invalid sample block or position")
            if ticks == 0:
                raise ValueError("zero probe duration")
            raw.append((block, position, kind, ticks))
            checksum = (checksum + (index + 1) * ticks + block + position +
                        KIND_INDEX[kind]) & MAX_U64
        elif row.startswith("HISTORY_END,"):
            if run is None or end is not None:
                raise ValueError("duplicate or premature HISTORY_END")
            end = fields(row, "HISTORY_END")
        elif row.startswith("HISTORY_HOST,"):
            if end is None or host is not None or binary_sha256 is not None:
                raise ValueError("duplicate or premature HISTORY_HOST")
            host = fields(row, "HISTORY_HOST")
        elif row.startswith("HISTORY_BINARY,"):
            if host is None or binary_sha256 is not None:
                raise ValueError("missing HISTORY_HOST or duplicate HISTORY_BINARY")
            binary = fields(row, "HISTORY_BINARY")
            if set(binary) != {"sha256"} or not re.fullmatch(
                    r"[0-9a-f]{64}", binary["sha256"]):
                raise ValueError("invalid binary SHA256")
            binary_sha256 = binary["sha256"]
        else:
            raise ValueError(f"unexpected trace line: {row[:60]}")

    if cpu is None or run is None or end is None or host is None or \
       binary_sha256 is None or affinity_cpu is None:
        raise ValueError("incomplete history trace")
    if set(cpu) != {"vendor", "signature", "invariant_tsc", "hypervisor"} or \
       not cpu["vendor"]:
        raise ValueError("invalid CPU metadata")
    if set(run) != {"version", "blocks", "episodes", "reset_calls",
                    "train_calls", "probe_calls", "warmup_blocks", "seed",
                    "branch_addr", "sham_addr", "timer", "protocol",
                    "compiler", "schedule_hash"}:
        raise ValueError("invalid run metadata")
    if run["version"] != "1":
        raise ValueError("unsupported history trace version")
    if unsigned(cpu["invariant_tsc"], "invariant TSC") != 1 or \
       unsigned(cpu["hypervisor"], "hypervisor") not in (0, 1):
        raise ValueError("invalid CPU feature flags")
    _address(cpu["signature"], "CPU signature")
    if _address(run["branch_addr"], "branch address") == \
       _address(run["sham_addr"], "sham address"):
        raise ValueError("conditional and sham addresses coincide")
    if run["timer"] != TIMER or run["protocol"] != PROTOCOL or \
       run["compiler"] != COMPILER:
        raise ValueError("unexpected timer, protocol or compiler")
    if (unsigned(run["blocks"], "block count") != EXPECTED_BLOCKS or
        unsigned(run["episodes"], "episode count") != EPISODES or
        unsigned(run["reset_calls"], "reset calls") != RESET_CALLS or
        unsigned(run["train_calls"], "train calls") != TRAIN_CALLS or
        unsigned(run["probe_calls"], "probe calls") != PROBE_CALLS or
        unsigned(run["warmup_blocks"], "warmup blocks") != WARMUP_BLOCKS):
        raise ValueError("unexpected protocol dimensions")
    seed = unsigned(run["seed"], "seed")
    if not 0 < seed <= MAX_U32:
        raise ValueError("invalid nonzero 32-bit seed")
    recorded_hash = unsigned(run["schedule_hash"], "schedule hash")
    if set(end) != {"count", "checksum", "sink"}:
        raise ValueError("invalid end metadata")
    if len(raw) != EXPECTED_BLOCKS * len(KINDS):
        raise ValueError("missing or extra samples")
    if unsigned(end["count"], "sample count") != len(raw) or \
       unsigned(end["checksum"], "checksum") != checksum:
        raise ValueError("sample count or checksum mismatch")
    unsigned(end["sink"], "sink")
    if set(host) != {"windows_build", "run_utc"} or \
       unsigned(host["windows_build"], "Windows build") == 0 or \
       not re.fullmatch(r"\d{8}T\d{6}Z", host["run_utc"]):
        raise ValueError("invalid host metadata")
    try:
        datetime.strptime(host["run_utc"], "%Y%m%dT%H%M%SZ")
    except ValueError as exc:
        raise ValueError("invalid run timestamp") from exc

    expected_orders, expected_hash = replay_schedule(EXPECTED_BLOCKS, seed)
    if recorded_hash != expected_hash:
        raise ValueError("schedule hash does not match seed")
    blocks: list[dict[str, int]] = []
    positions = {kind: [0] * len(KINDS) for kind in KINDS}
    for block in range(EXPECTED_BLOCKS):
        rows = raw[block * len(KINDS):(block + 1) * len(KINDS)]
        order = tuple(kind for _, _, kind, _ in rows)
        if set(order) != set(KINDS):
            raise ValueError(f"unbalanced conditions in block {block}")
        if order != expected_orders[block]:
            raise ValueError(f"class order does not match seed in block {block}")
        for _, position, kind, _ in rows:
            positions[kind][position] += 1
        blocks.append({kind: ticks for _, _, kind, ticks in rows})
    if any(count != EXPECTED_BLOCKS // len(KINDS) for row in positions.values()
           for count in row):
        raise ValueError("unbalanced condition positions")
    return Trace(cpu, run, host, binary_sha256, affinity_cpu, blocks)


def summarize(trace: Trace) -> dict[str, object]:
    b = trace.blocks
    probe0 = [x["b_t1_p0"] - x["b_t0_p0"] for x in b]
    probe1 = [x["b_t0_p1"] - x["b_t1_p1"] for x in b]
    sham0 = [x["s_t1_p0"] - x["s_t0_p0"] for x in b]
    sham1 = [x["s_t0_p1"] - x["s_t1_p1"] for x in b]
    adjusted0 = [a - s for a, s in zip(probe0, sham0)]
    adjusted1 = [a - s for a, s in zip(probe1, sham1)]
    comparisons = (
        ("probe0", probe0), ("probe1", probe1),
        ("sham0", sham0), ("sham1", sham1),
        ("adjusted0", adjusted0), ("adjusted1", adjusted1),
    )
    contrasts = {}
    for index, (name, values) in enumerate(comparisons):
        scale = EPISODES
        low, high = interval(values, seed=0x17c0 + index,
                             cycle_size=len(KINDS))
        contrasts[name] = {
            "paired_median_ticks_per_probe": median(values) / scale,
            "paired_trimmed_mean_ticks_per_probe": trimmed_mean(values) / scale,
            "within_run_cycle_bootstrap_95_ticks_per_probe":
                (low / scale, high / scale),
            "positive_blocks": sum(value > 0 for value in values),
            "total_blocks": len(values),
        }
    timer = [x["timer_slow"] - x["timer_fast"] for x in b]
    timer_low, timer_high = interval(timer, seed=0x17d0, cycle_size=len(KINDS))
    positives = sum(value > 0 for value in timer)
    half = len(b) // 2
    return {
        "contrasts": contrasts,
        "split_half_adjusted_ticks_per_probe": {
            "probe0": (trimmed_mean(adjusted0[:half]) / EPISODES,
                       trimmed_mean(adjusted0[half:]) / EPISODES),
            "probe1": (trimmed_mean(adjusted1[:half]) / EPISODES,
                       trimmed_mean(adjusted1[half:]) / EPISODES),
        },
        "timer_control": {
            "paired_trimmed_mean_ticks_total": trimmed_mean(timer),
            "within_run_cycle_bootstrap_95_ticks_total": (timer_low, timer_high),
            "paired_trimmed_mean_ticks_per_probe": trimmed_mean(timer) / EPISODES,
            "paired_median_ticks_per_probe": median(timer) / EPISODES,
            "within_run_cycle_bootstrap_95_ticks_per_probe":
                (timer_low / EPISODES, timer_high / EPISODES),
            "positive_fraction": positives / len(timer),
            "passes": positives / len(timer) >= 0.95 and timer_low > 0,
        },
        "observed_tick_gcd": reduce(gcd, (value for block in b
                                           for value in block.values())),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("trace", type=Path)
    parser.add_argument("--strict", action="store_true",
                        help="fail if the timer positive control is inconclusive")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    try:
        trace = parse_trace(args.trace.read_text(encoding="utf-8"))
    except (OSError, ValueError, KeyError) as exc:
        parser.exit(2, f"Invalid history trace: {exc}\n")
    result = summarize(trace)
    if args.json:
        print(json.dumps({"cpu": trace.cpu, "run": trace.run, "host": trace.host,
                          "binary_sha256": trace.binary_sha256, **result},
                         sort_keys=True))
    else:
        print(f"CPU: {trace.cpu['vendor']} signature {trace.cpu['signature']}; "
              f"hypervisor={trace.cpu['hypervisor']}; "
              f"Windows build {trace.host['windows_build']}")
        print(f"Validated {len(trace.blocks)} complete randomized blocks, "
              f"{trace.run['episodes']} episodes per condition; "
              f"seed {trace.run['seed']}; binary SHA256 {trace.binary_sha256}")
        print(f"Observed GCD of summed probe totals: "
              f"{result['observed_tick_gcd']} TSC ticks")
        timer = result["timer_control"]
        low, high = timer["within_run_cycle_bootstrap_95_ticks_per_probe"]
        print(f"Timer extra-work control: slow - fast "
              f"{timer['paired_trimmed_mean_ticks_per_probe']:+.2f} "
              f"TSC ticks per short probe [within-run 10-block cycle "
              f"bootstrap 95%: {low:+.2f}, {high:+.2f}]; "
              f"positive in {timer['positive_fraction']:.1%} of blocks "
              f"({'PASS' if timer['passes'] else 'INCONCLUSIVE'})")
        names = (
            ("probe0", "branch probe 0, mismatch - match"),
            ("probe1", "branch probe 1, mismatch - match"),
            ("sham0", "sham probe 0, mismatch - match"),
            ("sham1", "sham probe 1, mismatch - match"),
            ("adjusted0", "branch - sham probe 0"),
            ("adjusted1", "branch - sham probe 1"),
        )
        for key, label in names:
            value = result["contrasts"][key]
            low, high = value["within_run_cycle_bootstrap_95_ticks_per_probe"]
            print(f"{label:38s} {value['paired_trimmed_mean_ticks_per_probe']:+.2f} "
                  f"TSC ticks per fixed 16-call probe [within-run 10-block cycle "
                  f"bootstrap 95%: {low:+.2f}, {high:+.2f}]; "
                  f"positive {value['positive_blocks']}/{value['total_blocks']}")
        for probe in ("probe0", "probe1"):
            first, second = result["split_half_adjusted_ticks_per_probe"][probe]
            print(f"Adjusted {probe} first/second half: {first:+.2f}, "
                  f"{second:+.2f} ticks per fixed 16-call probe")
        print("Both probe-outcome directions and the sham comparison matter. "
              "These are within-run intervals, not across-run certainty.")
        print("User-mode timing does not count mispredictions or demonstrate "
              "predictor sharing across privilege domains.")
    return 1 if args.strict and not result["timer_control"]["passes"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
