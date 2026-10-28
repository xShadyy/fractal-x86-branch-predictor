"""Validate paired branch captures and calibration failure handling."""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from analyze_spec_probe import KIND_INDEX, parse_trace, summarize  # noqa: E402


def serial_trace(taken=65, not_taken=285, cold=300, arch_load=65,
                 arch_skip=300, version=2):
    rows = [
        "HOST_AFFINITY_CPU=0",
        "SPEC_CPU,vendor=AuthenticAMD,signature=0x00b40f40,"
        "clflush_bytes=64,invariant_tsc=1",
        f"SPEC_RUN,version={version},blocks=4,training=128,warmup_blocks=32,seed=7,"
        "branch_addr=0x140001000,timer=lfence_rdtsc_lfence,flush=clflush_mfence",
    ]
    checksum = 0
    index = 0
    for block, order in enumerate((0, 1, 1, 0)):
        kinds = (("train_taken", "train_not_taken") if order == 0 else
                 ("train_not_taken", "train_taken")) + ("hot", "cold")
        if version == 2:
            kinds += ("arch_load", "arch_skip")
        for position, kind in enumerate(kinds):
            cycles = {"train_taken": taken, "train_not_taken": not_taken,
                      "hot": 55, "cold": cold,
                      "arch_load": arch_load, "arch_skip": arch_skip}[kind]
            rows.append(f"SPEC_SAMPLE,{index},{block},{position},{kind},{cycles}")
            checksum += (index + 1) * cycles + block + position + KIND_INDEX[kind]
            index += 1
    rows.append(f"SPEC_END,count={index},checksum={checksum},sink=4")
    return "\r\n".join(rows) + "\r\n"


class BranchTraceTests(unittest.TestCase):
    def test_complete_pair_and_calibration(self):
        result = summarize(parse_trace(serial_trace()))
        self.assertTrue(result["controls_pass"])
        self.assertTrue(result["same_branch_controls_pass"])
        self.assertEqual(result["probe_hit_rates"]["train_taken"], 1)
        self.assertEqual(result["probe_hit_rates"]["train_not_taken"], 0)
        self.assertEqual(result["paired_hit_difference"], 1)

    def test_no_label_difference_is_reported(self):
        result = summarize(parse_trace(serial_trace(taken=285)))
        self.assertTrue(result["controls_pass"])
        self.assertEqual(result["paired_hit_difference"], 0)

    def test_failed_held_out_calibration(self):
        result = summarize(parse_trace(serial_trace(cold=55)))
        self.assertFalse(result["controls_pass"])

    def test_same_branch_site_controls_fail_independently(self):
        result = summarize(parse_trace(serial_trace(arch_load=300)))
        self.assertFalse(result["controls_pass"])
        self.assertFalse(result["same_branch_controls_pass"])
        self.assertEqual(result["control_hit_rates"]["hot"], 1)

    def test_old_capture_is_still_readable(self):
        result = summarize(parse_trace(serial_trace(version=1)))
        self.assertTrue(result["controls_pass"])
        self.assertNotIn("same_branch_control_hit_rates", result)

    def test_truncated_capture(self):
        with self.assertRaises(ValueError):
            parse_trace(serial_trace().split("SPEC_END")[0])

    def test_corrupted_sample_checksum(self):
        with self.assertRaisesRegex(ValueError, "checksum"):
            parse_trace(serial_trace().replace(",train_taken,65", ",train_taken,66", 1))

    def test_wrong_pair_order_rejected(self):
        raw = serial_trace().replace("0,0,train_taken,65", "0,0,train_not_taken,65", 1)
        with self.assertRaises(ValueError):
            parse_trace(raw)


if __name__ == "__main__":
    unittest.main()
