"""End-to-end checks for complete and corrupted serial captures."""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from analyze_cache_probe import CLASSES, parse_trace, summarize  # noqa: E402


def serial_trace(negative_cycles=210):
    rows = [
        "Fractal Bootloader",
        "CACHE_CPU,vendor=GenuineIntel,signature=0x000906a3,"
        "clflush_bytes=64,invariant_tsc=1",
        "CACHE_RUN,version=1,samples_per_class=4,warmup_per_class=1,"
        "seed=7,timer=lfence_rdtsc_lfence,flush=clflush_mfence",
    ]
    checksum = 0
    index = 0
    for occurrence in range(4):
        phase = "train" if occurrence < 2 else "validate"
        for kind_index, kind in enumerate(CLASSES):
            cycles = (40 + occurrence if kind in ("hot", "branch_load")
                      else negative_cycles + occurrence)
            rows.append(f"CACHE_SAMPLE,{index},{phase},{kind},{cycles}")
            checksum += (index + 1) * cycles + kind_index + (phase == "validate")
            index += 1
    rows.append(f"CACHE_END,count={index},checksum={checksum},sink=4")
    rows.append("FRACTAL_UTEST_OK: x86 cache controls completed")
    return "\r\n".join(rows) + "\r\n"


class TraceTests(unittest.TestCase):
    def test_separated_controls_pass_on_held_out_samples(self):
        result = summarize(parse_trace(serial_trace()))
        self.assertTrue(result["controls_pass"])
        self.assertEqual(result["hit_rates"]["branch_load"], 1)
        self.assertEqual(result["hit_rates"]["branch_skip"], 0)

    def test_overlapping_negative_control_is_inconclusive(self):
        raw = serial_trace().replace("validate,branch_skip,212",
                                     "validate,branch_skip,42")
        raw = raw.replace("validate,branch_skip,213",
                          "validate,branch_skip,43")
        # Recompute the checksum after deliberate changes to the captured data.
        rows = raw.splitlines()
        checksum = sum((int(parts[1]) + 1) * int(parts[4]) +
                       CLASSES.index(parts[3]) + (parts[2] == "validate")
                       for row in rows if row.startswith("CACHE_SAMPLE,")
                       for parts in (row.split(","),))
        rows[-2] = f"CACHE_END,count=16,checksum={checksum},sink=4"
        self.assertFalse(summarize(parse_trace("\n".join(rows)))["controls_pass"])

    def test_truncated_capture_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "incomplete"):
            parse_trace(serial_trace().split("CACHE_END,")[0])

    def test_modified_sample_fails_checksum(self):
        with self.assertRaisesRegex(ValueError, "checksum"):
            parse_trace(serial_trace().replace(",hot,40", ",hot,45"))

    def test_missing_class_or_phase_is_rejected(self):
        altered = serial_trace().replace("CACHE_SAMPLE,0,train,hot,40",
                                         "CACHE_SAMPLE,0,validate,hot,40")
        rows = altered.splitlines()
        # Recalculate rather than relying on checksum rejection.
        checksum = sum((int(parts[1]) + 1) * int(parts[4]) +
                       CLASSES.index(parts[3]) + (parts[2] == "validate")
                       for row in rows if row.startswith("CACHE_SAMPLE,")
                       for parts in (row.split(","),))
        rows[-2] = f"CACHE_END,count=16,checksum={checksum},sink=4"
        with self.assertRaisesRegex(ValueError, "phase"):
            parse_trace("\n".join(rows))

    def test_missing_cpu_metadata_is_rejected(self):
        altered = serial_trace().replace("vendor=GenuineIntel,", "")
        with self.assertRaisesRegex(ValueError, "missing CPU"):
            parse_trace(altered)

    def test_missing_run_metadata_is_rejected(self):
        altered = serial_trace().replace("timer=lfence_rdtsc_lfence,", "")
        with self.assertRaisesRegex(ValueError, "missing CPU or run"):
            parse_trace(altered)


if __name__ == "__main__":
    unittest.main()
