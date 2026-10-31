"""Synthetic indirect-target trace replay, paired contrasts and gates."""

from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import analyze_indirect_target as indirect  # noqa: E402


BLOCKS = 36
EPISODES = 4
CALLS = 8


def fixture(seed=125, small_extra=16, outlier=False):
    orders, schedule_hash = indirect.replay_schedule(BLOCKS, seed)
    rows = [
        "HOST_AFFINITY_CPU=0",
        "INDIRECT_CPU,vendor=AuthenticAMD,signature=0x00b40f40,"
        "invariant_tsc=1,hypervisor=1",
        "INDIRECT_RUN,version=1,blocks=36,episodes=4,reset_calls=8,"
        "train_calls=8,probe_calls=1,warmup_blocks=18,"
        f"seed={seed},branch_addr=0x140001c40,target0_addr=0x140001c80,"
        "target1_addr=0x140001c84,sham_addr=0x140001c90,"
        "live_addr=0x140023b00,fixed_addr=0x140023b40,"
        "mode_addr=0x140023b80,probe_addr=0x140023bc0,"
        "prelude_addr=0x140023c00,timer=lfence_rdtsc_lfence,"
        "protocol=indirect_target_history_same_site,compiler=msvc_O2,"
        f"schedule_hash={schedule_hash},"
        f"pattern_hash={indirect.replay_pattern_hash(CALLS)}",
    ]
    values = {}
    for arm in indirect.ARMS:
        for train in (0, 1):
            for probe in (0, 1):
                mismatch = train != probe
                difference = (40 if probe == 0 else 24) if arm == "r" else (
                    8 if arm == "s" else 0)
                values[f"{arm}_t{train}_p{probe}_n1"] = 1000 + (
                    difference if mismatch else 0)
    for probe in (0, 1):
        values[f"fast_p{probe}_n1"] = 1300
        values[f"small_p{probe}_n1"] = 1300 + small_extra
        values[f"pause_p{probe}_n1"] = 1540
    checksum = 0
    for block, order in enumerate(orders):
        for position, kind in enumerate(order):
            index = block * len(indirect.KINDS) + position
            ticks = values[kind] + block * 5
            if outlier and block == BLOCKS - 1 and kind == "r_t1_p0_n1":
                ticks += 100000
            rows.append(f"INDIRECT_SAMPLE,{index},{block},{position},{kind},{ticks}")
            checksum = (checksum + (index + 1) * ticks + block + position +
                        indirect.KIND_INDEX[kind]) & indirect.MAX_U64
    with patch.object(indirect, "EXPECTED_BLOCKS", BLOCKS), \
         patch.object(indirect, "EPISODES", EPISODES), \
         patch.object(indirect, "RESET_CALLS", CALLS), \
         patch.object(indirect, "TRAIN_CALLS", CALLS):
        sink = indirect.expected_sink()
    rows.append(f"INDIRECT_END,count={BLOCKS * len(indirect.KINDS)},"
                f"checksum={checksum},sink={sink}")
    rows.append("INDIRECT_HOST,windows_build=26200,run_utc=20261031T180038Z")
    rows.append("INDIRECT_BINARY,sha256=" + "a" * 64)
    return "\r\n".join(rows) + "\r\n"


def parsed(text):
    with patch.object(indirect, "EXPECTED_BLOCKS", BLOCKS), \
         patch.object(indirect, "EPISODES", EPISODES), \
         patch.object(indirect, "RESET_CALLS", CALLS), \
         patch.object(indirect, "TRAIN_CALLS", CALLS):
        return indirect.parse_trace(text)


def summary(text):
    trace = parsed(text)
    real_interval = indirect.interval

    def short_interval(values, **kwargs):
        return real_interval(values, iterations=250, **kwargs)

    with patch.object(indirect, "EPISODES", EPISODES), \
         patch.object(indirect, "interval", short_interval):
        return indirect.summarize(trace)


class IndirectTargetTests(unittest.TestCase):
    def test_contrasts_both_targets_and_controls(self):
        result = summary(fixture())
        self.assertEqual(result["contrasts"]["F_p0_n1"]["paired_trimmed_mean_ticks_per_probe"], 10)
        self.assertEqual(result["contrasts"]["F_p1_n1"]["paired_trimmed_mean_ticks_per_probe"], 6)
        self.assertEqual(result["contrasts"]["S_p0_n1"]["paired_trimmed_mean_ticks_per_probe"], 8)
        self.assertEqual(result["contrasts"]["S_p1_n1"]["paired_trimmed_mean_ticks_per_probe"], 4)
        self.assertTrue(result["statistical_control_gates_pass"])
        self.assertEqual(len(result["controls"]), 2)

    def test_outlier_and_failed_small_timer_remain_visible(self):
        self.assertEqual(summary(fixture(outlier=True))["contrasts"]["F_p0_n1"][
            "paired_trimmed_mean_ticks_per_probe"], 10)
        failed = summary(fixture(small_extra=0))
        self.assertFalse(failed["statistical_control_gates_pass"])
        self.assertIn("F_p0_n1", failed["contrasts"])

    def test_reject_modified_trace_and_target_layout(self):
        with self.assertRaisesRegex(ValueError, "checksum"):
            parsed(fixture().replace("r_t1_p0_n1,1040", "r_t1_p0_n1,1041", 1))
        with self.assertRaisesRegex(ValueError, "same 64-byte"):
            parsed(fixture().replace("target1_addr=0x140001c84",
                                     "target1_addr=0x140001d04", 1))
        with self.assertRaisesRegex(ValueError, "pattern hash"):
            parsed(fixture().replace("pattern_hash=", "pattern_hash=9", 1))
        with self.assertRaisesRegex(ValueError, "incomplete"):
            parsed(fixture().split("INDIRECT_BINARY")[0])

    def test_cli_nonzero_keeps_contrasts(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "indirect.log"
            path.write_text(fixture(small_extra=0), encoding="utf-8")
            real_interval = indirect.interval

            def short_interval(values, **kwargs):
                return real_interval(values, iterations=250, **kwargs)

            stream = StringIO()
            with patch.object(indirect, "EXPECTED_BLOCKS", BLOCKS), \
                 patch.object(indirect, "EPISODES", EPISODES), \
                 patch.object(indirect, "RESET_CALLS", CALLS), \
                 patch.object(indirect, "TRAIN_CALLS", CALLS), \
                 patch.object(indirect, "interval", short_interval), \
                 patch.object(sys, "argv", ["analyze_indirect_target.py", str(path), "--strict"]), \
                 redirect_stdout(stream):
                self.assertEqual(indirect.main(), 1)
            self.assertIn("INCONCLUSIVE", stream.getvalue())
            self.assertIn("F_p0_n1", stream.getvalue())


if __name__ == "__main__":
    unittest.main()
