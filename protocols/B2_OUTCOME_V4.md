# B2 v4: prospective same-site training outcome study

**Status:** frozen protocol for one physical Windows run. The earlier B2 v2
pilot failed three 16-call apparatus gates; its outcome estimates remain
inconclusive. The independently collected [v3 precision diagnostic](../results/RESULTS_LEDGER.json) passed all 16 specified
apparatus gates and its linked instruction audit, but contained no real-arm
outcome. This v4 executable collects a new outcome and repeats the controls
inside that same physical binary. Nothing in v2 or v3 is reclassified.

## Scientific question and scope

At one conditional branch address in a Windows **user process**, does changing
the real training outcome from matched to mismatched produce a probe timing
contrast beyond a same-site fixed-decision training comparator? The fixed
trainer reads and returns the corresponding live training byte but follows a
periodic branch-decision stream. It is an ablation, not a predictor-free
control. A timing interaction may reflect several physical mechanisms and
does not count mispredictions or demonstrate transient execution.

This study never changes privilege or address space and has no cache receiver.
It cannot confirm or refute the [Fractal paper's](https://people.csail.mit.edu/mengjia/data/2026.SP.fractal.pdf)
Apple M1 user-to-kernel conditional-predictor finding. The repository's prior
B1 and failed-control B2 observations motivated selecting the one-call,
probe-0 endpoint; that selection is disclosed and those observations are
excluded from the v4 estimate.

## Fixed conditions and schedule

For each probe outcome `p ∈ {0,1}` and length `n ∈ {1,16}`, measure five
adjacent, order-balanced pairs: real trainer `t0/t1`, fixed-decision trainer
`t0/t1`, identical fast timers `fast_a/fast_b`, `fast_c/dose4` small-work
timers, and `fast_d/pause` coarse timers. This is 20 pairs and 40 conditions
per complete block. All timed probes use the same fast function unless the
condition names `dose4` or `pause`. The `dose4` is a positive sensitivity
control, not an adjustment subtracted from the outcome. The different-site
sham from earlier work is omitted; it cannot isolate same-site training.

Each episode uses 256 calls of the `0011` prelude, 256 training calls, and
`n` live-decision probe calls at one assembly branch site. Training real
`t=0/1` uses live branch decisions. Training fixed `t=0/1` follows periodic
decisions independently of the live byte; the probe uses live decisions for
all conditions. There are 256 episodes per condition, 40 warm-up blocks and
3,200 recorded complete blocks. One preselected nonzero uint32 seed drives
Fisher–Yates shuffling of the 20 pairs and an orientation bit for each pair
at every 40-block cycle. Rotate pairs across 20 slots in the first 20 blocks
and invert their within-pair orientation in the second 20. This balances
each condition at all 40 positions across each complete cycle. The analyzer
replays the warm-up and recorded schedule, verifies the seed, hashes, all
128,000 samples, checksum, architectural totals and metadata. No adaptive
stopping, dropped blocks or replacement attempts are allowed.

## Prespecified estimand and decision

Within each complete block define `D_real(p,n) = real_t(1-p) - real_t(p)`
and `D_fixed(p,n) = fixed_t(1-p) - fixed_t(p)`. The interaction is
`F(p,n) = D_real(p,n) - D_fixed(p,n)`, divided by 256 episodes. Units are
TSC ticks per **complete probe episode**. A 16-call probe is not reported
as an isolated per-call branch cost. Report the paired median, 10%-trimmed
mean, split-half means, 20%-trimmed sensitivity estimate and 95% interval
from 2,000 bootstrap resamples of entire 40-block position cycles.

**One prespecified primary outcome:** `F(p0,n1)`. A provisional, within-run
practically meaningful timing association requires all apparatus gates below
to pass and the entire two-sided 95% interval for this primary interaction
to lie either above `+1` or below `-1` tick per probe episode. Otherwise the
primary is not detected by this decision rule. Report its estimate and
interval regardless. Report `F` and both underlying `D` values for all four
`p,n` combinations, plus one-call versus sixteen-call interactions. The
other outcomes are secondary descriptive findings and do not supply a
multiplicity-adjusted confirmatory claim. A zero or opposite-sign result
is retained, not considered a build failure.

The real and fixed `t0/t1` members are adjacent within their respective
pairs, while the real and fixed pairs can be separated by other conditions
inside a block. Pair order and position balance reduce systematic order
effects but do not eliminate cross-pair drift or carryover. The `0011`
prelude standardizes recent branch activity; it is not a proven predictor
reset. Report both underlying `D` estimates alongside every `F` estimate.

## Apparatus gates in the new executable

The following 16 gates are exactly the v3 rules, applied separately to each
of the four `p,n` strata. They are checked in the **new v4 binary** before
the outcome is considered eligible for interpretation:

| Paired control | Frozen gate in TSC ticks per probe episode |
| --- | --- |
| `fast_b - fast_a` | Full within-run 95% interval strictly inside `(-1,+1)`. |
| `fixed_t(1-p) - fixed_t(p)` | Full interval strictly inside `(-1,+1)`. This is also `D_fixed`. |
| `dose4 - fast_c` | Interval lower bound `>0`, upper bound `<8`, 10%-trimmed point in `[1,8]`. |
| `pause - fast_d` | Interval lower bound `>0`; at least 95% of paired blocks positive. |

An apparatus failure yields an **inconclusive outcome**, even when a raw
`F` interval appears to exclude zero. The complete failed-control trace is
archived. A valid null outcome returns a successful strict analyzer exit;
strict exit code `1` indicates a failed apparatus gate, not an unsuccessful
scientific hypothesis. Bootstrap intervals quantify uncertainty within one
run only. Even a primary interval beyond the margin remains a provisional
same-process timing association pending independent run-level replication
with new seeds and an audit of every executable. A run on a different date
is needed to assess day-to-day robustness.

## Run from VS Code on physical Windows

1. Merge the source revision into the existing repository and start with a
   clean Git working tree. Select **Terminal → Run Task → B2 v4 same-site
   outcome study (Windows)**. Let its fixed 3,200 blocks complete; this may
   take several minutes.
2. Upload the **one** `out\b2-outcome-windows-<UTC timestamp>.zip` printed
   after `READY TO SHARE:`, whether controls pass, fail, or the primary effect
   is null. A control failure intentionally exits nonzero but retains the
   complete ZIP. On build, run or trace-parse errors, upload the separately
   labeled `Diagnostic evidence ZIP (partial)` to debug the attempt.

The archive includes the exact EXE, trace, build/provenance files, linked
disassembly, machine-readable analysis, strict output, and SHA-256 manifest.
The source and toolchain versions, clean Git HEAD, seed, Windows build,
binary and PE `.text` hashes are recorded. Inspect the linked instructions
before attributing the physical timing to any branch-history hypothesis.
