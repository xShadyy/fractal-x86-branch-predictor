#!/usr/bin/env python3
"""Assemble the readable K4 layout and compare it with both frozen byte copies.

Development check: requires GNU-compatible cc and objcopy. The Windows runner
uses the frozen template directly, then verifies actual runtime snapshots.
"""
from pathlib import Path
import re
import subprocess
import tempfile
from context_receiver_contract import CODE, BRANCH, PATCHES, TARGETS, RELOAD, SERIAL, HOT


def verify(root: Path) -> None:
    header = (root / "programs/context_receiver_code.h").read_text()
    data = header.split("context_code_template[] = {", 1)[1].split("};", 1)[0]
    if bytes(int(x, 16) for x in re.findall(r"0x([0-9a-f]{2})", data)) != CODE:
        raise ValueError("C template differs from analyzer contract")
    expected = {"K4_BRANCH": BRANCH, "K4_PATCH_ONE": PATCHES[0], "K4_PATCH_ZERO": PATCHES[1],
                "K4_RELOAD": RELOAD, "K4_SERIAL": SERIAL, "K4_HOT": HOT}
    for name, value in expected.items():
        if re.search(rf"#define {name} {value}u\b", header) is None:
            raise ValueError(f"C entry offset mismatch: {name}")
    with tempfile.TemporaryDirectory() as temporary:
        obj, binary = Path(temporary) / "layout.o", Path(temporary) / "layout.bin"
        subprocess.run(["cc", "-c", str(root / "programs/context_receiver_layout.S"), "-o", str(obj)], check=True)
        subprocess.run(["objcopy", "-O", "binary", "-j", ".text", str(obj), str(binary)], check=True)
        if binary.read_bytes() != CODE:
            raise ValueError("assembled instructions differ from frozen runtime bytes")
    # The only conditional jump must reach the other exclusive target.
    if CODE[BRANCH:BRANCH+2] != b"\x0f\x84" or \
            BRANCH + 6 + int.from_bytes(CODE[BRANCH+2:BRANCH+6], "little", signed=True) != TARGETS[0]:
        raise ValueError("conditional target displacement mismatch")
    for offset in PATCHES:
        if CODE[offset:offset+2] != b"\x90\x90":
            raise ValueError("barrier patch slot differs")


if __name__ == "__main__":
    verify(Path(__file__).resolve().parents[1])
    print("K4 readable assembly, C template, offsets and analyzer byte contract match.")
