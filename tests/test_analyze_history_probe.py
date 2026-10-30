"""Protocol validation and paired contrasts for the history crossover trace."""

from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import analyze_history_probe as history  # noqa: E402


def fixture(*, timer_extra=400, outlier=False, seed=7):
    orders, schedule_hash = history.replay_schedule(20, seed)
    rows = [
        "HOST_AFFINITY_CPU=0",
        "HISTORY_CPU,vendor=AuthenticAMD,signature=0x00b40f40,"
        "invariant_tsc=1,hypervisor=1",
        "HISTORY_RUN,version=1,blocks=20,episodes=4,reset_calls=8,"
        f"train_calls=8,probe_calls=4,warmup_blocks=10,seed={seed},"
        "branch_addr=0x140001c10,sham_addr=0x140001c1e,"
        "timer=lfence_rdtsc_lfence,"
        "protocol=reset_train_fixed_probe_crossover,compiler=msvc_O2,"
        f"schedule_hash={schedule_hash}",
    ]
    values = {
        "b_t0_p0": 1000, "b_t1_p0": 1080,
        "b_t0_p1": 1072, "b_t1_p1": 1000,
        "s_t0_p0": 900, "s_t1_p0": 908,
        "s_t0_p1": 904, "s_t1_p1": 900,
        "timer_fast": 1200, "timer_slow": 1200 + timer_extra,
    }
    checksum = 0
    index = 0
    for block, order in enumerate(orders):
        for position, kind in enumerate(order):
            ticks = values[kind] + block * 5
            if outlier and block == 19 and kind == "b_t1_p0":
                ticks += 100000
            rows.append(f"HISTORY_SAMPLE,{index},{block},{position},{kind},{ticks}")
            checksum += (index + 1) * ticks + block + position + history.KIND_INDEX[kind]
            index += 1
    rows.append(f"HISTORY_END,count={index},checksum={checksum},sink=1")
    rows.append("HISTORY_HOST,windows_build=26200,run_utc=20261030T131602Z")
    rows.append("HISTORY_BINARY,sha256=" + "a" * 64)
    return "\r\n".join(rows) + "\r\n"


def parse_fixture(content):
    with patch.object(history, "EXPECTED_BLOCKS", 20), \
         patch.object(history, "EPISODES", 4), \
         patch.object(history, "RESET_CALLS", 8), \
         patch.object(history, "TRAIN_CALLS", 8), \
         patch.object(history, "PROBE_CALLS", 4):
        return history.parse_trace(content)


class HistoryProbeTests(unittest.TestCase):
    def test_two_directional_sham_adjusted_contrasts(self):
        trace = parse_fixture(fixture())
        self.assertEqual(trace.run["seed"], "7")
        self.assertEqual(len(trace.blocks), 20)
        with patch.object(history, "EPISODES", 4):
            result = history.summarize(trace)
        contrasts = result["contrasts"]
        self.assertEqual(contrasts["probe0"]["paired_trimmed_mean_ticks_per_probe"], 20)
        self.assertEqual(contrasts["probe1"]["paired_trimmed_mean_ticks_per_probe"], 18)
        self.assertEqual(contrasts["sham0"]["paired_trimmed_mean_ticks_per_probe"], 2)
        self.assertEqual(contrasts["sham1"]["paired_trimmed_mean_ticks_per_probe"], 1)
        self.assertEqual(contrasts["adjusted0"]["paired_trimmed_mean_ticks_per_probe"], 18)
        self.assertEqual(contrasts["adjusted1"]["paired_trimmed_mean_ticks_per_probe"], 17)
        self.assertEqual(result["split_half_adjusted_ticks_per_probe"],
                         {"probe0": (18, 18), "probe1": (17, 17)})
        self.assertNotIn("adjusted_crossover", contrasts)
        self.assertTrue(result["timer_control"]["passes"])
        self.assertEqual(result["timer_control"]["paired_trimmed_mean_ticks_total"], 400)
        self.assertEqual(result["timer_control"]["paired_trimmed_mean_ticks_per_probe"], 100)

    def test_one_large_outlier_does_not_drive_adjusted_result(self):
        with patch.object(history, "EPISODES", 4):
            result = history.summarize(parse_fixture(fixture(outlier=True)))
        self.assertEqual(result["contrasts"]["adjusted0"][
            "paired_trimmed_mean_ticks_per_probe"], 18)

    def test_timer_failure_keeps_complete_data(self):
        with patch.object(history, "EPISODES", 4):
            result = history.summarize(parse_fixture(fixture(timer_extra=0)))
        self.assertFalse(result["timer_control"]["passes"])
        self.assertEqual(len(result["contrasts"]), 6)

    def test_corrupt_sample_rejected_by_checksum(self):
        content = fixture().replace("b_t0_p0,1000", "b_t0_p0,1001", 1)
        with self.assertRaisesRegex(ValueError, "checksum"):
            parse_fixture(content)

    def test_seeded_order_rejected_even_with_recomputed_checksum(self):
        rows = fixture().splitlines()
        sample_start = 3
        first = rows[sample_start].split(",")
        second = rows[sample_start + 1].split(",")
        first[4:], second[4:] = second[4:], first[4:]
        rows[sample_start] = ",".join(first)
        rows[sample_start + 1] = ",".join(second)
        checksum = 0
        for row in rows:
            if not row.startswith("HISTORY_SAMPLE,"):
                continue
            _, index, block, position, kind, ticks = row.split(",")
            checksum += (int(index) + 1) * int(ticks) + int(block) + \
                int(position) + history.KIND_INDEX[kind]
        rows[-3] = f"HISTORY_END,count=200,checksum={checksum},sink=1"
        with self.assertRaisesRegex(ValueError, "class order does not match seed"):
            parse_fixture("\n".join(rows))

    def test_protocol_seed_and_provenance_checks(self):
        with self.assertRaisesRegex(ValueError, "protocol dimensions"):
            parse_fixture(fixture().replace("probe_calls=4", "probe_calls=5", 1))
        with self.assertRaisesRegex(ValueError, "schedule hash"):
            parse_fixture(fixture().replace("schedule_hash=", "schedule_hash=1", 1))
        with self.assertRaisesRegex(ValueError, "incomplete"):
            parse_fixture(fixture().split("HISTORY_BINARY")[0])
        with self.assertRaisesRegex(ValueError, "duplicate HISTORY_BINARY"):
            parse_fixture(fixture() + "HISTORY_BINARY,sha256=" + "a" * 64 + "\n")

    def test_cli_labels_and_strict_timer_gate(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "history.log"
            path.write_text(fixture(timer_extra=0), encoding="utf-8")
            output = StringIO()
            with patch.object(history, "EXPECTED_BLOCKS", 20), \
                 patch.object(history, "EPISODES", 4), \
                 patch.object(history, "RESET_CALLS", 8), \
                 patch.object(history, "TRAIN_CALLS", 8), \
                 patch.object(history, "PROBE_CALLS", 4), \
                 patch.object(sys, "argv", ["analyze_history_probe.py", str(path), "--strict"]), \
                 redirect_stdout(output):
                self.assertEqual(history.main(), 1)
            text = output.getvalue()
            self.assertIn("INCONCLUSIVE", text)
            self.assertIn("branch - sham probe 0", text)
            self.assertIn("branch - sham probe 1", text)
            self.assertIn("User-mode timing does not count mispredictions", text)


if __name__ == "__main__":
    unittest.main()
