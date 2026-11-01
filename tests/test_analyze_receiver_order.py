"""Synthetic K2 traces test event-order replay, held-out gates and endpoint."""

from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import analyze_receiver_order as kord  # noqa: E402


BLOCKS = 32
EPISODES = 8
SEED = 2423705098


def fixture(*, entry_signal: bool = True, weak_signal: bool = False,
            heated_no_probe: bool = False, corrupt_order: bool = False) -> str:
    with patch.object(kord, "EPISODES", EPISODES):
        plans, schedule_hash = kord.replay_schedule(BLOCKS, SEED)
    lines = [
        "HOST_AFFINITY_CPU=0",
        "KORD_CPU,vendor=AuthenticAMD,signature=0x00b40f40,"
        "clflush_bytes=64,invariant_tsc=1,hypervisor=1",
        f"KORD_RUN,version=1,blocks={BLOCKS},modes=2,conditions=16,episodes={EPISODES},"
        "prelude_calls=128,train_calls=256,warmup_blocks=16,"
        f"seed={SEED},branch_addr=0x140001000,condition_addr=0x180002000,"
        "target0_addr=0x140001080,target1_addr=0x140001100,"
        "line0_addr=0x180000000,line1_addr=0x180001000,"
        "timer=lfence_rdtsc_lfence,flush=clflush_mfence,"
        "protocol=receiver_order_diagnostic,compiler=msvc_O2,"
        f"schedule_hash={schedule_hash}",
    ]
    checksum = 0
    index = 0
    for block, (modes, original_order) in enumerate(plans):
        order = list(original_order)
        if corrupt_order and block == 3:
            order[0], order[1] = order[1], order[0]
        for mode in modes:
            for position, kind in enumerate(order):
                p = int(kind[-1])
                ticks = []
                for occurrence in range(EPISODES):
                    if kind.startswith(("hot_", "arch_load_")):
                        base = 94
                    elif heated_no_probe and mode == "grouped" and kind == "no_probe_t1_p0":
                        base = 94
                    elif entry_signal and mode == "grouped" and kind == "arch_skip_p0" and \
                            occurrence < kord.EARLY and \
                            (not weak_signal or block == BLOCKS // 2):
                        base = 94
                    else:
                        base = 470
                    ticks.append(base)
                    checksum = (checksum + (index + 1) * base + block +
                                kord.MODE_INDEX[mode] + position + kord.KIND_INDEX[kind]) & kord.MAX_U64
                lines.append(f"KORD_SAMPLE,{index},{block},{mode},{position},{kind}," +
                             ";".join(map(str, ticks)))
                index += 1
    prelude, train, probe, sink = kord.expected_architecture(BLOCKS, EPISODES)
    lines += [f"KORD_END,count={index},checksum={checksum},sink={sink},"
              f"prelude_total={prelude},train_total={train},probe_total={probe}",
              "KORD_HOST,windows_build=26200,run_utc=20261101T160000Z",
              "KORD_BINARY,sha256=" + "a" * 64]
    return "\n".join(lines) + "\n"


class ReceiverOrderTests(unittest.TestCase):
    def parsed(self, content: str) -> kord.Trace:
        with patch.object(kord, "BLOCKS", BLOCKS), \
             patch.object(kord, "EPISODES", EPISODES):
            return kord.parse_trace(content)

    def analyzed(self, content: str) -> dict[str, object]:
        with patch.object(kord, "EPISODES", EPISODES):
            return kord.summarize(self.parsed(content))

    def test_grouped_entry_signal_with_valid_controls(self):
        result = self.analyzed(fixture())
        self.assertTrue(result["apparatus_controls_pass"])
        self.assertEqual(result["primary_endpoint"],
                         "grouped_arch_skip_p0_early5_minus_late59")
        self.assertEqual(result["primary_practical_margin_hit_rate_difference"], .10)
        self.assertTrue(result["primary_entry_association"])
        self.assertEqual(result["outcomes"]["p0"]["grouped_arch_skip_early_minus_late"]
                         ["hit_rate_difference"], 1)
        self.assertEqual(result["outcomes"]["p0"]["grouped_minus_interleaved_entry_effect"]
                         ["hit_rate_difference"], 1)
        self.assertEqual(result["heldout_hit_rates"]["grouped"]["arch_skip_p0"], 5/EPISODES)
        self.assertEqual(result["heldout_hit_rates"]["interleaved"]["arch_skip_p0"], 0)
        self.assertEqual(result["outcomes"]["p0"]["grouped_entry_differences_by_heldout_cycle"], [1])
        self.assertEqual(result["outcomes"]["p0"]["interleaved_skip_full_cell_rates_by_heldout_cycle"], [0])

    def test_valid_null_and_submargin_signal(self):
        null = self.analyzed(fixture(entry_signal=False))
        self.assertTrue(null["apparatus_controls_pass"])
        self.assertFalse(null["primary_entry_association"])
        small = self.analyzed(fixture(weak_signal=True))
        self.assertTrue(small["apparatus_controls_pass"])
        self.assertGreater(small["outcomes"]["p0"]["grouped_arch_skip_early_minus_late"]
                           ["hit_rate_difference"], 0)
        self.assertFalse(small["primary_entry_association"])

    def test_failed_control_withholds_primary(self):
        result = self.analyzed(fixture(heated_no_probe=True))
        self.assertFalse(result["apparatus_controls_pass"])
        self.assertFalse(result["apparatus_gates"]["grouped_no_probe_t1_p0"])
        self.assertIsNone(result["primary_entry_association"])
        self.assertEqual(result["outcomes"]["p0"]["grouped_arch_skip_early_minus_late"]
                         ["hit_rate_difference"], 1)

    def test_schedule_order_and_checksum_tampering(self):
        with self.assertRaisesRegex(ValueError, "seeded mode or condition order"):
            self.parsed(fixture(corrupt_order=True))
        with self.assertRaisesRegex(ValueError, "schedule hash"):
            self.parsed(fixture().replace("schedule_hash=", "schedule_hash=1", 1))
        rows = fixture().splitlines()
        i = next(i for i, line in enumerate(rows) if line.startswith("KORD_SAMPLE,"))
        parts = rows[i].split(",")
        ticks = parts[-1].split(";")
        ticks[0] = "999"
        parts[-1] = ";".join(ticks)
        rows[i] = ",".join(parts)
        with self.assertRaisesRegex(ValueError, "checksum"):
            self.parsed("\n".join(rows) + "\n")

    def test_architecture_layout_and_incomplete_trace_rejected(self):
        content = fixture()
        prelude, _, _, _ = kord.expected_architecture(BLOCKS, EPISODES)
        with self.assertRaisesRegex(ValueError, "architectural"):
            self.parsed(content.replace(f"prelude_total={prelude}",
                                        f"prelude_total={prelude + 1}"))
        with self.assertRaisesRegex(ValueError, "separate aligned pages"):
            self.parsed(content.replace("line1_addr=0x180001000",
                                        "line1_addr=0x180000040"))
        with self.assertRaisesRegex(ValueError, "incomplete"):
            self.parsed(content.split("KORD_BINARY,")[0])

    def test_cli_strict_checks_apparatus_not_effect(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "kord.log"
            for content, expected_exit in ((fixture(entry_signal=False), 0),
                                           (fixture(heated_no_probe=True), 1)):
                path.write_text(content, encoding="utf-8")
                stream = StringIO()
                with patch.object(kord, "BLOCKS", BLOCKS), \
                     patch.object(kord, "EPISODES", EPISODES), \
                     patch.object(sys, "argv", ["analyze_receiver_order.py",
                                               str(path), "--strict"]), \
                     redirect_stdout(stream):
                    self.assertEqual(kord.main(), expected_exit)
                self.assertIn("does not identify speculation", stream.getvalue())


if __name__ == "__main__":
    unittest.main()
