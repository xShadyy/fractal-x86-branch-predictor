# Fractal x86 Branch Predictor

An independent x86 microarchitecture study using [Fractal OS](https://github.com/jprx/fractal) as experimental infrastructure. The first measurement is a calibrated cache probe with architectural controls.

Fractal was developed by Joseph Ravichandran and Mengjia Yan. Their [paper](https://people.csail.mit.edu/mengjia/data/2026.SP.fractal.pdf) studies Apple M1. This repository contains independent x86 code and pins the upstream source revision without copying it into Git.

## Run the cache controls

On an x86 Linux machine with a C compiler and Python 3:

```bash
./scripts/record_host.sh
./scripts/check_native.sh
```

The native check writes a raw trace under `out/` and reports the calibration result. When `taskset` is installed, it pins the process to the first allowed logical CPU; set `CACHE_PROBE_CPU` to select another allowed CPU. Run the same program under Fractal after installing the pinned upstream toolchain:

```bash
./scripts/fetch_upstream.sh
cd upstream/fractal/toolchain
./mk_toolchain.sh all
cd ../../..
./scripts/build_qemu.sh
./scripts/run_qemu.sh 2>&1 | tee out/qemu-cache-probe.log
python3 scripts/analyze_cache_probe.py out/qemu-cache-probe.log
```

Use `-machine q35` for the x86 QEMU boot, as configured in `run_qemu.sh`. The output ends with `CACHE_END` and `FRACTAL_UTEST_OK`. After that marker, stop QEMU with Ctrl+C. The program checks TSC and CLFLUSH support before collecting samples.

For a physical run, boot the Fractal image on the selected workstation and capture its complete serial output. Pass the saved trace to `scripts/analyze_cache_probe.py`. Add `--strict` to have the analyzer return a nonzero status when the controls are inconclusive; add `--json` for machine-readable output.

## Measurement

The program interleaves 1,024 samples in each of four classes: a known cached line, a flushed line, a flushed line loaded by an architectural branch target, and a flushed line skipped by the branch. The branch control places a fence before the target load to keep speculative execution out of this calibration. An assembly routine timestamps only the subsequent cache-line reload. Results stay in memory until all trials finish.

The analyzer fits a cache-hit threshold from the first half of the cached and flushed samples. It then reports held-out hit rates for all four classes and accepts the controls when known cached and target-loaded lines each have at least 95% hits, and flushed and skipped lines each have at most 5% hits. Keep the raw trace and the `record_host.sh` inventory together for each workstation run. QEMU exercises the build, serial capture, and parser; physical measurements use the target CPU.
