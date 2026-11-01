# B2 v2 apparatus calibration, physical Windows pilot

**Outcome: inconclusive calibration.** The recorded `dose4` timer meets its
predeclared small-work sensitivity gate in all four strata. Three separate
16-call baseline controls fail their predeclared practical equivalence gates,
so the pilot selects no timer candidate. Preserve the strict exit code `1`
and the complete trace as the observed outcome. This pilot did not measure a
real versus fixed training contrast or a cross-privilege effect.

## Evidence and provenance

The original archive is
`b2-calibration-windows-20261101T142148071Z.zip` (SHA-256
`9c71dca5d33c1751bfedcf759aa9eb5e5789b53a40ce8b8e437da449c840abce`).
It contains the exact executable, raw trace, analysis JSON, strict output,
linked disassembly, build record and manifest. The archive is retained as
the primary record; do not replace its contents with this report.

| Field | Archived value |
| --- | --- |
| Run start | 2026-11-01 14:21:51 UTC |
| CPU | AuthenticAMD, signature `0x00b40f40`, pinned logical CPU 0 |
| Hypervisor / Windows build | 1 / 26200 |
| Git HEAD / working tree | `938b7842fcfb94135fac2ba9713de126df65f39c` / clean |
| Seed / schedule | 3929608376 / 32-position rotations after each seeded shuffle |
| Recorded data | 1,280 complete blocks, 32 conditions per block, 128 episodes per condition |
| EXE SHA-256 | `0be911f040841e1d07c8b2c94301086e14fd37cc2543c685e3c14934d4597338` |
| PE `.text` SHA-256 | `863b6031a5b75dc23d882d740799038ca17b3e550c5fded2a94f28fc54697cda` |
| Raw trace SHA-256 | `cecf09b98f8870afdc32d64996b547fb9276addc37392945e0f367d09df83a33` |
| Observed GCD | 47 TSC ticks for recorded batch totals |

The ZIP CRC, all seven manifest file hashes, ten recorded source hashes
against the committed source, PE hashes and embedded trace hash match.
Independent replay validates the complete 40,960-sample schedule, checksum,
architectural totals and metadata. The archived JSON matches replay and its
strict analyzer exits `1`. These consistency checks do not attest the
hardware or eliminate all environmental interference.

The build log has an ASCII first line followed by UTF-16LE text from Windows
PowerShell 5.1 `Tee-Object -Append`. The assembly and C build succeeded without
recorded warnings or errors. This mixed encoding is a packaging defect to
correct in the next runner revision; it does not alter the executable or trace.

## Predeclared gates and measured estimates

Numbers are paired 10%-trimmed means and within-run 95% cycle-bootstrap
intervals in TSC ticks **per episode's probe**. A 16-call probe is one
episode, so these are not ticks per individual branch call. The `fast_b` and
fixed-neutral intervals must lie strictly inside `(-1,+1)`. `dose4` requires
a positive lower bound, upper bound below `8`, and point estimate in `[1,8]`.
`pause` requires a positive lower bound and at least 95% positive blocks.

| Stratum | `fast_b - fast_a` | Fixed neutral | `dose4 - fast_a` | `pause - fast_a` |
| --- | ---: | ---: | ---: | ---: |
| `p0_n1` | -0.056 [-0.286, +0.177] PASS | -0.108 [-0.374, +0.158] PASS | +6.255 [+6.087, +6.430] PASS | +50.841 [+50.611, +51.071] PASS |
| `p1_n1` | -0.231 [-0.455, -0.013] PASS | +0.223 [-0.077, +0.495] PASS | +5.346 [+5.156, +5.559] PASS | +49.807 [+49.614, +50.010] PASS |
| `p0_n16` | +0.601 [-0.127, +1.207] FAIL | +0.181 [-0.588, +1.103] FAIL | +6.343 [+5.540, +7.004] PASS | +57.512 [+56.808, +58.338] PASS |
| `p1_n16` | -0.377 [-1.213, +0.410] FAIL | +0.094 [-0.651, +0.884] PASS | +6.074 [+5.434, +6.794] PASS | +57.075 [+56.326, +57.803] PASS |

The original `oldsmall` diagnostic fails its gate in both one-call strata;
`dose8` exceeds the eight-tick upper limit in every stratum. All four PAUSE
checks pass. A passing `dose4` in isolation does not override a failed
baseline, and `selected_candidate` is null. The 16-call placebo block
differences are much more dispersed than the one-call differences. Their
20%-trimmed point estimates lie within ±1 but cannot replace the specified
95% interval gates. An occasional system interruption is a possible source
of spread, not a proven cause from these data.

An **exploratory, after-the-fact** spacing check groups blocks by the absolute
position gap between the two conditions. Among 16-call fast placebo blocks,
the median absolute difference is 2.203 ticks/episode when positions are at
most four apart, versus 6.242 for `p0` and 7.527 for `p1` when they are at
least 16 apart. The corresponding fixed-neutral medians are 2.203 versus
6.242 for `p0`, and 2.387 versus 4.773 for `p1`. These are descriptive
subsets with different blocks, chosen after viewing the pilot. They motivate
a *prospective* adjacent-pair precision diagnostic; they do not prove that
spacing caused the variance or change the original gate outcome.

## Linked instruction audit

The archived executable's PE `.text` bytes match the provenance hash. The
branch site at RVA `0x1f70` contains the expected live/fixed/mode loads,
conditional move, conditional branch and return. `run_branch` calls that
one site for prelude, training and probe. The linked condition decoder selects
one versus sixteen probe calls as labeled, and its condition-map check runs
before collection. Fixed training sets the mode to the periodic decision
stream; live training and all probes use the live mode. `fast_a`, `fast_b`
and fixed controls call the same timed function. Separate timed functions
contain the result-dependent `dose4` and `dose8` work and `PAUSE` between
their fenced TSC readings. No source-to-instruction mismatch was found.

This is a topology audit of a Windows user process. It does not identify
predictor state or count branch mispredictions. The [Fractal paper](https://people.csail.mit.edu/mengjia/data/2026.SP.fractal.pdf), Section 7.2, reports conditional predictor behavior on Apple M1 using sender/receiver and cross-privilege conditions. The present x86 calibration has neither a receiver signal nor a privilege transition and cannot confirm or refute that result.

## Decision

Keep the v2 result as an inconclusive apparatus pilot and do not treat a
repeated v2 run that happens to pass as a replacement. A separately versioned
precision diagnostic should predeclare how it will study 16-call variability
and retain the fixed ±1 practical tolerance. Only after its controls and
linked instructions are reviewed can a new B2 outcome design be frozen for
independent validation.
