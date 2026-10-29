"""Tests for complete 2x2 branch timing traces and paired contrasts."""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from analyze_branch_latency import KIND_INDEX, parse_trace, summarize  # noqa: E402


def serial_trace(delta=20):
    lines = [
        "HOST_AFFINITY_CPU=0",
        "LAT_CPU,vendor=AuthenticAMD,signature=0x00b40f40,invariant_tsc=1",
        "LAT_RUN,version=1,blocks=4,training=128,warmup_blocks=32,seed=7,"
        "branch_addr=0x140001000,timer=lfence_rdtsc_lfence",
    ]
    labels = ("train0_probe0", "train1_probe0", "train0_probe1", "train1_probe1")
    orders = ((0, 1, 2, 3), (2, 0, 3, 1), (3, 2, 1, 0), (1, 3, 0, 2))
    checksum = 0
    index = 0
    for block, order in enumerate(orders):
        for position, kind in enumerate(order):
            ticks = (70 if kind < 2 else 80) + (delta if kind in (1, 2) else 0)
            lines.append(f"LAT_SAMPLE,{index},{block},{position},{labels[kind]},{ticks}")
            checksum += (index + 1) * ticks + block + position + KIND_INDEX[labels[kind]]
            index += 1
    lines.append(f"LAT_END,count={index},checksum={checksum},sink=4")
    return "\r\n".join(lines) + "\r\n"


class BranchLatencyTests(unittest.TestCase):
    def test_paired_contrast_for_both_outcomes(self):
        result = summarize(parse_trace(serial_trace()))
        for probe in ("0", "1"):
            contrast = result["mismatch_minus_match"][probe]
            self.assertEqual(contrast["paired_median"], 20)
            self.assertEqual(contrast["paired_trimmed_mean"], 20)
            self.assertEqual(contrast["within_run_bootstrap_95"], (20, 20))

    def test_identical_outcomes_have_zero_contrast(self):
        result = summarize(parse_trace(serial_trace(delta=0)))
        self.assertEqual(result["mismatch_minus_match"]["0"]["paired_median"], 0)
        self.assertEqual(result["mismatch_minus_match"]["1"]["paired_median"], 0)

    def test_truncated_trace_rejected(self):
        with self.assertRaises(ValueError):
            parse_trace(serial_trace().split("LAT_END")[0])

    def test_modified_ticks_rejected(self):
        with self.assertRaisesRegex(ValueError, "checksum"):
            parse_trace(serial_trace().replace("train0_probe0,70", "train0_probe0,71", 1))

    def test_duplicate_class_rejected_even_with_adjusted_checksum(self):
        broken = serial_trace().replace("LAT_SAMPLE,1,0,1,train1_probe0,90",
                                        "LAT_SAMPLE,1,0,1,train0_probe0,90")
        original = int(broken.split("checksum=", 1)[1].split(",", 1)[0])
        broken = broken.replace(f"checksum={original}", f"checksum={original - 1}")
        with self.assertRaisesRegex(ValueError, "unbalanced"):
            parse_trace(broken)


if __name__ == "__main__":
    unittest.main()
