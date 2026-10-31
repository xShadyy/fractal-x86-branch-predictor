"""Synthetic replay, integrity, estimand and control checks for Study E."""

from pathlib import Path
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import analyze_training_dose as dose  # noqa: E402


SEED = 773
TEST_BLOCKS = 104  # Two complete 52-position cycles.
TEST_EPISODES = 4


def fixture(*, small_extra=16, corrupt=False, null_shift=0):
    orders, schedule_hash = dose.replay_schedule(TEST_BLOCKS, SEED)
    rows = [
        "HOST_AFFINITY_CPU=0",
        "DOSE_CPU,vendor=AuthenticAMD,signature=0x00b40f40,"
        "invariant_tsc=1,hypervisor=1",
        "DOSE_RUN,version=1,blocks=104,conditions=52,episodes=4,"
        "prelude_calls=256,train_budget=256,probe_calls=1,"
        "warmup_blocks=52,seed=773,doses=0_4_16_64_256,"
        "branch_addr=0x140001c00,timer=lfence_rdtsc_lfence,"
        "protocol=fixed_budget_training_dose,compiler=msvc_O2,"
        f"schedule_hash={schedule_hash},pattern_hash={dose.expected_pattern_hash()}",
    ]
    checksum, index = 0, 0
    for block, order in enumerate(orders):
        for position, kind in enumerate(order):
            dose_label = int(kind.split("_", 1)[0][1:])
            if "_timer_" in kind:
                mode = kind.split("_timer_")[1].split("_p")[0]
                probe = int(kind[-1])
                ticks = 5000 + block * 5 + dose_label // 4 + probe * 100
                ticks += {"fast": 0, "small": small_extra, "pause": 400}[mode]
            else:
                _, arm, t, p = kind.split("_")
                train, probe = int(t[1:]), int(p[1:])
                ticks = 5000 + block * 5 + dose_label // 4 + probe * 100
                if train != probe:
                    ticks += ((dose.DOSES.index(dose_label) * 8 +
                               (null_shift if dose_label == 0 else 0))
                              if arm == "real" else 0)
            original = ticks
            if corrupt and block == 10 and kind == "d16_real_t1_p0":
                ticks += 1
            rows.append(f"DOSE_SAMPLE,{index},{block},{position},{kind},{ticks}")
            checksum += ((index + 1) * original + block + position +
                         dose.KIND_INDEX[kind])
            index += 1
    with patch.object(dose, "BLOCKS", TEST_BLOCKS), \
         patch.object(dose, "EPISODES", TEST_EPISODES):
        sink = dose.expected_sink()
    rows += [
        f"DOSE_END,count={index},checksum={checksum},sink={sink}",
        "DOSE_HOST,windows_build=26200,run_utc=20261031T215500Z",
        "DOSE_BINARY,sha256=" + "b" * 64,
    ]
    return "\r\n".join(rows) + "\r\n"


def parse_fixture(content):
    with patch.object(dose, "BLOCKS", TEST_BLOCKS), \
         patch.object(dose, "EPISODES", TEST_EPISODES):
        return dose.parse_trace(content)


def summarize_fixture(trace):
    with patch.object(dose, "BLOCKS", TEST_BLOCKS), \
         patch.object(dose, "EPISODES", TEST_EPISODES):
        return dose.summarize(trace)


class TrainingDoseTests(unittest.TestCase):
    def test_complete_matrix_and_paired_dose_interaction(self):
        trace = parse_fixture(fixture())
        result = summarize_fixture(trace)
        self.assertEqual(len(trace.blocks), TEST_BLOCKS)
        self.assertEqual(result["total_recorded_site_calls"],
                         TEST_BLOCKS * 52 * TEST_EPISODES * 513)
        self.assertEqual(result["outcomes"]["p0_d0"]["real_minus_fixed"][
            "paired_trimmed_mean_ticks_per_probe"], 0)
        self.assertEqual(result["outcomes"]["p1_d256"]["real_minus_fixed"][
            "paired_trimmed_mean_ticks_per_probe"], 8)
        self.assertEqual(result["outcomes"]["p0_d256"]["minus_d0"][
            "paired_trimmed_mean_ticks_per_probe"], 8)
        self.assertTrue(result["timer_controls_pass"])
        self.assertTrue(result["fixed_trainer_all_within_tolerance"])
        self.assertEqual(result["zero_dose_adjusted_within_tolerance"],
                         {"p0": True, "p1": True})
        self.assertEqual(set(result["timer_controls"]),
                         {"p0_d0", "p1_d0", "p0_d256", "p1_d256"})

    def test_failed_small_control_and_null_keep_all_outcomes(self):
        result = summarize_fixture(parse_fixture(fixture(small_extra=0,
                                                        null_shift=16)))
        self.assertFalse(result["timer_controls_pass"])
        self.assertEqual(result["zero_dose_adjusted_within_tolerance"],
                         {"p0": False, "p1": False})
        self.assertEqual(len(result["outcomes"]), 10)
        self.assertTrue(all(control["coarse_pass"] for control
                            in result["timer_controls"].values()))

    def test_checksum_schedule_pattern_and_sink_tampering_rejected(self):
        with self.assertRaisesRegex(ValueError, "checksum"):
            parse_fixture(fixture(corrupt=True))
        with self.assertRaisesRegex(ValueError, "schedule hash"):
            parse_fixture(fixture().replace("schedule_hash=", "schedule_hash=1", 1))
        with self.assertRaisesRegex(ValueError, "pattern hash"):
            parse_fixture(fixture().replace("pattern_hash=", "pattern_hash=1", 1))
        rows = fixture().splitlines()
        rows[-3] = rows[-3].rsplit("sink=", 1)[0] + "sink=0"
        with self.assertRaisesRegex(ValueError, "architectural sink"):
            parse_fixture("\n".join(rows))

    def test_incomplete_trace_and_seed_order_rejected(self):
        with self.assertRaisesRegex(ValueError, "incomplete"):
            parse_fixture(fixture().split("DOSE_BINARY")[0])
        rows = fixture().splitlines()
        first, second = rows[3].split(","), rows[4].split(",")
        first[4], second[4] = second[4], first[4]
        rows[3], rows[4] = ",".join(first), ",".join(second)
        checksum = 0
        for row in rows:
            if row.startswith("DOSE_SAMPLE,"):
                _, index, block, position, kind, ticks = row.split(",")
                checksum += ((int(index) + 1) * int(ticks) + int(block) +
                             int(position) + dose.KIND_INDEX[kind])
        sink = rows[-3].split("sink=")[1]
        rows[-3] = f"DOSE_END,count={TEST_BLOCKS * 52},checksum={checksum},sink={sink}"
        with self.assertRaisesRegex(ValueError, "order mismatch"):
            parse_fixture("\n".join(rows))


if __name__ == "__main__":
    unittest.main()
