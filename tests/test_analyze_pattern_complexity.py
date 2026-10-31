"""Run-length sweep: source balance, seed replay, paired controls and failure cases."""

from contextlib import redirect_stdout
from io import StringIO
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import analyze_pattern_complexity as sweep  # noqa: E402


VALUES = {
    "live_p2": 1100, "live_p4": 1070, "live_p8": 1050,
    "live_p16": 1030, "live_p32": 1000, "live_random": 1150,
    "fixed_p2": 1002, "fixed_p4": 1001, "fixed_p8": 1000,
    "fixed_p16": 1000, "fixed_p32": 1000, "fixed_random": 1002,
    "branchless_p2": 901, "branchless_p4": 900,
    "branchless_p8": 900, "branchless_p16": 900,
    "branchless_p32": 900, "branchless_random": 901,
    "timer_fast": 500, "timer_slow": 800,
}


def fixture(*, seed=7, change=None, outlier=False):
    values = VALUES | (change or {})
    orders, digest = sweep.replay_patterns(8, 40, seed, sweep.KINDS, 20)
    rows = [
        "HOST_AFFINITY_CPU=0",
        "PATTERN_CPU,vendor=AuthenticAMD,signature=0x00b40f40,"
        "invariant_tsc=1,hypervisor=1",
        "PATTERN_RUN,version=1,blocks=40,iterations=8,warmup_blocks=20,"
        f"seed={seed},branch_addr=0x140001000,branchless_addr=0x140001020,"
        "input_addr=0x140006000,control_addr=0x140006040,"
        "mode_addr=0x140006080,timer=lfence_rdtsc_lfence,"
        "pattern=balanced_periods_2_4_8_16_32_and_block_shuffle,"
        "decision=runtime_cmov_live_vs_fixed_p4,compiler=msvc_O2,"
        f"pattern_hash={digest}",
    ]
    checksum = index = 0
    for block, order in enumerate(orders):
        for position, kind in enumerate(order):
            ticks = values[kind] + block * 3
            if outlier and block == 39 and kind == "live_p2":
                ticks += 100000
            rows.append(f"PATTERN_SAMPLE,{index},{block},{position},{kind},{ticks}")
            checksum += (index + 1) * ticks + block + position + sweep.KIND_INDEX[kind]
            index += 1
    rows.extend((
        f"PATTERN_END,count={index},checksum={checksum},sink=16",
        "PATTERN_HOST,windows_build=26200,run_utc=20261031T170000Z",
        "PATTERN_BINARY,sha256=" + "a" * 64,
    ))
    return "\r\n".join(rows) + "\r\n"


def parse_fixture(raw):
    with patch.object(sweep, "BLOCKS", 40), patch.object(sweep, "ITERATIONS", 8):
        return sweep.parse_trace(raw)


class PatternComplexityTests(unittest.TestCase):
    def test_primary_paired_estimand_and_controls(self):
        trace = parse_fixture(fixture())
        result = sweep.summarize(trace)
        self.assertEqual(result["primary"], "p2_minus_p32")
        primary = result["profile"][result["primary"]]
        self.assertEqual(primary["contrasts"]["live"]["paired_trimmed_mean_ticks_per_iteration"], 12.5)
        self.assertEqual(primary["contrasts"]["fixed"]["paired_trimmed_mean_ticks_per_iteration"], .25)
        self.assertEqual(primary["contrasts"]["adjusted"]["paired_trimmed_mean_ticks_per_iteration"], 12.25)
        self.assertEqual(len(result["profile"]), 5)
        self.assertTrue(result["controls_pass"])
        self.assertTrue(result["primary_positive_within_run"])
        self.assertEqual(result["timer_control"]["positive_blocks"], 40)
        self.assertTrue(all(v["fixed_within_tolerance"] and
                            v["branchless_within_tolerance"]
                            for v in result["profile"].values()))

    def test_null_primary_and_failed_controls_remain_visible(self):
        null = sweep.summarize(parse_fixture(fixture(change={"live_p2": 1002})))
        self.assertTrue(null["controls_pass"])
        self.assertFalse(null["primary_positive_within_run"])
        fixed = sweep.summarize(parse_fixture(fixture(change={"fixed_p2": 1020})))
        self.assertFalse(fixed["controls_pass"])
        self.assertFalse(fixed["profile"]["p2_minus_p32"]["fixed_within_tolerance"])
        slow = sweep.summarize(parse_fixture(fixture(change={"timer_slow": 500})))
        self.assertFalse(slow["timer_control"]["passes"])
        self.assertIn("p2_minus_p32", slow["profile"])

    def test_seed_pattern_and_checksum_tampering_rejected(self):
        first, second = parse_fixture(fixture(seed=7)), parse_fixture(fixture(seed=9))
        self.assertNotEqual(first.run["pattern_hash"], second.run["pattern_hash"])
        with self.assertRaisesRegex(ValueError, "pattern hash"):
            parse_fixture(fixture().replace("seed=7,", "seed=8,", 1))
        with self.assertRaisesRegex(ValueError, "invalid run seed"):
            parse_fixture(fixture().replace("seed=7,", "seed=0,", 1))
        raw = fixture()
        sample = next(row for row in raw.splitlines() if row.startswith("PATTERN_SAMPLE,"))
        fields = sample.split(",")
        fields[-1] = str(int(fields[-1]) + 1)
        with self.assertRaisesRegex(ValueError, "checksum mismatch"):
            parse_fixture(raw.replace(sample, ",".join(fields), 1))

    def test_reordered_class_rejected_even_with_repaired_checksum(self):
        lines = fixture().splitlines()
        a, b = [line.split(",") for line in lines[3:5]]
        for i, row in enumerate((b, a)):
            row[1], row[3] = str(i), str(i)
            lines[3 + i] = ",".join(row)
        checksum = 0
        for row in lines:
            if row.startswith("PATTERN_SAMPLE,"):
                _, index, block, position, kind, ticks = row.split(",")
                checksum += (int(index) + 1) * int(ticks) + int(block) + \
                            int(position) + sweep.KIND_INDEX[kind]
        end = next(i for i, row in enumerate(lines) if row.startswith("PATTERN_END,"))
        lines[end] = f"PATTERN_END,count=800,checksum={checksum},sink=16"
        with self.assertRaisesRegex(ValueError, "class order does not match seed"):
            parse_fixture("\n".join(lines))

    def test_outlier_trim_and_strict_cli(self):
        outlier = sweep.summarize(parse_fixture(fixture(outlier=True)))
        self.assertEqual(outlier["profile"]["p2_minus_p32"]["contrasts"]["adjusted"]
                         ["paired_trimmed_mean_ticks_per_iteration"], 12.25)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "sweep.log"
            path.write_text(fixture(), encoding="utf-8")
            output = StringIO()
            with patch.object(sweep, "BLOCKS", 40), patch.object(sweep, "ITERATIONS", 8), \
                 patch.object(sys, "argv", ["analyze_pattern_complexity.py",
                                          str(path), "--strict"]), redirect_stdout(output):
                self.assertEqual(sweep.main(), 0)
            self.assertIn("p2_minus_p32", output.getvalue())
            self.assertIn("20-block bootstrap", output.getvalue())


if __name__ == "__main__":
    unittest.main()
