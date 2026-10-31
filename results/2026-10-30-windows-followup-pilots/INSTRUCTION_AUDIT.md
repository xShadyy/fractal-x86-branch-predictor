# Instruction audit for the Windows follow-up pilots

This appendix checks the two archived pilot executables against their traces and the six runs per study in the [two-day replication](../2026-10-30-31-windows-followup-replication/README.md). The commands below run on Linux from the repository root and **read** the Windows PE files; they do not execute or modify them. The pilot source plan predates the measurements at commit `84f6182`, but inspecting a binary cannot prove which source revision produced it.

## Pairing, image addresses and bytes

The PE preferred image base is `0x140000000` in both pilot files. GNU `objdump` prints preferred virtual addresses (for example `0x140001bf0`). The traces print addresses after Windows ASLR. Subtract the symbol's relative virtual address (RVA) from its trace address to obtain that run's load base:

| Pilot | Full EXE SHA-256 | Trace branch address | RVA | Inferred runtime image base |
| --- | --- | --- | --- | --- |
| Decision source A | `f4b6e8e1970336781c018f70bc3f9360abf369a96faf657b1537c1b1f928fa03` | `0x7ff6451c1bf0` | `0x1bf0` | `0x7ff6451c0000` |
| History probe B | `6e7575cb065c1828feaa7ef01b20ae9533a1c049b94f3b0df7181275887a45b3` | `0x7ff7cb0b1c80` | `0x1c80` | `0x7ff7cb0b0000` |

Each full hash matches the `DECISION_BINARY` or `HISTORY_BINARY` line in its paired log. In A, the branchless site at RVA `0x1c09` and the live, periodic-control and mode bytes at `0x23b00`, `0x23b40`, `0x23b80` also agree with the addresses in the log after subtracting the inferred base. In B, the sham site is at RVA `0x1c8e`.

Relevant pilot instructions, with RVAs and the exact on-disk bytes:

| Executable | RVA | Bytes | Meaning |
| --- | --- | --- | --- |
| A | `0x1a8a` | `e8 61 01 00 00` | One direct call inside the 8,192-iteration primary loop to `0x1bf0` |
| A | `0x1bf0` | `0f b6 01 44 0f b6 12 45 0f b6 18 45 85 db 44 0f 45 d0 45 85 d2 74 01 90 c3` | Load live, control and mode; `test mode; cmovne` selects decision; `test decision; je` is the single conditional decision site; return live `AL` |
| A | `0x1afa` | `e8 0a 01 00 00` | Separate loop call to branchless comparator at `0x1c09`, whose final selection uses `setne` instead of `je` |
| B | `0x1ae2` | `e8 99 01 00 00` | One direct in-loop call to `0x1c80` shared by reset prelude, real training and timed probe |
| B | `0x1c80` | `0f b6 01 85 c0 74 04 b0 01 90 c3 33 c0 c3` | Read condition; `test; je`; return 0 or 1 without reading a target byte |
| B | `0x1b32` | `e8 57 01 00 00` | Separate sham training loop calls `0x1c8e`, which is `movzx eax,[rcx]; ret` (`0f b6 01 c3`) |

A's timed indirect runner call is at RVA `0x13cc` (`ff d5`), between `lfence; rdtsc; lfence` and `lfence; rdtsc` at RVAs `0x13b3`–`0x13c2` and `0x13d1`–`0x13d4`. For B, the primary wrapper at `0x1b50` reads TSC at `0x1b60`, calls the same branch runner at `0x1b7b`, then reads TSC at `0x1b85`, with fences around those operations. There is no added-work conditional in this primary wrapper. The separate slow timer wrapper at `0x1ba0` executes an unconditional `pause` (`f3 90`) at `0x1bbf` before calling the branch runner at `0x1bcd`. A positive timer check therefore demonstrates sensitivity to this separate wrapper's added work, not an isolated `PAUSE` cost.

The `je` instruction is also spelled `jz`, `cmovne` as `cmovnz`, and `setne` as `setnz` by some disassemblers. Those spellings refer to the same encodings here.

## Reproduce the disassembly

From the repository root, using GNU binutils on Linux:

```bash
decision=results/2026-10-30-windows-followup-pilots/decision-source-windows-20261030T163709Z.exe
history=results/2026-10-30-windows-followup-pilots/history-probe-windows-20261030T163724Z.exe
sha256sum "$decision" "$history"
objdump -d -Mintel --start-address=0x140001a60 --stop-address=0x140001aa0 "$decision"
objdump -d -Mintel --start-address=0x140001bf0 --stop-address=0x140001c23 "$decision"
objdump -d -Mintel --start-address=0x1400013b3 --stop-address=0x1400013d6 "$decision"
objdump -d -Mintel --start-address=0x140001ad0 --stop-address=0x140001af4 "$history"
objdump -d -Mintel --start-address=0x140001b50 --stop-address=0x140001bee "$history"
objdump -d -Mintel --start-address=0x140001c80 --stop-address=0x140001c92 "$history"
```

The start/stop arguments are **preferred virtual addresses**, not runtime ASLR addresses or file offsets. The A branchless caller at RVA `0x1afa` falls outside the first caller window; inspect it with `--start-address=0x140001ad0 --stop-address=0x140001b11` if needed. Inspect the complete loop, not merely an instruction at the recorded branch address: a source-level fixed branch is useful only when the optimized caller actually reaches it from the expected path.

## Verify raw `.text` equality across dates

The reported `.text` digests use the PE section header's `SizeOfRawData` bytes from `PointerToRawData`, including file-alignment padding. Both pilot `.text` raw sections start at file offset `0x400` and contain `0x16400` bytes. Their `VirtualSize` values are smaller (`0x162e0` for A, `0x16350` for B). This read-only script checks each pilot plus three A and three B builds from **each** of 30 and 31 October:

```bash
python3 - <<'PY'
from pathlib import Path
import hashlib
import struct

pilots = Path('results/2026-10-30-windows-followup-pilots')
replicas = Path('results/2026-10-30-31-windows-followup-replication')
studies = {
    'decision-source': (
        pilots / 'decision-source-windows-20261030T163709Z.exe',
        '0f302df7d38b2c1e1eb840104cd4c51da4d0d802a8e540ee74fd8d20a11ec1e9'),
    'history-probe': (
        pilots / 'history-probe-windows-20261030T163724Z.exe',
        'b7ee4707628ac45f621ffd281066efd0cff3652717324fe3baa7c592c8289e3b'),
}

def text_digest(path):
    data = path.read_bytes()  # Never opens the executable for writing.
    pe = struct.unpack_from('<I', data, 0x3c)[0]
    assert data[pe:pe + 4] == b'PE\0\0'
    count = struct.unpack_from('<H', data, pe + 6)[0]
    optional_size = struct.unpack_from('<H', data, pe + 20)[0]
    table = pe + 24 + optional_size
    for index in range(count):
        section = table + index * 40
        if data[section:section + 8].rstrip(b'\0') == b'.text':
            _, _, raw_size, raw_offset = struct.unpack_from('<IIII', data, section + 8)
            raw = data[raw_offset:raw_offset + raw_size]
            assert len(raw) == raw_size
            return hashlib.sha256(raw).hexdigest()
    raise ValueError(f'missing .text: {path}')

for study, (pilot, expected) in studies.items():
    paths = [pilot, *sorted(replicas.glob(f'session-*/{study}-windows-*.exe'))]
    assert len(paths) == 7, (study, len(paths))
    for path in paths:
        digest = text_digest(path)
        assert digest == expected, (path, digest)
        print(f'{path}: .text SHA-256 {digest}')
PY
```

All seven A files have `.text` SHA-256 `0f302df7d38b2c1e1eb840104cd4c51da4d0d802a8e540ee74fd8d20a11ec1e9`; all seven B files have `b7ee4707628ac45f621ffd281066efd0cff3652717324fe3baa7c592c8289e3b`. Their **full EXE hashes differ**, as recorded in each log and manifest, even though the raw executable-code sections agree. Equality of this section cannot establish equal runtime microcode, predictor state, environment, relocations in other sections or a particular compiler provenance. It also cannot count mispredictions or establish cross-domain predictor sharing. The fixed 16-call B probe can itself change the predictor state it is meant to sense; these bytes do not resolve that design limitation.
