"""Archive checks reject ambiguous members and altered linked-code listings."""
from io import BytesIO
from pathlib import Path
import struct
import sys
import unittest
from zipfile import ZipFile

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/"scripts"))
from audit_fresh_receiver_archive import check_disassembly, members
from diagnose_fresh_receiver import diagnose
import analyze_fresh_receiver as k3


class ArchiveAuditTests(unittest.TestCase):
    def archive(self, names):
        output = BytesIO()
        with ZipFile(output, "w") as archive:
            for name in names:
                archive.writestr(name, b"content")
        return output.getvalue()

    def test_windows_source_paths_are_normalized(self):
        self.assertEqual(members(self.archive(["scripts\\analyzer.py"])),
                         {"scripts/analyzer.py": b"content"})

    def test_unsafe_and_ambiguous_zip_names_are_rejected(self):
        for names in (["../outside"], ["/absolute"], ["C:/outside"],
                      ["scripts\\a.py", "scripts/a.py"]):
            with self.assertRaisesRegex(ValueError, "unsafe|duplicate"):
                members(self.archive(names))

    def pe_and_listing(self):
        binary = bytearray(1024)
        binary[:2] = b"MZ"
        struct.pack_into("<I", binary, 0x3c, 0x80)
        binary[0x80:0x84] = b"PE\0\0"
        struct.pack_into("<H", binary, 0x86, 1)
        struct.pack_into("<H", binary, 0x94, 0xf0)
        struct.pack_into("<H", binary, 0x98, 0x20b)
        struct.pack_into("<Q", binary, 0xb0, 0x140000000)
        struct.pack_into("<IIII", binary, 0x190, 0x100, 0x1000, 0x100, 0x200)
        binary[0x200:0x20c] = b"\x90"*12
        listing = "\n".join(f"  {0x140001000+i:016X}: 90  nop" for i in range(12))
        return bytes(binary), listing

    def test_listing_must_match_the_pe_not_just_the_archive_hash(self):
        binary, listing = self.pe_and_listing()
        self.assertEqual(check_disassembly(binary, listing)["bytes_checked"], 12)
        with self.assertRaisesRegex(ValueError, "mismatch"):
            check_disassembly(binary, listing.replace(": 90", ": CC", 1))

    def test_diagnostics_never_discard_early_hits_or_change_gates(self):
        samples = [k3.Sample(1, "nop", "candidate_t0_p0", i, 0,
                             80 if i < 4 else 500, 500) for i in range(16)]
        trace = k3.Trace({"hypervisor": "1"}, {"blocks": "2", "episodes": "16"}, {}, None, samples)
        result = {"study": "fresh_marker_k3_v1", "thresholds": {"p0": 100},
                  "heldout_hit_rates": {"nop": {"candidate_t0_p0": .25}, "cpuid": {}},
                  "gates": {"nop/candidate_t0_p0": False}}
        before = repr(result)
        data = diagnose(trace, result)
        self.assertEqual(repr(result), before)
        self.assertEqual(len(trace.samples), 16)
        profile = data["heldout_episode_profiles"]["nop"]["candidate_t0_p0"]
        self.assertEqual(profile["first_quarter_hit_rate"], 1)
        self.assertEqual(profile["remaining_hit_rate"], 0)
        self.assertEqual(data["failed_gates"][0]["observed_hit_rate"], .25)


if __name__ == "__main__":
    unittest.main()
