#!/usr/bin/env python3
"""Replay K2 receiver-order trace and analyze frozen held-out comparisons.

The K2 primary tests whether a probe-associated skip hit rate rises on entry
to a grouped condition. A hit does not identify speculative execution or a
branch predictor mechanism. The original K1 result remains inconclusive.
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
from analyze_conditional_receiver import KINDS, KIND_INDEX


MODES = ("grouped", "interleaved")
MODE_INDEX = {name: i for i, name in enumerate(MODES)}
BLOCKS = 256
WARMUP_BLOCKS = 16
EPISODES = 64
PRELUDE_CALLS = 128
TRAIN_CALLS = 256
EARLY = 5
PRACTICAL_MARGIN = .10
MAX_U32 = (1 << 32) - 1
FNV_OFFSET = 14695981039346656037
FNV_PRIME = 1099511628211
PROTOCOL = "receiver_order_diagnostic"
PRIMARY = "grouped_arch_skip_p0_early5_minus_late59"


@dataclass(frozen=True)
class Trace:
    cpu: dict[str, str]
    run: dict[str, str]
    host: dict[str, str]
    binary_sha256: str
    affinity_cpu: int
    blocks: list[dict[str, dict[str, tuple[int, ...]]]]


def replay_schedule(blocks: int, seed: int, warmup: int = WARMUP_BLOCKS
                    ) -> tuple[list[tuple[tuple[str, str], tuple[str, ...]]], int]:
    """Replay randomized/rotated cells and the actual episode event order."""
    state = seed
    plans: list[tuple[tuple[str, str], tuple[str, ...]]] = []
    schedule_hash = FNV_OFFSET

    def next32() -> int:
        nonlocal state
        state ^= (state << 13) & MAX_U32
        state ^= state >> 17
        state ^= (state << 5) & MAX_U32
        state &= MAX_U32
        return state

    for count, keep in ((warmup, False), (blocks, True)):
        base: list[int] = []
        for block in range(count):
            if block % len(KINDS) == 0:
                base = list(range(len(KINDS)))
                for i in range(len(KINDS) - 1, 0, -1):
                    j = next32() % (i + 1)
                    base[i], base[j] = base[j], base[i]
            order = tuple(KINDS[base[(position + block % len(KINDS)) %
                                     len(KINDS)]] for position in range(len(KINDS)))
            first = (block + (seed & 1)) & 1
            modes = (MODES[first], MODES[first ^ 1])
            if not keep:
                continue
            plans.append((modes, order))
            for mode in modes:
                mode_id = MODE_INDEX[mode]
                if mode == "grouped":
                    events = ((kind, occurrence) for kind in order
                              for occurrence in range(EPISODES))
                else:
                    events = ((kind, occurrence) for occurrence in range(EPISODES)
                              for kind in order)
                for kind, occurrence in events:
                    tag = mode_id * 1024 + KIND_INDEX[kind] * 64 + occurrence
                    schedule_hash = ((schedule_hash ^ tag) * FNV_PRIME) & MAX_U64
    return plans, schedule_hash


def expected_architecture(blocks: int = BLOCKS, episodes: int = EPISODES
                          ) -> tuple[int, int, int, int]:
    """Sums of architectural 1/2 return values; warm-up is discarded."""
    prelude = blocks * len(MODES) * episodes * 3072
    train = blocks * len(MODES) * episodes * 6144
    probe = blocks * len(MODES) * episodes * 12
    return prelude, train, probe, (prelude + train + probe) & MAX_U32


def _address(value: str, name: str) -> int:
    if re.fullmatch(r"0x[0-9a-fA-F]+", value) is None or int(value, 16) == 0:
        raise ValueError(f"invalid {name}")
    return int(value, 16)


def parse_trace(content: str) -> Trace:
    cpu = run = end = host = None
    binary_hash = None
    affinity = None
    rows: list[tuple[int, str, int, str, tuple[int, ...]]] = []
    checksum = 0
    for original in content.splitlines():
        row = original.strip()
        if row.startswith("HOST_AFFINITY_CPU="):
            if affinity is not None or cpu is not None:
                raise ValueError("duplicate or late affinity record")
            affinity = unsigned(row.split("=", 1)[1], "affinity CPU")
        elif row.startswith("KORD_CPU,"):
            if cpu is not None or run is not None or affinity is None:
                raise ValueError("duplicate, late or unpinned CPU record")
            cpu = fields(row, "KORD_CPU")
        elif row.startswith("KORD_RUN,"):
            if run is not None or cpu is None:
                raise ValueError("duplicate or premature run record")
            run = fields(row, "KORD_RUN")
        elif row.startswith("KORD_SAMPLE,"):
            if run is None or end is not None:
                raise ValueError("sample outside open run")
            parts = row.split(",")
            if len(parts) != 7:
                raise ValueError("malformed K2 sample")
            index = unsigned(parts[1], "sample index")
            block = unsigned(parts[2], "sample block")
            mode = parts[3]
            position = unsigned(parts[4], "sample position")
            kind = parts[5]
            if index != len(rows) or mode not in MODE_INDEX or kind not in KIND_INDEX:
                raise ValueError("sample index, mode or label mismatch")
            if block != index // (len(MODES) * len(KINDS)) or \
               position != index % len(KINDS):
                raise ValueError("sample block or position mismatch")
            ticks = tuple(unsigned(value, "receiver ticks") for value in parts[6].split(";"))
            if len(ticks) != EPISODES or any(value == 0 for value in ticks):
                raise ValueError("missing, zero or extra episode")
            for tick in ticks:
                checksum = (checksum + (index + 1) * tick + block + MODE_INDEX[mode] +
                            position + KIND_INDEX[kind]) & MAX_U64
            rows.append((block, mode, position, kind, ticks))
        elif row.startswith("KORD_END,"):
            if end is not None or run is None:
                raise ValueError("duplicate or premature end record")
            end = fields(row, "KORD_END")
        elif row.startswith("KORD_HOST,"):
            if end is None or host is not None or binary_hash is not None:
                raise ValueError("duplicate or premature host record")
            host = fields(row, "KORD_HOST")
        elif row.startswith("KORD_BINARY,"):
            if host is None or binary_hash is not None:
                raise ValueError("duplicate or premature binary record")
            binary = fields(row, "KORD_BINARY")
            if set(binary) != {"sha256"} or not re.fullmatch(r"[0-9a-f]{64}", binary["sha256"]):
                raise ValueError("invalid binary SHA256")
            binary_hash = binary["sha256"]
        else:
            raise ValueError(f"unexpected K2 trace line: {row[:60]}")

    if any(value is None for value in (cpu, run, end, host, binary_hash, affinity)):
        raise ValueError("incomplete K2 trace")
    assert cpu is not None and run is not None and end is not None and host is not None
    assert binary_hash is not None and affinity is not None
    if set(cpu) != {"vendor", "signature", "clflush_bytes", "invariant_tsc", "hypervisor"} or \
       not cpu["vendor"]:
        raise ValueError("invalid CPU metadata")
    _address(cpu["signature"], "CPU signature")
    if unsigned(cpu["clflush_bytes"], "cache line size") != 64 or \
       unsigned(cpu["invariant_tsc"], "invariant TSC") != 1 or \
       unsigned(cpu["hypervisor"], "hypervisor") not in (0, 1):
        raise ValueError("unsupported CPU metadata")
    expected_run = {"version", "blocks", "modes", "conditions", "episodes", "prelude_calls",
                    "train_calls", "warmup_blocks", "seed", "branch_addr", "condition_addr",
                    "target0_addr", "target1_addr", "line0_addr", "line1_addr", "timer",
                    "flush", "protocol", "compiler", "schedule_hash"}
    if set(run) != expected_run or run["version"] != "1" or \
       run["protocol"] != PROTOCOL or run["timer"] != "lfence_rdtsc_lfence" or \
       run["flush"] != "clflush_mfence" or run["compiler"] != "msvc_O2":
        raise ValueError("unsupported run version, metadata or protocol")
    for name, expected in (("blocks", BLOCKS), ("modes", len(MODES)),
                           ("conditions", len(KINDS)), ("episodes", EPISODES),
                           ("prelude_calls", PRELUDE_CALLS), ("train_calls", TRAIN_CALLS),
                           ("warmup_blocks", WARMUP_BLOCKS)):
        if unsigned(run[name], name) != expected:
            raise ValueError(f"unexpected {name}")
    seed = unsigned(run["seed"], "seed")
    if not 0 < seed <= MAX_U32:
        raise ValueError("seed must be nonzero uint32")
    if affinity >= 64:
        raise ValueError("unsupported processor group affinity")
    addrs = {name: _address(run[name], name) for name in
             ("branch_addr", "target0_addr", "target1_addr", "condition_addr",
              "line0_addr", "line1_addr")}
    if len(set(addrs.values())) != len(addrs):
        raise ValueError("overlapping target or receiver addresses")
    data_addrs = (addrs["condition_addr"], addrs["line0_addr"], addrs["line1_addr"])
    if any(addr % 4096 for addr in data_addrs) or \
       any(abs(a - b) < 4096 for i, a in enumerate(data_addrs)
           for b in data_addrs[i + 1:]):
        raise ValueError("condition and receiver lines must be on separate aligned pages")
    if addrs["target0_addr"] // 64 == addrs["target1_addr"] // 64:
        raise ValueError("branch target code shares a cache line")
    plans, expected_hash = replay_schedule(BLOCKS, seed)
    if unsigned(run["schedule_hash"], "schedule hash") != expected_hash:
        raise ValueError("schedule hash mismatch")
    expected_rows = BLOCKS * len(MODES) * len(KINDS)
    if set(end) != {"count", "checksum", "sink", "prelude_total", "train_total",
                    "probe_total"} or len(rows) != expected_rows or \
       unsigned(end.get("count", ""), "sample count") != expected_rows or \
       unsigned(end.get("checksum", ""), "checksum") != checksum:
        raise ValueError("sample count or checksum mismatch")
    prelude, train, probe, sink = expected_architecture(BLOCKS, EPISODES)
    if (unsigned(end["prelude_total"], "prelude total") != prelude or
        unsigned(end["train_total"], "train total") != train or
        unsigned(end["probe_total"], "probe total") != probe or
        unsigned(end["sink"], "architectural sink") != sink):
        raise ValueError("architectural totals or sink mismatch")
    if set(host) != {"windows_build", "run_utc"}:
        raise ValueError("missing host metadata")
    unsigned(host["windows_build"], "Windows build")
    if re.fullmatch(r"\d{8}T\d{6}Z", host["run_utc"]) is None:
        raise ValueError("invalid run UTC timestamp")
    try:
        datetime.strptime(host["run_utc"], "%Y%m%dT%H%M%SZ")
    except ValueError as exc:
        raise ValueError("invalid run UTC timestamp") from exc
    blocks: list[dict[str, dict[str, tuple[int, ...]]]] = []
    for block, (mode_order, kind_order) in enumerate(plans):
        subset = rows[block * 32:(block + 1) * 32]
        mapped: dict[str, dict[str, tuple[int, ...]]] = {}
        for m, mode in enumerate(mode_order):
            cells = subset[m * 16:(m + 1) * 16]
            if tuple((item[1], item[2], item[3]) for item in cells) != \
               tuple((mode, pos, kind) for pos, kind in enumerate(kind_order)):
                raise ValueError(f"seeded mode or condition order mismatch in block {block}")
            mapped[mode] = {kind: ticks for _, _, _, kind, ticks in cells}
        blocks.append(mapped)
    return Trace(cpu, run, host, binary_hash, affinity, blocks)


def cycle_interval(values: list[float], seed: int,
                   iterations: int = 2000) -> tuple[float, float]:
    """Resample complete 16-block cycles, not individual dependent episodes."""
    if not values or len(values) % len(KINDS):
        raise ValueError("incomplete 16-block cycles")
    size = len(KINDS)
    cycles = [sum(values[i:i + size]) / size for i in range(0, len(values), size)]
    rng = random.Random(seed)
    estimates = sorted(sum(cycles[rng.randrange(len(cycles))] for _ in cycles) /
                       len(cycles) for _ in range(iterations))
    return estimates[int(.025 * iterations)], estimates[int(.975 * iterations)]


def _estimate(values: list[float], seed: int) -> dict[str, object]:
    return {"hit_rate_difference": sum(values) / len(values),
            "within_run_cycle_bootstrap_95": cycle_interval(values, seed),
            "positive_blocks": sum(value > 0 for value in values),
            "total_blocks": len(values)}


def summarize(trace: Trace) -> dict[str, object]:
    """Use the first half for calibration and the last half for outcomes."""
    half = len(trace.blocks) // 2
    if half % len(KINDS) or EPISODES <= EARLY:
        raise ValueError("calibration split or early/late window invalid")
    thresholds: dict[str, int] = {}
    rates: dict[str, dict[str, float]] = {mode: {} for mode in MODES}
    medians: dict[str, dict[str, float]] = {mode: {} for mode in MODES}
    halves: dict[str, dict[str, dict[str, float]]] = {mode: {} for mode in MODES}
    gates: dict[str, bool] = {}
    for p in (0, 1):
        hot = [tick for block in trace.blocks[:half] for mode in MODES
               for tick in block[mode][f"hot_p{p}"]]
        cold = [tick for block in trace.blocks[:half] for mode in MODES
                for tick in block[mode][f"cold_p{p}"]]
        threshold = select_threshold(hot, cold)
        thresholds[f"p{p}"] = threshold
        for mode in MODES:
            for kind in KINDS[8 * p:8 * p + 8]:
                calibration = [tick for block in trace.blocks[:half]
                               for tick in block[mode][kind]]
                heldout = [tick for block in trace.blocks[half:]
                           for tick in block[mode][kind]]
                rates[mode][kind] = sum(value <= threshold for value in heldout) / len(heldout)
                medians[mode][kind] = median(heldout)
                halves[mode][kind] = {
                    "calibration_half_hit_rate": sum(value <= threshold for value in calibration) /
                                                 len(calibration),
                    "heldout_half_hit_rate": rates[mode][kind],
                }
            for control, lower_bound in (("hot", True), ("cold", False),
                                         ("arch_load", True), ("no_probe_t0", False),
                                         ("no_probe_t1", False)):
                rate = rates[mode][f"{control}_p{p}"]
                gates[f"{mode}_{control}_p{p}"] = rate >= .95 if lower_bound else rate <= .05
    outcomes: dict[str, dict[str, object]] = {}
    for p in (0, 1):
        mode_diffs: dict[str, list[float]] = {}
        outcome: dict[str, object] = {}
        for mode in MODES:
            threshold = thresholds[f"p{p}"]
            values = []
            for block in trace.blocks[half:]:
                ticks = block[mode][f"arch_skip_p{p}"]
                early = sum(t <= threshold for t in ticks[:EARLY]) / EARLY
                late = sum(t <= threshold for t in ticks[EARLY:]) / (EPISODES - EARLY)
                values.append(early - late)
            mode_diffs[mode] = values
            outcome[f"{mode}_arch_skip_early_minus_late"] = _estimate(
                values, 0xC200 + 16 * p + MODE_INDEX[mode])
            outcome[f"{mode}_entry_differences_by_heldout_cycle"] = [
                sum(values[start:start + 16]) / 16
                for start in range(0, len(values), 16)
            ]
            outcome[f"{mode}_skip_full_cell_rates_by_heldout_cycle"] = [
                sum(tick <= threshold for block in trace.blocks[start:start + 16]
                    for tick in block[mode][f"arch_skip_p{p}"]) / (16 * EPISODES)
                for start in range(half, len(trace.blocks), 16)
            ]
        outcome["grouped_minus_interleaved_entry_effect"] = _estimate(
            [g - i for g, i in zip(mode_diffs["grouped"], mode_diffs["interleaved"])],
            0xC210 + p)
        outcome["grouped_candidate_mismatch_minus_match"] = _estimate(
            [sum(t <= thresholds[f"p{p}"] for t in block["grouped"][f"candidate_t{1-p}_p{p}"]) / EPISODES -
             sum(t <= thresholds[f"p{p}"] for t in block["grouped"][f"candidate_t{p}_p{p}"]) / EPISODES
             for block in trace.blocks[half:]], 0xC220 + p)
        outcome["interleaved_candidate_mismatch_minus_match"] = _estimate(
            [sum(t <= thresholds[f"p{p}"] for t in block["interleaved"][f"candidate_t{1-p}_p{p}"]) / EPISODES -
             sum(t <= thresholds[f"p{p}"] for t in block["interleaved"][f"candidate_t{p}_p{p}"]) / EPISODES
             for block in trace.blocks[half:]], 0xC230 + p)
        outcomes[f"p{p}"] = outcome
    passed = all(gates.values())
    primary = outcomes["p0"]["grouped_arch_skip_early_minus_late"]
    primary_low = primary["within_run_cycle_bootstrap_95"][0]
    return {"thresholds_ticks": thresholds,
            "heldout_hit_rates": rates,
            "heldout_median_ticks": medians,
            "half_hit_rates": halves,
            "apparatus_gates": gates,
            "apparatus_controls_pass": passed,
            "primary_endpoint": PRIMARY,
            "primary_practical_margin_hit_rate_difference": PRACTICAL_MARGIN,
            "primary_entry_association": (primary_low > PRACTICAL_MARGIN) if passed else None,
            "outcomes": outcomes,
            "interpretation": "Within-run same-process entry-associated cache heat only; no mechanism or cross-domain claim."}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("trace", type=Path)
    parser.add_argument("--strict", action="store_true",
                        help="fail only on invalid trace or failed apparatus gates")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    try:
        trace = parse_trace(args.trace.read_text(encoding="utf-8-sig"))
        result = summarize(trace)
    except (OSError, KeyError, ValueError) as exc:
        parser.exit(2, f"Invalid K2 receiver-order trace: {exc}\n")
    if args.json:
        print(json.dumps({"cpu": trace.cpu, "run": trace.run, "host": trace.host,
                          "binary_sha256": trace.binary_sha256,
                          "affinity_cpu": trace.affinity_cpu, **result}, sort_keys=True))
    else:
        print(f"K2 receiver order: {len(trace.blocks)} balanced blocks, {EPISODES} occurrences per cell/mode; seed {trace.run['seed']}")
        print(f"CPU {trace.cpu['vendor']} {trace.cpu['signature']}; hypervisor={trace.cpu['hypervisor']}; pinned logical CPU {trace.affinity_cpu}")
        print(f"Pooled first-half thresholds: p0={result['thresholds_ticks']['p0']}, p1={result['thresholds_ticks']['p1']} TSC ticks")
        for mode in MODES:
            for p in (0, 1):
                rates = result["heldout_hit_rates"][mode]
                print(f"{mode} p{p}: hot {rates[f'hot_p{p}']:.1%}, cold {rates[f'cold_p{p}']:.1%}, arch-load {rates[f'arch_load_p{p}']:.1%}, arch-skip {rates[f'arch_skip_p{p}']:.1%}, no-probe t0/t1 {rates[f'no_probe_t0_p{p}']:.1%}/{rates[f'no_probe_t1_p{p}']:.1%}")
        for p in (0, 1):
            for name in ("grouped_arch_skip_early_minus_late",
                         "interleaved_arch_skip_early_minus_late",
                         "grouped_minus_interleaved_entry_effect",
                         "grouped_candidate_mismatch_minus_match",
                         "interleaved_candidate_mismatch_minus_match"):
                item = result["outcomes"][f"p{p}"][name]
                low, high = item["within_run_cycle_bootstrap_95"]
                print(f"p{p} {name}: {item['hit_rate_difference']:+.1%} [{low:+.1%},{high:+.1%}] within-run 16-block-cycle bootstrap 95%")
        print("K2 apparatus controls: " + ("PASS" if result["apparatus_controls_pass"] else "INCONCLUSIVE"))
        if result["primary_entry_association"] is None:
            print("Primary classification WITHHELD: K2 apparatus controls failed.")
        else:
            print("Predeclared grouped p0 entry association beyond +10 percentage points: " +
                  ("present within this run" if result["primary_entry_association"] else "not detected"))
        print("Condition-entry cache heat does not identify speculation, a predictor circuit, or any privilege effect.")
        print(f"Binary SHA256: {trace.binary_sha256}")
    return int(args.strict and not result["apparatus_controls_pass"])


if __name__ == "__main__":
    raise SystemExit(main())
