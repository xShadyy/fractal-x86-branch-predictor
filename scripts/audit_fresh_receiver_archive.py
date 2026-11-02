#!/usr/bin/env python3
"""Verify an archived K3 pilot without executing its EXE or extracting ZIP paths.

Checks hashes, source snapshots, trace replay, frozen analysis, runtime code and
the correspondence between the archived dumpbin bytes and the linked PE. None
of these checks attests the host or proves a microarchitectural mechanism.
"""
from __future__ import annotations

import argparse
import hashlib
from io import BytesIO
import json
from pathlib import Path, PurePosixPath
import re
import struct
import tempfile
from zipfile import BadZipFile, ZipFile

from analyze_fresh_receiver import audit_files, parse_trace, summarize
from diagnose_fresh_receiver import diagnose


def digest(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def members(content: bytes) -> dict[str, bytes]:
    with ZipFile(BytesIO(content)) as archive:
        result = {}
        if sum(i.file_size for i in archive.infolist()) > 128 * 1024 * 1024:
            raise ValueError("archive exceeds evidence size limit")
        for info in archive.infolist():
            name = info.filename.replace("\\", "/")
            path = PurePosixPath(name)
            if path.is_absolute() or ".." in path.parts or ":" in name or name in result:
                raise ValueError("unsafe or duplicate ZIP member")
            if not info.is_dir():
                result[name] = archive.read(info)
        return result


def json_bytes(data: bytes):
    return json.loads(data.decode("utf-8-sig"))


def check_disassembly(binary: bytes, listing: str) -> dict:
    if binary[:2] != b"MZ":
        raise ValueError("missing PE header")
    pe = struct.unpack_from("<I", binary, 0x3c)[0]
    if binary[pe:pe+4] != b"PE\0\0":
        raise ValueError("invalid PE signature")
    count, optional_size = struct.unpack_from("<H", binary, pe+6)[0], struct.unpack_from("<H", binary, pe+20)[0]
    optional = pe + 24
    if struct.unpack_from("<H", binary, optional)[0] != 0x20b:
        raise ValueError("PE32+ required")
    base = struct.unpack_from("<Q", binary, optional+24)[0]
    sections = []
    for index in range(count):
        off = optional + optional_size + index*40
        size, rva, raw_size, raw = struct.unpack_from("<IIII", binary, off+8)
        sections.append((rva, raw_size, raw))

    def linked_bytes(address: int, length: int) -> bytes:
        rva = address-base
        for start, size, raw in sections:
            if start <= rva and rva+length <= start+size:
                return binary[raw+rva-start:raw+rva-start+length]
        raise ValueError("disassembly address outside linked file sections")

    address = None
    encoded = bytearray()
    instruction_count = byte_count = 0

    def flush():
        nonlocal instruction_count, byte_count
        if address is not None:
            if linked_bytes(address, len(encoded)) != encoded:
                raise ValueError(f"disassembly bytes mismatch at 0x{address:x}")
            instruction_count += 1
            byte_count += len(encoded)

    for line in listing.splitlines():
        match = re.match(r"^\s*([0-9A-Fa-f]{16}):\s+((?:[0-9A-Fa-f]{2}(?:\s+|$))+)", line)
        if match:
            flush()
            address = int(match[1], 16)
            encoded = bytearray.fromhex(match[2])
        elif address is not None and re.fullmatch(r"\s+(?:[0-9A-Fa-f]{2}\s*)+", line):
            encoded.extend(bytes.fromhex(line))
    flush()
    if instruction_count < 10:
        raise ValueError("missing linked disassembly")
    return {"listing_matches_linked_pe": True, "instruction_records_checked": instruction_count,
            "bytes_checked": byte_count,
            "scope": "byte_correspondence_only_not_control_flow_or_exclusivity_proof"}


def audit_archive(path: Path) -> dict:
    content = path.read_bytes()
    files = members(content)
    manifests = [n for n in files if n.endswith(".manifest.json")]
    if len(manifests) != 1:
        raise ValueError("one manifest required")
    manifest_name = manifests[0]
    prefix = manifest_name.removesuffix(".manifest.json")
    manifest = json_bytes(files[manifest_name])
    if set(manifest["files_sha256"]) != set(files)-{manifest_name}:
        raise ValueError("manifest file inventory mismatch")
    for name, expected in manifest["files_sha256"].items():
        if digest(files[name]) != expected:
            raise ValueError(f"manifest SHA256 mismatch: {name}")
    build = json_bytes(files[prefix+".build.json"])
    if build["git_head"] != manifest["git_head"]:
        raise ValueError("source revision mismatch")
    for key in ("build_runtime_status", "control_status"):
        if build[key] != manifest[key]:
            raise ValueError(f"manifest/build {key} mismatch")
    source = members(files[prefix+".sources.zip"])
    if set(source) != set(build["source_sha256"]):
        raise ValueError("source inventory mismatch")
    for name, expected in build["source_sha256"].items():
        if digest(source[name]) != expected:
            raise ValueError(f"source SHA256 mismatch: {name}")
    trace = parse_trace(files[prefix+".log"].decode("utf-8-sig"))
    if int(trace.run["seed"]) != build["seed"]:
        raise ValueError("build/trace seed mismatch")
    host = json_bytes(files[prefix+".host.json"])
    if str(host["os"]["BuildNumber"]) != trace.host["windows_build"]:
        raise ValueError("host/trace Windows build mismatch")
    if host["virtualization"]["HypervisorPresent"] != (trace.cpu["hypervisor"] == "1"):
        raise ValueError("host/trace hypervisor metadata mismatch")
    result = summarize(trace)
    with tempfile.TemporaryDirectory() as temporary:
        paths = []
        for suffix in (".exe", ".nop.bin", ".cpuid.bin"):
            target = Path(temporary)/("image"+suffix)
            target.write_bytes(files[prefix+suffix])
            paths.append(target)
        result["artifact_audit"] = audit_files(trace, *paths)
    archived = json_bytes(files[prefix+".analysis.json"])
    if result != archived:
        raise ValueError("archived analysis disagrees with frozen reanalysis")
    if build["binary_sha256"] != result["binary_sha256"]:
        raise ValueError("build binary hash mismatch")
    if build["control_status"] != ("passed" if result["apparatus_controls_pass"] else "inconclusive"):
        raise ValueError("control status mismatch")
    listing = check_disassembly(files[prefix+".exe"], files[prefix+".disasm.txt"].decode("utf-8-sig"))
    return {
        "archive_name": path.name, "archive_sha256": digest(content),
        "internal_consistency_verified": True, "manifest_files_checked": len(manifest["files_sha256"]),
        "source_files_checked": len(source), "git_head": build["git_head"],
        "archived_analysis_reproduced_exactly": True, "linked_listing_audit": listing,
        "analysis": result, "diagnostics": diagnose(trace, result),
        "physical_mechanism_proven": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("archive", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    try:
        result = audit_archive(args.archive)
        output = json.dumps(result, indent=2, sort_keys=True)+"\n"
        if args.output:
            args.output.write_text(output, encoding="utf-8")
        else:
            print(output, end="")
    except (OSError, ValueError, KeyError, TypeError, struct.error, BadZipFile) as exc:
        parser.exit(2, f"Invalid archived K3 evidence: {exc}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
