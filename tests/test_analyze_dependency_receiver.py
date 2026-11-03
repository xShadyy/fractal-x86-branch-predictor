"""K5 dependency control rejects CPUID-only, residual-heat and privilege artifacts."""
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
import analyze_dependency_receiver as k5
from dependency_receiver_contract import code_for, CODE, BRANCH, MASK_ONE, MASK_ZERO, PATCH_ONE, PATCH_ZERO
from verify_dependency_receiver_layout import verify


def fixture(pattern="null", *, heated_no_probe=False, hot_decoy=False):
    blocks, episodes, seed = 32, 2, 2423705098
    lines = [
        "K5_CPU,vendor=AuthenticAMD,signature=0x00b40f40,clflush_bytes=64,"
        "invariant_tsc=1,rdtscp=1,hypervisor=1",
        f"K5_RUN,version=1,protocol=dependency_marker_k5_v1,blocks={blocks},episodes={episodes},"
        "conditions=16,modes=3,warmup_blocks=16,prelude_calls=128,train_calls=256,"
        f"history_prefix_branches=256,schedule=interleaved_modes_and_rounds,mask=resolved_condition_index_zero,"
        f"pages=64,stride=4096,seed={seed},affinity_cpu=0,platform=native_dev,"
        "timer=cpuid_outside_rdtscp_load_rdtscp,code_addr=0x100000,condition_addr=0x200000,"
        "token0_addr=0x201000,token1_addr=0x202000,bank0_addr=0x300000,bank1_addr=0x400000",
        *(f"K5_CODE,mode={mode},hex={code_for(mode).hex()}" for mode in k5.MODES),
    ]
    checksum, event_hash = 0, k5.FNV_OFFSET
    for index, plan in enumerate(k5.replay(blocks, episodes, seed)):
        block, mode, position, kind, occurrence, tag0, tag1, decoy, order = plan
        kind_id = k5.KINDS.index(kind)
        p, member = divmod(kind_id, 8)
        t = member & 1 if member < 4 else (1 - p if member == 7 else p)
        probe = 1 + p if member in (0, 1, 7) else (2 - p if member == 6 else 0)
        hot = member in (4, 6)
        if member in (0, 1) and t != p:
            hot |= pattern == "barrier_insensitive" or (pattern == "signature" and mode == "plain")
            hot |= pattern == "cpuid_only" and mode in ("plain", "mask")
        if pattern == "entry_heat" and member in (0, 1):
            hot = mode == "plain" and occurrence == 0
        if heated_no_probe and member in (2, 3):
            hot = True
        wanted_ticks, decoy_ticks = (80 if hot else 500), (80 if hot_decoy else 500)
        lines.append(f"K5_SAMPLE,{index},{block},{mode},{position},{kind},{occurrence},"
                     f"{tag0},{tag1},{decoy},{order},{wanted_ticks},{decoy_ticks},192,{256*(1+t)},{probe},3,{3 if member in (0,1,6,7) else 255},"
                     f"{hex(0x100000+BRANCH)},{hex(0x100000+BRANCH) if member in (0,1,6,7) else '0x0'}")
        checksum = k5.mix(k5.mix(k5.mix(checksum, index+1), wanted_ticks), decoy_ticks)
        event_hash = k5.mix(event_hash, k5.MODES.index(mode)*256 + kind_id*16 + occurrence)
        event_hash = k5.mix(event_hash, tag0*65536+tag1*256+decoy*2+order)
    lines.append(f"K5_END,count={blocks*3*16*episodes},checksum={checksum},"
                 f"event_hash={event_hash},architecture_errors=0")
    return "\n".join(lines)+"\n"


class DependencyReceiverTests(unittest.TestCase):
    def parsed(self, text):
        return k5.parse_trace(text, development=True)

    def result(self, text):
        return k5.summarize(self.parsed(text))

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
        self.assertEqual(result["outcomes"]["p0"]["plain_adjusted"]["hit_rate_difference"], 0)

    def test_residual_training_heat_withholds_signature(self):
        self.assertFalse(self.result(fixture("signature", heated_no_probe=True))["numerical_signature_detected"])

    def test_decoy_heat_withholds_signature(self):
        self.assertFalse(self.result(fixture("signature", hot_decoy=True))["numerical_signature_detected"])

    def test_native_trace_requires_explicit_development_mode(self):
        with self.assertRaisesRegex(ValueError, "development"):
            k5.parse_trace(fixture())

    def test_dependency_control_is_distinct_from_target_cpuid(self):
        plain, mask, cpuid = (code_for(m) for m in k5.MODES)
        self.assertEqual(mask[PATCH_ONE:PATCH_ONE+3], b"\x90"*3)
        self.assertEqual(mask[PATCH_ZERO:PATCH_ZERO+3], b"\x90"*3)
        self.assertEqual(mask[MASK_ONE:MASK_ONE+5], bytes.fromhex("85d20f44c2"))
        self.assertEqual(mask[MASK_ZERO:MASK_ZERO+11], bytes.fromhex("85d2b9000000000f45c190"))
        self.assertEqual(len(plain), len(mask))
        self.assertEqual(plain[:BRANCH+6], mask[:BRANCH+6])
        self.assertEqual(cpuid[PATCH_ONE:PATCH_ONE+2], bytes.fromhex("0fa2"))

    def test_cpuid_suppression_without_mask_suppression_is_not_signature(self):
        result = self.result(fixture("cpuid_only"))
        self.assertFalse(result["numerical_signature_detected"])
        self.assertFalse(result["apparatus_controls_pass"])

    def test_measured_privilege_and_pc_corruption_rejected(self):
        for column, value in ((16,"0"),(17,"2"),(18,"0xdead"),(19,"0xbeef")):
            rows=fixture().splitlines();row=rows[5].split(",");row[column]=value;rows[5]=",".join(row)
            with self.assertRaisesRegex(ValueError,"privilege|address"):
                self.parsed("\n".join(rows))

    def test_each_interleaved_round_contains_all_conditions_once(self):
        rows = list(k5.replay(32, 2, 2423705098))
        for index in range(0, len(rows), 16):
            round_rows = rows[index:index+16]
            self.assertEqual({r[3] for r in round_rows}, set(k5.KINDS))
            self.assertEqual([r[2] for r in round_rows], list(range(16)))
            self.assertEqual(len({(r[0], r[1], r[4]) for r in round_rows}), 1)

    def test_grouped_schedule_or_changed_prefix_metadata_rejected(self):
        for before, after in (("interleaved_modes_and_rounds", "grouped"),
                              ("history_prefix_branches=256", "history_prefix_branches=0")):
            with self.assertRaisesRegex(ValueError, "protocol"):
                self.parsed(fixture().replace(before, after))

    def test_shortened_windows_run_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "dimensions"):
            self.parsed(fixture().replace("platform=native_dev", "platform=windows"))

    def test_reordered_or_missing_sample_rejected(self):
        lines = fixture().splitlines()
        for edit in (lambda rows: rows.__setitem__(slice(5,7), rows[5:7][::-1]),
                     lambda rows: rows.pop(5)):
            rows = lines.copy(); edit(rows)
            with self.assertRaises(ValueError):
                self.parsed("\n".join(rows))

    def test_token_zero_or_wrong_decoy_is_rejected(self):
        for column, value in ((7, "0"), (9, "64"), (10, "2"), (13, "191"), (15, "77")):
            rows = fixture().splitlines(); row = rows[5].split(","); row[column] = value
            rows[5] = ",".join(row)
            with self.assertRaises(ValueError):
                self.parsed("\n".join(rows))

    def test_wrong_checksum_duplicate_records_and_code_mutation_rejected(self):
        original = fixture()
        changed = original.replace(code_for("plain").hex(), "00"+code_for("plain").hex()[2:], 1)
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
            plain, mask, cpuid = (folder/(m+".bin") for m in k5.MODES)
            binary.write_bytes(b"example image"+CODE)
            plain.write_bytes(code_for("plain")); mask.write_bytes(code_for("mask")); cpuid.write_bytes(code_for("cpuid"))
            digest = hashlib.sha256(binary.read_bytes()).hexdigest()
            text = fixture()+"K5_HOST,windows_build=26200,run_utc=20261102T180000Z\nK5_BINARY,sha256="+digest+"\n"
            trace = self.parsed(text)
            self.assertTrue(k5.audit_files(trace, binary, plain, mask, cpuid)["runtime_snapshots_verified"])
            cpuid.write_bytes(code_for("plain"))
            with self.assertRaisesRegex(ValueError, "runtime bytes"):
                k5.audit_files(trace, binary, plain, mask, cpuid)
            binary.write_bytes(b"modified")
            with self.assertRaisesRegex(ValueError, "SHA256"):
                k5.audit_files(trace, binary, plain, mask, cpuid)

    @unittest.skipUnless(shutil.which("cc") and shutil.which("objcopy"), "GNU assembly tools unavailable")
    def test_readable_instructions_match_exact_runtime_contract(self):
        verify(ROOT)

    def test_strict_cli_accepts_valid_null_and_rejects_failed_controls(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary)/"trace.log"
            for text, expected in ((fixture(), 0), (fixture(hot_decoy=True), 1)):
                path.write_text(text)
                with patch.object(sys, "argv", ["k5", str(path), "--development", "--strict", "--json"]), redirect_stdout(StringIO()):
                    self.assertEqual(k5.main(), expected)


if __name__ == "__main__":
    unittest.main()
