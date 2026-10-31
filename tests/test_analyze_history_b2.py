"""Synthetic B2 trace replay, paired estimands and control gates."""

from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import analyze_history_b2 as b2  # noqa: E402


def fixture(seed=123, small_extra=16, corrupt_outlier=False):
    orders, schedule_hash = b2.replay_schedule(72, seed)
    rows = [
        "HOST_AFFINITY_CPU=0",
        "B2_CPU,vendor=AuthenticAMD,signature=0x00b40f40,"
        "invariant_tsc=1,hypervisor=1",
        "B2_RUN,version=1,blocks=72,episodes=4,reset_calls=8,"
        "train_calls=8,probe_lengths=1:16,warmup_blocks=36,"
        f"seed={seed},branch_addr=0x140001c80,sham_addr=0x140001c90,"
        "live_addr=0x140023b00,fixed_addr=0x140023b40,"
        "mode_addr=0x140023b80,probe_addr=0x140023bc0,"
        "prelude_addr=0x140023c00,"
        "timer=lfence_rdtsc_lfence,"
        "protocol=history_same_site_fixed_probe_length,compiler=msvc_O2,"
        f"schedule_hash={schedule_hash},pattern_hash={b2.replay_pattern_hash(8)}",
    ]
    values = {}
    for n in (1, 16):
        base = 1000 if n == 1 else 2000
        for arm in ("r", "f", "s"):
            for t in (0, 1):
                for p in (0, 1):
                    mismatch = t != p
                    difference = (40 if n == 1 else 16) if p == 0 else (
                        20 if n == 1 else 8)
                    if arm == "f":
                        difference = 0
                    if arm == "s":
                        difference = 8 if p == 0 else 4
                    values[f"{arm}_t{t}_p{p}_n{n}"] = base + (
                        difference if mismatch else 0)
        for p in (0, 1):
            values[f"fast_p{p}_n{n}"] = base + 300
            values[f"small_p{p}_n{n}"] = base + 300 + small_extra
            values[f"pause_p{p}_n{n}"] = base + 540
    checksum = 0
    for block, order in enumerate(orders):
        for position, kind in enumerate(order):
            index = len(rows) - 3
            ticks = values[kind] + block * 5
            if corrupt_outlier and block == 71 and kind == "r_t1_p0_n1":
                ticks += 100000
            rows.append(f"B2_SAMPLE,{index},{block},{position},{kind},{ticks}")
            checksum = (checksum + (index + 1) * ticks + block + position +
                        b2.KIND_INDEX[kind]) & b2.MAX_U64
    rows.append(f"B2_END,count=2592,checksum={checksum},sink=1")
    rows.append("B2_HOST,windows_build=26200,run_utc=20261031T180038Z")
    rows.append("B2_BINARY,sha256=" + "a" * 64)
    return "\r\n".join(rows) + "\r\n"


def parse_fixture(text):
    with patch.object(b2, "EXPECTED_BLOCKS", 72), \
         patch.object(b2, "EPISODES", 4), \
         patch.object(b2, "RESET_CALLS", 8), \
         patch.object(b2, "TRAIN_CALLS", 8):
        return b2.parse_trace(text)


def summarize_fixture(text):
    trace = parse_fixture(text)
    actual_interval = b2.interval

    def faster_interval(values, **kwargs):
        return actual_interval(values, iterations=250, **kwargs)

    with patch.object(b2, "EPISODES", 4), \
         patch.object(b2, "interval", faster_interval):
        return b2.summarize(trace)


class B2AnalysisTests(unittest.TestCase):
    def test_replayed_trace_and_four_primary_exploratory_contrasts(self):
        result = summarize_fixture(fixture())
        contrasts = result["contrasts"]
        self.assertEqual(len(contrasts), 22)  # 12 D, 4 F, 4 S, 2 interactions
        self.assertEqual(contrasts["F_p0_n1"]["paired_trimmed_mean_ticks_per_probe"], 10)
        self.assertEqual(contrasts["F_p0_n16"]["paired_trimmed_mean_ticks_per_probe"], 4)
        self.assertEqual(contrasts["F_p1_n1"]["paired_trimmed_mean_ticks_per_probe"], 5)
        self.assertEqual(contrasts["F_p1_n16"]["paired_trimmed_mean_ticks_per_probe"], 2)
        self.assertEqual(contrasts["S_p0_n1"]["paired_trimmed_mean_ticks_per_probe"], 8)
        self.assertEqual(contrasts["interaction_p0"]["paired_trimmed_mean_ticks_per_probe"], 6)
        self.assertEqual(contrasts["F_p0_n16"]["descriptive_ticks_per_call"], 0.25)
        self.assertEqual(len(result["controls"]), 4)
        self.assertTrue(result["statistical_control_gates_pass"])
        for control in result["controls"].values():
            self.assertEqual(control["small"]["paired_trimmed_mean_ticks_per_probe"], 4)
            self.assertEqual(control["pause"]["paired_trimmed_mean_ticks_per_probe"], 60)
            self.assertTrue(control["fixed_neutral"]["passes"])

    def test_outlier_does_not_drive_primary_estimate(self):
        result = summarize_fixture(fixture(corrupt_outlier=True))
        self.assertEqual(result["contrasts"]["F_p0_n1"][
            "paired_trimmed_mean_ticks_per_probe"], 10)

    def test_small_timer_failure_retains_contrasts(self):
        result = summarize_fixture(fixture(small_extra=0))
        self.assertFalse(result["statistical_control_gates_pass"])
        self.assertFalse(all(c["small"]["passes"] for c in result["controls"].values()))
        self.assertEqual(len(result["contrasts"]), 22)

    def test_length_interaction_is_paired_before_trimming(self):
        trace = parse_fixture(fixture())
        first, sixteenth = [], []
        for index, row in enumerate(trace.blocks):
            a = index % 10
            b = 100 if index % 10 == 9 else 0
            row["r_t1_p0_n1"] = row["r_t0_p0_n1"] + a
            row["r_t1_p0_n16"] = row["r_t0_p0_n16"] + b
            first.append(a)
            sixteenth.append(b)
        actual_interval = b2.interval

        def faster_interval(values, **kwargs):
            return actual_interval(values, iterations=250, **kwargs)

        with patch.object(b2, "EPISODES", 4), \
             patch.object(b2, "interval", faster_interval):
            observed = b2.summarize(trace)["contrasts"]["interaction_p0"][
                "paired_trimmed_mean_ticks_per_probe"]
        paired = b2.trimmed_mean([a - b for a, b in zip(first, sixteenth)]) / 4
        separately_trimmed = (b2.trimmed_mean(first) -
                              b2.trimmed_mean(sixteenth)) / 4
        self.assertEqual(observed, paired)
        self.assertNotEqual(observed, separately_trimmed)

    def test_reject_modified_samples_and_order_even_when_rechecksummed(self):
        text = fixture()
        with self.assertRaisesRegex(ValueError, "checksum"):
            parse_fixture(text.replace("r_t1_p0_n1,1040", "r_t1_p0_n1,1041", 1))
        rows = text.splitlines()
        first, second = rows[3].split(","), rows[4].split(",")
        first[4:], second[4:] = second[4:], first[4:]
        rows[3], rows[4] = ",".join(first), ",".join(second)
        checksum = 0
        for row in rows:
            if row.startswith("B2_SAMPLE,"):
                _, index, block, position, kind, ticks = row.split(",")
                checksum += ((int(index) + 1) * int(ticks) + int(block) +
                             int(position) + b2.KIND_INDEX[kind])
        rows[-3] = f"B2_END,count=2592,checksum={checksum & b2.MAX_U64},sink=1"
        with self.assertRaisesRegex(ValueError, "order does not match seed"):
            parse_fixture("\n".join(rows))

    def test_reject_protocol_pattern_and_missing_binary(self):
        with self.assertRaisesRegex(ValueError, "protocol dimensions"):
            parse_fixture(fixture().replace("train_calls=8", "train_calls=7", 1))
        with self.assertRaisesRegex(ValueError, "pattern hash"):
            parse_fixture(fixture().replace("pattern_hash=", "pattern_hash=9", 1))
        with self.assertRaisesRegex(ValueError, "incomplete"):
            parse_fixture(fixture().split("B2_BINARY")[0])
        with self.assertRaisesRegex(ValueError, "addresses coincide"):
            parse_fixture(fixture().replace("probe_addr=0x140023bc0",
                                            "probe_addr=0x140023b00", 1))

    def test_cli_strict_does_not_hide_inconclusive_data(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "b2.log"
            path.write_text(fixture(small_extra=0), encoding="utf-8")
            actual_interval = b2.interval

            def faster_interval(values, **kwargs):
                return actual_interval(values, iterations=250, **kwargs)

            output = StringIO()
            with patch.object(b2, "EXPECTED_BLOCKS", 72), \
                 patch.object(b2, "EPISODES", 4), \
                 patch.object(b2, "RESET_CALLS", 8), \
                 patch.object(b2, "TRAIN_CALLS", 8), \
                 patch.object(b2, "interval", faster_interval), \
                 patch.object(sys, "argv", ["analyze_history_b2.py", str(path), "--strict"]), \
                 redirect_stdout(output):
                self.assertEqual(b2.main(), 1)
            self.assertIn("INCONCLUSIVE", output.getvalue())
            self.assertIn("F_p0_n1", output.getvalue())
            self.assertIn("does not count", output.getvalue())


if __name__ == "__main__":
    unittest.main()
