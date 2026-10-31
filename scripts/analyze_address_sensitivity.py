#!/usr/bin/env python3
"""Validate and analyze native Windows executable-site address comparisons.

This is an exploratory within-process latency study. A latency interaction does
not establish a predictor-table alias, speculative execution, or ASID sharing.
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


SITES = ("target", "same4k", "offset128")
KINDS = tuple(
    f"{arm}_{site}_t{train}_p{probe}"
    for site in SITES
    for arm in ("r", "f")
    for train in (0, 1)
    for probe in (0, 1)
) + tuple(
    f"s_t{train}_p{probe}" for train in (0, 1) for probe in (0, 1)
) + tuple(
    f"{timer}_p{probe}"
    for timer in ("fast", "small", "pause") for probe in (0, 1)
)
KIND_INDEX = {kind: index for index, kind in enumerate(KINDS)}
BLOCKS = 680
WARMUP_BLOCKS = 34
EPISODES = 128
PRELUDE_CALLS = 256
TRAIN_CALLS = 256
PROBE_CALLS = 1
MAX_U32 = (1 << 32) - 1
FNV_OFFSET = 14695981039346656037
FNV_PRIME = 1099511628211
TIMER = "lfence_rdtsc_lfence"
PROTOCOL = "rx_clone_address_sensitivity"
COMPILER = "msvc_O2"
FIXED_TOLERANCE = 1.0  # ticks per complete one-call probe

# One verified x64 function with no relocation or external target. Three RX
# copies are checked byte-for-byte by the producer before the first episode.
BRANCH_TEMPLATE = bytes.fromhex(
    "0f b6 01 44 0f b6 12 45 0f b6 18 45 85 db "
    "44 0f 45 d0 45 85 d2 74 01 90 c3"
)


@dataclass(frozen=True)
class Trace:
    cpu: dict[str, str]
    run: dict[str, str]
    host: dict[str, str]
    binary_sha256: str
    affinity_cpu: int
    blocks: list[dict[str, int]]


def _fnv_bytes(values: bytes) -> int:
    value = FNV_OFFSET
    for byte in values:
        value = ((value ^ byte) * FNV_PRIME) & MAX_U64
    return value


def replay_schedule(blocks: int, seed: int,
                    warmup_blocks: int = WARMUP_BLOCKS
                    ) -> tuple[list[tuple[str, ...]], int]:
    """Replay C xorshift32, Fisher-Yates and full condition-position cycles."""
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

    def one_block(block: int, store: bool) -> None:
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
        one_block(block, False)
    for block in range(blocks):
        one_block(block, True)
    return orders, schedule_hash


def expected_sink() -> int:
    per_block = 0
    for kind in KINDS:
        if kind.startswith("s_t"):
            train = int(kind[3])
            probe = int(kind[-1])
        elif kind.startswith(("r_", "f_")):
            train = int(kind.rsplit("_t", 1)[1][0])
            probe = int(kind[-1])
        else:
            train = 0
            probe = int(kind[-1])
        per_block += EPISODES * (PRELUDE_CALLS // 2 +
                                 TRAIN_CALLS * train + PROBE_CALLS * probe)
    return (per_block * (BLOCKS + WARMUP_BLOCKS)) & MAX_U32


def _address(value: str, name: str) -> int:
    if not re.fullmatch(r"0x[0-9a-fA-F]+", value) or int(value, 16) == 0:
        raise ValueError(f"invalid {name} address")
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
    for original in content.splitlines():
        row = original.strip()
        if row.startswith("HOST_AFFINITY_CPU="):
            if affinity is not None or cpu is not None:
                raise ValueError("duplicate or late affinity")
            affinity = unsigned(row.split("=", 1)[1], "affinity CPU")
        elif row.startswith("ADDR_CPU,"):
            if affinity is None or cpu is not None:
                raise ValueError("duplicate or premature CPU")
            cpu = fields(row, "ADDR_CPU")
        elif row.startswith("ADDR_RUN,"):
            if cpu is None or run is not None:
                raise ValueError("duplicate or premature RUN")
            run = fields(row, "ADDR_RUN")
        elif row.startswith("ADDR_SAMPLE,"):
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
                raise ValueError("sample index or kind mismatch")
            if block != index // len(KINDS) or position != index % len(KINDS):
                raise ValueError("sample block or position mismatch")
            if ticks == 0:
                raise ValueError("zero probe duration")
            raw.append((block, position, kind, ticks))
            checksum = (checksum + (index + 1) * ticks + block + position +
                        KIND_INDEX[kind]) & MAX_U64
        elif row.startswith("ADDR_END,"):
            if run is None or end is not None:
                raise ValueError("duplicate or premature END")
            end = fields(row, "ADDR_END")
        elif row.startswith("ADDR_HOST,"):
            if end is None or host is not None or binary_sha256 is not None:
                raise ValueError("duplicate or premature HOST")
            host = fields(row, "ADDR_HOST")
        elif row.startswith("ADDR_BINARY,"):
            if host is None or binary_sha256 is not None:
                raise ValueError("duplicate or premature BINARY")
            binary = fields(row, "ADDR_BINARY")
            if set(binary) != {"sha256"} or not re.fullmatch(
                    r"[0-9a-f]{64}", binary["sha256"]):
                raise ValueError("invalid EXE SHA-256")
            binary_sha256 = binary["sha256"]
        else:
            raise ValueError(f"unexpected trace row: {row[:60]}")

    if any(value is None for value in (affinity, cpu, run, end, host, binary_sha256)):
        raise ValueError("incomplete address-sensitivity trace")
    assert cpu is not None and run is not None and end is not None
    assert host is not None and binary_sha256 is not None and affinity is not None
    if set(cpu) != {"vendor", "signature", "invariant_tsc", "hypervisor"} or \
       not cpu["vendor"] or cpu["invariant_tsc"] != "1" or \
       cpu["hypervisor"] not in ("0", "1"):
        raise ValueError("invalid CPU metadata")
    _address(cpu["signature"], "CPU signature")
    fields_needed = {
        "version", "blocks", "episodes", "prelude_calls", "train_calls",
        "probe_calls", "warmup_blocks", "seed", "template_bytes",
        "template_hash", "template_addr", "branch_jcc_offset",
        "target_addr", "same4k_addr", "offset128_addr",
        "sham_addr", "mode_addr", "live_addr", "fixed_addr", "timer",
        "protocol", "compiler", "schedule_hash",
    }
    if set(run) != fields_needed:
        raise ValueError("invalid run metadata")
    if (run["version"], run["timer"], run["protocol"], run["compiler"]) != \
       ("1", TIMER, PROTOCOL, COMPILER):
        raise ValueError("unexpected protocol, timer, or compiler")
    if not BRANCH_TEMPLATE:
        raise ValueError("unfrozen executable branch template")
    if unsigned(run["template_bytes"], "template byte count") != len(BRANCH_TEMPLATE) or \
       unsigned(run["template_hash"], "template hash") != _fnv_bytes(BRANCH_TEMPLATE):
        raise ValueError("branch template commitment mismatch")
    if unsigned(run["branch_jcc_offset"], "branch JCC offset") != 21:
        raise ValueError("branch JCC offset mismatch")
    for name, expected in (
        ("blocks", BLOCKS), ("episodes", EPISODES),
        ("prelude_calls", PRELUDE_CALLS), ("train_calls", TRAIN_CALLS),
        ("probe_calls", PROBE_CALLS), ("warmup_blocks", WARMUP_BLOCKS),
    ):
        if unsigned(run[name], name) != expected:
            raise ValueError(f"invalid {name} dimension")
    seed = unsigned(run["seed"], "seed")
    if not 0 < seed <= MAX_U32:
        raise ValueError("invalid seed")
    addresses = {name: _address(run[name], name) for name in (
        "template_addr", "target_addr", "same4k_addr", "offset128_addr",
        "sham_addr", "mode_addr", "live_addr", "fixed_addr")}
    if len(set(addresses.values())) != len(addresses):
        raise ValueError("site/data addresses must be distinct")
    if addresses["same4k_addr"] - addresses["target_addr"] != 0x1000 or \
       addresses["offset128_addr"] - addresses["same4k_addr"] != 0x80 or \
       addresses["target_addr"] % 0x1000 != 0x100:
        raise ValueError("unexpected cloned site placement")
    if set(end) != {"count", "checksum", "sink"} or \
       len(raw) != BLOCKS * len(KINDS) or \
       unsigned(end["count"], "sample count") != len(raw) or \
       unsigned(end["checksum"], "sample checksum") != checksum:
        raise ValueError("sample count or checksum mismatch")
    if unsigned(end["sink"], "architectural sink") != expected_sink():
        raise ValueError("architectural sink mismatch")
    if set(host) != {"windows_build", "run_utc"} or \
       unsigned(host["windows_build"], "Windows build") == 0 or \
       not re.fullmatch(r"\d{8}T\d{6}Z", host["run_utc"]):
        raise ValueError("invalid host metadata")
    try:
        datetime.strptime(host["run_utc"], "%Y%m%dT%H%M%SZ")
    except ValueError as exc:
        raise ValueError("invalid run timestamp") from exc

    orders, replay_hash = replay_schedule(BLOCKS, seed)
    if unsigned(run["schedule_hash"], "schedule hash") != replay_hash:
        raise ValueError("schedule hash mismatch")
    position_counts = {kind: [0] * len(KINDS) for kind in KINDS}
    blocks: list[dict[str, int]] = []
    for block_index in range(BLOCKS):
        rows = raw[block_index * len(KINDS):(block_index + 1) * len(KINDS)]
        order = tuple(kind for _, _, kind, _ in rows)
        if order != orders[block_index] or len(set(order)) != len(KINDS):
            raise ValueError(f"condition order mismatch in block {block_index}")
        for _, position, kind, _ in rows:
            position_counts[kind][position] += 1
        blocks.append({kind: ticks for _, _, kind, ticks in rows})
    if any(n != BLOCKS // len(KINDS) for counts in position_counts.values()
           for n in counts):
        raise ValueError("condition-position imbalance")
    return Trace(cpu, run, host, binary_sha256, affinity, blocks)


def _summary(values: list[int], seed: int) -> dict[str, object]:
    low, high = interval(values, seed=seed, cycle_size=len(KINDS))
    return {
        "paired_trimmed_mean_ticks_per_probe": trimmed_mean(values) / EPISODES,
        "paired_median_ticks_per_probe": median(values) / EPISODES,
        "within_run_cycle_bootstrap_95_ticks_per_probe":
            (low / EPISODES, high / EPISODES),
        "positive_blocks": sum(v > 0 for v in values),
        "total_blocks": len(values),
    }


def summarize(trace: Trace) -> dict[str, object]:
    blocks = trace.blocks
    results: dict[str, object] = {}
    raw_adjusted: dict[tuple[str, int], list[int]] = {}
    fixed_gates: dict[str, bool] = {}
    for site_index, site in enumerate(SITES):
        for p in (0, 1):
            mismatch, match = ((1, 0) if p == 0 else (0, 1))
            differences = {
                arm: [b[f"{letter}_{site}_t{mismatch}_p{p}"] -
                      b[f"{letter}_{site}_t{match}_p{p}"] for b in blocks]
                for arm, letter in (("real", "r"), ("fixed", "f"))
            }
            adjusted = [r - f for r, f in zip(differences["real"],
                                                differences["fixed"])]
            raw_adjusted[(site, p)] = adjusted
            fixed = _summary(differences["fixed"], 0xF100 + site_index * 2 + p)
            low, high = fixed["within_run_cycle_bootstrap_95_ticks_per_probe"]
            gate = -FIXED_TOLERANCE <= low and high <= FIXED_TOLERANCE
            fixed_gates[f"{site}_p{p}"] = gate
            results[f"{site}_p{p}"] = {
                "real_mismatch_minus_match": _summary(
                    differences["real"], 0xF200 + site_index * 2 + p),
                "fixed_mismatch_minus_match": fixed,
                "real_minus_fixed": _summary(
                    adjusted, 0xF300 + site_index * 2 + p),
            }
    interactions: dict[str, object] = {}
    for p in (0, 1):
        mismatch, match = ((1, 0) if p == 0 else (0, 1))
        sham = [b[f"s_t{mismatch}_p{p}"] - b[f"s_t{match}_p{p}"]
                for b in blocks]
        results[f"sham_p{p}"] = _summary(sham, 0xF400 + p)
        for site_index, site in enumerate(SITES):
            real = [b[f"r_{site}_t{mismatch}_p{p}"] -
                    b[f"r_{site}_t{match}_p{p}"] for b in blocks]
            results[f"{site}_p{p}"]["real_minus_sham"] = _summary(
                [r - s for r, s in zip(real, sham)],
                0xF500 + site_index * 2 + p)
        for idx, (left, right) in enumerate((
            ("same4k", "offset128"),
            ("target", "same4k"),
            ("target", "offset128"),
        )):
            diffs = [a - b for a, b in zip(
                raw_adjusted[(left, p)], raw_adjusted[(right, p)])]
            interactions[f"{left}_minus_{right}_p{p}"] = _summary(
                diffs, 0xF600 + idx * 2 + p)

    controls: dict[str, object] = {}
    timer_passes = True
    for p in (0, 1):
        fast = f"fast_p{p}"
        small = _summary([b[f"small_p{p}"] - b[fast] for b in blocks],
                         0xF700 + p)
        pause = _summary([b[f"pause_p{p}"] - b[fast] for b in blocks],
                         0xF710 + p)
        small_low, small_high = small[
            "within_run_cycle_bootstrap_95_ticks_per_probe"]
        pause_low, _ = pause[
            "within_run_cycle_bootstrap_95_ticks_per_probe"]
        small_point = small["paired_trimmed_mean_ticks_per_probe"]
        small_pass = small_low > 0 and small_high < 8 and 1 <= small_point <= 8
        pause_pass = (pause_low > 0 and
                      pause["positive_blocks"] / pause["total_blocks"] >= 0.95)
        controls[f"p{p}"] = {
            "small_minus_fast": small,
            "pause_minus_fast": pause,
            "small_pass": small_pass,
            "pause_pass": pause_pass,
        }
        timer_passes &= small_pass and pause_pass
    return {
        "site_outcomes": results,
        "address_interactions": interactions,
        "timer_controls": controls,
        "timer_controls_pass": timer_passes,
        "fixed_tolerance_ticks_per_probe": FIXED_TOLERANCE,
        "fixed_within_tolerance": fixed_gates,
        "fixed_all_within_tolerance": all(fixed_gates.values()),
        "observed_tick_gcd": reduce(gcd, (
            value for block in blocks for value in block.values())),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("trace", type=Path)
    parser.add_argument("--strict", action="store_true",
                        help="fail if timer or fixed-decision controls are inconclusive")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    try:
        trace = parse_trace(args.trace.read_text(encoding="utf-8"))
    except (OSError, ValueError, KeyError) as exc:
        parser.exit(2, f"Invalid address-sensitivity trace: {exc}\n")
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
        print(f"Validated {len(trace.blocks)} complete blocks, "
              f"{len(KINDS)} site/trainer/timer conditions; "
              f"seed {trace.run['seed']}; EXE SHA256 {trace.binary_sha256}")
        print(f"RX sites: target={trace.run['target_addr']}, "
              f"same4k={trace.run['same4k_addr']}, "
              f"offset128={trace.run['offset128_addr']}; "
              f"observed GCD {result['observed_tick_gcd']} TSC ticks")
        for key, value in result["timer_controls"].items():
            small = value["small_minus_fast"]
            pause = value["pause_minus_fast"]
            print(f"Timer {key}: small {small['paired_trimmed_mean_ticks_per_probe']:+.3f} "
                  f"[{small['within_run_cycle_bootstrap_95_ticks_per_probe'][0]:+.3f},"
                  f"{small['within_run_cycle_bootstrap_95_ticks_per_probe'][1]:+.3f}], "
                  f"PAUSE {pause['paired_trimmed_mean_ticks_per_probe']:+.3f}; "
                  f"sensitivity {'PASS' if value['small_pass'] and value['pause_pass'] else 'INCONCLUSIVE'}")
        for p in (0, 1):
            for site in SITES:
                key = f"{site}_p{p}"
                row = result["site_outcomes"][key]["real_minus_fixed"]
                low, high = row["within_run_cycle_bootstrap_95_ticks_per_probe"]
                print(f"Site {site}, probe {p}: adjusted mismatch−match "
                      f"{row['paired_trimmed_mean_ticks_per_probe']:+.3f} "
                      f"[{low:+.3f}, {high:+.3f}] ticks/probe; fixed control "
                      f"{'PASS' if result['fixed_within_tolerance'][key] else 'INCONCLUSIVE'}")
            key = f"same4k_minus_offset128_p{p}"
            row = result["address_interactions"][key]
            low, high = row["within_run_cycle_bootstrap_95_ticks_per_probe"]
            print(f"Primary exploratory interaction {key}: "
                  f"{row['paired_trimmed_mean_ticks_per_probe']:+.3f} "
                  f"[{low:+.3f}, {high:+.3f}] ticks/probe")
        print("Address-dependent latency includes indirect-call and code-layout effects. "
              "This is not a predictor-table alias or ASID-isolation test.")
    return 1 if args.strict and (
        not result["timer_controls_pass"] or
        not result["fixed_all_within_tolerance"]) else 0


if __name__ == "__main__":
    raise SystemExit(main())
