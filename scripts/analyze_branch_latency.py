#!/usr/bin/env python3
"""Validate balanced branch latency traces and summarize paired contrasts."""

from __future__ import annotations

import argparse
from dataclasses import dataclass
import json
from pathlib import Path
import random
from statistics import median

from analyze_cache_probe import MAX_U64, fields, unsigned


KINDS = ("train0_probe0", "train1_probe0", "train0_probe1", "train1_probe1")
KIND_INDEX = {kind: index for index, kind in enumerate(KINDS)}


@dataclass(frozen=True)
class Trace:
    cpu: dict[str, str]
    run: dict[str, str]
    blocks: list[dict[str, int]]


def parse_trace(content: str) -> Trace:
    cpu: dict[str, str] | None = None
    run: dict[str, str] | None = None
    end: dict[str, str] | None = None
    rows: list[tuple[int, int, str, int]] = []
    checksum = 0
    for line in content.splitlines():
        row = line.strip()
        if row.startswith("HOST_AFFINITY_CPU=") and cpu is None:
            unsigned(row.split("=", 1)[1], "affinity CPU")
        elif row.startswith("LAT_CPU,"):
            if cpu is not None or run is not None:
                raise ValueError("duplicate or late LAT_CPU")
            cpu = fields(row, "LAT_CPU")
        elif row.startswith("LAT_RUN,"):
            if cpu is None or run is not None:
                raise ValueError("missing LAT_CPU or duplicate LAT_RUN")
            run = fields(row, "LAT_RUN")
            if run.get("version") != "1":
                raise ValueError("unsupported trace version")
        elif row.startswith("LAT_SAMPLE,"):
            if run is None or end is not None:
                raise ValueError("sample outside an open run")
            parts = row.split(",")
            if len(parts) != 6:
                raise ValueError("malformed LAT_SAMPLE")
            index = unsigned(parts[1], "index")
            block = unsigned(parts[2], "block")
            position = unsigned(parts[3], "position")
            kind = parts[4]
            ticks = unsigned(parts[5], "ticks")
            if index != len(rows) or block != index // 4 or position != index % 4:
                raise ValueError("sample order or block mismatch")
            if kind not in KIND_INDEX:
                raise ValueError("sample class mismatch")
            rows.append((block, position, kind, ticks))
            checksum = (checksum + (index + 1) * ticks + block + position +
                        KIND_INDEX[kind]) & MAX_U64
        elif row.startswith("LAT_END,"):
            if run is None or end is not None:
                raise ValueError("unexpected LAT_END")
            end = fields(row, "LAT_END")
        else:
            raise ValueError(f"unexpected trace line: {row[:60]}")

    if cpu is None or run is None or end is None:
        raise ValueError("incomplete latency trace")
    if not {"vendor", "signature", "invariant_tsc"} <= cpu.keys():
        raise ValueError("missing CPU metadata")
    if not {"version", "blocks", "training", "warmup_blocks", "seed",
            "branch_addr", "timer"} <= run.keys():
        raise ValueError("missing run metadata")
    unsigned(cpu["invariant_tsc"], "invariant TSC")
    if unsigned(run["training"], "training calls") == 0:
        raise ValueError("zero training calls")
    unsigned(run["warmup_blocks"], "warmup blocks")
    unsigned(run["seed"], "seed")
    blocks = unsigned(run["blocks"], "blocks")
    if blocks < 2 or len(rows) != blocks * 4:
        raise ValueError("missing blocks or samples")
    if unsigned(end["count"], "sample count") != len(rows) or \
       unsigned(end["checksum"], "checksum") != checksum:
        raise ValueError("sample count or checksum mismatch")
    parsed = []
    for block in range(blocks):
        samples = rows[block * 4:(block + 1) * 4]
        if {kind for _, _, kind, _ in samples} != set(KINDS):
            raise ValueError(f"unbalanced conditions in block {block}")
        parsed.append({kind: ticks for _, _, kind, ticks in samples})
    return Trace(cpu, run, parsed)


def trimmed_mean(values: list[int]) -> float:
    ordered = sorted(values)
    cut = len(ordered) // 10
    middle = ordered[cut:len(ordered) - cut] if cut else ordered
    return sum(middle) / len(middle)


def paired_interval(differences: list[int], iterations: int = 1000) -> tuple[float, float]:
    rng = random.Random(0x49b5)
    n = len(differences)
    estimates = sorted(trimmed_mean([differences[rng.randrange(n)]
                                     for _ in range(n)])
                       for _ in range(iterations))
    return estimates[int(iterations * 0.025)], estimates[int(iterations * 0.975)]


def summarize(trace: Trace) -> dict[str, object]:
    medians = {kind: median(block[kind] for block in trace.blocks)
               for kind in KINDS}
    contrasts = {}
    for probe, match, mismatch in ((0, KINDS[0], KINDS[1]),
                                   (1, KINDS[3], KINDS[2])):
        differences = [block[mismatch] - block[match] for block in trace.blocks]
        contrasts[str(probe)] = {
            "paired_median": median(differences),
            "paired_trimmed_mean": trimmed_mean(differences),
            "within_run_bootstrap_95": paired_interval(differences),
        }
    return {"medians": medians, "mismatch_minus_match": contrasts}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("trace", type=Path)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    try:
        trace = parse_trace(args.trace.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        parser.exit(2, f"Invalid latency trace: {exc}\n")
    result = summarize(trace)
    if args.json:
        print(json.dumps({"cpu": trace.cpu, "run": trace.run, **result},
                         sort_keys=True))
    else:
        print(f"CPU: {trace.cpu['vendor']} signature {trace.cpu['signature']}")
        print(f"Validated {len(trace.blocks)} balanced blocks at one branch site")
        for probe in (0, 1):
            match = f"train{probe}_probe{probe}"
            mismatch = f"train{1 - probe}_probe{probe}"
            contrast = result["mismatch_minus_match"][str(probe)]
            low, high = contrast["within_run_bootstrap_95"]
            print(f"probe={probe}: matched median {result['medians'][match]:.1f}, "
                  f"mismatched median {result['medians'][mismatch]:.1f} TSC ticks")
            print(f"  mismatch - match: paired median {contrast['paired_median']:+.1f}, "
                  f"trimmed mean {contrast['paired_trimmed_mean']:+.1f} "
                  f"[within-run bootstrap 95%: {low:+.1f}, {high:+.1f}] ticks")
        print("Timing difference alone does not identify a mispredicted branch.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
