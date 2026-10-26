#!/usr/bin/env python3
"""Validate and summarize a Fractal x86 cache-probe serial trace."""

from __future__ import annotations

import argparse
from bisect import bisect_right
from dataclasses import dataclass
import json
from pathlib import Path
from statistics import median


CLASSES = ("hot", "cold", "branch_load", "branch_skip")
CLASS_INDEX = {name: index for index, name in enumerate(CLASSES)}
MAX_U64 = (1 << 64) - 1


@dataclass(frozen=True)
class Sample:
    index: int
    phase: str
    kind: str
    cycles: int


@dataclass(frozen=True)
class Trace:
    cpu: dict[str, str]
    run: dict[str, str]
    samples: list[Sample]


def fields(row: str, marker: str) -> dict[str, str]:
    parts = row.split(",")
    if parts[0] != marker:
        raise ValueError(f"expected {marker}")
    result: dict[str, str] = {}
    for part in parts[1:]:
        key, separator, value = part.partition("=")
        if not separator or not key or not value or key in result:
            raise ValueError(f"invalid {marker} field: {part!r}")
        result[key] = value
    return result


def unsigned(value: str, label: str) -> int:
    if not value.isascii() or not value.isdecimal():
        raise ValueError(f"invalid {label}: {value!r}")
    number = int(value)
    if number > MAX_U64:
        raise ValueError(f"{label} exceeds 64 bits")
    return number


def parse_trace(content: str) -> Trace:
    cpu: dict[str, str] | None = None
    run: dict[str, str] | None = None
    end: dict[str, str] | None = None
    samples: list[Sample] = []
    completed = False
    checksum = 0

    for original in content.splitlines():
        row = original.strip()
        if row.startswith("CACHE_CPU,"):
            if cpu is not None or run is not None:
                raise ValueError("duplicate or late CACHE_CPU")
            cpu = fields(row, "CACHE_CPU")
        elif row.startswith("CACHE_RUN,"):
            if cpu is None or run is not None:
                raise ValueError("missing CACHE_CPU or duplicate CACHE_RUN")
            run = fields(row, "CACHE_RUN")
            if run.get("version") != "1":
                raise ValueError("unsupported trace version")
        elif row.startswith("CACHE_SAMPLE,"):
            if run is None or end is not None:
                raise ValueError("sample outside an open run")
            columns = row.split(",")
            if len(columns) != 5:
                raise ValueError("malformed CACHE_SAMPLE")
            index = unsigned(columns[1], "sample index")
            phase, kind = columns[2:4]
            cycles = unsigned(columns[4], "cycles")
            if index != len(samples) or phase not in ("train", "validate"):
                raise ValueError("invalid sample order or phase")
            if kind not in CLASS_INDEX:
                raise ValueError(f"unknown class: {kind}")
            samples.append(Sample(index, phase, kind, cycles))
            checksum = (checksum + (index + 1) * cycles +
                        CLASS_INDEX[kind] + (phase == "validate")) & MAX_U64
        elif row.startswith("CACHE_END,"):
            if run is None or end is not None:
                raise ValueError("unexpected CACHE_END")
            end = fields(row, "CACHE_END")
        elif row == "FRACTAL_UTEST_OK: x86 cache controls completed":
            completed = True

    if cpu is None or run is None or end is None or not completed:
        raise ValueError("incomplete cache-probe trace")
    count = unsigned(end["count"], "sample count")
    if count != len(samples) or unsigned(end["checksum"], "checksum") != checksum:
        raise ValueError("sample count or checksum mismatch")
    per_class = unsigned(run["samples_per_class"], "samples per class")
    if per_class == 0 or per_class % 2:
        raise ValueError("samples per class must be positive and even")
    if len(samples) != per_class * len(CLASSES):
        raise ValueError("wrong number of samples")
    for kind in CLASSES:
        phases = [sample.phase for sample in samples if sample.kind == kind]
        if phases != ["train"] * (per_class // 2) + ["validate"] * (per_class // 2):
            raise ValueError(f"unbalanced or reordered phase for {kind}")
    return Trace(cpu, run, samples)


def select_threshold(hot: list[int], cold: list[int]) -> int:
    if not hot or not cold:
        raise ValueError("empty calibration class")
    values = sorted(set(hot + cold))
    candidates = [values[0] - 1]
    candidates.extend((left + right) // 2 for left, right in
                      zip(values, values[1:]))
    candidates.append(values[-1])
    ordered_hot, ordered_cold = sorted(hot), sorted(cold)
    midpoint = (median(hot) + median(cold)) / 2

    def rank(threshold: int) -> tuple[float, float]:
        hot_hit = bisect_right(ordered_hot, threshold) / len(hot)
        cold_miss = 1 - bisect_right(ordered_cold, threshold) / len(cold)
        return (hot_hit + cold_miss) / 2, -abs(threshold - midpoint)

    return max(candidates, key=rank)


def summarize(trace: Trace) -> dict[str, object]:
    groups = {
        (kind, phase): [sample.cycles for sample in trace.samples
                        if sample.kind == kind and sample.phase == phase]
        for kind in CLASSES for phase in ("train", "validate")
    }
    threshold = select_threshold(groups["hot", "train"],
                                 groups["cold", "train"])
    rates = {
        kind: sum(cycles <= threshold for cycles in groups[kind, "validate"])
              / len(groups[kind, "validate"])
        for kind in CLASSES
    }
    medians = {
        kind: median(groups[kind, "validate"])
        for kind in CLASSES
    }
    passed = (rates["hot"] >= 0.95 and rates["cold"] <= 0.05 and
              rates["branch_load"] >= 0.95 and
              rates["branch_skip"] <= 0.05)
    return {"threshold": threshold, "hit_rates": rates,
            "median_validate_cycles": medians, "controls_pass": passed}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("trace", type=Path, help="captured serial output")
    parser.add_argument("--json", action="store_true", help="emit a JSON summary")
    parser.add_argument("--strict", action="store_true",
                        help="fail if the held-out controls are inconclusive")
    args = parser.parse_args()
    try:
        trace = parse_trace(args.trace.read_text(encoding="utf-8"))
    except (OSError, ValueError, KeyError) as exc:
        parser.exit(2, f"Invalid cache-probe trace: {exc}\n")
    result = summarize(trace)
    if args.json:
        print(json.dumps({"cpu": trace.cpu, "run": trace.run,
                          "sample_count": len(trace.samples), **result},
                         sort_keys=True))
    else:
        print(f"CPU: {trace.cpu['vendor']} signature {trace.cpu['signature']}")
        print(f"Validated {len(trace.samples)} samples; threshold from training half: "
              f"{result['threshold']} TSC ticks")
        for kind in CLASSES:
            print(f"{kind:12s} held-out median={result['median_validate_cycles'][kind]:>6} "
                  f"hit rate={result['hit_rates'][kind]:.1%}")
        print("Architectural controls: " +
              ("PASS" if result["controls_pass"] else "INCONCLUSIVE"))
    return 1 if args.strict and not result["controls_pass"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
