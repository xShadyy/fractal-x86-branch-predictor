"""K4 rejects false mechanism patterns, corrupted traces and changed RX bytes."""
from contextlib import redirect_stdout
from io import StringIO
import hashlib
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import analyze_context_receiver as k4
from context_receiver_contract import code_for, CODE, PREFIX, PREFIX_BRANCHES
from verify_context_receiver_layout import verify


def fixture(pattern="null", *, heated_no_probe=False, hot_decoy=False):
    blocks, episodes, seed = 32, 2, 2423705098
    lines = [
        "K4_CPU,vendor=AuthenticAMD,signature=0x00b40f40,clflush_bytes=64,"
        "invariant_tsc=1,rdtscp=1,hypervisor=1",
        f"K4_RUN,version=1,protocol=context_marker_k4_v1,blocks={blocks},episodes={episodes},"
        "conditions=16,modes=2,warmup_blocks=16,prelude_calls=128,train_calls=256,"
        f"history_prefix_branches=256,schedule=interleaved_round_shuffle,"
        f"pages=64,stride=4096,seed={seed},affinity_cpu=0,platform=native_dev,"
        "timer=cpuid_outside_rdtscp_load_rdtscp,code_addr=0x100000,condition_addr=0x200000,"
        "token0_addr=0x201000,token1_addr=0x202000,bank0_addr=0x300000,bank1_addr=0x400000",
        *(f"K4_CODE,mode={mode},hex={code_for(mode).hex()}" for mode in k4.MODES),
    ]
    checksum, event_hash = 0, k4.FNV_OFFSET
    for index, plan in enumerate(k4.replay(blocks, episodes, seed)):
        block, mode, position, kind, occurrence, tag0, tag1, decoy, order = plan
        kind_id = k4.KINDS.index(kind)
        p, member = divmod(kind_id, 8)
        t = member & 1 if member < 4 else (1 - p if member == 7 else p)
        probe = 1 + p if member in (0, 1, 7) else (2 - p if member == 6 else 0)
        hot = member in (4, 6)
        if member in (0, 1) and t != p:
            hot |= pattern == "barrier_insensitive" or (pattern == "signature" and mode == "nop")
        if pattern == "entry_heat" and member in (0, 1):
            hot = mode == "nop" and occurrence == 0
        if heated_no_probe and member in (2, 3):
            hot = True
        wanted_ticks, decoy_ticks = (80 if hot else 500), (80 if hot_decoy else 500)
        lines.append(f"K4_SAMPLE,{index},{block},{mode},{position},{kind},{occurrence},"
                     f"{tag0},{tag1},{decoy},{order},{wanted_ticks},{decoy_ticks},192,{256*(1+t)},{probe}")
        checksum = k4.mix(k4.mix(k4.mix(checksum, index+1), wanted_ticks), decoy_ticks)
        event_hash = k4.mix(event_hash, k4.MODES.index(mode)*256 + kind_id*16 + occurrence)
        event_hash = k4.mix(event_hash, tag0*65536+tag1*256+decoy*2+order)
    lines.append(f"K4_END,count={blocks*2*16*episodes},checksum={checksum},"
                 f"event_hash={event_hash},architecture_errors=0")
    return "\n".join(lines)+"\n"


class ContextReceiverTests(unittest.TestCase):
    def parsed(self, text):
        return k4.parse_trace(text, development=True)

    def result(self, text):
        return k4.summarize(self.parsed(text))

    def test_eligible_null_is_not_mechanism_evidence(self):
        result = self.result(fixture())
        self.assertTrue(result["apparatus_controls_pass"])
        self.assertFalse(result["numerical_signature_detected"])
        self.assertFalse(result["windows_collection"])

    def test_signature_requires_training_and_barrier_interaction(self):
        result = self.result(fixture("signature"))
        self.assertTrue(result["apparatus_controls_pass"])
        self.assertTrue(result["numerical_signature_detected"])
        self.assertEqual(result["outcomes"]["p0"]["interaction"]["hit_rate_difference"], 1)
        self.assertIn("pending", result["mechanism_conclusion"])

    def test_barrier_insensitive_heat_cannot_be_claimed(self):
        result = self.result(fixture("barrier_insensitive"))
        self.assertFalse(result["apparatus_controls_pass"])
        self.assertFalse(result["numerical_signature_detected"])

    def test_k2_style_entry_heat_does_not_identify_training(self):
        result = self.result(fixture("entry_heat"))
        self.assertFalse(result["numerical_signature_detected"])
        self.assertEqual(result["outcomes"]["p0"]["nop_adjusted"]["hit_rate_difference"], 0)

    def test_residual_training_heat_withholds_signature(self):
        self.assertFalse(self.result(fixture("signature", heated_no_probe=True))["numerical_signature_detected"])

    def test_decoy_heat_withholds_signature(self):
        self.assertFalse(self.result(fixture("signature", hot_decoy=True))["numerical_signature_detected"])

    def test_native_trace_requires_explicit_development_mode(self):
        with self.assertRaisesRegex(ValueError, "development"):
            k4.parse_trace(fixture())

    def test_fixed_prefix_and_modes_share_branch_and_target_addresses(self):
        self.assertEqual(PREFIX_BRANCHES, 256)
        self.assertEqual(len(PREFIX), 1344)
        self.assertEqual(PREFIX.count(b"\x85\xc0\x74\x01\xcc"), 256)
        self.assertEqual(code_for("nop")[:1344], code_for("cpuid")[:1344])

    def test_each_interleaved_round_contains_all_conditions_once(self):
        rows = list(k4.replay(32, 2, 2423705098))
        for index in range(0, len(rows), 16):
            round_rows = rows[index:index+16]
            self.assertEqual({r[3] for r in round_rows}, set(k4.KINDS))
            self.assertEqual([r[2] for r in round_rows], list(range(16)))
            self.assertEqual(len({(r[0], r[1], r[4]) for r in round_rows}), 1)

    def test_grouped_schedule_or_changed_prefix_metadata_rejected(self):
        for before, after in (("interleaved_round_shuffle", "grouped"),
                              ("history_prefix_branches=256", "history_prefix_branches=0")):
            with self.assertRaisesRegex(ValueError, "protocol"):
                self.parsed(fixture().replace(before, after))

    def test_shortened_windows_run_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "dimensions"):
            self.parsed(fixture().replace("platform=native_dev", "platform=windows"))

    def test_reordered_or_missing_sample_rejected(self):
        lines = fixture().splitlines()
        for edit in (lambda rows: rows.__setitem__(slice(4,6), rows[4:6][::-1]),
                     lambda rows: rows.pop(4)):
            rows = lines.copy(); edit(rows)
            with self.assertRaises(ValueError):
                self.parsed("\n".join(rows))

    def test_token_zero_or_wrong_decoy_is_rejected(self):
        for column, value in ((7, "0"), (9, "64"), (10, "2"), (13, "191"), (15, "77")):
            rows = fixture().splitlines(); row = rows[4].split(","); row[column] = value
            rows[4] = ",".join(row)
            with self.assertRaises(ValueError):
                self.parsed("\n".join(rows))

    def test_wrong_checksum_duplicate_records_and_code_mutation_rejected(self):
        original = fixture()
        changed = original.replace(code_for("nop").hex(), "00"+code_for("nop").hex()[2:], 1)
        for text in (changed, original+original.splitlines()[0]+"\n",
                     original.replace("architecture_errors=0", "architecture_errors=1"),
                     original.replace("condition_addr=0x200000", "condition_addr=0x201000")):
            with self.assertRaises(ValueError):
                self.parsed(text)

    def test_heldout_calibration_does_not_use_outcome_labels(self):
        null = self.result(fixture())
        signal = self.result(fixture("signature"))
        self.assertEqual(null["thresholds"], signal["thresholds"])

    def test_artifact_audit_detects_modified_snapshot_and_executable(self):
        with tempfile.TemporaryDirectory() as temporary:
            folder = Path(temporary); binary = folder/"image.exe"
            nop, cpuid = folder/"nop.bin", folder/"cpuid.bin"
            binary.write_bytes(b"example image"+CODE)
            nop.write_bytes(code_for("nop")); cpuid.write_bytes(code_for("cpuid"))
            digest = hashlib.sha256(binary.read_bytes()).hexdigest()
            text = fixture()+"K4_HOST,windows_build=26200,run_utc=20261102T180000Z\nK4_BINARY,sha256="+digest+"\n"
            trace = self.parsed(text)
            self.assertTrue(k4.audit_files(trace, binary, nop, cpuid)["runtime_snapshots_verified"])
            cpuid.write_bytes(code_for("nop"))
            with self.assertRaisesRegex(ValueError, "runtime bytes"):
                k4.audit_files(trace, binary, nop, cpuid)
            binary.write_bytes(b"modified")
            with self.assertRaisesRegex(ValueError, "SHA256"):
                k4.audit_files(trace, binary, nop, cpuid)

    @unittest.skipUnless(shutil.which("cc") and shutil.which("objcopy"), "GNU assembly tools unavailable")
    def test_readable_instructions_match_exact_runtime_contract(self):
        verify(ROOT)

    def test_strict_cli_accepts_valid_null_and_rejects_failed_controls(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary)/"trace.log"
            for text, expected in ((fixture(), 0), (fixture(hot_decoy=True), 1)):
                path.write_text(text)
                with patch.object(sys, "argv", ["k4", str(path), "--development", "--strict", "--json"]), redirect_stdout(StringIO()):
                    self.assertEqual(k4.main(), expected)


if __name__ == "__main__":
    unittest.main()
