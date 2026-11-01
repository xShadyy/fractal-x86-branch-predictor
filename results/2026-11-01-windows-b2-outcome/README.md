# B2 v4 same-site outcome, physical Windows run

**Observed result:** all 16 predeclared apparatus gates pass. The one
preselected primary real-versus-fixed interaction is +0.136 TSC ticks per
complete probe episode, with a 95% **within-run** 40-block-cycle bootstrap
interval of [+0.003,+0.272]. It does **not** satisfy the frozen practical
association rule, which requires the whole interval to be beyond +1 or -1.
This is an eligible, small within-run outcome, not a predictor mechanism or
cross-privilege finding.

## Archive and provenance

The original evidence archive is
`b2-outcome-windows-20261101T155752221Z.zip`, SHA-256
`2e52aaffa916e575976fbf81aab7d907173b35945c7985adc8c44d71d3005f35`.
It contains the complete raw trace, executable, linked disassembly, build
provenance, analysis, strict transcript and SHA-256 manifest. This report
does not replace the eight original archive members.

| Field | Archived value |
| --- | --- |
| Protocol source | [`B2_OUTCOME_V4.md`](../../B2_OUTCOME_V4.md) at clean Git HEAD `6ffb1989ac3487c1d191f36d0b711c8ba99f1740` |
| Run start | 2026-11-01 15:57:55 UTC, after the frozen source commit |
| CPU / affinity | AuthenticAMD `0x00b40f40`, logical CPU 0 |
| Windows build / hypervisor | 26200 / present |
| Seed | 4294791526 |
| Schedule | 3,200 complete 40-condition blocks, 20 adjacent pairs per block, 256 episodes per condition; 40 warm-up blocks |
| Executable SHA-256 | `ee1085a210d9b2426991251dea4802b08239a077f7957689ca8149a17e56921b` |
| PE `.text` SHA-256 | `1289fa0d276ca798fdf80b0319730d97fc19391e85f78d71c64e96f62c3b947e` |
| Batch-total GCD | 47 TSC ticks, cause not identified |
| Build | MSVC `cl.exe` 19.51.36260.0, `/std:c11 /O2 /W4 /WX`; `ml64`, `link` and `dumpbin` 14.51.36260.0 |

ZIP CRC, seven manifest member hashes, ten source hashes at the recorded Git
commit, executable hash and `.text` hash match. The archived build transcript
has no compiler warning. Independent analyzer replay accepts the 128,000
samples and reproduces the archived JSON values and strict exit code `0`.
The replay checks the seed-derived order and position balance, schedule and
pattern hashes, checksum, sample labels, and architectural totals. These
checks establish internal consistency, not independent hardware attestation.

## Frozen controls

Entries are paired 10%-trimmed means [95% within-run bootstrap interval], in
TSC ticks per **complete** probe episode. `fast_b - fast_a` and fixed-neutral
intervals must fit strictly inside ±1; `dose4 - fast_c` must have a positive
lower bound, upper bound below 8 and point in [1,8]; `pause - fast_d` must
have a positive lower bound and at least 95% positive paired blocks.

| Stratum | Fast placebo | Fixed neutral | `dose4` | `pause` |
| --- | ---: | ---: | ---: | ---: |
| `p0_n1` | -0.100 [-0.185,-0.013] | -0.020 [-0.086,+0.045] | +6.235 [+6.152,+6.328] | +50.568 [+50.474,+50.671] |
| `p1_n1` | +0.016 [-0.050,+0.086] | +0.005 [-0.056,+0.066] | +5.381 [+5.300,+5.463] | +49.693 [+49.603,+49.776] |
| `p0_n16` | +0.204 [-0.111,+0.502] | -0.078 [-0.328,+0.157] | +5.708 [+5.456,+5.991] | +55.584 [+55.255,+55.945] |
| `p1_n16` | -0.163 [-0.424,+0.104] | -0.006 [-0.245,+0.210] | +5.687 [+5.398,+5.950] | +53.039 [+52.638,+53.462] |

Every entry passes its own frozen gate. The PAUSE positive fractions are
98.6%, 98.2%, 97.0% and 96.9% in table order. The `p0_n1` fast placebo's
tiny interval also excludes zero within this run, while passing its practical
±1 gate. Small interval exclusions around zero therefore require care.

## Training outcome

`D_real` is mismatched minus matched training for a live decision stream;
`D_fixed` uses the same branch site with a fixed `0011` decision stream while
the live training byte changes. `F` subtracts these two differences **within
each block**, then takes a paired trimmed mean. It need not equal a subtraction
of the separately trimmed displayed means. The fixed trainer is an ablation,
not a predictor-free control.

| Stratum | `D_real` | `D_fixed` | `F = D_real - D_fixed` blockwise |
| --- | ---: | ---: | ---: |
| `p0_n1` **primary** | +0.108 [+0.022,+0.184] | -0.020 [-0.086,+0.045] | **+0.136 [+0.003,+0.272]** |
| `p1_n1` | +0.034 [-0.048,+0.110] | +0.005 [-0.056,+0.066] | -0.000 [-0.115,+0.116] |
| `p0_n16` | +0.009 [-0.213,+0.222] | -0.078 [-0.328,+0.157] | +0.278 [-0.253,+0.859] |
| `p1_n16` | +0.005 [-0.280,+0.288] | -0.006 [-0.245,+0.210] | +0.157 [-0.470,+0.858] |

The primary `F` split-half estimates are +0.098 and +0.190; its positive
paired-block fraction is exactly 50.0%. Its within-run interval is entirely
below the prespecified +1 tick practical threshold. The other three `F`
intervals include zero. The secondary n1-minus-n16 interactions are -0.243
[-1.018,+0.604] for probe 0 and -0.232 [-1.199,+0.737] for probe 1. No
secondary result supplies a separate confirmatory claim.

The primary block differences have extreme outliers: the arithmetic mean is
+6.182 ticks per episode, and the minimum and maximum are -5,859 and
+12,143. Those values make an untrimmed mean misleading for this trace. The
reported 10%-trimmed paired estimator and cycle bootstrap were fixed before
the physical run; the outlier check does not change them.

## Linked instruction audit and scientific boundary

The trace's branch address maps to RVA `0x20e0` in the matched PE. The
assembly function loads live, fixed and mode bytes, uses `cmovne` to choose
the decision, then has one conditional `je` at RVA `0x20f5` and returns the
live byte. One direct call at RVA `0x1eb1` in `run_branch` reaches this
function; prelude, training and timed probes all use that loop. The common
fast timer at RVA `0x1fb0` serves real/fixed conditions and the fast controls.
The separate `dose4` and PAUSE timers contain their specified extra work
between fenced TSC readings. This verifies topology of the archived linked
binary, not the origin of a tiny timing contrast.

The same user-mode Windows process supplies both training and probe. The
paper's Apple M1 sender/receiver and privilege-domain effects are not tested
here. A fixed `0011` prelude is not a proven predictor reset. Real and fixed
pairs can be separated within a block, leaving possible cross-pair drift and
carryover. The hypervisor is present and the observed batch GCD is 47 ticks.
Bootstrap intervals are conditional on this single run and do not measure
run-to-run or day-to-day variation. Do not rerun selectively to replace this
outcome. A separately declared replication with new seeds would assess
robustness; a distinct target-sensitive single-domain receiver is needed
before attributing an effect to predictor state or testing a domain change.

To reproduce the archived statistical analysis from a copy of the original
ZIP, extract its `.log` and invoke `python scripts/analyze_b2_outcome.py
<extracted-log> --strict --json` at the recorded source revision. A valid
absence of a practical effect still exits successfully.
