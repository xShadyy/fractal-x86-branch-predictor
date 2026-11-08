#!/usr/bin/env python3
"""Generate or check the Windows runtime template from readable assembly.

Development tools required: GNU-compatible cc, nm, readelf and objcopy.
The Windows collector uses these checked-in bytes, not an assembler at runtime.
"""
from __future__ import annotations
import argparse
from pathlib import Path
import subprocess
import tempfile

SYMBOLS = ("BRANCH", "PATCH_ONE", "PATCH_ZERO", "MASK_ONE", "MASK_ZERO",
           "LOAD_ONE", "LOAD_ZERO", "RELOAD", "SERIAL", "HOT")
CONTRACT_TAIL = '''MODES = {
    "dependency": ("plain", "true_mask", "sham_mask", "lfence", "cpuid"),
    "receiver": ("plain", "ablate_zero", "ablate_one", "ablate_both", "sink_both"),
}


def code_for(study: str, mode: str) -> bytes:
    if study not in MODES or mode not in MODES[study]:
        raise ValueError("unknown causal receiver study or mode")
    image = bytearray(CODE)
    if study == "dependency":
        if mode in ("lfence", "cpuid"):
            patch = bytes.fromhex("0faee8" if mode == "lfence" else "0fa290")
            for offset in (PATCH_ONE, PATCH_ZERO):
                image[offset:offset+3] = patch
        elif mode in ("true_mask", "sham_mask"):
            # Both controls have identical TEST/CMOV instruction topology.
            # ESI=0 and EDI=1 were prepared before the condition load.
            one = "85d20f44c6" if mode == "true_mask" else "85ff0f44c6"
            zero = "85d20f45c6" if mode == "true_mask" else "85f60f45c6"
            image[MASK_ONE:MASK_ONE+11] = bytes.fromhex(one) + b"\\x90"*6
            image[MASK_ZERO:MASK_ZERO+11] = bytes.fromhex(zero) + b"\\x90"*6
    else:
        # MOV EAX,constant is exactly as long as the original marker load.
        # It preserves all architectural return-value checks.
        if mode in ("ablate_zero", "ablate_both"):
            image[LOAD_ZERO:LOAD_ZERO+5] = bytes.fromhex("b801000000")
        if mode in ("ablate_one", "ablate_both"):
            image[LOAD_ONE:LOAD_ONE+5] = bytes.fromhex("b802000000")
        # sink_both retains plain bytes; context pointers bind private banks.
    return bytes(image)
'''


def generated(root: Path) -> dict[Path, str]:
    with tempfile.TemporaryDirectory() as tmp:
        obj, binary = Path(tmp)/"layout.o", Path(tmp)/"layout.bin"
        subprocess.run(["cc", "-c", str(root/"programs/causal_receiver_layout.S"), "-o", str(obj)], check=True)
        relocations = subprocess.check_output(["readelf", "-r", str(obj)], text=True)
        if "There are no relocations" not in relocations:
            raise ValueError("runtime object contains unresolved relocations")
        subprocess.run(["objcopy", "-O", "binary", "-j", ".text", str(obj), str(binary)], check=True)
        code = binary.read_bytes()
        symbols = {line.split()[2]: int(line.split()[0], 16)
                   for line in subprocess.check_output(["nm", "--defined-only", str(obj)], text=True).splitlines()}
    offsets = {name: symbols["causal_"+name.lower()] for name in SYMBOLS}
    if len(code) > 4096 or symbols["causal_start"] != 0 or symbols["causal_end"] != len(code):
        raise ValueError("runtime image geometry changed")
    branch = offsets["BRANCH"]
    if code[branch:branch+2] != b"\x0f\x84" or branch+6+int.from_bytes(code[branch+2:branch+6], "little", signed=True) != offsets["PATCH_ZERO"]:
        raise ValueError("measured conditional target mismatch")
    lea = code.index(bytes.fromhex("488d05"))
    if lea+7+int.from_bytes(code[lea+3:lea+7], "little", signed=True) != branch:
        raise ValueError("recorded measured-site PC displacement mismatch")
    for name in ("PATCH_ONE", "PATCH_ZERO"):
        if code[offsets[name]:offsets[name]+3] != b"\x90"*3:
            raise ValueError("barrier patch slot mismatch")
    for name in ("MASK_ONE", "MASK_ZERO"):
        if code[offsets[name]:offsets[name]+11] != b"\x90"*11:
            raise ValueError("mask patch slot mismatch")
    if code[offsets["LOAD_ONE"]:offsets["LOAD_ONE"]+5] != bytes.fromhex("410fb60403") or code[offsets["LOAD_ZERO"]:offsets["LOAD_ZERO"]+5] != bytes.fromhex("410fb60402"):
        raise ValueError("marker load opcode mismatch")
    header = "/* Generated from causal_receiver_layout.S; run scripts/generate_causal_receiver.py --check. */\n"
    header += "".join(f"#define K7_{name} {offset}u\n" for name, offset in offsets.items())
    header += "static const unsigned char causal_code_template[] = {\n"
    header += "".join("    "+", ".join(f"0x{x:02x}" for x in code[i:i+16])+",\n" for i in range(0, len(code), 16)) + "};\n"
    contract = '"""Generated runtime contract for the K7/K8 Windows user-mode follow-up."""\nCODE = bytes.fromhex(\n'
    contract += "".join(f'    "{code[i:i+30].hex()}"\n' for i in range(0, len(code), 30)) + ")\n"
    contract += "".join(f"{name} = {offset}\n" for name, offset in offsets.items()) + CONTRACT_TAIL
    return {root/"programs/causal_receiver_code.h": header, root/"scripts/causal_receiver_contract.py": contract}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    for path, content in generated(Path(__file__).resolve().parents[1]).items():
        if args.check:
            if not path.exists() or path.read_text() != content:
                raise SystemExit(f"Generated runtime contract differs: {path.name}")
        else:
            path.write_text(content)
    print("K7/K8 readable assembly, C template and Python byte contract match.")


if __name__ == "__main__":
    main()
