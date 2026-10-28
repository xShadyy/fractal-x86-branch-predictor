#!/usr/bin/env python3
"""Validate paired Windows branch trials and summarize cache effects."""

from __future__ import annotations

import argparse
from dataclasses import dataclass
import json
from pathlib import Path
import random
from statistics import median

from analyze_cache_probe import MAX_U64, fields, select_threshold, unsigned


KINDS = ("train_taken", "train_not_taken", "hot", "cold")
KIND_INDEX = {name: index for index, name in enumerate(KINDS)}


@dataclass(frozen=True)
class Trace:
    cpu: dict[str, str]
    run: dict[str, str]
    blocks: list[dict[str, int]]


def parse_trace(content: str) -> Trace:
    cpu: dict[str, str] | None = None
    run: dict[str, str] | None = None
    end: dict[str, str] | None = None
    raw: list[tuple[int, int, str, int]] = []
    checksum = 0

    for line in content.splitlines():
        row = line.strip()
        if row.startswith("SPEC_CPU,"):
            if cpu is not None or run is not None:
                raise ValueError("duplicate or late SPEC_CPU")
            cpu = fields(row, "SPEC_CPU")
        elif row.startswith("SPEC_RUN,"):
            if cpu is None or run is not None:
                raise ValueError("missing SPEC_CPU or duplicate SPEC_RUN")
            run = fields(row, "SPEC_RUN")
            if run.get("version") != "1":
                raise ValueError("unsupported trace version")
        elif row.startswith("SPEC_SAMPLE,"):
            if run is None or end is not None:
                raise ValueError("sample outside an open run")
            parts = row.split(",")
            if len(parts) != 6:
                raise ValueError("malformed SPEC_SAMPLE")
            index = unsigned(parts[1], "index")
            block = unsigned(parts[2], "block")
            position = unsigned(parts[3], "position")
            kind = parts[4]
            cycles = unsigned(parts[5], "cycles")
            if index != len(raw) or kind not in KIND_INDEX:
                raise ValueError("sample order or class mismatch")
            if block != index // 4 or position != index % 4:
                raise ValueError("invalid block or position")
            raw.append((block, position, kind, cycles))
            checksum = (checksum + (index + 1) * cycles + block + position +
                        KIND_INDEX[kind]) & MAX_U64
        elif row.startswith("SPEC_END,"):
            if run is None or end is not None:
                raise ValueError("unexpected SPEC_END")
            end = fields(row, "SPEC_END")

    if cpu is None or run is None or end is None:
        raise ValueError("incomplete branch trace")
    if not {"vendor", "signature", "clflush_bytes", "invariant_tsc"} <= cpu.keys():
        raise ValueError("missing CPU metadata")
    if not {"version", "blocks", "training", "warmup_blocks", "seed",
            "branch_addr", "timer", "flush"} <= run.keys():
        raise ValueError("missing run metadata")
    if unsigned(cpu["clflush_bytes"], "line size") == 0:
        raise ValueError("invalid CLFLUSH line size")
    unsigned(cpu["invariant_tsc"], "invariant TSC")
    if unsigned(run["training"], "training calls") == 0:
        raise ValueError("invalid training count")
    unsigned(run["warmup_blocks"], "warmup blocks")
    unsigned(run["seed"], "seed")
    count = unsigned(run["blocks"], "blocks")
    if count < 2 or count % 2 or len(raw) != count * 4:
        raise ValueError("missing or unbalanced blocks")
    if unsigned(end["count"], "sample count") != len(raw) or \
       unsigned(end["checksum"], "checksum") != checksum:
        raise ValueError("sample count or checksum mismatch")

    blocks: list[dict[str, int]] = []
    first_taken = 0
    for block in range(count):
        rows = raw[block * 4:(block + 1) * 4]
        classes = tuple(row[2] for row in rows)
        if set(classes[:2]) != set(KINDS[:2]) or classes[2:] != KINDS[2:]:
            raise ValueError(f"incorrect pair or controls in block {block}")
        first_taken += classes[0] == "train_taken"
        blocks.append({kind: cycles for _, _, kind, cycles in rows})
    if first_taken != count // 2:
        raise ValueError("unbalanced pair order")
    return Trace(cpu, run, blocks)


def paired_interval(differences: list[int], iterations: int = 2000) -> tuple[float, float]:
    rng = random.Random(0x7135)
    count = len(differences)
    estimates = sorted(sum(differences[rng.randrange(count)]
                           for _ in range(count)) / count
                       for _ in range(iterations))
    return estimates[int(iterations * 0.025)], estimates[int(iterations * 0.975)]


def summarize(trace: Trace) -> dict[str, object]:
    half = len(trace.blocks) // 2
    threshold = select_threshold(
        [block["hot"] for block in trace.blocks[:half]],
        [block["cold"] for block in trace.blocks[:half]],
    )
    hot_rate = sum(b["hot"] <= threshold for b in trace.blocks[half:]) / half
    cold_rate = sum(b["cold"] <= threshold for b in trace.blocks[half:]) / half
    taken = [b["train_taken"] for b in trace.blocks]
    not_taken = [b["train_not_taken"] for b in trace.blocks]
    taken_rate = sum(v <= threshold for v in taken) / len(taken)
    not_taken_rate = sum(v <= threshold for v in not_taken) / len(not_taken)
    paired = [(t <= threshold) - (n <= threshold)
              for t, n in zip(taken, not_taken)]
    return {
        "threshold": threshold,
        "control_hit_rates": {"hot": hot_rate, "cold": cold_rate},
        "controls_pass": hot_rate >= 0.95 and cold_rate <= 0.05,
        "probe_hit_rates": {"train_taken": taken_rate,
                            "train_not_taken": not_taken_rate},
        "probe_medians": {"train_taken": median(taken),
                          "train_not_taken": median(not_taken)},
        "paired_hit_difference": sum(paired) / len(paired),
        "paired_bootstrap_95": paired_interval(paired),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("trace", type=Path)
    parser.add_argument("--strict", action="store_true",
                        help="fail if calibration controls do not separate")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    try:
        trace = parse_trace(args.trace.read_text(encoding="utf-8"))
    except (OSError, ValueError, KeyError) as exc:
        parser.exit(2, f"Invalid branch trace: {exc}\n")
    result = summarize(trace)
    if args.json:
        print(json.dumps({"cpu": trace.cpu, "run": trace.run, **result},
                         sort_keys=True))
    else:
        print(f"CPU: {trace.cpu['vendor']} signature {trace.cpu['signature']}")
        print(f"Validated {len(trace.blocks)} paired blocks; "
              f"calibration threshold: {result['threshold']} TSC ticks")
        control = result["control_hit_rates"]
        print(f"Held-out controls: hot {control['hot']:.1%}, "
              f"cold {control['cold']:.1%} "
              f"({'PASS' if result['controls_pass'] else 'INCONCLUSIVE'})")
        rates = result["probe_hit_rates"]
        medians = result["probe_medians"]
        for kind in KINDS[:2]:
            print(f"{kind:16s} median={medians[kind]:>6} "
                  f"hit rate={rates[kind]:.1%}")
        low, high = result["paired_bootstrap_95"]
        print(f"Paired hit-rate difference (taken - not taken): "
              f"{result['paired_hit_difference']:+.1%} "
              f"[within-run bootstrap 95%: {low:+.1%}, {high:+.1%}]")
    return 1 if args.strict and not result["controls_pass"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
