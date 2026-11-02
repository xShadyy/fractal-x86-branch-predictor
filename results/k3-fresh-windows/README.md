# First K3 Windows engineering pilot

Collected 2 November 2026, 22:49:52 UTC. Reviewed 3 November 2026.

The collector succeeded. The original runner intentionally threw after
analysis because two frozen scientific controls failed. This is not a
compiler failure, antivirus error or a refusal by the assistant.

The original evidence archive is retained byte for byte as
`fresh-receiver-windows-20261102T224945699Z.zip`.

| Item | Value |
| --- | --- |
| Original ZIP SHA256 | `f163cb4d912ff33a06edd9660fb95a481ec0d89dfe10359ba9a67162b260d8d9` |
| Source commit | `6e824deb74249191839d943e7819195f60487c2c` |
| EXE SHA256 | `80ff83876f351fabfe24ce58b9d74fd8c7472b496a60077b0f0dc93517d8263b` |
| Host reported | AMD Ryzen 7 9800X3D, Windows 11 Pro 26200, hypervisor present |
| Seed and recorded episodes | 70098319; 131,072 |
| Gates | 56/58; inconclusive |
| Matched candidate, NOP p0 | 8.9355% hits; frozen maximum 5% |
| Matched candidate, NOP p1 | 9.5215% hits; frozen maximum 5% |
| p0 adjusted NOP contrast | +4.541 percentage points, 95% within-run interval [-6.689,+15.625] |
| p0 adjusted CPUID contrast | 0.000 points, interval [0.000,0.000] |
| p0 NOP minus CPUID interaction | +4.541 points, interval [-6.689,+15.625] |
| Frozen numerical signature | False |
| Trained target or transient execution established | No |

## Reproduced checks

`verified-audit.json` verifies all 11 manifest member hashes, all 12 source
snapshot hashes, the 131,072-row schedule and token replay, architectural
returns, event/checksum records, EXE hash and both 399-byte RX snapshots.
The archived analysis is reproduced exactly, including all failed gates.
The 31,330 instruction records in the archived disassembly account for
107,360 checked bytes and match the linked PE. This last check establishes
byte correspondence, not the semantic correctness of the C harness.

```bash
python scripts/audit_fresh_receiver_archive.py \
  results/k3-fresh-windows/fresh-receiver-windows-20261102T224945699Z.zip \
  --output /tmp/k3-audit.json
```

These checks establish internal artifact consistency. They do not attest
physical host conditions, firmware settings or microarchitectural events.

## Exploratory episode-position diagnostic

Thresholds remain the frozen 399 TSC ticks for both receivers. This table
uses all held-out candidate observations, split after the first four of
sixteen episodes for description only. Every episode remains in the primary.

| NOP candidate | Episodes 0..3, n=512 | Episodes 4..15, n=1,536 |
| --- | --- | --- |
| t0, probe p0, matched | 30.273% | 1.823% |
| t1, probe p0, mismatched | 43.945% | 3.255% |
| t0, probe p1, mismatched | 38.672% | 0.651% |
| t1, probe p1, matched | 34.375% | 1.237% |

All four corresponding CPUID rates are zero. The measured timing GCD is
47 TSC ticks. Its cause is undetermined. Entry-sensitive heat also occurs
with matched training, so a NOP/CPUID difference by itself cannot identify
the selected trained target. Dropping the initial episodes would be an
outcome-driven change and is not permitted for K3.

## Bounded linked-path review

PE image base is `0x140000000`; addresses below are RVAs. Runtime code is
separately allocated and represented by the two archived RX snapshots.

| Path | Observed linked instructions |
| --- | --- |
| Shared invocation, `0x1bd0` | LEA context at `0xac000`; indirect tail jump through `0x5ac038`; INT3 follows. |
| Training loop, `0x23f3` | Store constant condition, call the shared invocation, accumulate return, loop branch at `0x2403`. |
| End of preparation, `0x27d0` | Warm-condition branch; otherwise condition CLFLUSH; MFENCE; register restores; jump to serializer through `0x5ac048`. |
| Candidate wrapper, `0x2860` | Call preparation at `0x2869`; shared invocation at `0x286e`; store return at `0x2873`; RET. |
| Omitted wrapper, `0x28b0` | Call preparation; store zero probe return; RET. |
| HOT wrapper, `0x2880` | Call preparation; pass receiver pointer to the serialized HOT helper. |
| Reload calls, `0x17b5`, `0x17c8`, `0x17d8`, `0x17e6` | Use the helper through `0x5ac040`; order selects wanted/decoy. Runtime helper starts with CPUID before its timed marker read. |

The RX body has only two exclusive architectural token/marker paths, with
RET/INT3 endings. Tokens are assigned after page-zero training; the measured
opposite bank is disjoint from the architecturally selected probe bank.
Returns agree with the selected architectural path in every retained sample.

The linked paths also establish a limitation: the immediately preceding
instruction paths differ between training and probing. Reusing a conditional
address does not ensure identical predictor context. The snapshot and linked
review constrain intended architectural access; they cannot rule out all
prefetching, speculative control-flow, prior-episode, patching, Hyper-V or
context effects. No hardware event trace or misprediction counter resolves
those alternatives. The original pending mechanism conclusion remains valid.

## Follow-up

K3's collector, byte contract, analyzer and frozen protocol remain unchanged.
The runner now distinguishes successful evidence collection from failed
scientific gates. `-RequireValidControls` retains a nonzero gate for automation.
The separate [K4 protocol](../../protocols/CONTEXT_RECEIVER_K4.md) adds a fixed
local branch prefix and interleaves conditions. Its design is a prospective
apparatus diagnostic, not evidence that the confound is resolved.
