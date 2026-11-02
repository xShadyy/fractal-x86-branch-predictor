"""K4 code: fixed prefix before the frozen K3 body; no predictor reset claim."""
from fresh_receiver_contract import CODE as BODY, PATCHES as BODY_PATCHES
from fresh_receiver_contract import BRANCH as BODY_BRANCH, TARGETS as BODY_TARGETS
from fresh_receiver_contract import RELOAD as BODY_RELOAD, SERIAL as BODY_SERIAL, HOT as BODY_HOT

PREFIX_BRANCHES = 256
PREFIX = b"\x31\xc0" + b"\x85\xc0\x74\x01\xcc" * PREFIX_BRANCHES + b"\x90" * 62
CODE = PREFIX + BODY
PATCHES = tuple(len(PREFIX) + offset for offset in BODY_PATCHES)
BRANCH = len(PREFIX) + BODY_BRANCH
TARGETS = tuple(len(PREFIX) + offset for offset in BODY_TARGETS)
RELOAD, SERIAL, HOT = (len(PREFIX) + offset for offset in (BODY_RELOAD, BODY_SERIAL, BODY_HOT))


def code_for(mode: str) -> bytes:
    if mode not in ("nop", "cpuid"):
        raise ValueError("unknown K4 mode")
    image = bytearray(CODE)
    if mode == "cpuid":
        for offset in PATCHES:
            image[offset:offset+2] = b"\x0f\xa2"
    return bytes(image)
