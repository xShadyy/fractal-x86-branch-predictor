#!/usr/bin/env python3
"""Independent frequency/count audit of K7/K8 raw Windows evidence.

Uses Python's standard library only. Does not import project analyzers or execute
any archived program. Threshold selection uses a histogram/CDF sweep with exact
integer balanced-accuracy scores and median-midpoint tie breaks. Counts and
point estimates are independently recomputed; confidence intervals are outside
this script's scope.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import csv
from fractions import Fraction
import hashlib
import json
from math import gcd
from pathlib import Path
from zipfile import ZipFile

MODES = {
    "dependency": ("plain", "true_mask", "sham_mask", "lfence", "cpuid"),
    "receiver": ("plain", "ablate_zero", "ablate_one", "ablate_both", "sink_both"),
}
MEMBERS = ("candidate_t0", "candidate_t1", "no_probe_t0", "no_probe_t1",
           "hot", "cold", "arch_load", "warm_mismatch")
KINDS = tuple(f"{member}_p{p}" for p in (0, 1) for member in MEMBERS)
ENDPOINTS = {
    "dependency": (("p0_sham_minus_true", 0, "sham_mask", "true_mask"),
                   ("p0_plain_minus_sham", 0, "plain", "sham_mask")),
    "receiver": (("p0_plain_minus_ablate_one", 0, "plain", "ablate_one"),
                 ("p1_plain_minus_ablate_zero", 1, "plain", "ablate_zero"),
                 ("p0_plain_minus_sink_both", 0, "plain", "sink_both"),
                 ("p1_plain_minus_sink_both", 1, "plain", "sink_both")),
}


def fields(line):
    return dict(item.split("=", 1) for item in line.split(",")[1:])


def histogram_middle_pair(histogram):
    n = sum(histogram.values())
    ranks = ((n - 1) // 2, n // 2)
    found = []
    lower = 0
    for value, count in sorted(histogram.items()):
        for rank in ranks[len(found):]:
            if lower <= rank < lower + count:
                found.append(value)
            else:
                break
        lower += count
        if len(found) == 2:
            return tuple(found)
    raise ValueError("empty or invalid histogram")


def threshold_from_histograms(hot, cold):
    """Exact independent equivalent of the declared threshold rule."""
    observed = sorted(hot.keys() | cold.keys())
    candidates = [observed[0] - 1]
    candidates += [(left + right) // 2 for left, right in zip(observed, observed[1:])]
    candidates.append(observed[-1])
    nh, nc = sum(hot.values()), sum(cold.values())
    middle_sum = sum(histogram_middle_pair(hot)) + sum(histogram_middle_pair(cold))
    hot_hits = cold_hits = index = 0
    best = None
    best_record = None
    for candidate in candidates:
        while index < len(observed) and observed[index] <= candidate:
            hot_hits += hot[observed[index]]
            cold_hits += cold[observed[index]]
            index += 1
        # The common denominator is 2*nh*nc. No floating point ranking.
        score = hot_hits * nc + (nc - cold_hits) * nh
        rank = (score, -abs(4 * candidate - middle_sum))
        if best is None or rank > best:
            best = rank
            best_record = dict(threshold=candidate, hot_n=nh, cold_n=nc,
                               hot_hits=hot_hits, cold_false_hits=cold_hits,
                               balanced_accuracy=score / (2 * nh * nc),
                               median_midpoint=middle_sum / 4,
                               hot_median=sum(histogram_middle_pair(hot)) / 2,
                               cold_median=sum(histogram_middle_pair(cold)) / 2,
                               candidate_thresholds=len(candidates))
    return best_record


def public_arch_present(study, mode, p):
    if study == "dependency":
        return True
    observed_bank = 1 - p
    absent = {"plain": (), "ablate_zero": (0,), "ablate_one": (1,),
              "ablate_both": (0, 1), "sink_both": (0, 1)}[mode]
    return observed_bank not in absent


def fraction_record(value):
    return dict(numerator=value.numerator, denominator=value.denominator,
                hit_rate_difference=float(value), percentage_points=100 * float(value))


def audit_attempt(z, prefix, csv_writer):
    archived = json.loads(z.read(prefix + "/analysis.json"))
    trace_name = prefix + "/trace.log"
    hot = {p: Counter() for p in (0, 1)}
    cold = {p: Counter() for p in (0, 1)}
    run = cpu = None
    total = 0
    timing_gcd = 0
    trace_hash = hashlib.sha256()
    with z.open(trace_name) as trace:
        for raw in trace:
            trace_hash.update(raw)
            line = raw.decode("ascii").strip()
            if line.startswith("K7_CPU,"):
                cpu = fields(line)
            elif line.startswith("K7_RUN,"):
                run = fields(line)
                assert (int(run["blocks"]), int(run["episodes"])) == (512, 4)
            elif line.startswith("K7_SAMPLE,"):
                row = line.split(",")
                assert len(row) == 24 and int(row[1]) == total
                total += 1
                block, kind, wanted = int(row[2]), row[5], int(row[11])
                timing_gcd = gcd(timing_gcd, wanted, int(row[12]))
                if block < 256:
                    p = int(kind[-1])
                    if kind == f"hot_p{p}":
                        hot[p][wanted] += 1
                    elif kind == f"cold_p{p}":
                        cold[p][wanted] += 1
    assert total == 163840
    study = run["study"]
    modes = MODES[study]
    calibration = {f"p{p}": threshold_from_histograms(hot[p], cold[p]) for p in (0, 1)}
    threshold = {p: calibration[f"p{p}"]["threshold"] for p in (0, 1)}
    wanted_count, decoy_count, cell_n = Counter(), Counter(), Counter()
    block_n = Counter()
    # Each stratum stores [hits, total]. Includes both wanted and decoy sensors.
    order_counts = defaultdict(lambda: [0, 0])
    occurrence_counts = defaultdict(lambda: [0, 0])
    position_counts = defaultdict(lambda: [0, 0])
    with z.open(trace_name) as trace:
        for raw in trace:
            if not raw.startswith(b"K7_SAMPLE,"):
                continue
            row = raw.decode("ascii").strip().split(",")
            block = int(row[2])
            if block < 256:
                continue
            mode, position, kind, occurrence, order = row[3], int(row[4]), row[5], int(row[6]), int(row[10])
            assert mode in modes and kind in KINDS
            p = int(kind[-1])
            key = mode, kind
            wh, dh = int(int(row[11]) <= threshold[p]), int(int(row[12]) <= threshold[p])
            wanted_count[key] += wh
            decoy_count[key] += dh
            cell_n[key] += 1
            block_n[block, mode, kind] += 1
            for sensor, hit in (("wanted", wh), ("decoy", dh)):
                for counts, stratum in ((order_counts, order), (occurrence_counts, occurrence), (position_counts, position)):
                    counts[mode, kind, sensor, stratum][0] += hit
                    counts[mode, kind, sensor, stratum][1] += 1
    assert len(block_n) == 256 * 80 and set(block_n.values()) == {4}
    assert len(cell_n) == 80 and set(cell_n.values()) == {1024}
    rates = {m: {k: wanted_count[m, k] / cell_n[m, k] for k in KINDS} for m in modes}
    decoys = {m: {k: decoy_count[m, k] / cell_n[m, k] for k in KINDS} for m in modes}
    gates = {}
    for mode in modes:
        for p in (0, 1):
            for member in ("hot", "cold", "no_probe_t0", "no_probe_t1", f"candidate_t{p}", "arch_load"):
                kind = f"{member}_p{p}"
                positive = member == "hot" or (member == "arch_load" and public_arch_present(study, mode, p))
                count = wanted_count[mode, kind]
                gates[f"{mode}/{kind}"] = 100 * count >= 95 * 1024 if positive else 100 * count <= 5 * 1024
        for kind in KINDS:
            gates[f"{mode}/{kind}/decoy"] = 100 * decoy_count[mode, kind] <= 5 * 1024

    def adjusted(p, mode, counter=None, denominators=None):
        # Fresh wanted cache response: mismatch minus match, minus the same
        # training contrast when the probe is omitted.
        terms = ((f"candidate_t{1-p}_p{p}", 1), (f"candidate_t{p}_p{p}", -1),
                 (f"no_probe_t{1-p}_p{p}", -1), (f"no_probe_t{p}_p{p}", 1))
        if counter is None:
            return sum((Fraction(sign * wanted_count[mode, kind], cell_n[mode, kind]) for kind, sign in terms), Fraction())
        return sum((Fraction(sign * counter[mode, kind], denominators[mode, kind]) for kind, sign in terms), Fraction())

    endpoints = {}
    for name, p, left, right in ENDPOINTS[study]:
        l, r = adjusted(p, left), adjusted(p, right)
        metric = fraction_record(l-r)
        metric.update(p=p, left_mode=left, right_mode=right,
                      left_adjusted=fraction_record(l), right_adjusted=fraction_record(r))
        endpoints[name] = metric
    # Descriptive sensitivity: recompute complete contrasts within reload order
    # and episode occurrence, with their own exact cell denominators.
    strata = {}
    for label, counts, values in (("reload_order", order_counts, (0, 1)),
                                  ("episode", occurrence_counts, range(4))):
        strata[label] = {}
        for value in values:
            sub = {(m, k): counts[m, k, "wanted", value][0] for m in modes for k in KINDS}
            den = {(m, k): counts[m, k, "wanted", value][1] for m in modes for k in KINDS}
            strata[label][str(value)] = {
                name: fraction_record(adjusted(p, left, sub, den) - adjusted(p, right, sub, den))
                for name, p, left, right in ENDPOINTS[study]}

    comparisons = {
        "calibration_thresholds_match": {f"p{p}": threshold[p] for p in (0, 1)} == archived["thresholds"],
        "all_80_wanted_rates_match": rates == archived["heldout_hit_rates"],
        "all_80_decoy_rates_match": decoys == archived["heldout_decoy_hit_rates"],
        "all_140_gates_match": gates == archived["gates"],
        "all_primary_point_estimates_match": all(metric["hit_rate_difference"] == archived["primary_endpoints"][name]["hit_rate_difference"] for name, metric in endpoints.items()),
        "all_10_adjusted_outcomes_match": all(float(adjusted(p, m)) == archived["outcomes"][f"p{p}"][m]["adjusted"]["hit_rate_difference"] for p in (0, 1) for m in modes),
        "trace_sha256_matches": trace_hash.hexdigest() == archived["trace_sha256"],
    }
    order_rates, occurrence_rates = {}, {}
    max_order = []
    max_episode = []
    for mode in modes:
        for kind in KINDS:
            key = mode + "/" + kind
            order_rates[key] = {str(o): dict(hits=order_counts[mode, kind, "wanted", o][0],
                n=order_counts[mode, kind, "wanted", o][1],
                rate=order_counts[mode, kind, "wanted", o][0] / order_counts[mode, kind, "wanted", o][1]) for o in (0, 1)}
            occurrence_rates[key] = {str(e): dict(hits=occurrence_counts[mode, kind, "wanted", e][0],
                n=occurrence_counts[mode, kind, "wanted", e][1],
                rate=occurrence_counts[mode, kind, "wanted", e][0] / occurrence_counts[mode, kind, "wanted", e][1]) for e in range(4)}
            observed_order_rates = [item["rate"] for item in order_rates[key].values()]
            observed_episode_rates = [item["rate"] for item in occurrence_rates[key].values()]
            max_order.append(dict(cell=key, absolute_difference_pp=100 * abs(observed_order_rates[1]-observed_order_rates[0])))
            max_episode.append(dict(cell=key, range_pp=100 * (max(observed_episode_rates)-min(observed_episode_rates))))
            gate_key = mode + "/" + kind
            wanted_gate = gates.get(gate_key)
            csv_writer.writerow(dict(attempt=prefix, study=study, mode=mode, kind=kind,
                threshold=threshold[int(kind[-1])], n=cell_n[mode, kind],
                wanted_hits=wanted_count[mode, kind], decoy_hits=decoy_count[mode, kind],
                wanted_rate=rates[mode][kind], decoy_rate=decoys[mode][kind],
                wanted_gate="not_preregistered" if wanted_gate is None else wanted_gate,
                decoy_gate=gates[gate_key+"/decoy"],
                order0_n=order_rates[key]["0"]["n"], order0_hits=order_rates[key]["0"]["hits"],
                order1_n=order_rates[key]["1"]["n"], order1_hits=order_rates[key]["1"]["hits"],
                **{f"episode{e}_hits":occurrence_rates[key][str(e)]["hits"] for e in range(4)}))
    comparison_orders = {m: {k: {str(o): order_rates[m+"/"+k][str(o)]["rate"] for o in (0, 1)} for k in KINDS} for m in modes}
    comparison_episodes = {m: {k: [occurrence_rates[m+"/"+k][str(e)]["rate"] for e in range(4)] for k in KINDS} for m in modes}
    comparisons["all_order_strata_match"] = comparison_orders == archived["receiver_order_hit_rates"]
    comparisons["all_episode_strata_match"] = comparison_episodes == archived["episode_position_hit_rates"]
    assert all(comparisons.values()), comparisons
    cell_counts = {m: {k: dict(n=cell_n[m,k], wanted_hits=wanted_count[m,k], decoy_hits=decoy_count[m,k]) for k in KINDS} for m in modes}
    adjusted_counts = {f"p{p}": {m: fraction_record(adjusted(p,m)) for m in modes} for p in (0,1)}
    control_counts = defaultdict(list)
    for mode in modes:
        for kind in KINDS:
            p = int(kind[-1])
            hits = wanted_count[mode, kind]
            control_counts["all_decoys"].append(decoy_count[mode, kind])
            if kind == f"hot_p{p}": control_counts["hot"].append(hits)
            if kind == f"cold_p{p}": control_counts["cold"].append(hits)
            if kind.startswith("no_probe_"): control_counts["omitted_probe"].append(hits)
            if kind == f"candidate_t{p}_p{p}": control_counts["training_matched_candidate"].append(hits)
            if kind == f"arch_load_p{p}":
                control_counts["arch_load_present" if public_arch_present(study, mode, p) else "arch_load_absent"].append(hits)
    control_ranges = {name: dict(min_hits=min(values), max_hits=max(values), n_per_cell=1024)
                      for name, values in control_counts.items()}
    return dict(attempt=prefix, study=study, seed=int(run["seed"]), cpu=cpu,
        trace_sha256=trace_hash.hexdigest(), samples=total, heldout_samples=81920,
        calibration=calibration, counts=cell_counts, thresholds=threshold,
        gates_passed=sum(gates.values()), gates_total=len(gates), failed_gates=[k for k,v in gates.items() if not v],
        comparisons=comparisons, adjusted_outcomes=adjusted_counts, primary_endpoints=endpoints,
        descriptive_stratified_point_estimates=strata,
        reload_order_cells=order_rates, episode_cells=occurrence_rates,
        largest_reload_order_cell_differences=sorted(max_order,key=lambda x:x["absolute_difference_pp"],reverse=True)[:10],
        largest_episode_cell_ranges=sorted(max_episode,key=lambda x:x["range_pp"],reverse=True)[:10],
        archived_classification=archived["classification"],
        timing_gcd_all_wanted_and_decoy=timing_gcd, control_count_ranges=control_ranges,
        scope="Independent raw-count/threshold/gate/point-estimate audit only; no interval recalculation and no uploaded executable execution.")


def markdown_report(report):
    lines = ["# Independent K7/K8 raw-count audit", "",
        "For each of the six Windows traces, this independent count implementation matches the archived thresholds, 80 heldout wanted rates, 80 decoy rates, 140 apparatus gates, every adjusted outcome and all primary point estimates. Across the six traces, that is 480 wanted rates, 480 decoy rates and 840 gates. The script uses the Python standard library without importing the project analyzers or executing the uploaded EXE.", "",
        "Each trace has 163,840 rows: 81,920 calibration and 81,920 heldout rows. Each heldout mode/condition cell has exactly 1,024 observations, four in every heldout block. The six runs therefore contain 983,040 recorded rows and 491,520 heldout rows.", "",
        "| Attempt | Study | Seed | p0 threshold | p1 threshold | Gates |", "|---|---|---:|---:|---:|---:|"]
    for a in report["attempts"]:
        lines.append(f'| {a["attempt"]} | {a["study"]} | {a["seed"]} | {a["calibration"]["p0"]["threshold"]} | {a["calibration"]["p1"]["threshold"]} | {a["gates_passed"]}/{a["gates_total"]} |')
    lines += ["", "| Attempt | Declared primary endpoint | Exact point estimate (pp) |", "|---|---|---:|"]
    for a in report["attempts"]:
        for name,m in a["primary_endpoints"].items():
            lines.append(f'| {a["attempt"]} | {name} | {m["percentage_points"]:+.9f} |')
    lines += ["", "## Exact count interpretation", "",
        "For each mode and p, the adjusted outcome is (mismatched candidate hits minus matched candidate hits minus mismatched omitted-probe hits plus matched omitted-probe hits) divided by 1,024. The endpoint then subtracts the two modes' adjusted outcomes. This difference of differences is not a single hit probability; values slightly above +100 percentage points are mathematically valid and must not be clipped.", ""]
    for a in report["attempts"]:
        for name,m in a["primary_endpoints"].items():
            if m["hit_rate_difference"] > 1:
                p=m["p"]; lc=a["counts"][m["left_mode"]];rc=a["counts"][m["right_mode"]]
                order=(f"candidate_t{1-p}_p{p}",f"candidate_t{p}_p{p}",f"no_probe_t{1-p}_p{p}",f"no_probe_t{p}_p{p}")
                ls=" - ".join(str(lc[k]["wanted_hits"]) for k in order[:3])+" + "+str(lc[order[3]]["wanted_hits"])
                rs=" - ".join(str(rc[k]["wanted_hits"]) for k in order[:3])+" + "+str(rc[order[3]]["wanted_hits"])
                lines += [f'- {a["attempt"]}, `{name}`: [({ls}) - ({rs})] / 1024 = {m["percentage_points"]:+.9f} pp.']
    lines += ["", "## Stratum checks", "",
        "Reload-order and episode occurrence strata were independently counted and matched the archived strata exactly. The CSV records their raw counts; JSON also records stratum-specific endpoint point estimates. These are descriptive checks, without multiplicity adjustment or separate confidence intervals.", ""]
    for a in report["attempts"]:
        order=a["largest_reload_order_cell_differences"][0];ep=a["largest_episode_cell_ranges"][0]
        lines.append(f'- {a["attempt"]}: largest reload-order cell difference is {order["absolute_difference_pp"]:.3f} pp in `{order["cell"]}`; largest episode range is {ep["range_pp"]:.3f} pp in `{ep["cell"]}`.')
    suppression = []
    equivalence = []
    for a in report["attempts"]:
        for strata in a["descriptive_stratified_point_estimates"].values():
            for metrics in strata.values():
                for name, metric in metrics.items():
                    (equivalence if name == "p0_plain_minus_sham" else suppression).append(metric["percentage_points"])
    lines += ["", f'Across both reload orders and all four episode occurrences, the smallest suppression point estimate is {min(suppression):.6f} pp; the largest absolute plain-minus-sham point estimate is {max(map(abs,equivalence)):.6f} pp. These descriptive strata do not expose a loss of the large primary pattern, although they do not independently establish interval coverage.', "",
        "## Exploratory warm-condition limitation", "",
        "The matched sham is equivalent to plain for the declared cold-condition primary outcome. It is not inert in every condition: with a warm condition line, p0 sham responses are consistently smaller than plain. This is a secondary observation, without a new confirmatory test or unique mechanism attribution.", "",
        "| Dependency attempt | Warm p0 plain hits /1024 | Warm p0 sham hits /1024 | Plain minus sham (pp) |", "|---|---:|---:|---:|"]
    for a in report["attempts"]:
        if a["study"] == "dependency":
            plain=a["counts"]["plain"]["warm_mismatch_p0"]["wanted_hits"]
            sham=a["counts"]["sham_mask"]["warm_mismatch_p0"]["wanted_hits"]
            lines.append(f'| {a["attempt"]} | {plain} | {sham} | {100*(plain-sham)/1024:+.6f} |')
    lines += ["", "## Control and timing checks", "",
        "| Attempt | HOT hit range /1024 | Largest matched candidate hits /1024 | Largest omitted-probe hits /1024 | Largest decoy hits /1024 | Timing gcd |", "|---|---:|---:|---:|---:|---:|"]
    for a in report["attempts"]:
        c=a["control_count_ranges"]
        lines.append(f'| {a["attempt"]} | {c["hot"]["min_hits"]}–{c["hot"]["max_hits"]} | {c["training_matched_candidate"]["max_hits"]} | {c["omitted_probe"]["max_hits"]} | {c["all_decoys"]["max_hits"]} | {a["timing_gcd_all_wanted_and_decoy"]} |')
    lines += ["", "The timing gcd is computed across every wanted and decoy timing, including calibration. All values are multiples of the recorded gcd; the calibration HOT median is 94 and COLD median is 470 in all banks and attempts. This quantization does not remove the observed cache-class separation, but these values should be described as recorded TSC differences rather than precise instruction-cycle latencies. The audit does not determine the cause of the quantization."]
    lines += ["", "## Limits", "",
        "This audit independently checks recorded-count arithmetic; bootstrap intervals remain the frozen analyzer's outputs. Collection metadata records three fresh processes per study on one reported boot. Interventions act during training and probing. The private-bank control observes the public response without measuring private-bank heat.", "",
        "All six CPU records report hypervisor=1, IBS=0 and LFenceAlwaysSerializing=0. The absent advertised bit does not determine LFENCE's actual configuration. Its suppression is an observed result in this environment. The [result report](../README.md#host-and-measurement-scope) documents the host and measurement limits.", ""]
    return "\n".join(lines)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("archive",type=Path)
    parser.add_argument("--output",type=Path,default=Path(__file__).resolve().parent)
    args=parser.parse_args()
    args.output.mkdir(parents=True,exist_ok=True)
    with ZipFile(args.archive) as z, (args.output/"cell-counts.csv").open("w",newline="") as f:
        writer=csv.DictWriter(f,fieldnames=("attempt","study","mode","kind","threshold","n","wanted_hits","decoy_hits","wanted_rate","decoy_rate","wanted_gate","decoy_gate","order0_n","order0_hits","order1_n","order1_hits","episode0_hits","episode1_hits","episode2_hits","episode3_hits"))
        writer.writeheader()
        attempts=[audit_attempt(z,f"attempt-{i:02d}",writer) for i in range(1,7)]
    report=dict(archive=args.archive.name,archive_sha256=hashlib.sha256(args.archive.read_bytes()).hexdigest(),
        independent_implementation=True, imports_project_analyzer=False, executes_uploaded_program=False,
        threshold_method="Frequency-CDF sweep; exact integer balanced accuracy; median-midpoint tie break; ascending-first final tie.",
        confidence_intervals_recomputed=False,attempts=attempts,
        all_comparisons_pass=all(all(a["comparisons"].values()) for a in attempts))
    (args.output/"report.json").write_text(json.dumps(report,indent=2,sort_keys=True)+"\n")
    (args.output/"REPORT.md").write_text(markdown_report(report))
    print(json.dumps(dict(all_comparisons_pass=report["all_comparisons_pass"],attempts=[dict(attempt=a["attempt"],study=a["study"],thresholds=a["thresholds"],gates=f'{a["gates_passed"]}/{a["gates_total"]}',endpoints_pp={k:v["percentage_points"] for k,v in a["primary_endpoints"].items()}) for a in attempts]),indent=2))


if __name__=="__main__":
    main()
