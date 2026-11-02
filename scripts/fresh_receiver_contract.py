"""Frozen K3 runtime bytes. Compare actual RX snapshots, not source spelling.

The branch reads the cold condition. Each exclusive target reads its own
fresh token, shifts that token by 12, and reads its own marker bank. Both
returns are followed by INT3. CPUID patches replace two NOPs in-place.
The timer and HOT control serialize with CPUID before any marker load.
Regenerate/audit against programs/fresh_receiver_layout.S with GNU as/objcopy.
"""

CODE = bytes.fromhex(
    "53488b114c8b41084c8b49104c8b51184c8b592031c00fb61285d20f84920000"
    "009090410fb60148c1e00c410fb604035bc3cccccccccccccccccccccccccccc"
    "cccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccc"
    "cccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccc"
    "cccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccc"
    "cccccccccccccccccccccccccccccccccccccc9090410fb60048c1e00c410fb6"
    "04025bc3cccccccccccccccccccccccccccccccccccccccccccccccccccccccc"
    "cccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccc"
    "534989ca31c00fa20f01f948c1e2204809d04989c00faee8410fb6020f01f90f"
    "aee848c1e2204809d04c29c05bc3cccccccccccccccccccccccccccccccccccc"
    "5331c00fa25bc3cccccccccccccccccccccccccccccccccccccccccccccccccc"
    "cccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccc"
    "534989ca31c00fa2410fb6025bc3cc"
)
PATCHES = (33, 179)
BRANCH = 27
TARGETS = (179, 33)
RELOAD = 256
SERIAL = 320
HOT = 384

def code_for(mode: str) -> bytes:
    if mode not in ("nop", "cpuid"):
        raise ValueError("unknown code mode")
    image = bytearray(CODE)
    if mode == "cpuid":
        for offset in PATCHES:
            image[offset:offset + 2] = b"\x0f\xa2"
    return bytes(image)
