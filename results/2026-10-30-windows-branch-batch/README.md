# Windows branch-pattern timing: two archived runs

**Status:** preliminary, same-domain user-mode timing result. This directory contains the complete traces and the exact executables from two runs on 2026-10-30 UTC. Both runs used the experiment introduced in `366ec1f` and the corrected reporting/archival script in `4c073cb`. No kernel or Fractal measurement was made.

## Question and protocol

Does a balanced, shuffled sequence of branch outcomes take longer than the balanced periodic `0011` sequence when both pass through the same conditional branch address and the same caller site?

Each run consists of 144 complete blocks. Each block measures six conditions in a shuffled, position-balanced order. Every condition contains 8,192 loop iterations; six warm-up blocks precede recorded data. The two patterns have 4,096 zeroes and 4,096 ones each. The shuffled pattern changes between blocks, but the fixed seed (`824702107`) produces the **same sequence of patterns and condition orders in both runs**. Input copying and shuffle generation are outside the timed batch.

The branch function reads the condition and loads the target byte when the condition is nonzero. Its branchless comparator reads both bytes on every iteration, so memory traffic is not exactly matched. The timer positive control adds `PAUSE` once every 128 iterations. The 10% trimmed mean is computed from the within-block random-minus-periodic differences; the adjusted estimate is the trimmed mean of each block's branch difference minus its branchless difference. Its bootstrap interval resamples whole six-block position cycles **within a run**.

## Host and artifact checks

The host was reported as an AMD Ryzen 7 9800X3D; the traces record `AuthenticAMD`, CPUID signature `0x00b40f40`, invariant TSC, `hypervisor=1`, and affinity to logical CPU 0. The reported motherboard is Gigabyte X870E AORUS ELITE WIFI7 with BIOS FA9. The Windows version, power policy, microcode revision, background workload and mitigation configuration were not captured in these traces.

| UTC run | Trace | Archived EXE SHA-256 |
| --- | --- | --- |
| `20261030T000304Z` | [raw trace](branch-batch-windows-20261030T000304Z.log) | `6f982db3152f11800fef1024f8d18ae1b671060d436a01d402528e9dee77ddf1` |
| `20261030T000321Z` | [raw trace](branch-batch-windows-20261030T000321Z.log) | `1e964ddcba8cdbdaa70bc2eacbe3d533160176697434ed17c5af7e5ad84ae91c` |

The `BATCH_BINARY` record in each trace equals the SHA-256 of its timestamp-matched EXE. The two EXEs differ in two linker timestamp bytes; their `.text` sections are identical, SHA-256 `e81a36ff7a733a1b97e25ea213b86264dec677387fd56d837e19d82a782176ca`. Read-only disassembly shows one direct call from the timed branch loop to `test; je` at RVA `0x1b10`, and a separate direct call from the comparator loop to the branchless function at RVA `0x1b1e`. Logged runtime addresses agree with these RVAs after ASLR. The timed interval brackets the runner with fenced TSC reads.

## Results

Units for the three contrasts are TSC ticks per loop iteration. Intervals in brackets are 95% six-block-cycle bootstrap intervals **within the same run**, not intervals over independent seeds, days or hosts.

| UTC run | Branch random − periodic | Branchless random − periodic | Adjusted within-block interaction | Timer slow − fast, ticks/batch |
| --- | ---: | ---: | ---: | ---: |
| `000304Z` | +16.086 [16.053, 16.137] | −0.001 [−0.002, +0.000] | +16.082 [16.047, 16.134] | +13,557.9 |
| `000321Z` | +16.095 [16.063, 16.130] | +0.000 [−0.001, +0.002] | +16.093 [16.064, 16.127] | +13,527.1 |

Both timer controls were positive in all 144 blocks. All 144 adjusted block contrasts were positive in each run. The adjusted estimates in the first and second halves were +16.119/+16.045, then +16.079/+16.107 ticks per iteration. Median branch durations were about 4.946 for periodic and 21.039/21.036 for shuffled input; the two branchless medians were each about 3.597. All batch totals have a GCD of 47 TSC ticks, with an undetermined cause; the batch difference is much larger than this per-batch quantum.

An earlier console-only pilot reported an adjusted +16.179 ticks per iteration, but its raw trace and matching EXE are **not archived here**, so that report is excluded from the two-run validation above.

## Interpretation and next falsification tests

These two archived runs reproduce a large timing difference tied to branch outcome order under this fixed program and seed. The branchless comparator's estimate is near zero, but its interval crossing zero is not proof of exact equivalence. The comparator's target-read behavior differs from the conditional branch. Both runs occurred 17 seconds apart with the same fixed stimulus, so the narrow within-run intervals cannot establish reproducibility across seeds, sessions, power states or processors. TSC ticks are not a count of wrong predictions. The current result does not answer whether predictor state crosses a privilege boundary.

The next experiment should retain the conditional branch but remove its target-byte load, with matched outcomes and a separate call site. Use independent recorded seeds for further full runs, preserve all runs including null results, and compare the conditional sites with the branchless and timer controls. A future hardware counter validation would require a reliable counter configuration on this Windows host; the `hypervisor=1` flag and 47-tick lattice need explicit investigation before stronger mechanistic claims.

## Reanalysis

From the repository root, run each trace through the historical-compatible analyzer:

```bash
python3 scripts/analyze_branch_batch.py results/2026-10-30-windows-branch-batch/branch-batch-windows-20261030T000304Z.log --strict --json
python3 scripts/analyze_branch_batch.py results/2026-10-30-windows-branch-batch/branch-batch-windows-20261030T000321Z.log --strict --json
```

Verify each EXE's SHA-256 against its trace's `BATCH_BINARY` line before inspecting instructions. The raw traces contain the complete recorded samples, order, seed, pattern commitment and checksums; the paired EXEs allow independent disassembly.
