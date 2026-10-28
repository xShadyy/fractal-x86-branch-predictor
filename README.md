# x86 Branch Predictor Experiments

Independent microarchitecture experiments on x86, informed by [Fractal](https://github.com/jprx/fractal) and the [Fractal paper](https://people.csail.mit.edu/mengjia/data/2026.SP.fractal.pdf) by Joseph Ravichandran and Mengjia Yan. The repository pins the upstream revision and contains independent measurement code.

## Run from VS Code on Windows

Install [VS Code](https://code.visualstudio.com/), Microsoft C++ Build Tools with **Desktop development with C++** and a Windows SDK, and Python 3. Open this repository in VS Code and press **Ctrl+Shift+B**. The `Cache probe: build, run, analyze (Windows)` task compiles a native x64 executable, pins it to one allowed logical CPU, records a raw trace in `out/`, and runs the analyzer. It locates the MSVC build environment automatically through `vswhere`.

The output reports the CPU signature, a threshold fitted from the first half of the calibration samples, and held-out hit rates for four controls. The task returns an error if the controls are inconclusive. `out/` is ignored by Git.

## Measurement

The program interleaves 1,024 samples in each class: a known cached line, a flushed line, a line loaded at an architecturally executed branch target, and a line skipped by the branch. A fence before the target load keeps speculation out of this calibration. Only the subsequent cache-line reload is timed. The full record is buffered until the measurement ends.

The analyzer uses the first half of the hot and cold samples to fit a cache-hit threshold and evaluates all four controls on the held-out half. Its acceptance gate requires at least 95% hits for the cached and target-loaded classes, and at most 5% hits for flushed and skipped classes. Inspect the optimized instructions when changing compiler settings or branch code.

## Linux development check

The same experiment can be built in an x86 Linux environment with a C compiler and Python 3:

```bash
./scripts/check_native.sh
```

The Linux runner writes a raw trace in `out/`. Use `./scripts/record_host.sh` for an inventory of that Linux environment. The separate Fractal build scripts remain in `scripts/` for kernel experiments.
