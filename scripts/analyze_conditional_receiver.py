#!/usr/bin/env python3
"""Validate the K1 conditional target-data receiver and held-out controls.

This is a same-process Windows user-mode assay. A hot target data line is not
by itself evidence of transient execution, a predictor mechanism or sharing
across security domains. Only the receiver apparatus is gated by --strict.
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


KINDS = tuple(f"{arm}_p{p}" for p in (0, 1) for arm in
              ("candidate_t0", "candidate_t1", "no_probe_t0", "no_probe_t1",
               "hot", "cold", "arch_load", "arch_skip"))
KIND_INDEX = {name: i for i, name in enumerate(KINDS)}
BLOCKS = 512
EPISODES = 64
PRELUDE_CALLS = 128
TRAIN_CALLS = 256
WARMUP_BLOCKS = 16
MAX_U32 = (1 << 32) - 1
FNV_OFFSET = 14695981039346656037
FNV_PRIME = 1099511628211
PROTOCOL = "conditional_target_data_receiver"
PRACTICAL_MARGIN = .05


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
    """Replay xorshift shuffles and 16-position rotations, including warmup."""
    state = seed
    orders: list[tuple[str, ...]] = []
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
                for index in range(len(KINDS) - 1, 0, -1):
                    other = next32() % (index + 1)
                    base[index], base[other] = base[other], base[index]
            if keep:
                order = tuple(KINDS[base[(position + block % len(KINDS)) %
                                         len(KINDS)]] for position in range(len(KINDS)))
                orders.append(order)
                for kind in order:
                    schedule_hash = ((schedule_hash ^ KIND_INDEX[kind]) * FNV_PRIME) & MAX_U64
    return orders, schedule_hash


def _address(value: str, name: str) -> int:
    if re.fullmatch(r"0x[0-9a-fA-F]+", value) is None or int(value, 16) == 0:
        raise ValueError(f"invalid {name}")
    return int(value, 16)


def expected_architecture(blocks: int = BLOCKS, episodes: int = EPISODES
                          ) -> tuple[int, int, int, int]:
    """Recorded sums of 1/2 target returns; warm-up totals are discarded."""
    prelude = blocks * episodes * 3072
    train = blocks * episodes * 6144
    probe = blocks * episodes * 12
    return prelude, train, probe, (prelude + train + probe) & MAX_U32


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
        elif row.startswith("KREC_CPU,"):
            if cpu is not None or run is not None or affinity is None:
                raise ValueError("duplicate, late or unpinned CPU record")
            cpu = fields(row, "KREC_CPU")
        elif row.startswith("KREC_RUN,"):
            if run is not None or cpu is None:
                raise ValueError("duplicate or premature run record")
            run = fields(row, "KREC_RUN")
        elif row.startswith("KREC_SAMPLE,"):
            if run is None or end is not None:
                raise ValueError("sample outside open run")
            parts = row.split(",")
            if len(parts) != 6:
                raise ValueError("malformed receiver sample")
            index = unsigned(parts[1], "sample index")
            block = unsigned(parts[2], "sample block")
            position = unsigned(parts[3], "sample position")
            kind = parts[4]
            if kind not in KIND_INDEX or index != len(rows):
                raise ValueError("sample index or label mismatch")
            if block != index // len(KINDS) or position != index % len(KINDS):
                raise ValueError("sample block or position mismatch")
            ticks = tuple(unsigned(value, "receiver ticks") for value in parts[5].split(";"))
            if len(ticks) != EPISODES or any(value == 0 for value in ticks):
                raise ValueError("missing, zero or extra episode")
            for tick in ticks:
                checksum = (checksum + (index + 1) * tick + block + position +
                            KIND_INDEX[kind]) & MAX_U64
            rows.append((block, position, kind, ticks))
        elif row.startswith("KREC_END,"):
            if end is not None or run is None:
                raise ValueError("duplicate or premature end record")
            end = fields(row, "KREC_END")
        elif row.startswith("KREC_HOST,"):
            if end is None or host is not None or binary_hash is not None:
                raise ValueError("duplicate or premature host record")
            host = fields(row, "KREC_HOST")
        elif row.startswith("KREC_BINARY,"):
            if host is None or binary_hash is not None:
                raise ValueError("duplicate or premature binary record")
            binary = fields(row, "KREC_BINARY")
            if set(binary) != {"sha256"} or not re.fullmatch(r"[0-9a-f]{64}", binary["sha256"]):
                raise ValueError("invalid binary SHA256")
            binary_hash = binary["sha256"]
        else:
            raise ValueError(f"unexpected receiver trace line: {row[:60]}")

    if any(value is None for value in (cpu, run, end, host, binary_hash, affinity)):
        raise ValueError("incomplete conditional receiver trace")
    assert cpu is not None and run is not None and end is not None and host is not None
    assert binary_hash is not None and affinity is not None
    if set(cpu) != {"vendor", "signature", "clflush_bytes", "invariant_tsc", "hypervisor"} or not cpu["vendor"]:
        raise ValueError("invalid CPU metadata")
    _address(cpu["signature"], "CPU signature")
    if unsigned(cpu["clflush_bytes"], "cache line size") != 64 or \
       unsigned(cpu["invariant_tsc"], "invariant TSC") != 1 or \
       unsigned(cpu["hypervisor"], "hypervisor") not in (0, 1):
        raise ValueError("unsupported CPU or cache line metadata")
    expected_run = {"version", "blocks", "conditions", "episodes", "prelude_calls",
                    "train_calls", "warmup_blocks", "seed", "branch_addr", "condition_addr",
                    "target0_addr", "target1_addr", "line0_addr", "line1_addr",
                    "timer", "flush", "protocol", "compiler", "schedule_hash"}
    if set(run) != expected_run or run["version"] != "1" or \
       run["protocol"] != PROTOCOL or run["timer"] != "lfence_rdtsc_lfence" or \
       run["flush"] != "clflush_mfence" or run["compiler"] != "msvc_O2":
        raise ValueError("unsupported run version, metadata or protocol")
    for field, expected in (("blocks", BLOCKS), ("conditions", len(KINDS)),
                            ("episodes", EPISODES), ("prelude_calls", PRELUDE_CALLS),
                            ("train_calls", TRAIN_CALLS),
                            ("warmup_blocks", WARMUP_BLOCKS)):
        if unsigned(run[field], field) != expected:
            raise ValueError(f"unexpected {field}")
    seed = unsigned(run["seed"], "seed")
    if not 0 < seed <= MAX_U32:
        raise ValueError("seed must be nonzero uint32")
    if affinity >= 64:
        raise ValueError("unsupported processor group affinity")
    addrs = {key: _address(run[key], key) for key in
             ("branch_addr", "target0_addr", "target1_addr", "condition_addr",
              "line0_addr", "line1_addr")}
    if len(set(addrs.values())) != len(addrs):
        raise ValueError("overlapping target or receiver addresses")
    data_addrs = (addrs["condition_addr"], addrs["line0_addr"], addrs["line1_addr"])
    if any(addr % 4096 for addr in data_addrs) or \
       any(abs(a-b) < 4096 for i, a in enumerate(data_addrs)
           for b in data_addrs[i+1:]):
        raise ValueError("condition and receiver lines must be on separate aligned pages")
    if addrs["target0_addr"] // 64 == addrs["target1_addr"] // 64:
        raise ValueError("branch target code shares a cache line")
    orders, schedule_hash = replay_schedule(BLOCKS, seed)
    if unsigned(run["schedule_hash"], "schedule hash") != schedule_hash:
        raise ValueError("schedule hash mismatch")
    if set(end) != {"count", "checksum", "sink", "prelude_total",
                    "train_total", "probe_total"} or \
       len(rows) != BLOCKS * len(KINDS) or \
       unsigned(end.get("count", ""), "sample count") != len(rows) or \
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
    try:
        if not re.fullmatch(r"\d{8}T\d{6}Z", host["run_utc"]):
            raise ValueError("bad timestamp shape")
        datetime.strptime(host["run_utc"], "%Y%m%dT%H%M%SZ")
    except ValueError as exc:
        raise ValueError("invalid run UTC timestamp") from exc
    blocks: list[dict[str, tuple[int, ...]]] = []
    for block in range(BLOCKS):
        subset = rows[block * len(KINDS):(block + 1) * len(KINDS)]
        if tuple(item[2] for item in subset) != orders[block]:
            raise ValueError(f"seeded condition order mismatch in block {block}")
        blocks.append({kind: ticks for _, _, kind, ticks in subset})
    return Trace(cpu, run, host, binary_hash, affinity, blocks)


def cycle_interval(values: list[float], seed: int,
                   iterations: int = 2000) -> tuple[float, float]:
    """Resample complete 16-block cycles, preserving pair and time balance."""
    if not values or len(values) % len(KINDS):
        raise ValueError("incomplete position cycles")
    size = len(KINDS)
    cycles = [sum(values[i:i + size]) / size for i in range(0, len(values), size)]
    rng = random.Random(seed)
    estimates = sorted(sum(cycles[rng.randrange(len(cycles))] for _ in cycles)
                       / len(cycles) for _ in range(iterations))
    return estimates[int(.025 * iterations)], estimates[int(.975 * iterations)]


def summarize(trace: Trace) -> dict[str, object]:
    """Thresholds on training half, apparatus and outcomes on held-out half."""
    half = len(trace.blocks) // 2
    if half % len(KINDS):
        raise ValueError("calibration split breaks position cycles")
    thresholds: dict[str, int] = {}
    rates: dict[str, float] = {}
    medians: dict[str, float] = {}
    outcomes: dict[str, dict[str, object]] = {}
    gates: dict[str, bool] = {}
    halves: dict[str, dict[str, float]] = {}
    for p in (0, 1):
        threshold = select_threshold(
            [v for block in trace.blocks[:half] for v in block[f"hot_p{p}"]],
            [v for block in trace.blocks[:half] for v in block[f"cold_p{p}"]],
        )
        thresholds[f"p{p}"] = threshold
        for kind in KINDS[8*p:8*p+8]:
            data = [v for block in trace.blocks[half:] for v in block[kind]]
            rates[kind] = sum(v <= threshold for v in data) / len(data)
            medians[kind] = median(data)
            halves[kind] = {
                "calibration_half_hit_rate": sum(v <= threshold for block in trace.blocks[:half]
                                                 for v in block[kind]) / (half * EPISODES),
                "heldout_half_hit_rate": rates[kind],
            }
        for control, comparator, limit in (("hot", ">=", .95), ("cold", "<=", .05),
                                           ("arch_load", ">=", .95),
                                           ("arch_skip", "<=", .05),
                                           ("no_probe_t0", "<=", .05),
                                           ("no_probe_t1", "<=", .05)):
            rate = rates[f"{control}_p{p}"]
            gates[f"{control}_p{p}"] = rate >= limit if comparator == ">=" else rate <= limit
        mismatch = f"candidate_t{1-p}_p{p}"
        match = f"candidate_t{p}_p{p}"
        nomismatch = f"no_probe_t{1-p}_p{p}"
        nomatch = f"no_probe_t{p}_p{p}"
        unadjusted = []
        baseline = []
        adjusted = []
        for block in trace.blocks[half:]:
            h = {key: sum(v <= threshold for v in block[key]) / EPISODES
                 for key in (mismatch, match, nomismatch, nomatch)}
            raw = h[mismatch] - h[match]
            neutral = h[nomismatch] - h[nomatch]
            unadjusted.append(raw)
            baseline.append(neutral)
            adjusted.append(raw - neutral)
        outcome: dict[str, object] = {}
        for label, values, seed in (("candidate_mismatch_minus_match", unadjusted, 0xC100+p),
                                    ("no_probe_mismatch_minus_match", baseline, 0xC110+p),
                                    ("adjusted", adjusted, 0xC120+p)):
            outcome[label] = {"hit_rate_difference": sum(values) / len(values),
                              "within_run_cycle_bootstrap_95": cycle_interval(values, seed),
                              "positive_blocks": sum(value > 0 for value in values),
                              "total_blocks": len(values)}
        outcomes[f"p{p}"] = outcome
    passed = all(gates.values())
    primary_low = outcomes["p0"]["adjusted"]["within_run_cycle_bootstrap_95"][0]
    return {
        "thresholds_ticks": thresholds,
        "heldout_hit_rates": rates,
        "heldout_median_ticks": medians,
        "half_hit_rates": halves,
        "apparatus_gates": gates,
        "apparatus_controls_pass": passed,
        "primary_endpoint": "adjusted_p0",
        "primary_practical_margin_hit_rate_difference": PRACTICAL_MARGIN,
        "primary_candidate_association": (primary_low > PRACTICAL_MARGIN) if passed else None,
        "outcomes": outcomes,
        "interpretation": "Same-process conditional target-data receiver; one-run association alone cannot establish speculation or a privilege effect.",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("trace", type=Path)
    parser.add_argument("--strict", action="store_true",
                        help="fail only when receiver controls fail; a null outcome is valid")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    try:
        trace = parse_trace(args.trace.read_text(encoding="utf-8-sig"))
        result = summarize(trace)
    except (OSError, KeyError, ValueError) as exc:
        parser.exit(2, f"Invalid conditional receiver trace: {exc}\n")
    if args.json:
        print(json.dumps({"cpu": trace.cpu, "run": trace.run, "host": trace.host,
                          "binary_sha256": trace.binary_sha256,
                          "affinity_cpu": trace.affinity_cpu, **result}, sort_keys=True))
    else:
        print(f"K1 receiver: {len(trace.blocks)} complete blocks; {EPISODES} raw episodes per condition; seed {trace.run['seed']}")
        print(f"CPU {trace.cpu['vendor']} {trace.cpu['signature']}; hypervisor={trace.cpu['hypervisor']}; pinned logical CPU {trace.affinity_cpu}")
        for p in (0, 1):
            s = f"p{p}"; rates = result["heldout_hit_rates"]
            print(f"target {1-p}: threshold {result['thresholds_ticks'][s]} ticks; hot {rates['hot_'+s]:.1%}, cold {rates['cold_'+s]:.1%}, arch-load {rates['arch_load_'+s]:.1%}, arch-skip {rates['arch_skip_'+s]:.1%}")
            print(f"  no-probe t0/t1: {rates['no_probe_t0_'+s]:.1%}/{rates['no_probe_t1_'+s]:.1%}; gates {'PASS' if all(result['apparatus_gates'][g+'_'+s] for g in ('hot','cold','arch_load','arch_skip','no_probe_t0','no_probe_t1')) else 'INCONCLUSIVE'}")
            outcome = result["outcomes"][s]
            for name in ("candidate_mismatch_minus_match", "no_probe_mismatch_minus_match", "adjusted"):
                value = outcome[name]; lo, hi = value["within_run_cycle_bootstrap_95"]
                print(f"  {name}: {value['hit_rate_difference']:+.1%} [{lo:+.1%},{hi:+.1%}] within-run 16-block cycle bootstrap 95%")
        print("All receiver apparatus gates: " + ("PASS" if result["apparatus_controls_pass"] else "INCONCLUSIVE"))
        if result["primary_candidate_association"] is None:
            print("Primary candidate classification WITHHELD: receiver controls failed.")
        else:
            print("Predeclared p0 candidate train-label association beyond +5 percentage points: " +
                  ("present within this run" if result["primary_candidate_association"]
                   else "not detected"))
        print("Target data-cache association alone does not prove transient execution; linked instruction audit and independent replication remain required.")
        print(f"Binary SHA256: {trace.binary_sha256}")
    return int(args.strict and not result["apparatus_controls_pass"])


if __name__ == "__main__":
    raise SystemExit(main())
