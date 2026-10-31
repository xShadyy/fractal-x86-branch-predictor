"""Synthetic schedule, integrity, and paired-estimand checks for Study D."""

from pathlib import Path
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import analyze_history_decay as decay  # noqa: E402


def fixture(*, small_extra=16, corrupt=False, seed=7):
    orders, schedule_hash = decay.replay_schedule(88, seed)
    rows = [
        "HOST_AFFINITY_CPU=0",
        "DECAY_CPU,vendor=AuthenticAMD,signature=0x00b40f40,"
        "invariant_tsc=1,hypervisor=1",
        "DECAY_RUN,version=1,blocks=88,conditions=44,episodes=4,"
        "prelude_calls=8,filler_calls=8,train_calls=8,probe_calls=1,"
        "warmup_blocks=44,seed=7,lags=0_16_64_256,"
        "branch_addr=0x140001c00,small_addr=0x140001c20,"
        "timer=lfence_rdtsc_lfence,protocol=balanced_filler_position,"
        f"compiler=msvc_O2,schedule_hash={schedule_hash}",
    ]
    checksum, index = 0, 0
    for block, order in enumerate(orders):
        for position, kind in enumerate(order):
            if "_timer_" in kind:
                label, rest = kind.split("_timer_")
                timer, p = rest.split("_p")
                ticks = 5000 + block * 5 + int(label[1:]) // 16 + int(p) * 100
                ticks += {"fast": 0, "small": small_extra, "pause": 400}[timer]
            else:
                lag, arm, t, p = kind.split("_")
                lag_index = decay.LAGS.index(int(lag[1:]))
                train, probe = int(t[1:]), int(p[1:])
                mismatch = train != probe
                ticks = 5000 + block * 5 + lag_index * 10 + probe * 100
                if mismatch:
                    ticks += (80 - lag_index * 12 if arm == "real" else 2)
            if corrupt and block == 10 and kind == "l16_real_t1_p0":
                ticks += 1
            rows.append(f"DECAY_SAMPLE,{index},{block},{position},{kind},{ticks}")
            # The corruption fixture keeps the original checksum.
            recorded = ticks - (1 if corrupt and block == 10 and
                                kind == "l16_real_t1_p0" else 0)
            checksum += ((index + 1) * recorded + block + position +
                         decay.KIND_INDEX[kind])
            index += 1
    with patch.object(decay, "BLOCKS", 88), \
         patch.object(decay, "EPISODES", 4), \
         patch.object(decay, "PRELUDE_CALLS", 8), \
         patch.object(decay, "FILLER_CALLS", 8), \
         patch.object(decay, "TRAIN_CALLS", 8):
        sink = decay.expected_sink()
    rows += [
        f"DECAY_END,count={index},checksum={checksum},sink={sink}",
        "DECAY_HOST,windows_build=26200,run_utc=20261031T195000Z",
        "DECAY_BINARY,sha256=" + "a" * 64,
    ]
    return "\r\n".join(rows) + "\r\n"


def parse_fixture(text):
    with patch.object(decay, "BLOCKS", 88), \
         patch.object(decay, "EPISODES", 4), \
         patch.object(decay, "PRELUDE_CALLS", 8), \
         patch.object(decay, "FILLER_CALLS", 8), \
         patch.object(decay, "TRAIN_CALLS", 8):
        return decay.parse_trace(text)


class DecayTests(unittest.TestCase):
    def test_complete_design_and_paired_lag_interaction(self):
        trace = parse_fixture(fixture())
        with patch.object(decay, "BLOCKS", 88), \
             patch.object(decay, "EPISODES", 4), \
             patch.object(decay, "PRELUDE_CALLS", 8), \
             patch.object(decay, "FILLER_CALLS", 8), \
             patch.object(decay, "TRAIN_CALLS", 8):
            result = decay.summarize(trace)
        self.assertEqual(len(trace.blocks), 88)
        self.assertEqual(result["total_recorded_site_calls"], 88 * 44 * 4 * 25)
        self.assertEqual(result["outcomes"]["p0_l0"]["real_minus_fixed"][
            "paired_trimmed_mean_ticks_per_probe"], 19.5)
        self.assertEqual(result["outcomes"]["p0_l256"]["minus_l0"][
            "paired_trimmed_mean_ticks_per_probe"], -9.0)
        self.assertEqual(result["outcomes"]["p1_l0"]["real_minus_fixed"][
            "paired_trimmed_mean_ticks_per_probe"], 19.5)
        self.assertEqual(result["outcomes"]["p0_l0"][
            "fixed_mismatch_minus_match"][
            "paired_trimmed_mean_ticks_per_probe"], 0.5)
        self.assertTrue(result["timer_controls_pass"])
        self.assertTrue(result["fixed_trainer_all_within_tolerance"])
        self.assertEqual(set(result["timer_controls"]),
                         {"p0_l0", "p1_l0", "p0_l256", "p1_l256"})

    def test_few_tick_control_failure_does_not_remove_data(self):
        trace = parse_fixture(fixture(small_extra=0))
        with patch.object(decay, "BLOCKS", 88), \
             patch.object(decay, "EPISODES", 4):
            result = decay.summarize(trace)
        self.assertFalse(result["timer_controls_pass"])
        self.assertEqual(len(result["outcomes"]), 8)
        self.assertTrue(all(control["coarse_pass"] for control
                            in result["timer_controls"].values()))

    def test_corrupted_data_and_seed_schedule_rejected(self):
        with self.assertRaisesRegex(ValueError, "checksum"):
            parse_fixture(fixture(corrupt=True))
        with self.assertRaisesRegex(ValueError, "schedule hash"):
            parse_fixture(fixture().replace("schedule_hash=", "schedule_hash=1", 1))
        rows = fixture().splitlines()
        rows[-3] = rows[-3].rsplit("sink=", 1)[0] + "sink=0"
        with self.assertRaisesRegex(ValueError, "architectural sink"):
            parse_fixture("\n".join(rows))
        with self.assertRaisesRegex(ValueError, "incomplete"):
            parse_fixture(fixture().split("DECAY_BINARY")[0])

    def test_rejects_unbalanced_positions(self):
        # Change two kind labels, preserving a complete count and rechecksummed
        # trace, so the seed-derived randomized order is the only failing gate.
        rows = fixture().splitlines()
        first, second = rows[3].split(","), rows[4].split(",")
        first[4], second[4] = second[4], first[4]
        rows[3], rows[4] = ",".join(first), ",".join(second)
        checksum = 0
        for row in rows:
            if row.startswith("DECAY_SAMPLE,"):
                _, index, block, position, kind, ticks = row.split(",")
                checksum += ((int(index) + 1) * int(ticks) + int(block) +
                             int(position) + decay.KIND_INDEX[kind])
        sink = rows[-3].split("sink=")[1]
        rows[-3] = f"DECAY_END,count=3872,checksum={checksum},sink={sink}"
        with self.assertRaisesRegex(ValueError, "order mismatch"):
            parse_fixture("\n".join(rows))


if __name__ == "__main__":
    unittest.main()
