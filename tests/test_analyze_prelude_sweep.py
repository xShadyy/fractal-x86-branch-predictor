"""Synthetic trace and contrast checks for Study L prelude history sweep."""

from pathlib import Path
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import analyze_prelude_sweep as prelude  # noqa: E402


def fixture(*, small_extra=4, corrupt=False, seed=7):
    blocks, episodes, train_calls = 216, 2, 4
    orders, hash_value = prelude.replay_schedule(blocks, seed)
    rows = [
        "HOST_AFFINITY_CPU=3",
        "PRELUDE_CPU,vendor=AuthenticAMD,signature=0x00b40f40,"
        "invariant_tsc=1,hypervisor=1",
        "PRELUDE_RUN,version=1,blocks=216,conditions=108,episodes=2,"
        "prelude_lengths=128_256,patterns=p4_p32_c0_c1,"
        "train_calls=4,probe_calls=1,warmup_blocks=108,seed=7,"
        "branch_addr=0x140001c00,sham_addr=0x140001c30,"
        "small_addr=0x140001c40,timer=lfence_rdtsc_lfence,"
        "protocol=prelude_pattern_by_length,compiler=msvc_O2,"
        f"schedule_hash={hash_value}",
    ]
    checksum = index = 0
    for block, order in enumerate(orders):
        for position, kind in enumerate(order):
            length, pattern, arm, train, probe = prelude._features(kind)
            ticks = 2000 + block * 3 + length // 128 * 10 + probe * 100
            if "_timer_" in kind:
                ticks += {"fast": 0, "small": small_extra,
                          "pause": 100}[arm]
            elif train != probe:
                if arm == "real":
                    ticks += {"p4": 8, "p32": 16, "c0": 4, "c1": 12}[pattern]
                    ticks += 4 if length == 256 else 0
                elif arm == "sham":
                    ticks += 2
            unchanged = ticks
            if corrupt and block == 10 and kind == "n128_p32_real_t1_p0":
                ticks += 1
            rows.append(
                f"PRELUDE_SAMPLE,{index},{block},{position},{kind},{ticks}")
            checksum += ((index + 1) * unchanged + block + position +
                         prelude.KIND_INDEX[kind])
            index += 1
    with patch.object(prelude, "BLOCKS", blocks), \
         patch.object(prelude, "EPISODES", episodes), \
         patch.object(prelude, "TRAIN_CALLS", train_calls):
        sink = prelude.expected_sink()
    rows += [
        f"PRELUDE_END,count={index},checksum={checksum},sink={sink}",
        "PRELUDE_HOST,windows_build=26200,run_utc=20261031T195000Z",
        "PRELUDE_BINARY,sha256=" + "a" * 64,
    ]
    return "\r\n".join(rows) + "\r\n"


def parse_fixture(content):
    with patch.object(prelude, "BLOCKS", 216), \
         patch.object(prelude, "EPISODES", 2), \
         patch.object(prelude, "TRAIN_CALLS", 4):
        return prelude.parse_trace(content)


class PreludeTests(unittest.TestCase):
    def test_paired_balanced_history_and_length_interactions(self):
        trace = parse_fixture(fixture())
        with patch.object(prelude, "BLOCKS", 216), \
             patch.object(prelude, "EPISODES", 2), \
             patch.object(prelude, "TRAIN_CALLS", 4):
            result = prelude.summarize(trace)
        self.assertEqual(len(prelude.KINDS), 108)
        self.assertEqual(len(trace.blocks), 216)
        self.assertEqual(trace.affinity_cpu, 3)
        self.assertEqual(result["total_recorded_site_or_sham_calls"],
                         216 * 2 * (54 * 128 + 54 * 256 + 108 * 5))
        self.assertTrue(result["timer_controls_pass"])
        self.assertTrue(result["fixed_trainer_all_within_tolerance"])
        self.assertEqual(
            result["interactions"]["n128_p32_minus_p4_p0"][
                "paired_trimmed_mean_ticks_per_probe"], 4.0)
        self.assertEqual(
            result["interactions"]["n256_minus_n128_p4_p1"][
                "paired_trimmed_mean_ticks_per_probe"], 2.0)
        self.assertEqual(
            result["interactions"]["n128_c1_minus_c0_p0"][
                "paired_trimmed_mean_ticks_per_probe"], 4.0)
        self.assertEqual(len(result["outcomes"]), 16)
        self.assertEqual(len(result["timer_controls"]), 4)

    def test_few_tick_gate_failure_keeps_all_contrasts(self):
        trace = parse_fixture(fixture(small_extra=0))
        with patch.object(prelude, "BLOCKS", 216), \
             patch.object(prelude, "EPISODES", 2), \
             patch.object(prelude, "TRAIN_CALLS", 4):
            result = prelude.summarize(trace)
        self.assertFalse(result["timer_controls_pass"])
        self.assertEqual(len(result["outcomes"]), 16)
        self.assertTrue(all(item["coarse_pass"] for item in
                            result["timer_controls"].values()))

    def test_corruption_schedule_sink_and_truncation_rejected(self):
        with self.assertRaisesRegex(ValueError, "checksum"):
            parse_fixture(fixture(corrupt=True))
        with self.assertRaisesRegex(ValueError, "schedule hash"):
            parse_fixture(fixture().replace("schedule_hash=",
                                             "schedule_hash=1", 1))
        rows = fixture().splitlines()
        rows[-3] = rows[-3].rsplit("sink=", 1)[0] + "sink=0"
        with self.assertRaisesRegex(ValueError, "sink"):
            parse_fixture("\n".join(rows))
        with self.assertRaisesRegex(ValueError, "incomplete"):
            parse_fixture(fixture().split("PRELUDE_BINARY")[0])


if __name__ == "__main__":
    unittest.main()
