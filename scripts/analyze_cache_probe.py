#!/usr/bin/env python3
"""Validate and summarize a Fractal x86 cache-probe serial trace."""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from pathlib import Path


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


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("trace", type=Path, help="captured serial output")
    args = parser.parse_args()
    try:
        trace = parse_trace(args.trace.read_text(encoding="utf-8"))
    except (OSError, ValueError, KeyError) as exc:
        parser.exit(2, f"Invalid cache-probe trace: {exc}\n")
    print(f"Validated {len(trace.samples)} samples from {trace.cpu['vendor']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
