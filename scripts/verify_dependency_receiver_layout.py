#!/usr/bin/env python3
"""Assemble the readable K5 layout and compare it with both frozen byte copies.

Development check: requires GNU-compatible cc and objcopy. The Windows runner
uses the frozen template directly, then verifies actual runtime snapshots.
"""
from pathlib import Path
import re
import subprocess
import tempfile
from dependency_receiver_contract import CODE, BRANCH, PATCH_ONE, PATCH_ZERO, MASK_ONE, MASK_ZERO, RELOAD, SERIAL, HOT


def verify(root: Path) -> None:
    header = (root / "programs/dependency_receiver_code.h").read_text()
    data = header.split("dependency_code_template[] = {", 1)[1].split("};", 1)[0]
    if bytes(int(x, 16) for x in re.findall(r"0x([0-9a-f]{2})", data)) != CODE:
        raise ValueError("C template differs from analyzer contract")
    expected = {"K5_MASK_ONE": MASK_ONE, "K5_MASK_ZERO": MASK_ZERO, "K5_BRANCH": BRANCH, "K5_PATCH_ONE": PATCH_ONE, "K5_PATCH_ZERO": PATCH_ZERO,
                "K5_RELOAD": RELOAD, "K5_SERIAL": SERIAL, "K5_HOT": HOT}
    for name, value in expected.items():
        if re.search(rf"#define {name} {value}u\b", header) is None:
            raise ValueError(f"C entry offset mismatch: {name}")
    with tempfile.TemporaryDirectory() as temporary:
        obj, binary = Path(temporary) / "layout.o", Path(temporary) / "layout.bin"
        subprocess.run(["cc", "-c", str(root / "programs/dependency_receiver_layout.S"), "-o", str(obj)], check=True)
        relocations = subprocess.check_output(["readelf", "-r", str(obj)], text=True)
        if "There are no relocations" not in relocations:
            raise ValueError("runtime object contains unresolved relocations")
        subprocess.run(["objcopy", "-O", "binary", "-j", ".text", str(obj), str(binary)], check=True)
        if binary.read_bytes() != CODE:
            raise ValueError("assembled instructions differ from frozen runtime bytes")
    # The measured conditional jump must reach the other exclusive target.
    if CODE[BRANCH:BRANCH+2] != b"\x0f\x84" or \
            BRANCH + 6 + int.from_bytes(CODE[BRANCH+2:BRANCH+6], "little", signed=True) != PATCH_ZERO:
        raise ValueError("conditional target displacement mismatch")
    for offset in (PATCH_ONE, PATCH_ZERO):
        if CODE[offset:offset+3] != b"\x90\x90\x90":
            raise ValueError("barrier patch slot differs")
    lea = CODE.index(bytes.fromhex("488d05"))
    if lea + 7 + int.from_bytes(CODE[lea+3:lea+7], "little", signed=True) != BRANCH:
        raise ValueError("recorded measured-site RIP displacement mismatch")


if __name__ == "__main__":
    verify(Path(__file__).resolve().parents[1])
    print("K5 readable assembly, C template, offsets and analyzer byte contract match.")
