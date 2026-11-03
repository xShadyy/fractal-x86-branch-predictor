# K4: Windows pilot and three planned follow-up process sessions

Reviewed 3 November 2026. All collection timestamps below are the UTC values
reported in the traces. Source revision for all four collections:
`ee8422ffe6d466c4f51b1b550224ac63e30c96b4`.

**The frozen numerical fresh-marker signature occurred in the pilot and all
three follow-up sessions, with 58/58 apparatus gates passing in every run.**
This establishes recurrence of the controlled same-process signature on one
reported Ryzen 7 9800X3D host. It supports the transient-execution
interpretation; mechanism attribution is still incomplete. No privilege
boundary, Fractal execution, independent host, boot or day was tested.

## Run-level results

The primary is the adjusted p0 training contrast in NOP mode minus the
corresponding CPUID contrast. Values and intervals are percentage points.
Each interval resamples 16 complete held-out block cycles within that run.

| Run | Reported UTC start | Seed | Gates | Primary | 95% within-run interval |
| --- | --- | --- | --- | --- | --- |
| Pilot | 2 Nov 23:33:16 | 888890949 | 58/58 | +99.731 | [+99.609,+99.829] |
| Follow-up 1 | 2 Nov 23:41:38 | 830217184 | 58/58 | +99.878 | [+99.756,+99.976] |
| Follow-up 2 | 2 Nov 23:42:25 | 4108945320 | 58/58 | +99.512 | [+99.292,+99.707] |
| Follow-up 3 | 2 Nov 23:43:15 | 3039835034 | 58/58 | +99.731 | [+99.609,+99.854] |

The three follow-ups contain 786,432 recorded episodes, with 1,048,576 across
all four runs including calibration. Episodes are dependent observations,
not a million independent replications. The descriptive follow-up mean is
+99.707 points, range [+99.512,+99.878]. No pooled confidence interval or
population inference is reported.

In the follow-ups, NOP p0 opposite-training receiver hit rates were
99.927%, 99.707%, and 99.927%, versus matched-training rates of 0.049%,
0.195%, and 0.195%. No p0 candidate receiver hits were observed in CPUID
mode. The p1 mirror also showed high opposite-training and low matched
rates; it remains descriptive, not a replacement primary. No-probe and
decoy controls passed in every run.

## What was specified before the follow-ups

After examining the pilot, the chat instruction specified exactly three
fresh sessions with seeds 830217184, 4108945320, and 3039835034, keeping
the code and settings unchanged and retaining failed runs and nulls.
These are exactly the supplied three follow-up seeds. K4's pre-existing
per-run criteria were unchanged. There was no additional prespecified
pooled statistic or across-host decision rule.

This section is an archival record written after collection. It is not a
claim that this Markdown file was committed or independently registered
before those runs. The follow-ups were selected after a positive pilot and
ran sequentially on the same reported host within minutes.

## Reproduced artifact and numerical checks

All original ZIP bytes are retained. The second follow-up was uploaded
with a `(1)` suffix; its canonical filename here omits that suffix without
changing any archive bytes.

| Archive timestamp in filename | SHA256 |
| --- | --- |
| `20261102T233310118Z` | `48a26cabb7935b3550c7894fc69bf359088281dee4ec72daec90aadd4dd7e085` |
| `20261102T234133431Z` | `eed1622f5685f2f930ebaf0d4986b1d216665416dbce4304d25ec106d70f4130` |
| `20261102T234220965Z` | `14009b7bf51fbeb4f96ada80f5363324a88c43eebc7c5e5a6b1e36e465445172` |
| `20261102T234310535Z` | `ba97bb5a8f54f986300b2d944a6ffb1e19957587d2c0bf00eff766fe338622e2` |

Every archive's 11 manifest members and 13 source snapshots verify. All
source hashes, recorded toolchain versions, reported host inventories and
linked `.text` sections match the pilot. Source snapshot bytes also match
the recorded Git revision. The full EXE hashes differ; the raw linked
`.text` SHA256 is identical in all four:
`586dfb46074aa49327bb6d1b80070140759d560669d93e996f166cbd228b1b1b`.

The archived disassembly matches 107,120 linked bytes in 31,282 instruction
records per run. Both 1,743-byte RX snapshots match the frozen contract.
The collector used different recorded code-allocation addresses across
the four processes; no predictor-address-index claim follows from that.

Each full trace replays its schedule and both RNG streams, verifies
architectural returns and checksums, and reproduces its archived analysis
exactly. A separate raw-CSV implementation reproduces the primary point,
cycle contrasts and bootstrap endpoints. `verified-series.json` retains
the complete results and comparison flags. These checks establish internal
consistency, not independent attestation of the machine or measurement time.

## Bounded linked-path review

The common PE code places shared invocation at RVA `0x1ae0`, preparation
at `0x2280`, the candidate wrapper at `0x2770`, HOT at `0x2790` and omitted
probe at `0x27c0`. Training and probing both use the shared invocation;
each runtime invocation executes the fixed 256-branch prefix. Preparation
ends with MFENCE and the serializer through RVA `0xaac048`; the reload
calls use the helper through RVA `0xaac040`.

Within the runtime image, the measured conditional is at offset `0x55b`,
target-one entry at `0x561`, and target-zero entry at `0x5f3`. The reload,
serializer and HOT helpers are at `0x640`, `0x680`, and `0x6c0`. The two
target entries have same-address NOP/CPUID patch slots. Each exclusive
architectural body reads its own fresh token and its own bank, ending in
RET/INT3. Training uses page zero; fresh tokens are stored afterward.
The normal probe architecturally selects the bank opposite the receiver.

The repeated training selectivity, fresh-marker construction, clean no-probe
and decoy controls, matching committed returns and serialization sensitivity
support the intended interpretation. The review is bounded: CPUID also
changes timing and microarchitectural state, and the host reports a
hypervisor. It does not prove that every alternative cache-fill explanation
has been eliminated or identify an internal predictor entry. No branch-miss
counter or independent event trace was collected.

## Current claim and next milestone

The supported claim is a repeated, training-specific, serialization-sensitive
fresh-marker cache signature in one Windows user process on this reported
host. K3 remains inconclusive under its own unchanged criteria; its result
is not replaced by K4. Earlier native server K4 checks also remain failed
development observations, not Windows replications.

The next mechanism check should distinguish serialization at the target
from CPUID's wider effects and further test alternative cache-fill paths.
A Fractal privilege comparison then requires validating the receiver on
physical Fractal x86 in the same domain before changing privilege. More
identical sessions alone cannot answer either question.

## Reproduce

From the repository root, run this single command:

```bash
python scripts/audit_context_receiver_series.py --pilot results/k4-context-windows/context-receiver-windows-20261102T233310118Z.zip results/k4-context-windows/context-receiver-windows-20261102T234133431Z.zip results/k4-context-windows/context-receiver-windows-20261102T234220965Z.zip results/k4-context-windows/context-receiver-windows-20261102T234310535Z.zip --output /tmp/verified-k4-series.json
```

On Windows choose a suitable local path instead of `/tmp/verified-k4-series.json`.
The auditor reads the archives without executing their EXEs or source files.
