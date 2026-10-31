# Exploratory Windows indirect-target history study

**Status:** source and analysis prepared after the A/B results; no physical Windows executable, timer calibration or measurement has been validated. This is a user-mode x86 timing study, not a test of speculative fetch or privilege isolation.

The [Fractal paper](https://people.csail.mit.edu/mengjia/data/2026.SP.fractal.pdf) develops same-domain indirect-branch train/receiver tests before comparing security domains on Apple M1. Here the question is narrower: **does the latency of one fixed indirect dispatch depend on the preceding architectural target sequence in this Windows executable?** A positive contrast would be a target-history association under one instruction sequence. It would not identify a particular predictor, count mispredictions, or reproduce the paper's cache-based or cross-domain result.

## Instruction and condition design

MASM contains one indirect `jmp r11` dispatch site, two distinct target addresses with byte-identical `mov eax,r9d; ret` bodies, and a separate branchless sham site. Both targets return the **live input byte**, even when the selected target follows a fixed periodic `0011` decision stream. The C runner must compile to one direct call instruction serving the prelude, real/fixed training and timed probe. The two target bodies are placed adjacent after `ALIGN 16`; the strict analyzer requires their runtime addresses to lie within the same 64-byte aligned line. Exact bytes, offsets and the caller still need inspection in the physical Windows PE.

Each episode has a common 256-call balanced `0011` target prelude, 256 all-`t` training inputs, and one timed fixed-`p` probe. The prelude standardizes previous activity; it does not prove predictor state is erased. During training:

| Arm | Dispatched target during training | Scope |
| --- | --- | --- |
| `real` | All live target `t` | Target-history intervention. |
| `fixed` | Same indirect dispatch follows `0011` while still reading and returning all-`t` live inputs | Primary same-site control. |
| `sham` | Separate branchless site reads and returns all-`t` inputs | Secondary control with a different address/path. |

All probe calls select the actual live target at the same dispatch. Both train labels and both probe targets occur in every arm. Fast, small-added-work and `PAUSE` wrappers are each tested for both probe targets after real training of label 0. This gives **18 conditions per complete block**, **18 warm-up blocks** and **360 recorded blocks** with **128 episodes per condition**. A seeded shuffle is rotated through all 18 positions once per cycle, yielding 20 position-balanced cycles. The trace records all raw condition totals, exact schedule and pattern hashes, architectural sink checksum, CPU/affinity/build metadata and matched EXE hash. Preserve failed-control and null traces.

## Paired estimands and gates

For each block, `Y(a,t,p)` is the sum of 128 one-call probe durations in trainer arm `a`. The mismatch is train label `1-p`, the match is train label `p`. Form differences inside the block before trimming:

```text
D_a(p) = [Y(a,1-p,p) - Y(a,p,p)] / 128
F(p)   = D_real(p) - D_fixed(p)
S(p)   = D_real(p) - D_sham(p)
```

Report both `F(0)` and `F(1)` and their real, fixed and sham components in TSC ticks per **complete single-call probe**; report `S` separately. Apply the declared 10% trim to each blockwise series and resample complete 18-block cycles for within-run 95% bootstrap intervals. Report medians, split halves, the exploratory 20% trim and all raw blocks. Within-run intervals are not cross-day or cross-machine intervals. No sign or positive contrast is a pass gate.

The fixed trainer's mismatch-minus-match interval must lie entirely inside ±1 tick/probe for each target before calling its residual live-input sensitivity negligible. The separate `PAUSE` control must have a positive interval lower bound and at least 95% positive paired blocks for each probe target. The result-dependent small-work control must have a positive lower bound, upper bound below +8 ticks/probe, and point estimate in [+1,+8] for each target before treating a few-tick difference as resolved. These ranges are pilot calibration requirements, not assumed instruction costs. The small control and sham occupy different paths, so even passing controls cannot uniquely attribute a timing contrast to one predictor structure.

The physical pilot requires an instruction audit: verify one dispatch `jmp`, the same caller instruction for all real/fixed/probe phases, two actually distinct but byte-identical nearby targets, common fast timer wrapper, and the exact added-work paths. Record MSVC/MASM/link versions, source hashes, Git state, seed, full PE and `.text` hashes, timing controls and any failures. If a gate fails, retain the pilot and version a correction before a confirmatory series. Subsequent independent seeds and days can test repeatability of a frozen comparison, but only a separate validated receiver could support a speculative-fetch claim.
