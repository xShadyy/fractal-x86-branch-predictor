#!/usr/bin/env python3
"""Validate a prospective adjacent-pair B2 apparatus precision diagnostic.

This version tests the sensitivity and equivalence of timing controls after
the inconclusive B2 v2 pilot. It does not estimate any real-arm effect.
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


LENGTHS = (1, 16)
PAIR_MEMBERS = (("fast_a", "fast_b"), ("fast_c", "dose4"),
                ("fast_d", "pause"), ("fixed_t0", "fixed_t1"))
KINDS = tuple(
    f"{member}_p{p}_n{n}"
    for n in LENGTHS for p in (0, 1)
    for pair in PAIR_MEMBERS for member in pair
)
KIND_INDEX = {name: index for index, name in enumerate(KINDS)}
PAIRS = len(KINDS) // 2
EXPECTED_BLOCKS = 2560
EPISODES = 256
RESET_CALLS = 256
TRAIN_CALLS = 256
WARMUP_BLOCKS = 32
MAX_U32 = (1 << 32) - 1
FNV_OFFSET = 14695981039346656037
FNV_PRIME = 1099511628211
PROTOCOL = "b2_adjacent_pairs_precision"
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
    """Replay pair shuffles, seeded orientation and 32-position rotations."""
    state = seed
    base: list[int] = []
    orientations: list[int] = []
    orders: list[tuple[str, ...]] = []
    schedule_hash = FNV_OFFSET

    def random32() -> int:
        nonlocal state
        state ^= (state << 13) & MAX_U32
        state ^= state >> 17
        state ^= (state << 5) & MAX_U32
        state &= MAX_U32
        return state

    # A pair rotates through all 16 slots, and each member occupies both
    # within-pair positions by inverting orientation in the second half.
    # The RNG state spans warm-up and recording, but each starts at block 0.
    for count, store in ((warmup_blocks, False), (blocks, True)):
        for block in range(count):
            if block % len(KINDS) == 0:
                base = list(range(PAIRS))
                for index in range(PAIRS - 1, 0, -1):
                    other = random32() % (index + 1)
                    base[index], base[other] = base[other], base[index]
                orientations = [random32() & 1 for _ in range(PAIRS)]
            if store:
                order_list: list[str] = []
                for slot in range(PAIRS):
                    pair = base[(slot + block % PAIRS) % PAIRS]
                    first = orientations[pair] ^ int(block % len(KINDS) >= PAIRS)
                    order_list.extend((KINDS[2 * pair + first],
                                       KINDS[2 * pair + (first ^ 1)]))
                order = tuple(order_list)
                orders.append(order)
                for kind in order:
                    schedule_hash = ((schedule_hash ^ KIND_INDEX[kind]) * FNV_PRIME) & MAX_U64
    return orders, schedule_hash


def replay_pattern_hash(calls: int = RESET_CALLS) -> int:
    """Hash the 0011 prelude and fixed-decision streams in that order."""
    value = FNV_OFFSET
    for _ in range(2):
        for index in range(calls):
            value = ((value ^ ((index >> 1) & 1)) * FNV_PRIME) & MAX_U64
    return value


def _address(value: str, label: str) -> int:
    if re.fullmatch(r"0x[0-9a-fA-F]+", value) is None or int(value, 16) == 0:
        raise ValueError(f"invalid {label}")
    return int(value, 16)


def _expected_architecture(blocks: int) -> tuple[int, int, int]:
    """Totals include all recorded conditions; warm-up is intentionally reset."""
    prelude = blocks * len(KINDS) * EPISODES * RESET_CALLS // 2
    # Four fixed t=1 conditions per complete block, each returning live=1.
    training = blocks * 4 * EPISODES * TRAIN_CALLS
    # Eight probe=1 conditions per length stratum (six timers, two fixed).
    probing = blocks * 8 * EPISODES * sum(LENGTHS)
    return prelude, training, probing


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
        elif row.startswith("B2PREC_CPU,"):
            if cpu is not None or run is not None or affinity is None:
                raise ValueError("duplicate or late B2PREC_CPU")
            cpu = fields(row, "B2PREC_CPU")
        elif row.startswith("B2PREC_RUN,"):
            if cpu is None or run is not None:
                raise ValueError("missing B2PREC_CPU or duplicate B2PREC_RUN")
            run = fields(row, "B2PREC_RUN")
        elif row.startswith("B2PREC_SAMPLE,"):
            if run is None or end is not None:
                raise ValueError("sample outside open run")
            parts = row.split(",")
            if len(parts) != 6:
                raise ValueError("malformed B2PREC_SAMPLE")
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
        elif row.startswith("B2PREC_END,"):
            if run is None or end is not None:
                raise ValueError("duplicate or premature B2PREC_END")
            end = fields(row, "B2PREC_END")
        elif row.startswith("B2PREC_HOST,"):
            if end is None or host is not None or sha is not None:
                raise ValueError("duplicate or premature B2PREC_HOST")
            host = fields(row, "B2PREC_HOST")
        elif row.startswith("B2PREC_BINARY,"):
            if host is None or sha is not None:
                raise ValueError("duplicate or premature B2PREC_BINARY")
            binary = fields(row, "B2PREC_BINARY")
            if set(binary) != {"sha256"} or not re.fullmatch(r"[a-f0-9]{64}",
                                                             binary["sha256"]):
                raise ValueError("invalid binary SHA-256")
            sha = binary["sha256"]
        else:
            raise ValueError(f"unexpected trace line: {row[:60]}")

    if any(value is None for value in (cpu, run, end, host, sha, affinity)):
        raise ValueError("incomplete B2 precision trace")
    assert cpu is not None and run is not None and end is not None
    assert host is not None and sha is not None and affinity is not None
    if set(cpu) != {"vendor", "signature", "invariant_tsc", "hypervisor"} or not cpu["vendor"]:
        raise ValueError("invalid CPU metadata")
    if unsigned(cpu["invariant_tsc"], "invariant TSC") != 1 or \
       unsigned(cpu["hypervisor"], "hypervisor") not in (0, 1):
        raise ValueError("invalid CPU flags")
    _address(cpu["signature"], "CPU signature")
    expected_run = {"version", "blocks", "conditions", "pairs", "episodes", "reset_calls",
                    "train_calls", "probe_lengths", "warmup_blocks", "seed",
                    "branch_addr", "live_addr", "fixed_addr", "mode_addr",
                    "probe_addr", "prelude_addr", "timer", "protocol", "compiler",
                    "schedule_hash", "pattern_hash"}
    if set(run) != expected_run or run["version"] != "3":
        raise ValueError("invalid B2 precision run version or fields")
    addresses = [_address(run[name], name) for name in
                 ("branch_addr", "live_addr", "fixed_addr", "mode_addr",
                  "probe_addr", "prelude_addr")]
    if len(set(addresses)) != len(addresses):
        raise ValueError("code or data addresses coincide")
    if run["timer"] != TIMER or run["protocol"] != PROTOCOL or run["compiler"] != COMPILER:
        raise ValueError("unexpected timer, protocol or compiler")
    if (unsigned(run["blocks"], "blocks") != EXPECTED_BLOCKS or
        unsigned(run["conditions"], "conditions") != len(KINDS) or
        unsigned(run["pairs"], "pairs") != PAIRS or
        unsigned(run["episodes"], "episodes") != EPISODES or
        unsigned(run["reset_calls"], "reset calls") != RESET_CALLS or
        unsigned(run["train_calls"], "train calls") != TRAIN_CALLS or
        run["probe_lengths"] != "1:16" or
        unsigned(run["warmup_blocks"], "warm-up blocks") != WARMUP_BLOCKS):
        raise ValueError("unexpected protocol dimensions")
    seed = unsigned(run["seed"], "seed")
    if not 0 < seed <= MAX_U32:
        raise ValueError("invalid nonzero 32-bit seed")
    if unsigned(run["pattern_hash"], "pattern hash") != replay_pattern_hash():
        raise ValueError("pattern hash does not match fixed streams")
    if set(end) != {"count", "checksum", "sink", "prelude_total",
                    "train_total", "probe_total"}:
        raise ValueError("invalid B2 precision END fields")
    if unsigned(end["count"], "sample count") != len(raw) or \
       unsigned(end["checksum"], "checksum") != checksum:
        raise ValueError("sample count or checksum mismatch")
    expected_prelude, expected_train, expected_probe = _expected_architecture(EXPECTED_BLOCKS)
    if unsigned(end["prelude_total"], "prelude total") != expected_prelude or \
       unsigned(end["train_total"], "train total") != expected_train or \
       unsigned(end["probe_total"], "probe total") != expected_probe or \
       unsigned(end["sink"], "sink") != (expected_prelude + expected_train +
                                         expected_probe) & MAX_U32:
        raise ValueError("architectural output totals or sink mismatch")
    if set(host) != {"windows_build", "run_utc"} or \
       unsigned(host["windows_build"], "Windows build") == 0 or \
       not re.fullmatch(r"\d{8}T\d{6}Z", host["run_utc"]):
        raise ValueError("invalid host metadata")
    try:
        datetime.strptime(host["run_utc"], "%Y%m%dT%H%M%SZ")
    except ValueError as exc:
        raise ValueError("invalid UTC timestamp") from exc
    if affinity >= 64:
        raise ValueError("invalid processor group affinity CPU")
    if len(raw) != EXPECTED_BLOCKS * len(KINDS):
        raise ValueError("missing or extra B2 precision samples")
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
        "positive_fraction": sum(x > 0 for x in values) / len(values),
    }


def summarize(trace: Trace) -> dict[str, object]:
    """Apply frozen placebo, neutral, dose and PAUSE gates to adjacent pairs.

    Intervals are conditional on this run and cannot confirm a B2 effect.
    """
    controls: dict[str, dict[str, dict[str, object]]] = {}
    for n in LENGTHS:
        for p in (0, 1):
            suffix = f"p{p}_n{n}"
            stratum: dict[str, dict[str, object]] = {}
            for index, (name, comparator) in enumerate((
                ("fast_b", "fast_a"), ("dose4", "fast_c"),
                ("pause", "fast_d"),
            )):
                values = [row[f"{name}_{suffix}"] - row[f"{comparator}_{suffix}"]
                          for row in trace.blocks]
                result = _stats(values, 0xB600 + 32 * n + 8 * p + index)
                low, high = result["within_run_cycle_bootstrap_95_ticks_per_probe"]
                point = result["paired_trimmed_mean_ticks_per_probe"]
                if name == "fast_b":
                    result["passes"] = low > -1 and high < 1
                elif name == "pause":
                    result["passes"] = low > 0 and result["positive_fraction"] >= 0.95
                else:
                    result["passes"] = low > 0 and high < 8 and 1 <= point <= 8
                result["comparator"] = comparator
                stratum[name] = result
            # Adjacent fixed_t0/t1 conditions use the same fast timer; their
            # branch decisions follow fixed 0011 independent of live t.
            fixed = [row[f"fixed_t{1 - p}_{suffix}"] -
                     row[f"fixed_t{p}_{suffix}"] for row in trace.blocks]
            neutral = _stats(fixed, 0xB700 + 32 * n + p)
            low, high = neutral["within_run_cycle_bootstrap_95_ticks_per_probe"]
            neutral["passes"] = low > -1 and high < 1
            stratum["fixed_neutral"] = neutral
            controls[suffix] = stratum
    passes = all(row[gate]["passes"] for row in controls.values()
                 for gate in ("fast_b", "dose4", "pause", "fixed_neutral"))
    return {
        "controls": controls,
        "precision_controls_pass": passes,
        "observed_tick_gcd": reduce(gcd, (x for block in trace.blocks
                                           for x in block.values())),
        "interpretation": "Prospective adjacent-pair same-process precision diagnostic "
                          "following an inconclusive v2 pilot. No B2 outcome contrast.",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("trace", type=Path)
    parser.add_argument("--strict", action="store_true",
                        help="fail when any frozen apparatus control gate fails")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    try:
        trace = parse_trace(args.trace.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        parser.exit(2, f"Invalid B2 precision trace: {exc}\n")
    result = summarize(trace)
    if args.json:
        print(json.dumps({"cpu": trace.cpu, "run": trace.run, "host": trace.host,
                          "binary_sha256": trace.binary_sha256,
                          "affinity_cpu": trace.affinity_cpu, **result},
                         sort_keys=True))
    else:
        print(f"B2 precision diagnostic: {len(trace.blocks)} complete blocks; "
              f"{EPISODES} episodes/condition; binary SHA256 {trace.binary_sha256}")
        print(f"CPU {trace.cpu['vendor']} {trace.cpu['signature']}; "
              f"hypervisor={trace.cpu['hypervisor']}; "
              f"GCD of batch totals {result['observed_tick_gcd']} ticks")
        for suffix, control in result["controls"].items():
            for gate in ("fast_b", "dose4", "pause", "fixed_neutral"):
                value = control[gate]
                low, high = value["within_run_cycle_bootstrap_95_ticks_per_probe"]
                print(f"{suffix} {gate:13s} {value['paired_trimmed_mean_ticks_per_probe']:+.3f} "
                      f"[{low:+.3f},{high:+.3f}] ticks/probe; "
                      f"positive {value['positive_fraction']:.1%}; "
                      f"{'PASS' if value['passes'] else 'INCONCLUSIVE'}")
        print("All frozen apparatus gates: " +
              ("PASS" if result["precision_controls_pass"] else "INCONCLUSIVE"))
        print("Within-run estimates only. This diagnostic does not estimate "
              "a real-arm training contrast, count mispredictions, or establish "
              "cross-privilege sharing. Audit physical instructions in the archived EXE.")
    return int(args.strict and not result["precision_controls_pass"])


if __name__ == "__main__":
    raise SystemExit(main())
