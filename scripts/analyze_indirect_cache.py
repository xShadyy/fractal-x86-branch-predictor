#!/usr/bin/env python3
"""Strict raw-trace validation for the exploratory indirect target-cache pilot.

An architectural cache hit does not by itself prove speculative execution.
Only the receiver and trace-quality controls are gates in --strict mode.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from datetime import datetime
import json
from pathlib import Path
import random
import re
from statistics import median

from analyze_cache_probe import MAX_U64, fields, select_threshold, unsigned


KINDS = tuple(
    [f"{arm}_t{t}_p{p}" for arm in "rfs" for t in (0, 1) for p in (0, 1)]
    + [f"{arm}_p{p}" for arm in ("hot", "cold", "skip") for p in (0, 1)]
    + [f"skipr_t{t}_p{p}" for t in (0, 1) for p in (0, 1)]
)
KIND_INDEX = {name: i for i, name in enumerate(KINDS)}
BLOCKS = 220
EPISODES = 64
PRELUDE_CALLS = 128
TRAIN_CALLS = 256
WARMUP_BLOCKS = 22
FNV_OFFSET = 14695981039346656037
FNV_PRIME = 1099511628211
MAX_U32 = 2**32 - 1
PROTOCOL = "indirect_target_cache_receiver"


@dataclass(frozen=True)
class Trace:
    cpu: dict[str, str]
    run: dict[str, str]
    host: dict[str, str]
    binary_sha256: str
    affinity_cpu: int
    blocks: list[dict[str, tuple[int, ...]]]


def replay_schedule(blocks: int, seed: int, warmup: int = WARMUP_BLOCKS
                    ) -> tuple[list[tuple[str, ...]], int]:
    """Reconstruct xorshift32, including the discarded warmup permutations."""
    state = seed
    order: list[int] = []
    recorded: list[tuple[str, ...]] = []
    schedule_hash = FNV_OFFSET

    def random32() -> int:
        nonlocal state
        state ^= (state << 13) & MAX_U32
        state ^= state >> 17
        state ^= (state << 5) & MAX_U32
        state &= MAX_U32
        return state

    for count, store in ((warmup, False), (blocks, True)):
        for block in range(count):
            if block % len(KINDS) == 0:
                order = list(range(len(KINDS)))
                for index in range(len(KINDS) - 1, 0, -1):
                    other = random32() % (index + 1)
                    order[index], order[other] = order[other], order[index]
            if store:
                sequence = tuple(KINDS[order[(position + block % len(KINDS)) %
                                             len(KINDS)]] for position in range(len(KINDS)))
                recorded.append(sequence)
                for label in sequence:
                    schedule_hash = ((schedule_hash ^ KIND_INDEX[label]) * FNV_PRIME) & MAX_U64
    return recorded, schedule_hash


def expected_sink(blocks: int = BLOCKS, warmup: int = WARMUP_BLOCKS,
                  episodes: int = EPISODES, prelude: int = PRELUDE_CALLS,
                  training: int = TRAIN_CALLS) -> int:
    per_block = 0
    for kind in KINDS:
        if kind.startswith("skipr_"):
            _, train, _ = kind.split("_")
            train_bit = int(train[1])
            train_sum = (1 + train_bit) * training
            probe_sum = 0
        elif kind.startswith(("r_", "f_", "s_")):
            arm, train, probe = kind.split("_")
            train_bit, probe_bit = int(train[1]), int(probe[1])
            train_sum = (1 + train_bit) * training if arm != "f" else training * 3 // 2
            probe_sum = 1 + probe_bit
        else:
            arm, probe = kind.split("_")
            probe_bit = int(probe[1])
            train_sum = training * 3 // 2
            probe_sum = 0 if arm == "skip" else 1 + (1 - probe_bit if arm == "hot" else probe_bit)
        per_block += prelude * 3 // 2 + train_sum + probe_sum
    return (per_block * (blocks + warmup) * episodes) & MAX_U32


def _address(value: str, name: str) -> int:
    if re.fullmatch(r"0x[0-9a-fA-F]+", value) is None or int(value, 16) == 0:
        raise ValueError(f"invalid {name}")
    return int(value, 16)


def parse_trace(content: str) -> Trace:
    cpu = run = end = host = None
    binary_hash = None
    affinity = None
    rows: list[tuple[int, int, str, tuple[int, ...]]] = []
    checksum = 0
    for original in content.splitlines():
        row = original.strip()
        if row.startswith("HOST_AFFINITY_CPU="):
            if affinity is not None or cpu is not None:
                raise ValueError("duplicate or late affinity record")
            affinity = unsigned(row.split("=", 1)[1], "affinity CPU")
        elif row.startswith("ICACHE_CPU,"):
            if cpu is not None or run is not None or affinity is None:
                raise ValueError("duplicate, late or unpinned CPU record")
            cpu = fields(row, "ICACHE_CPU")
        elif row.startswith("ICACHE_RUN,"):
            if run is not None or cpu is None:
                raise ValueError("duplicate or premature run record")
            run = fields(row, "ICACHE_RUN")
        elif row.startswith("ICACHE_SAMPLE,"):
            if run is None or end is not None:
                raise ValueError("sample outside open run")
            parts = row.split(",")
            if len(parts) != 6:
                raise ValueError("malformed sample")
            index = unsigned(parts[1], "index")
            block = unsigned(parts[2], "block")
            position = unsigned(parts[3], "position")
            kind = parts[4]
            ticks = tuple(unsigned(value, "reload ticks") for value in parts[5].split(";"))
            if index != len(rows) or kind not in KIND_INDEX:
                raise ValueError("sample index or condition mismatch")
            if block != index // len(KINDS) or position != index % len(KINDS):
                raise ValueError("sample block or position mismatch")
            if run.get("episodes") != str(len(ticks)) or any(value == 0 for value in ticks):
                raise ValueError("missing, zero or surplus episode")
            checksum = ((checksum + index + 1 + block + position + KIND_INDEX[kind])
                        * FNV_PRIME) & MAX_U64
            for value in ticks:
                checksum = ((checksum ^ value) * FNV_PRIME) & MAX_U64
            rows.append((block, position, kind, ticks))
        elif row.startswith("ICACHE_END,"):
            if end is not None or run is None:
                raise ValueError("duplicate or premature end record")
            end = fields(row, "ICACHE_END")
        elif row.startswith("ICACHE_HOST,"):
            if end is None or host is not None or binary_hash is not None:
                raise ValueError("duplicate or premature host record")
            host = fields(row, "ICACHE_HOST")
        elif row.startswith("ICACHE_BINARY,"):
            if host is None or binary_hash is not None:
                raise ValueError("duplicate or premature binary record")
            binary = fields(row, "ICACHE_BINARY")
            if set(binary) != {"sha256"} or not re.fullmatch(r"[a-f0-9]{64}", binary["sha256"]):
                raise ValueError("invalid executable SHA256")
            binary_hash = binary["sha256"]
        else:
            raise ValueError(f"unexpected trace line: {row[:60]}")

    if any(value is None for value in (cpu, run, end, host, binary_hash, affinity)):
        raise ValueError("incomplete indirect cache trace")
    assert cpu is not None and run is not None and end is not None and host is not None
    assert affinity is not None and binary_hash is not None
    if set(cpu) != {"vendor", "signature", "clflush_bytes", "invariant_tsc", "hypervisor"} or not cpu["vendor"]:
        raise ValueError("invalid CPU metadata")
    _address(cpu["signature"], "CPU signature")
    if unsigned(cpu["clflush_bytes"], "CLFLUSH bytes") != 64 or \
       unsigned(cpu["invariant_tsc"], "invariant TSC") != 1 or \
       unsigned(cpu["hypervisor"], "hypervisor") not in (0, 1):
        raise ValueError("unsupported CPU or cache-line metadata")
    expected = {"version", "blocks", "episodes", "prelude_calls", "train_calls",
                "probe_calls", "warmup_blocks", "seed", "site_addr", "target0_addr",
                "target1_addr", "sham_addr", "data0_addr", "data1_addr", "slot_addr",
                "timer", "flush", "protocol", "compiler", "schedule_hash"}
    if set(run) != expected or run["version"] != "1" or \
       run["protocol"] != PROTOCOL or run["timer"] != "lfence_rdtsc_lfence" or \
       run["flush"] != "clflush_mfence" or run["compiler"] != "msvc_O2":
        raise ValueError("unsupported run version, metadata or protocol")
    for key, value in (("blocks", BLOCKS), ("episodes", EPISODES),
                       ("prelude_calls", PRELUDE_CALLS), ("train_calls", TRAIN_CALLS),
                       ("probe_calls", 1), ("warmup_blocks", WARMUP_BLOCKS)):
        if unsigned(run[key], key) != value:
            raise ValueError(f"unexpected {key}")
    seed = unsigned(run["seed"], "seed")
    if not 0 < seed <= MAX_U32:
        raise ValueError("seed must be nonzero uint32")
    addresses = {name: _address(run[name], name) for name in
                 ("site_addr", "target0_addr", "target1_addr", "sham_addr",
                  "data0_addr", "data1_addr", "slot_addr")}
    if len(set(addresses.values())) != len(addresses):
        raise ValueError("duplicate physical addresses")
    if addresses["target1_addr"] - addresses["target0_addr"] < 128 or \
       addresses["target0_addr"] // 64 == addresses["target1_addr"] // 64:
        raise ValueError("target bodies must use separate I-cache lines")
    if any(addresses[name] % 4096 for name in ("data0_addr", "data1_addr", "slot_addr")) or \
       any(abs(addresses[a] - addresses[b]) < 4096 for a, b in
           (("data0_addr", "data1_addr"), ("data0_addr", "slot_addr"),
            ("data1_addr", "slot_addr"))):
        raise ValueError("data and pointer-slot layout not isolated")
    orders, schedule_hash = replay_schedule(BLOCKS, seed)
    if unsigned(run["schedule_hash"], "schedule hash") != schedule_hash:
        raise ValueError("schedule hash mismatch")
    if len(rows) != BLOCKS * len(KINDS) or \
       unsigned(end.get("count", ""), "sample count") != len(rows) or \
       unsigned(end.get("checksum", ""), "checksum") != checksum:
        raise ValueError("sample count or checksum mismatch")
    if set(end) != {"count", "checksum", "sink"} or \
       unsigned(end["sink"], "architectural sink") != expected_sink(
           BLOCKS, WARMUP_BLOCKS, EPISODES, PRELUDE_CALLS, TRAIN_CALLS):
        raise ValueError("architectural sink mismatch")
    if set(host) != {"windows_build", "run_utc"}:
        raise ValueError("missing host metadata")
    unsigned(host["windows_build"], "Windows build")
    try:
        datetime.strptime(host["run_utc"], "%Y%m%dT%H%M%SZ")
    except ValueError as exc:
        raise ValueError("invalid UTC timestamp") from exc
    blocks: list[dict[str, tuple[int, ...]]] = []
    for block in range(BLOCKS):
        subset = rows[block * len(KINDS):(block + 1) * len(KINDS)]
        if tuple(item[2] for item in subset) != orders[block]:
            raise ValueError(f"seeded randomized order mismatch in block {block}")
        blocks.append({kind: ticks for _, _, kind, ticks in subset})
    return Trace(cpu, run, host, binary_hash, affinity, blocks)


def cycle_interval(values: list[float], iterations: int = 2000
                   ) -> tuple[float, float]:
    """Resample complete 22-block cycles, not the dependent episode rows."""
    if len(values) % len(KINDS):
        raise ValueError("incomplete cycle")
    cycles = [sum(values[i:i + len(KINDS)]) / len(KINDS)
              for i in range(0, len(values), len(KINDS))]
    rng = random.Random(0x513c)
    estimates = sorted(sum(cycles[rng.randrange(len(cycles))]
                           for _ in cycles) / len(cycles)
                       for _ in range(iterations))
    return estimates[int(iterations * .025)], estimates[int(iterations * .975)]


def summarize(trace: Trace) -> dict[str, object]:
    half = len(trace.blocks) // 2
    thresholds = {}
    control_rates: dict[str, float] = {}
    rates: dict[str, float] = {}
    medians: dict[str, float] = {}
    for probe in (0, 1):
        hot = f"hot_p{probe}"
        cold = f"cold_p{probe}"
        threshold = select_threshold(
            [v for block in trace.blocks[:half] for v in block[hot]],
            [v for block in trace.blocks[:half] for v in block[cold]],
        )
        thresholds[f"p{probe}"] = threshold
        for kind in KINDS:
            if kind.endswith(f"p{probe}"):
                heldout = [v for block in trace.blocks[half:] for v in block[kind]]
                rates[kind] = sum(v <= threshold for v in heldout) / len(heldout)
                medians[kind] = median(heldout)
        for kind in (hot, cold, f"skip_p{probe}",
                     f"skipr_t0_p{probe}", f"skipr_t1_p{probe}"):
            control_rates[kind] = rates[kind]

    gates_pass = all(control_rates[f"hot_p{p}"] >= .95 and
                     control_rates[f"cold_p{p}"] <= .05 and
                     control_rates[f"skip_p{p}"] <= .05 and
                     control_rates[f"skipr_t0_p{p}"] <= .05 and
                     control_rates[f"skipr_t1_p{p}"] <= .05 for p in (0, 1))

    contrasts: dict[str, dict[str, object]] = {}
    for p in (0, 1):
        threshold = thresholds[f"p{p}"]
        pair = {}
        for arm in "rfs":
            mismatch = f"{arm}_t{1 - p}_p{p}"
            match = f"{arm}_t{p}_p{p}"
            per_block = [sum(v <= threshold for v in block[mismatch]) / EPISODES -
                         sum(v <= threshold for v in block[match]) / EPISODES
                         for block in trace.blocks]
            pair[arm] = per_block
            contrasts[f"{arm}_p{p}"] = {
                "mismatch_minus_match": sum(per_block) / len(per_block),
                "cycle_bootstrap_95": cycle_interval(per_block),
            }
        for baseline in "fs":
            adjusted = [a - b for a, b in zip(pair["r"], pair[baseline])]
            contrasts[f"real_minus_{baseline}_p{p}"] = {
                "difference_of_differences": sum(adjusted) / len(adjusted),
                "cycle_bootstrap_95": cycle_interval(adjusted),
            }
    return {"thresholds": thresholds, "heldout_hit_rates": rates,
            "heldout_medians": medians, "controls_pass": gates_pass,
            "contrasts": contrasts,
            "interpretation": "Exploratory cache association; physical PE audit pending, no speculative execution claim"}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("trace", type=Path)
    parser.add_argument("--strict", action="store_true",
                        help="fail only if receiver/trace quality controls fail")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    try:
        trace = parse_trace(args.trace.read_text(encoding="utf-8-sig"))
        result = summarize(trace)
    except (OSError, ValueError, KeyError) as exc:
        parser.exit(2, f"Invalid indirect-cache pilot trace: {exc}\n")
    if args.json:
        print(json.dumps({"cpu": trace.cpu, "run": trace.run, "host": trace.host,
                          "binary_sha256": trace.binary_sha256, **result}, sort_keys=True))
    else:
        print(f"CPU: {trace.cpu['vendor']} {trace.cpu['signature']}; "
              f"hypervisor={trace.cpu['hypervisor']}; pinned logical CPU {trace.affinity_cpu}")
        print(f"Validated {len(trace.blocks)} complete blocks × {EPISODES} raw episodes; "
              f"seed {trace.run['seed']}")
        for p in (0, 1):
            rates = result["heldout_hit_rates"]
            print(f"Receiver target {1 - p}: threshold {result['thresholds'][f'p{p}']} ticks; "
                  f"held-out hot {rates[f'hot_p{p}']:.1%}, "
                  f"cold {rates[f'cold_p{p}']:.1%}, fixed no-call {rates[f'skip_p{p}']:.1%}, "
                  f"real train no-call t0/t1 "
                  f"{rates[f'skipr_t0_p{p}']:.1%}/{rates[f'skipr_t1_p{p}']:.1%}")
            for arm in "rfs":
                item = result["contrasts"][f"{arm}_p{p}"]
                low, high = item["cycle_bootstrap_95"]
                print(f"  {arm} mismatch - match: {item['mismatch_minus_match']:+.1%} "
                      f"[within-run 22-block cycle bootstrap 95%: {low:+.1%}, {high:+.1%}]")
            for baseline in "fs":
                item = result["contrasts"][f"real_minus_{baseline}_p{p}"]
                print(f"  real - {baseline} adjusted contrast: "
                      f"{item['difference_of_differences']:+.1%}")
        print("Receiver and schedule controls: " +
              ("PASS" if result["controls_pass"] else "INCONCLUSIVE"))
        print("Scientific status: exploratory cache association; linked-EXE physical "
              "audit pending; cache hits do not establish transient execution.")
        print(f"Binary SHA256: {trace.binary_sha256}")
    return 1 if args.strict and not result["controls_pass"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
