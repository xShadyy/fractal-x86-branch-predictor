# B2 v3 adjacent-pair precision diagnostic, physical Windows run

**Observed apparatus outcome: all 16 predeclared control gates pass in one
run.** This separately versioned diagnostic followed the failed v2 calibration
pilot. It preselected adjacent matched pairs, reversed their order across
complete cycles, and increased the episode and block counts. The v2 failure
remains in the ledger. V3 measures no real-training outcome contrast, branch
misprediction count, speculative receiver, or privilege transition.

## Archive and verification

The original evidence archive is
`b2-precision-windows-20261101T154326965Z.zip`, SHA-256
`d956fc935b24e547154d1979eac1d6a873a7b9d7ce708f3920baf205f1cc88c1`.
It contains the complete raw trace, timestamped executable, disassembly,
analysis and strict outputs, build provenance and SHA-256 manifest. This
report summarizes that archive and does not replace it.

| Field | Archived value |
| --- | --- |
| Run start | 2026-11-01 15:43:30 UTC |
| CPU | AuthenticAMD `0x00b40f40`, pinned logical CPU 0 |
| Hypervisor / Windows build | 1 / 26200 |
| Git HEAD / tree | `679070bf82f97ca11a2ab43144dda67104cd652f` / clean |
| Seed | 2810554800 |
| Recorded design | 2,560 complete blocks, 32 conditions as 16 adjacent pairs, 256 episodes per condition |
| Executable SHA-256 | `cd878d64459c57bd3545ccab8ab8124e4786295634e2990df9729c972ff9c567` |
| PE `.text` SHA-256 | `9bfc7d8615690c65481e8c5ef365abf5e869faedeb7b22868f5846bbb104cc86` |
| Observed batch-timer GCD | 47 TSC ticks |
| Toolchain | MSVC `cl.exe` 19.51.36260.0, `/std:c11 /O2 /W4 /WX`; `ml64`, `link`, `dumpbin` 14.51.36260.0 |

ZIP CRC, seven manifest file hashes, ten source hashes against the recorded
commit, executable, PE `.text`, disassembly and embedded trace binary hashes
match. Independent analyzer replay accepts all 81,920 samples, seed order,
balanced positions, schedule/pattern hashes, checksum and architectural
totals. Its JSON reproduces the archived output and strict analysis exits
`0`. The build log is consistent UTF-8 and contains no compiler warnings.
These are internal consistency checks, not independent hardware attestation.

## Frozen control results

Each estimate is a paired 10%-trimmed mean followed by its 95% within-run
32-block-cycle bootstrap interval. Units are TSC ticks per complete probe
episode, not per branch call. `fast_b - fast_a` and fixed-neutral intervals
must fit strictly inside `(-1,+1)`; `dose4 - fast_c` needs a positive lower
bound, upper bound below `8`, and point in `[1,8]`; `pause - fast_d` needs a
positive lower bound and at least 95% positive paired blocks. All criteria
apply separately to each `p,n` stratum.

| Stratum | Fast placebo | Fixed neutral | `dose4` | `pause` |
| --- | ---: | ---: | ---: | ---: |
| `p0_n1` | +0.058 [-0.010,+0.126] | +0.014 [-0.086,+0.119] | +6.236 [+6.163,+6.307] | +50.564 [+50.457,+50.677] |
| `p1_n1` | -0.003 [-0.071,+0.074] | -0.024 [-0.122,+0.072] | +5.396 [+5.315,+5.477] | +49.686 [+49.578,+49.795] |
| `p0_n16` | -0.120 [-0.350,+0.098] | -0.230 [-0.518,+0.026] | +6.172 [+5.871,+6.459] | +55.535 [+55.164,+55.970] |
| `p1_n16` | +0.177 [-0.059,+0.428] | +0.100 [-0.149,+0.358] | +6.095 [+5.846,+6.361] | +56.954 [+56.655,+57.258] |

Every table entry passes its specified gate. Positive paired block fractions
for the four PAUSE controls are 98.4%, 98.8%, 96.9%, and 97.5%, respectively.
The `dose4` positive fractions at n16 are about 87–88%; that fraction was
descriptive and was **not** a dose gate. Split-half estimates remain close to
the full-run estimates, though all intervals condition on this one host run.

## Instruction audit and interpretation

The archived branch address resolves to RVA `0x2230` in the matched PE. The
linked conditional branch reads live, fixed and mode bytes, uses a conditional
move for the decision source, branches once and returns the live byte. Only
one direct call to this assembly branch site appears in the measurement
`run_branch` function; that function serves prelude, training and probe.
The condition decoder selects one versus sixteen probe calls as specified.
Live training and every probe use live mode, fixed training uses the periodic
decision stream. All `fast_a/b/c/d` and fixed controls dispatch to the same
timed function. The result-dependent four-step `dose4` sequence and the
`PAUSE` instruction appear in their distinct timed paths between the fenced
TSC readings. The executable and section hashes match the archive.

This verifies the linked instruction topology, not a predictor mechanism.
The narrower v3 placebo intervals are consistent with a more precise paired
apparatus, but adjacency and sample size changed together. This run cannot
attribute the improvement to either change or erase the failed v2 pilot.

The [Fractal paper](https://people.csail.mit.edu/mengjia/data/2026.SP.fractal.pdf)
studied Apple M1 conditional prediction using sender/receiver observations
across privilege and ASID domains. This same-process Windows timing control
does not confirm or refute those findings. A new outcome experiment must be
specified before collecting any real-versus-fixed B2 contrast, must include
fresh apparatus controls and a physical instruction audit, and must retain
null and failed-control outcomes as attempts.
