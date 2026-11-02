#!/usr/bin/env python3
"""Descriptive K3 diagnostics. Never change its frozen gates or discard episodes."""
from __future__ import annotations

import argparse
import json
from math import gcd
from pathlib import Path
from statistics import mean

from analyze_fresh_receiver import Trace, parse_trace, summarize


def diagnose(trace: Trace, result: dict) -> dict:
    half = int(trace.run["blocks"]) // 2
    split = max(1, int(trace.run["episodes"]) // 4)
    heldout = [s for s in trace.samples if s.block >= half]
    profiles = {}
    for mode in ("nop", "cpuid"):
        profiles[mode] = {}
        for kind in result["heldout_hit_rates"][mode]:
            rows = [s for s in heldout if s.mode == mode and s.kind == kind]
            threshold = result["thresholds"][kind[-2:]]
            first = [s.wanted <= threshold for s in rows if s.occurrence < split]
            rest = [s.wanted <= threshold for s in rows if s.occurrence >= split]
            profiles[mode][kind] = {
                "first_quarter_count": len(first),
                "remaining_count": len(rest),
                "first_quarter_hit_rate": mean(first),
                "remaining_hit_rate": mean(rest) if rest else None,
            }
    tick_gcd = 0
    for s in trace.samples:
        tick_gcd = gcd(tick_gcd, s.wanted)
        tick_gcd = gcd(tick_gcd, s.decoy)
    failures = []
    for name, passed in result["gates"].items():
        if not passed:
            mode, kind, *decoy = name.split("/")
            rates = result["heldout_decoy_hit_rates" if decoy else "heldout_hit_rates"]
            failures.append({"gate": name, "observed_hit_rate": rates[mode][kind]})
    return {
        "study": result["study"],
        "status": "descriptive_only_no_reclassification",
        "failed_gates": failures,
        "episode_split": {"first": [0, split - 1],
                          "remaining": [split, int(trace.run["episodes"]) - 1]},
        "heldout_episode_profiles": profiles,
        "observed_tick_gcd": tick_gcd,
        "hypervisor_reported": trace.cpu["hypervisor"] == "1",
        "interpretation": [
            "Episode-position differences are exploratory; all episodes remain in the frozen analysis.",
            "Architectural returns verify committed paths, not transient predictor targets.",
            "Hypervisor presence and a timing lattice do not identify the source of the cache hits.",
            "No linked-harness or physical-mechanism approval is inferred from these diagnostics.",
        ],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("trace", type=Path)
    parser.add_argument("--development", action="store_true")
    args = parser.parse_args()
    try:
        trace = parse_trace(args.trace.read_text(encoding="utf-8-sig"),
                            development=args.development)
        print(json.dumps(diagnose(trace, summarize(trace)), indent=2, sort_keys=True))
    except (OSError, ValueError, KeyError, TypeError) as exc:
        parser.exit(2, f"Invalid K3 evidence: {exc}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
