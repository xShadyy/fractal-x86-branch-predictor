#!/usr/bin/env python3
"""Validate and analyze the frozen Windows user-mode causal receiver studies.

All intervals describe resampling within one process run. Runtime-byte,
schedule, CPL and timing checks do not establish a predictor mechanism,
independent boot replication, or user-to-kernel influence.
"""
from __future__ import annotations

import argparse
from dataclasses import dataclass
from datetime import datetime
import hashlib
import json
from pathlib import Path
import random
import re

from analyze_cache_probe import fields, select_threshold, unsigned
from causal_receiver_contract import BRANCH, CODE, MODES, code_for

BLOCKS, EPISODES, WARMUP = 512, 4, 8
PRELUDE, TRAIN, PAGES, STRIDE = 128, 256, 64, 4096
MASK32, MASK64 = (1 << 32) - 1, (1 << 64) - 1
FNV_OFFSET, FNV_PRIME = 14695981039346656037, 1099511628211
CLUSTER_BLOCKS, BOOTSTRAP_DRAWS, BOOTSTRAP_SEED = 16, 2048, 20261108
FAMILY_SIZE, FAMILY_ALPHA, PRACTICAL_MARGIN = 6, .05, .10
MEMBERS = ("candidate_t0", "candidate_t1", "no_probe_t0", "no_probe_t1",
           "hot", "cold", "arch_load", "warm_mismatch")
KINDS = tuple(f"{member}_p{p}" for p in (0, 1) for member in MEMBERS)
SCOPE = ("Windows user-mode single-process intervention study; not a privilege-boundary "
         "experiment, independent-boot replication, or proof of a predictor mechanism")


def average(values):
    return sum(values) / len(values)


def next32(state: int) -> int:
    state ^= (state << 13) & MASK32
    state ^= state >> 17
    state ^= (state << 5) & MASK32
    return state & MASK32


def mix(value: int, tag: int) -> int:
    return ((value ^ tag) * FNV_PRIME) & MASK64


def replay(study: str, blocks: int, episodes: int, seed: int):
    """Independently replay both RNG streams, including unrecorded warmup."""
    schedule, tags = seed, (seed ^ 0xa5f1523d) or 1
    modes = MODES[study]
    for count, keep in ((WARMUP, False), (blocks, True)):
        for block in range(count):
            mode_order = list(range(len(modes)))
            for i in range(len(modes) - 1, 0, -1):
                schedule = next32(schedule)
                j = schedule % (i + 1)
                mode_order[i], mode_order[j] = mode_order[j], mode_order[i]
            for mode in mode_order:
                for occurrence in range(episodes):
                    order = list(range(16))
                    for i in range(15, 0, -1):
                        schedule = next32(schedule)
                        j = schedule % (i + 1)
                        order[i], order[j] = order[j], order[i]
                    for position, kind in enumerate(order):
                        p = kind // 8
                        tags = next32(tags); tag0 = 1 + tags % 63
                        tags = next32(tags); tag1 = 1 + tags % 63
                        wanted = tag0 if p else tag1
                        tags = next32(tags); decoy = 1 + tags % 62
                        if decoy >= wanted:
                            decoy += 1
                        tags = next32(tags); first = tags & 1
                        if keep:
                            yield (block, modes[mode], position, KINDS[kind],
                                   occurrence, tag0, tag1, decoy, first)


@dataclass(frozen=True)
class Sample:
    block: int
    mode: str
    kind: str
    occurrence: int
    order: int
    wanted: int
    decoy: int


@dataclass(frozen=True)
class Trace:
    cpu: dict[str, str]
    run: dict[str, str]
    host: dict[str, str]
    binary_sha256: str | None
    samples: list[Sample]
    bindings: dict[str, dict[str, str]]
    observed_aux: int


def checked_fields(row: str, prefix: str, allowed: set[str]) -> dict[str, str]:
    result = fields(row, prefix)
    if set(result) != allowed:
        raise ValueError(f"missing or unexpected {prefix} fields")
    return result


def address(value: str, name: str, *, zero: bool = False) -> int:
    if re.fullmatch(r"0x[0-9a-fA-F]+", value) is None:
        raise ValueError(f"invalid hexadecimal {name}")
    result = int(value, 16)
    if result > MASK64 or (not zero and result == 0):
        raise ValueError(f"invalid {name}")
    return result


RUN_FIXED = dict(version="1", protocol="causal_receiver_v1", conditions="16",
    modes="5", warmup_blocks="8", prelude_calls="128", train_calls="256",
    history_prefix_branches="256", schedule="interleaved_modes_and_rounds",
    pages="64", stride="4096", timer="cpuid_outside_rdtscp_load_rdtscp_aux",
    binding="mode_installed_before_training", flush="all_public_and_sink_lines",
    prng="xorshift32_v1", checksum="fnv64_k5_timing_v1")
REGIONS = ("code", "condition", "token0", "token1", "bank0", "bank1", "sink0", "sink1")
RUN_FIELDS = set(RUN_FIXED) | {"study", "blocks", "episodes", "seed", "affinity_cpu", "platform"} | {
    f"{region}_addr" for region in REGIONS}
CPU_FIELDS = {"vendor", "signature", "clflush_bytes", "invariant_tsc", "rdtscp",
              "hypervisor", "ibs", "lfence_always_serializing", "cpuid_80000021_eax"}


def validate_run(run: dict[str, str], development: bool) -> None:
    if any(run.get(k) != v for k, v in RUN_FIXED.items()) or run.get("study") not in MODES:
        raise ValueError("run disagrees with the frozen causal receiver protocol")
    blocks, episodes = unsigned(run["blocks"], "blocks"), unsigned(run["episodes"], "episodes")
    seed = unsigned(run["seed"], "seed")
    if not 0 < seed <= MASK32 or blocks < 32 or blocks % 32 or blocks > BLOCKS:
        raise ValueError("invalid seed or balanced block dimensions")
    if not 1 <= episodes <= EPISODES:
        raise ValueError("invalid episode count")
    if run["platform"] == "windows":
        if (blocks, episodes) != (BLOCKS, EPISODES):
            raise ValueError("Windows collection dimensions changed")
    elif run["platform"] != "native_dev" or not development:
        raise ValueError("native development requires --development; not Windows evidence")
    if unsigned(run["affinity_cpu"], "affinity CPU") > 4095:
        raise ValueError("invalid affinity CPU")
    ranges = []
    for region in REGIONS:
        start = address(run[f"{region}_addr"], region)
        length = STRIDE * (PAGES if region.startswith(("bank", "sink")) else 1)
        if start % STRIDE or start + length > MASK64:
            raise ValueError("misaligned or overflowing memory region")
        ranges.append((start, start + length))
    ranges.sort()
    if any(left[1] > right[0] for left, right in zip(ranges, ranges[1:])):
        raise ValueError("code, condition, tokens, public or sink banks overlap")


def public_arch_load_expected(study: str, mode: str, p: int) -> bool:
    """ARCH_LOAD selects the bank queried by p: bank 1-p."""
    return not (study == "receiver" and
                (mode in ("ablate_both", "sink_both") or
                 mode == ("ablate_one" if p == 0 else "ablate_zero")))


def parse_trace(content: str, *, development: bool = False) -> Trace:
    cpu = run = end = host = None
    binary = None
    codes, bindings = set(), {}
    expected = None
    samples = []
    observed_aux = None
    checksum, event_hash = 0, FNV_OFFSET
    for original in content.splitlines():
        row = original.strip()
        if not row:
            continue
        if row.startswith("K7_CPU,"):
            if cpu is not None or run is not None:
                raise ValueError("duplicate or late CPU record")
            cpu = checked_fields(row, "K7_CPU", CPU_FIELDS)
            if (cpu["vendor"] != "AuthenticAMD" or cpu["rdtscp"] != "1" or
                cpu["clflush_bytes"] != "64" or cpu["invariant_tsc"] != "1" or
                any(cpu[key] not in ("0", "1") for key in
                    ("hypervisor", "ibs", "lfence_always_serializing")) or
                any(re.fullmatch(r"0x[0-9a-fA-F]{8}", cpu[key]) is None for key in
                    ("signature", "cpuid_80000021_eax"))):
                raise ValueError("invalid or unsupported CPU metadata")
        elif row.startswith("K7_RUN,"):
            if cpu is None or run is not None:
                raise ValueError("missing CPU or duplicate run")
            run = checked_fields(row, "K7_RUN", RUN_FIELDS)
            validate_run(run, development)
            expected = iter(replay(run["study"], int(run["blocks"]), int(run["episodes"]), int(run["seed"])))
        elif row.startswith("K7_CODE,"):
            if run is None or samples or end is not None:
                raise ValueError("late runtime code snapshot")
            record = checked_fields(row, "K7_CODE", {"mode", "hex"})
            mode = record["mode"]
            if mode in codes or record["hex"] != code_for(run["study"], mode).hex():
                raise ValueError("unexpected runtime code bytes or duplicate mode")
            codes.add(mode)
        elif row.startswith("K7_BIND,"):
            if run is None or samples or end is not None:
                raise ValueError("late runtime context binding")
            record = checked_fields(row, "K7_BIND", {"mode", "bank0_addr", "bank1_addr"})
            mode = record["mode"]
            if mode not in MODES[run["study"]] or mode in bindings:
                raise ValueError("unknown or duplicate context binding")
            source = "sink" if run["study"] == "receiver" and mode == "sink_both" else "bank"
            if any(address(record[f"bank{p}_addr"], "context binding") !=
                   address(run[f"{source}{p}_addr"], "expected binding") for p in (0, 1)):
                raise ValueError("public/private context binding mismatch")
            bindings[mode] = record
        elif row.startswith("K7_SAMPLE,"):
            if (expected is None or codes != set(MODES[run["study"]]) or
                set(bindings) != codes or end is not None):
                raise ValueError("sample outside complete code/context-audited run")
            columns = row.split(",")
            if len(columns) != 24 or unsigned(columns[1], "index") != len(samples):
                raise ValueError("malformed or reordered sample")
            try:
                plan = next(expected)
            except StopIteration:
                raise ValueError("extra sample") from None
            actual = (unsigned(columns[2], "block"), columns[3], unsigned(columns[4], "position"),
                      columns[5], *(unsigned(c, "episode or token") for c in columns[6:11]))
            if actual != plan:
                raise ValueError("schedule, episode or fresh-token replay mismatch")
            block, mode, position, kind, occurrence, tag0, tag1, decoy, order = plan
            wanted, other, prelude, train, probe = (unsigned(c, "timer or return") for c in columns[11:16])
            if not wanted or not other:
                raise ValueError("zero timer delta")
            kind_id = KINDS.index(kind)
            p, member = divmod(kind_id, 8)
            training = member & 1 if member < 4 else (1 - p if member == 7 else p)
            probed = member in (0, 1, 6, 7)
            expected_probe = 1 + p if member in (0, 1, 7) else (2 - p if member == 6 else 0)
            if (prelude, train, probe) != (PRELUDE * 3 // 2, TRAIN * (1 + training), expected_probe):
                raise ValueError("architectural path disagrees with intended probe")
            training_cpl, probe_cpl = (unsigned(c, "CPL") for c in columns[16:18])
            training_pc = address(columns[18], "training PC")
            probe_pc = address(columns[19], "probe PC", zero=True)
            expected_pc = address(run["code_addr"], "code") + BRANCH
            if (training_cpl != 3 or training_pc != expected_pc or
                probe_cpl != (3 if probed else 255) or probe_pc != (expected_pc if probed else 0)):
                raise ValueError("actual privilege or measured-site address mismatch")
            aux = [unsigned(c, "TSC_AUX") for c in columns[20:24]]
            if any(value > MASK32 for value in aux) or len(set(aux)) != 1:
                raise ValueError("TSC_AUX migration within an episode")
            if observed_aux is None:
                observed_aux = aux[0]
            elif aux[0] != observed_aux:
                raise ValueError("TSC_AUX changed despite pinned-core collection")
            samples.append(Sample(block, mode, kind, occurrence, order, wanted, other))
            checksum = mix(mix(mix(checksum, len(samples)), wanted), other)
            event_hash = mix(event_hash, MODES[run["study"]].index(mode) * 256 + kind_id * 16 + occurrence)
            event_hash = mix(event_hash, tag0 * 65536 + tag1 * 256 + decoy * 2 + order)
        elif row.startswith("K7_END,"):
            if run is None or end is not None:
                raise ValueError("unexpected end record")
            end = checked_fields(row, "K7_END", {"count", "checksum", "event_hash", "architecture_errors"})
            count = int(run["blocks"]) * 5 * 16 * int(run["episodes"])
            if (len(samples) != count or unsigned(end["count"], "count") != count or
                unsigned(end["checksum"], "checksum") != checksum or
                unsigned(end["event_hash"], "event hash") != event_hash or
                end["architecture_errors"] != "0"):
                raise ValueError("incomplete trace, checksum, event hash or architectural error")
        elif row.startswith("K7_HOST,"):
            if end is None or host is not None or binary is not None:
                raise ValueError("unexpected host record")
            host = checked_fields(row, "K7_HOST", {"windows_build", "run_utc"})
            unsigned(host["windows_build"], "Windows build")
            datetime.strptime(host["run_utc"], "%Y%m%dT%H%M%SZ")
        elif row.startswith("K7_BINARY,"):
            if end is None or host is None or binary is not None:
                raise ValueError("unexpected binary record")
            binary = checked_fields(row, "K7_BINARY", {"sha256"})["sha256"]
            if re.fullmatch(r"[0-9a-f]{64}", binary) is None:
                raise ValueError("invalid executable hash")
        else:
            raise ValueError(f"unexpected trace row: {row[:100]}")
    if (cpu is None or run is None or end is None or observed_aux is None or
        codes != set(MODES[run["study"]]) or set(bindings) != codes):
        raise ValueError("missing run, runtime code or context-binding records")
    if host is not None and binary is None:
        raise ValueError("incomplete optional host/executable provenance pair")
    return Trace(cpu, run, host or {}, binary, samples, bindings, observed_aux)


def quantile(values: list[float], probability: float) -> float:
    position = (len(values) - 1) * probability
    lower = int(position)
    upper = min(lower + 1, len(values) - 1)
    return values[lower] + (values[upper] - values[lower]) * (position - lower)


def bootstrap_plan(clusters: int) -> list[list[int]]:
    rng = random.Random(BOOTSTRAP_SEED)
    return [[rng.randrange(clusters) for _ in range(clusters)] for _ in range(BOOTSTRAP_DRAWS)]


def interval(values: list[float], plan: list[list[int]], *, confirmatory: bool = False) -> dict:
    if not values or len(values) % CLUSTER_BLOCKS:
        raise ValueError("outcome lacks complete paired 16-block clusters")
    clusters = [average(values[i:i + CLUSTER_BLOCKS]) for i in range(0, len(values), CLUSTER_BLOCKS)]
    boot = sorted(average([clusters[index] for index in draw]) for draw in plan)
    alpha = FAMILY_ALPHA / FAMILY_SIZE if confirmatory else .05
    return dict(hit_rate_difference=average(values),
                ci=[quantile(boot, alpha / 2), quantile(boot, 1 - alpha / 2)],
                nominal_confidence=1 - alpha, cluster_differences=clusters,
                interval_scope="within_run_paired_16_block_cluster_bootstrap",
                confirmatory_family_size=FAMILY_SIZE if confirmatory else None)


def effect_decision(metric: dict) -> str:
    lower, upper = metric["ci"]
    if lower > PRACTICAL_MARGIN:
        return "response_in_expected_direction"
    if upper < -PRACTICAL_MARGIN:
        return "response_in_opposite_direction"
    if lower >= -PRACTICAL_MARGIN and upper <= PRACTICAL_MARGIN:
        return "equivalent_within_practical_margin"
    return "unresolved"


def summarize(trace: Trace) -> dict:
    study, modes = trace.run["study"], MODES[trace.run["study"]]
    blocks, episodes = int(trace.run["blocks"]), int(trace.run["episodes"])
    half = blocks // 2
    thresholds = {}
    for p in (0, 1):
        hot = [s.wanted for s in trace.samples if s.block < half and s.kind == f"hot_p{p}"]
        cold = [s.wanted for s in trace.samples if s.block < half and s.kind == f"cold_p{p}"]
        thresholds[p] = select_threshold(hot, cold)
    per_block = {(b, m, k): [] for b in range(half, blocks) for m in modes for k in KINDS}
    decoys = {(m, k): [] for m in modes for k in KINDS}
    orders = {(m, k, o): [] for m in modes for k in KINDS for o in (0, 1)}
    occurrences = {(m, k, e): [] for m in modes for k in KINDS for e in range(episodes)}
    for sample in trace.samples:
        if sample.block < half:
            continue
        p = int(sample.kind[-1])
        hit = int(sample.wanted <= thresholds[p])
        per_block[sample.block, sample.mode, sample.kind].append(hit)
        decoys[sample.mode, sample.kind].append(int(sample.decoy <= thresholds[p]))
        orders[sample.mode, sample.kind, sample.order].append(hit)
        occurrences[sample.mode, sample.kind, sample.occurrence].append(hit)
    rates = {m: {k: average([average(per_block[b, m, k]) for b in range(half, blocks)])
                 for k in KINDS} for m in modes}
    decoy_rates = {m: {k: average(decoys[m, k]) for k in KINDS} for m in modes}
    gates = {}
    for mode in modes:
        for p in (0, 1):
            for member in ("hot", "cold", "no_probe_t0", "no_probe_t1", f"candidate_t{p}", "arch_load"):
                kind = f"{member}_p{p}"
                positive = member == "hot" or (member == "arch_load" and public_arch_load_expected(study, mode, p))
                gates[f"{mode}/{kind}"] = rates[mode][kind] >= .95 if positive else rates[mode][kind] <= .05
        for kind in KINDS:
            gates[f"{mode}/{kind}/decoy"] = decoy_rates[mode][kind] <= .05
    plan = bootstrap_plan((blocks - half) // CLUSTER_BLOCKS)
    adjusted = {}
    outcomes = {}
    for p in (0, 1):
        outcomes[f"p{p}"] = {}
        for mode in modes:
            candidate, no_probe = [], []
            for block in range(half, blocks):
                candidate.append(average(per_block[block, mode, f"candidate_t{1-p}_p{p}"]) -
                                 average(per_block[block, mode, f"candidate_t{p}_p{p}"]))
                no_probe.append(average(per_block[block, mode, f"no_probe_t{1-p}_p{p}"]) -
                                average(per_block[block, mode, f"no_probe_t{p}_p{p}"]))
            adjusted[p, mode] = [a - b for a, b in zip(candidate, no_probe)]
            outcomes[f"p{p}"][mode] = dict(adjusted=interval(adjusted[p, mode], plan),
                                          candidate=interval(candidate, plan), no_probe=interval(no_probe, plan))
    specifications = (("p0_sham_minus_true", 0, "sham_mask", "true_mask", "suppression"),
                      ("p0_plain_minus_sham", 0, "plain", "sham_mask", "equivalence")) if study == "dependency" else (
                      ("p0_plain_minus_ablate_one", 0, "plain", "ablate_one", "suppression"),
                      ("p1_plain_minus_ablate_zero", 1, "plain", "ablate_zero", "suppression"),
                      ("p0_plain_minus_sink_both", 0, "plain", "sink_both", "suppression"),
                      ("p1_plain_minus_sink_both", 1, "plain", "sink_both", "suppression"))
    endpoints = {}
    for name, p, left, right, purpose in specifications:
        metric = interval([a - b for a, b in zip(adjusted[p, left], adjusted[p, right])], plan, confirmatory=True)
        metric.update(purpose=purpose, practical_margin=PRACTICAL_MARGIN, decision=effect_decision(metric))
        endpoints[name] = metric
    baseline_banks = (0,) if study == "dependency" else (0, 1)
    baseline_eligibility = {}
    for p in baseline_banks:
        metric = outcomes[f"p{p}"]["plain"]["adjusted"]
        baseline_eligibility[f"p{p}"] = dict(
            decision=effect_decision(metric), supporting_metric=metric,
            interval_role="descriptive_95_percent_not_an_additional_confirmatory_endpoint",
            is_apparatus_gate=False)
    baseline_decisions = [item["decision"] for item in baseline_eligibility.values()]
    controls = all(gates.values())
    if not controls:
        classification, reason = "inconclusive", "failed_apparatus_controls"
    elif all(value == "equivalent_within_practical_margin" for value in baseline_decisions):
        classification, reason = "valid_no_baseline_response", "plain_baseline_within_practical_margin"
    elif not all(value == "response_in_expected_direction" for value in baseline_decisions):
        classification, reason = "inconclusive", "intervention_eligibility_unresolved_or_partial_plain_baseline"
    elif study == "dependency":
        main = endpoints["p0_sham_minus_true"]["decision"]
        matched = endpoints["p0_plain_minus_sham"]["decision"] == "equivalent_within_practical_margin"
        if main == "response_in_expected_direction" and matched:
            classification, reason = "valid_response", "matched_dependency_suppression_with_sham_equivalence"
        elif main == "equivalent_within_practical_margin" and matched:
            classification, reason = "valid_no_response", "sham_minus_true_within_practical_margin"
        else:
            classification, reason = "inconclusive", "unresolved_opposite_or_unmatched_intervention"
    else:
        decisions = [metric["decision"] for metric in endpoints.values()]
        if all(value == "response_in_expected_direction" for value in decisions):
            classification, reason = "valid_response", "both_banks_suppress_under_ablation_and_public_bank_relocation"
        elif all(value == "equivalent_within_practical_margin" for value in decisions):
            classification, reason = "valid_no_response", "all_four_receiver_contrasts_within_practical_margin"
        else:
            classification, reason = "inconclusive", "mixed_unresolved_or_opposite_receiver_contrasts"
    return dict(study=study, protocol="causal_receiver_v1", seed=int(trace.run["seed"]),
        platform=trace.run["platform"], count=len(trace.samples), sample_count=len(trace.samples),
        cpu=trace.cpu, run=trace.run, host=trace.host, binary_sha256=trace.binary_sha256,
        runtime_bytes_match_contract=True, context_bindings_verified=True,
        observed_tsc_aux=trace.observed_aux, aux_matches_windows_cpu_index_not_assumed=True,
        calibration_blocks=[0, half-1], heldout_blocks=[half, blocks-1],
        thresholds={f"p{p}": thresholds[p] for p in (0, 1)},
        apparatus_controls_pass=controls, gates=gates, heldout_hit_rates=rates,
        heldout_decoy_hit_rates=decoy_rates, outcomes=outcomes, primary_endpoints=endpoints,
        baseline_eligibility=baseline_eligibility,
        receiver_order_hit_rates={m: {k: {str(o): average(orders[m,k,o]) if orders[m,k,o] else None
            for o in (0,1)} for k in KINDS} for m in modes},
        episode_position_hit_rates={m: {k: [average(occurrences[m,k,e]) for e in range(episodes)]
            for k in KINDS} for m in modes},
        bootstrap=dict(seed=BOOTSTRAP_SEED, draws=BOOTSTRAP_DRAWS, cluster_blocks=CLUSTER_BLOCKS,
            heldout_clusters=(blocks-half)//CLUSTER_BLOCKS, family_size=FAMILY_SIZE,
            confirmatory_family_nominal_confidence=1-FAMILY_ALPHA,
            per_endpoint_nominal_confidence=1-FAMILY_ALPHA/FAMILY_SIZE,
            supporting_nominal_confidence=.95, shared_paired_resampling=True,
            limitation="Percentile-bootstrap coverage is approximate and within-run; clusters do not become independent host sessions."),
        classification=classification, classification_reason=reason, practical_margin=PRACTICAL_MARGIN,
        mechanism_proven=False,
        scope=SCOPE if trace.run["platform"] == "windows" else "Development trace only, not Windows host evidence. " + SCOPE,
        windows_collection=trace.run["platform"] == "windows",
        mechanism_conclusion="not_established_by_these_user_mode_interventions",
        limitation="Suppression and equivalence constrain tested alternatives. They do not uniquely identify a branch-predictor structure or establish user-to-kernel influence.")


def audit_files(trace: Trace, binary: Path | None = None,
                snapshots: dict[str, Path] | None = None) -> dict | None:
    if binary is None and snapshots is None:
        return None
    if binary is None or snapshots is None or set(snapshots) != set(MODES[trace.run["study"]]):
        raise ValueError("provide the executable and all five runtime snapshots together")
    image = Path(binary).read_bytes()
    digest = hashlib.sha256(image).hexdigest()
    if trace.binary_sha256 is not None and digest != trace.binary_sha256:
        raise ValueError("executable SHA256 disagrees with trace provenance")
    if CODE not in image:
        raise ValueError("expected causal receiver template is absent from executable image")
    hashes = {}
    for mode, path in snapshots.items():
        content = Path(path).read_bytes()
        if content != code_for(trace.run["study"], mode):
            raise ValueError("archived runtime bytes disagree with observed code contract")
        hashes[mode] = hashlib.sha256(content).hexdigest()
    return dict(binary_sha256=digest, binary_hash_matched_trace=trace.binary_sha256 is not None,
                runtime_snapshots_verified=True, runtime_code_sha256=hashes,
                template_present_in_linked_image=CODE in image,
                linked_harness_review="not_automatically_attested")


def analyze(trace: Path, binary: Path | None = None, snapshots: dict[str, Path] | None = None,
            *, development: bool = False) -> dict:
    parsed = parse_trace(Path(trace).read_text(encoding="utf-8-sig"), development=development)
    result = summarize(parsed)
    result["artifact_audit"] = audit_files(parsed, binary, snapshots)
    result["trace_sha256"] = hashlib.sha256(Path(trace).read_bytes()).hexdigest()
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("trace", type=Path)
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--strict", action="store_true", help="fail apparatus controls, not a valid null")
    parser.add_argument("--development", action="store_true")
    parser.add_argument("--binary", type=Path)
    parser.add_argument("--code-prefix", type=Path, help="prefix for <prefix>.<mode>.bin snapshots")
    args = parser.parse_args()
    try:
        parsed = parse_trace(args.trace.read_text(encoding="utf-8-sig"), development=args.development)
        snapshots = ({mode: Path(f"{args.code_prefix}.{mode}.bin") for mode in MODES[parsed.run["study"]]}
                     if args.code_prefix is not None else None)
        result = summarize(parsed)
        result["artifact_audit"] = audit_files(parsed, args.binary, snapshots)
        result["trace_sha256"] = hashlib.sha256(args.trace.read_bytes()).hexdigest()
    except (OSError, ValueError, KeyError, TypeError) as error:
        parser.exit(2, f"Invalid causal receiver evidence: {error}\n")
    if args.json:
        print(json.dumps(result, sort_keys=True))
    else:
        print(f"{result['study']} complete: {result['count']} samples; platform={result['platform']}")
        print(f"Apparatus gates: {sum(result['gates'].values())}/{len(result['gates'])}")
        for name, metric in result["primary_endpoints"].items():
            lower, upper = metric["ci"]
            print(f"{name}: {100*metric['hit_rate_difference']:+.3f} pp; "
                  f"family-adjusted within-run CI [{100*lower:+.3f},{100*upper:+.3f}] pp")
        print(f"Run classification: {result['classification']} ({result['classification_reason']})")
        print("Mechanism proven: False")
        for name, passed in result["gates"].items():
            if not passed:
                print(f"FAILED CONTROL: {name}")
    return 1 if args.strict and not result["apparatus_controls_pass"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
