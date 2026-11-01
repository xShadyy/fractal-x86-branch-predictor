"""Synthetic K1 complete-cycle traces exercise controls and validation."""

from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import analyze_conditional_receiver as krec  # noqa: E402


BLOCKS = 32
EPISODES = 8
SEED = 1732072136


def fixture(*, candidate_signal: bool = True, heated_no_probe: bool = False,
            corrupt_order: bool = False, weak_signal: bool = False) -> str:
    orders, schedule_hash = krec.replay_schedule(BLOCKS, SEED)
    lines = [
        "HOST_AFFINITY_CPU=0",
        "KREC_CPU,vendor=AuthenticAMD,signature=0x00b40f40,"
        "clflush_bytes=64,invariant_tsc=1,hypervisor=1",
        f"KREC_RUN,version=1,blocks={BLOCKS},conditions=16,episodes={EPISODES},"
        "prelude_calls=128,train_calls=256,warmup_blocks=16,"
        f"seed={SEED},branch_addr=0x140001000,condition_addr=0x180002000,"
        "target0_addr=0x140001080,"
        "target1_addr=0x140001100,line0_addr=0x180000000,"
        "line1_addr=0x180001000,timer=lfence_rdtsc_lfence,"
        "flush=clflush_mfence,protocol=conditional_target_data_receiver,"
        f"compiler=msvc_O2,schedule_hash={schedule_hash}",
    ]
    checksum = 0
    index = 0
    for block, original_order in enumerate(orders):
        order = list(original_order)
        if corrupt_order and block == 3:
            order[0], order[1] = order[1], order[0]
        for position, kind in enumerate(order):
            p = int(kind[-1])
            if kind.startswith(("hot_", "arch_load_")):
                base = 45 + p
            elif kind.startswith("candidate_t") and candidate_signal and \
                    int(kind.split("_")[1][1]) != p and \
                    (not weak_signal or block == BLOCKS // 2):
                base = 45 + p
            elif heated_no_probe and kind == "no_probe_t1_p0":
                base = 45
            else:
                base = 400 + p
            ticks = [base + i % 3 for i in range(EPISODES)]
            if weak_signal and kind.startswith("candidate_t") and block == BLOCKS // 2:
                ticks[1:] = [400 + p + i % 3 for i in range(1, EPISODES)]
            for tick in ticks:
                checksum = (checksum + (index + 1) * tick + block + position +
                            krec.KIND_INDEX[kind]) & krec.MAX_U64
            lines.append(f"KREC_SAMPLE,{index},{block},{position},{kind}," +
                         ";".join(map(str, ticks)))
            index += 1
    prelude, train, probe, sink = krec.expected_architecture(BLOCKS, EPISODES)
    lines += [f"KREC_END,count={index},checksum={checksum},sink={sink},"
              f"prelude_total={prelude},train_total={train},probe_total={probe}",
              "KREC_HOST,windows_build=26200,run_utc=20261101T160000Z",
              "KREC_BINARY,sha256=" + "a" * 64]
    return "\n".join(lines) + "\n"


class ConditionalReceiverTests(unittest.TestCase):
    def parsed(self, text: str) -> krec.Trace:
        with patch.object(krec, "BLOCKS", BLOCKS), \
             patch.object(krec, "EPISODES", EPISODES):
            return krec.parse_trace(text)

    def analyzed(self, text: str) -> dict[str, object]:
        with patch.object(krec, "EPISODES", EPISODES):
            return krec.summarize(self.parsed(text))

    def test_complete_trace_controls_and_candidate_signal(self):
        result = self.analyzed(fixture())
        self.assertTrue(result["apparatus_controls_pass"])
        self.assertEqual(result["primary_endpoint"], "adjusted_p0")
        self.assertEqual(result["primary_practical_margin_hit_rate_difference"], .05)
        self.assertTrue(result["primary_candidate_association"])
        self.assertGreater(result["outcomes"]["p0"]["adjusted"]["hit_rate_difference"], .95)
        self.assertGreater(result["outcomes"]["p1"]["adjusted"]["hit_rate_difference"], .95)
        self.assertEqual(result["heldout_hit_rates"]["arch_skip_p0"], 0)
        self.assertEqual(result["heldout_hit_rates"]["no_probe_t1_p0"], 0)

    def test_valid_null_does_not_fail_controls(self):
        result = self.analyzed(fixture(candidate_signal=False))
        self.assertTrue(result["apparatus_controls_pass"])
        self.assertEqual(result["outcomes"]["p0"]["adjusted"]["hit_rate_difference"], 0)
        self.assertFalse(result["primary_candidate_association"])

    def test_submargin_signal_is_not_candidate_association(self):
        result = self.analyzed(fixture(weak_signal=True))
        self.assertTrue(result["apparatus_controls_pass"])
        self.assertGreater(result["outcomes"]["p0"]["adjusted"]["hit_rate_difference"], 0)
        self.assertFalse(result["primary_candidate_association"])

    def test_no_probe_residual_heat_withholds_interpretation(self):
        result = self.analyzed(fixture(heated_no_probe=True))
        self.assertFalse(result["apparatus_controls_pass"])
        self.assertFalse(result["apparatus_gates"]["no_probe_t1_p0"])
        self.assertIsNone(result["primary_candidate_association"])
        self.assertGreater(result["outcomes"]["p0"]["candidate_mismatch_minus_match"]
                           ["hit_rate_difference"], .95)

    def test_seed_order_and_hash_tampering(self):
        with self.assertRaisesRegex(ValueError, "seeded condition order"):
            self.parsed(fixture(corrupt_order=True))
        with self.assertRaisesRegex(ValueError, "schedule hash"):
            self.parsed(fixture().replace("schedule_hash=", "schedule_hash=1", 1))
        lines = fixture().splitlines()
        index = next(i for i, line in enumerate(lines) if line.startswith("KREC_SAMPLE,"))
        parts = lines[index].split(",")
        values = parts[-1].split(";")
        values[0] = "999"
        parts[-1] = ";".join(values)
        lines[index] = ",".join(parts)
        with self.assertRaisesRegex(ValueError, "checksum"):
            self.parsed("\n".join(lines) + "\n")

    def test_architecture_and_layout_rejected(self):
        text = fixture()
        prelude, _, _, _ = krec.expected_architecture(BLOCKS, EPISODES)
        with self.assertRaisesRegex(ValueError, "architectural"):
            self.parsed(text.replace(f"prelude_total={prelude}",
                                     f"prelude_total={prelude+1}"))
        with self.assertRaisesRegex(ValueError, "separate aligned pages"):
            self.parsed(text.replace("line1_addr=0x180001000", "line1_addr=0x180000040"))
        with self.assertRaisesRegex(ValueError, "incomplete"):
            self.parsed(text.split("KREC_BINARY,")[0])

    def test_cli_strict_only_fails_apparatus_not_null(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "krec.log"
            for text, expected_exit in ((fixture(candidate_signal=False), 0),
                                        (fixture(heated_no_probe=True), 1)):
                path.write_text(text, encoding="utf-8")
                stream = StringIO()
                with patch.object(krec, "BLOCKS", BLOCKS), \
                     patch.object(krec, "EPISODES", EPISODES), \
                     patch.object(sys, "argv", ["analyze_conditional_receiver.py",
                                               str(path), "--strict"]), \
                     redirect_stdout(stream):
                    self.assertEqual(krec.main(), expected_exit)
                self.assertIn("Target data-cache association alone", stream.getvalue())


if __name__ == "__main__":
    unittest.main()
