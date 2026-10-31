#!/usr/bin/env python3
"""Validate and analyze exploratory intervening-branch placement traces."""

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


LAGS = (0, 16, 64, 256)
TIMER_LAGS = (0, 256)
KINDS = tuple(
    f"l{lag}_{arm}_t{train}_p{probe}"
    for lag in LAGS
    for arm in ("real", "fixed")
    for train in (0, 1)
    for probe in (0, 1)
) + tuple(
    f"l{lag}_timer_{timer}_p{probe}"
    for lag in TIMER_LAGS
    for probe in (0, 1)
    for timer in ("fast", "small", "pause")
)
KIND_INDEX = {kind: index for index, kind in enumerate(KINDS)}
BLOCKS = 704
EPISODES = 128
PRELUDE_CALLS = 256
FILLER_CALLS = 256
TRAIN_CALLS = 256
PROBE_CALLS = 1
WARMUP_BLOCKS = 44
MAX_U32 = (1 << 32) - 1
FNV_OFFSET = 14695981039346656037
FNV_PRIME = 1099511628211
TIMER = "lfence_rdtsc_lfence"
PROTOCOL = "balanced_filler_position"
COMPILER = "msvc_O2"
FIXED_TOLERANCE = 1.0  # TSC ticks per complete single-call probe.


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
    """Replay C's xorshift32, Fisher-Yates, and position-balanced rotation."""
    state = seed
    base: list[int] = []
    orders: list[tuple[str, ...]] = []
    schedule_hash = FNV_OFFSET

    def next_random() -> int:
        nonlocal state
        value = state
        value ^= (value << 13) & MAX_U32
        value ^= value >> 17
        value ^= (value << 5) & MAX_U32
        state = value & MAX_U32
        return state

    def block_order(block: int, store: bool) -> None:
        nonlocal base, schedule_hash
        if block % len(KINDS) == 0:
            base = list(range(len(KINDS)))
            for index in range(len(KINDS) - 1, 0, -1):
                other = next_random() % (index + 1)
                base[index], base[other] = base[other], base[index]
        if store:
            order = tuple(KINDS[base[(position + block % len(KINDS)) %
                                     len(KINDS)]] for position in range(len(KINDS)))
            orders.append(order)
            for kind in order:
                schedule_hash = ((schedule_hash ^ KIND_INDEX[kind]) *
                                 FNV_PRIME) & MAX_U64

    for block in range(warmup_blocks):
        block_order(block, False)
    for block in range(blocks):
        block_order(block, True)
    return orders, schedule_hash


def _address(value: str) -> int:
    if not re.fullmatch(r"0x[0-9a-fA-F]+", value) or int(value, 16) == 0:
        raise ValueError("invalid address")
    return int(value, 16)


def expected_sink() -> int:
    """Architectural return-value checksum, including the small timer chain."""
    per_block = 0
    for kind in KINDS:
        if "_timer_" in kind:
            train, probe = 0, int(kind[-1])
            small_work = 8 if "_timer_small_p1" in kind else 0
        else:
            train = int(kind.split("_t")[1][0])
            probe = int(kind[-1])
            small_work = 0
        per_block += EPISODES * (
            PRELUDE_CALLS // 2 + FILLER_CALLS // 2 +
            TRAIN_CALLS * train + PROBE_CALLS * probe + small_work)
    return (per_block * (BLOCKS + WARMUP_BLOCKS)) & MAX_U32


def parse_trace(content: str) -> Trace:
    cpu: dict[str, str] | None = None
    run: dict[str, str] | None = None
    end: dict[str, str] | None = None
    host: dict[str, str] | None = None
    sha256: str | None = None
    affinity: int | None = None
    raw: list[tuple[int, int, str, int]] = []
    checksum = 0
    for original in content.splitlines():
        row = original.strip()
        if row.startswith("HOST_AFFINITY_CPU="):
            if affinity is not None or cpu is not None:
                raise ValueError("duplicate or late affinity")
            affinity = unsigned(row.split("=", 1)[1], "affinity")
        elif row.startswith("DECAY_CPU,"):
            if affinity is None or cpu is not None:
                raise ValueError("duplicate or premature CPU")
            cpu = fields(row, "DECAY_CPU")
        elif row.startswith("DECAY_RUN,"):
            if cpu is None or run is not None:
                raise ValueError("duplicate or premature RUN")
            run = fields(row, "DECAY_RUN")
        elif row.startswith("DECAY_SAMPLE,"):
            if run is None or end is not None:
                raise ValueError("sample outside open run")
            parts = row.split(",")
            if len(parts) != 6:
                raise ValueError("malformed sample")
            index = unsigned(parts[1], "sample index")
            block = unsigned(parts[2], "block")
            position = unsigned(parts[3], "position")
            kind = parts[4]
            ticks = unsigned(parts[5], "ticks")
            if index != len(raw) or kind not in KIND_INDEX:
                raise ValueError("sample order or kind")
            if block != index // len(KINDS) or position != index % len(KINDS):
                raise ValueError("invalid sample block or position")
            if not ticks:
                raise ValueError("zero probe duration")
            raw.append((block, position, kind, ticks))
            checksum = (checksum + (index + 1) * ticks + block + position +
                        KIND_INDEX[kind]) & MAX_U64
        elif row.startswith("DECAY_END,"):
            if run is None or end is not None:
                raise ValueError("duplicate or premature END")
            end = fields(row, "DECAY_END")
        elif row.startswith("DECAY_HOST,"):
            if end is None or host is not None or sha256 is not None:
                raise ValueError("duplicate or premature HOST")
            host = fields(row, "DECAY_HOST")
        elif row.startswith("DECAY_BINARY,"):
            if host is None or sha256 is not None:
                raise ValueError("duplicate or premature BINARY")
            binary = fields(row, "DECAY_BINARY")
            if set(binary) != {"sha256"} or not re.fullmatch(
                    r"[0-9a-f]{64}", binary["sha256"]):
                raise ValueError("invalid binary SHA256")
            sha256 = binary["sha256"]
        else:
            raise ValueError(f"unexpected trace line: {row[:60]}")

    if None in (cpu, run, end, host, sha256, affinity):
        raise ValueError("incomplete decay trace")
    assert cpu is not None and run is not None and end is not None
    assert host is not None and sha256 is not None and affinity is not None
    if set(cpu) != {"vendor", "signature", "invariant_tsc", "hypervisor"} or \
       not cpu["vendor"] or cpu["invariant_tsc"] != "1" or \
       cpu["hypervisor"] not in ("0", "1"):
        raise ValueError("invalid CPU metadata")
    _address(cpu["signature"])
    if set(run) != {"version", "blocks", "conditions", "episodes",
                    "prelude_calls", "filler_calls", "train_calls",
                    "probe_calls", "warmup_blocks", "seed", "lags",
                    "branch_addr", "small_addr", "timer", "protocol",
                    "compiler", "schedule_hash"}:
        raise ValueError("invalid run metadata")
    if run["version"] != "1" or run["lags"] != "0_16_64_256" or \
       run["timer"] != TIMER or run["protocol"] != PROTOCOL or \
       run["compiler"] != COMPILER:
        raise ValueError("unexpected trace version or protocol")
    if (_address(run["branch_addr"]) == _address(run["small_addr"])):
        raise ValueError("branch and work addresses coincide")
    for label, expected in (
        ("blocks", BLOCKS), ("conditions", len(KINDS)),
        ("episodes", EPISODES), ("prelude_calls", PRELUDE_CALLS),
        ("filler_calls", FILLER_CALLS), ("train_calls", TRAIN_CALLS),
        ("probe_calls", PROBE_CALLS), ("warmup_blocks", WARMUP_BLOCKS),
    ):
        if unsigned(run[label], label) != expected:
            raise ValueError(f"invalid {label} dimension")
    seed = unsigned(run["seed"], "seed")
    if not 0 < seed <= MAX_U32:
        raise ValueError("invalid seed")
    if set(end) != {"count", "checksum", "sink"} or \
       len(raw) != BLOCKS * len(KINDS) or \
       unsigned(end["count"], "count") != len(raw) or \
       unsigned(end["checksum"], "checksum") != checksum:
        raise ValueError("sample count or checksum mismatch")
    if unsigned(end["sink"], "sink") != expected_sink():
        raise ValueError("architectural sink checksum mismatch")
    if set(host) != {"windows_build", "run_utc"} or \
       unsigned(host["windows_build"], "Windows build") == 0 or \
       not re.fullmatch(r"\d{8}T\d{6}Z", host["run_utc"]):
        raise ValueError("invalid host metadata")
    try:
        datetime.strptime(host["run_utc"], "%Y%m%dT%H%M%SZ")
    except ValueError as exc:
        raise ValueError("invalid timestamp") from exc
    orders, expected_hash = replay_schedule(BLOCKS, seed)
    if unsigned(run["schedule_hash"], "schedule hash") != expected_hash:
        raise ValueError("schedule hash mismatch")
    positions = {kind: [0] * len(KINDS) for kind in KINDS}
    blocks: list[dict[str, int]] = []
    for block in range(BLOCKS):
        rows = raw[block * len(KINDS):(block + 1) * len(KINDS)]
        order = tuple(kind for _, _, kind, _ in rows)
        if order != orders[block] or len(set(order)) != len(KINDS):
            raise ValueError(f"order mismatch in block {block}")
        for _, position, kind, _ in rows:
            positions[kind][position] += 1
        blocks.append({kind: ticks for _, _, kind, ticks in rows})
    if any(count != BLOCKS // len(KINDS) for counts in positions.values()
           for count in counts):
        raise ValueError("condition-position balance mismatch")
    return Trace(cpu, run, host, sha256, affinity, blocks)


def _summary(values: list[int], seed: int) -> dict[str, object]:
    low, high = interval(values, seed=seed, cycle_size=len(KINDS))
    scale = EPISODES
    return {
        "paired_trimmed_mean_ticks_per_probe": trimmed_mean(values) / scale,
        "paired_median_ticks_per_probe": median(values) / scale,
        "within_run_cycle_bootstrap_95_ticks_per_probe": (low / scale, high / scale),
        "positive_blocks": sum(value > 0 for value in values),
        "total_blocks": len(values),
    }


def summarize(trace: Trace) -> dict[str, object]:
    blocks = trace.blocks
    outcomes: dict[str, dict[str, object]] = {}
    adjusted_values: dict[tuple[int, int], list[int]] = {}
    fixed_within_tolerance: dict[str, bool] = {}
    for lag in LAGS:
        for probe in (0, 1):
            pair = (1, 0) if probe == 0 else (0, 1)
            def difference(block: dict[str, int], arm: str) -> int:
                return (block[f"l{lag}_{arm}_t{pair[0]}_p{probe}"] -
                        block[f"l{lag}_{arm}_t{pair[1]}_p{probe}"])
            real = [difference(b, "real") for b in blocks]
            fixed = [difference(b, "fixed") for b in blocks]
            adjusted = [a - f for a, f in zip(real, fixed)]
            adjusted_values[(lag, probe)] = adjusted
            key = f"p{probe}_l{lag}"
            fixed_summary = _summary(fixed, 0xD420 + lag * 2 + probe)
            low, high = fixed_summary[
                "within_run_cycle_bootstrap_95_ticks_per_probe"]
            fixed_within_tolerance[key] = -FIXED_TOLERANCE <= low and \
                high <= FIXED_TOLERANCE
            outcomes[key] = {
                "real_mismatch_minus_match": _summary(
                    real, 0xD310 + lag * 2 + probe),
                "fixed_mismatch_minus_match": fixed_summary,
                "real_minus_fixed": _summary(
                    adjusted, 0xD520 + lag * 2 + probe),
            }
    for lag in LAGS[1:]:
        for probe in (0, 1):
            key = f"p{probe}_l{lag}"
            values = [a - b for a, b in zip(
                adjusted_values[(lag, probe)], adjusted_values[(0, probe)])]
            outcomes[key]["minus_l0"] = _summary(values, 0xD900 + lag * 2 + probe)
    controls: dict[str, dict[str, object]] = {}
    all_controls_pass = True
    for lag in TIMER_LAGS:
        for probe in (0, 1):
            fast = f"l{lag}_timer_fast_p{probe}"
            key = f"p{probe}_l{lag}"
            small = _summary(
                [b[f"l{lag}_timer_small_p{probe}"] - b[fast] for b in blocks],
                0xDA00 + lag * 2 + probe)
            pause = _summary(
                [b[f"l{lag}_timer_pause_p{probe}"] - b[fast] for b in blocks],
                0xDB00 + lag * 2 + probe)
            slow_low, _ = pause[
                "within_run_cycle_bootstrap_95_ticks_per_probe"]
            small_low, small_high = small[
                "within_run_cycle_bootstrap_95_ticks_per_probe"]
            small_point = small["paired_trimmed_mean_ticks_per_probe"]
            coarse_pass = (pause["positive_blocks"] / pause["total_blocks"] >= 0.95
                           and slow_low > 0)
            small_pass = (small_low > 0 and small_high < 8 and
                          1 <= small_point <= 8)
            controls[key] = {
                "pause_minus_fast": pause, "small_minus_fast": small,
                "coarse_pass": coarse_pass, "few_tick_pass": small_pass,
            }
            all_controls_pass &= coarse_pass and small_pass
    return {
        "outcomes": outcomes,
        "timer_controls": controls,
        "timer_controls_pass": all_controls_pass,
        "fixed_trainer_practical_tolerance_ticks_per_probe": FIXED_TOLERANCE,
        "fixed_trainer_within_tolerance": fixed_within_tolerance,
        "fixed_trainer_all_within_tolerance": all(fixed_within_tolerance.values()),
        "observed_tick_gcd": reduce(gcd, (
            value for block in blocks for value in block.values())),
        "total_recorded_site_calls": (
            BLOCKS * len(KINDS) * EPISODES *
            (PRELUDE_CALLS + FILLER_CALLS + TRAIN_CALLS + PROBE_CALLS)),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("trace", type=Path)
    parser.add_argument("--strict", action="store_true",
                        help="fail on timer sensitivity or fixed-trainer diagnostic")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    try:
        trace = parse_trace(args.trace.read_text(encoding="utf-8"))
    except (OSError, ValueError, KeyError) as exc:
        parser.exit(2, f"Invalid decay trace: {exc}\n")
    result = summarize(trace)
    if args.json:
        print(json.dumps({
            "cpu": trace.cpu, "run": trace.run, "host": trace.host,
            "affinity_cpu": trace.affinity_cpu,
            "binary_sha256": trace.binary_sha256, **result,
        }, sort_keys=True))
    else:
        print(f"CPU: {trace.cpu['vendor']} {trace.cpu['signature']}; "
              f"hypervisor={trace.cpu['hypervisor']}")
        print(f"Validated {len(trace.blocks)} randomized complete blocks; "
              f"{trace.run['episodes']} episodes per condition; "
              f"{result['total_recorded_site_calls']:,} recorded branch-site calls")
        print(f"Seed {trace.run['seed']}; binary SHA256 {trace.binary_sha256}; "
              f"observed TSC GCD {result['observed_tick_gcd']}")
        for key, control in result["timer_controls"].items():
            small = control["small_minus_fast"]
            pause = control["pause_minus_fast"]
            print(f"Timer {key}: small {small['paired_trimmed_mean_ticks_per_probe']:+.2f} "
                  f"[{small['within_run_cycle_bootstrap_95_ticks_per_probe'][0]:+.2f},"
                  f"{small['within_run_cycle_bootstrap_95_ticks_per_probe'][1]:+.2f}], "
                  f"PAUSE {pause['paired_trimmed_mean_ticks_per_probe']:+.2f}; "
                  f"few-tick {'PASS' if control['few_tick_pass'] else 'INCONCLUSIVE'}, "
                  f"coarse {'PASS' if control['coarse_pass'] else 'INCONCLUSIVE'}")
        for probe in (0, 1):
            for lag in LAGS:
                key = f"p{probe}_l{lag}"
                row = result["outcomes"][key]
                value = row["real_minus_fixed"]
                low, high = value["within_run_cycle_bootstrap_95_ticks_per_probe"]
                print(f"Intervening balanced branches {key}: "
                      f"real-minus-fixed mismatch contrast "
                      f"{value['paired_trimmed_mean_ticks_per_probe']:+.3f} "
                      f"[{low:+.3f}, {high:+.3f}] ticks per one-call probe; "
                      f"fixed diagnostic "
                      f"{'within' if result['fixed_trainer_within_tolerance'][key] else 'outside'} "
                      f"±{FIXED_TOLERANCE:g}")
                if lag:
                    diff = row["minus_l0"]
                    low, high = diff[
                        "within_run_cycle_bootstrap_95_ticks_per_probe"]
                    print(f"  vs same-outcome L0, paired within block: "
                          f"{diff['paired_trimmed_mean_ticks_per_probe']:+.3f} "
                          f"[{low:+.3f}, {high:+.3f}] ticks/probe")
        print("Timing associations are exploratory within-run comparisons. "
              "Moving filler also changes outer loop boundaries and prior activity. "
              "No predictor retention depth, misprediction count or privilege "
              "sharing follows from these data.")
    return 1 if args.strict and (
        not result["timer_controls_pass"] or
        not result["fixed_trainer_all_within_tolerance"]) else 0


if __name__ == "__main__":
    raise SystemExit(main())
