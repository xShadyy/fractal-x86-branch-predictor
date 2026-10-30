"""Seed, balance, provenance and control tests for decision-source traces."""

from contextlib import redirect_stdout
from io import StringIO
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import analyze_decision_source as decision  # noqa: E402


def fixture(*, seed=7, live_effect=80, fixed_effect=2,
            branchless_effect=1, timer_effect=300, mode_offset=0,
            outlier=False):
    kinds = decision.KINDS
    orders, pattern_hash = decision.replay_patterns(8, 16, seed, kinds, 8)
    rows = [
        "HOST_AFFINITY_CPU=0",
        "DECISION_CPU,vendor=AuthenticAMD,signature=0x00b40f40,"
        "invariant_tsc=1,hypervisor=1",
        "DECISION_RUN,version=1,blocks=16,iterations=8,warmup_blocks=8,"
        f"seed={seed},branch_addr=0x140001000,branchless_addr=0x140001020,"
        "input_addr=0x140006000,control_addr=0x140006040,"
        "mode_addr=0x140006080,timer=lfence_rdtsc_lfence,"
        "pattern=periodic0011_vs_fresh_balanced_shuffle,"
        "decision=runtime_cmov_live_vs_fixed_periodic,compiler=msvc_O2,"
        f"pattern_hash={pattern_hash}",
    ]
    values = (1000, 1000 + live_effect,
              1000 + mode_offset, 1000 + mode_offset + fixed_effect,
              900, 900 + branchless_effect, 500, 500 + timer_effect)
    checksum = 0
    index = 0
    for block, order in enumerate(orders):
        for position, kind in enumerate(order):
            ticks = values[decision.KIND_INDEX[kind]] + block * 3
            if outlier and block == 15 and kind == "live_random":
                ticks += 100000
            rows.append(f"DECISION_SAMPLE,{index},{block},{position},{kind},{ticks}")
            checksum += (index + 1) * ticks + block + position + \
                decision.KIND_INDEX[kind]
            index += 1
    rows.extend((
        f"DECISION_END,count={index},checksum={checksum},sink=16",
        "DECISION_HOST,windows_build=26200,run_utc=20261030T170000Z",
        "DECISION_BINARY,sha256=" + "a" * 64,
    ))
    return "\r\n".join(rows) + "\r\n"


def parse_fixture(text):
    with patch.object(decision, "BLOCKS", 16), \
         patch.object(decision, "ITERATIONS", 8):
        return decision.parse_trace(text)


class DecisionSourceTests(unittest.TestCase):
    def test_blockwise_primary_and_controls(self):
        trace = parse_fixture(fixture())
        result = decision.summarize(trace)
        self.assertEqual(result["contrasts"]["primary_interaction"][
            "paired_trimmed_mean_ticks_per_iteration"], 9.75)
        self.assertEqual(result["contrasts"]["live_pattern"][
            "paired_trimmed_mean_ticks_per_iteration"], 10)
        self.assertEqual(result["contrasts"]["fixed_pattern"][
            "paired_trimmed_mean_ticks_per_iteration"], 0.25)
        self.assertEqual(result["contrasts"]["branchless_pattern"][
            "paired_trimmed_mean_ticks_per_iteration"], 0.125)
        self.assertEqual(result["contrasts"]["periodic_mode"][
            "paired_trimmed_mean_ticks_per_iteration"], 0)
        self.assertTrue(result["controls_pass"])
        self.assertTrue(result["primary_positive_within_run"])
        self.assertEqual(result["timer_control"]["positive_blocks"], 16)

    def test_distinct_seeds_replay_and_validate(self):
        first = parse_fixture(fixture(seed=7))
        second = parse_fixture(fixture(seed=987654321))
        self.assertNotEqual(first.run["pattern_hash"], second.run["pattern_hash"])
        self.assertNotEqual(first.run["seed"], second.run["seed"])

    def test_sample_tampering_and_seed_tampering_rejected(self):
        text = fixture()
        first_sample = next(row for row in text.splitlines()
                            if row.startswith("DECISION_SAMPLE,"))
        fields = first_sample.split(",")
        fields[-1] = str(int(fields[-1]) + 1)
        with self.assertRaisesRegex(ValueError, "checksum mismatch"):
            parse_fixture(text.replace(first_sample, ",".join(fields), 1))
        with self.assertRaisesRegex(ValueError, "pattern hash"):
            parse_fixture(text.replace("seed=7,", "seed=8,", 1))
        with self.assertRaisesRegex(ValueError, "invalid run seed"):
            parse_fixture(text.replace("seed=7,", "seed=0,", 1))

    def test_class_reordering_rejected_even_after_checksum_repair(self):
        lines = fixture().splitlines()
        first = 3 + len(decision.KINDS)
        pair = [line.split(",") for line in lines[first:first + 2]]
        for position, row in enumerate(reversed(pair)):
            row[1] = str(first - 3 + position)
            row[3] = str(position)
            lines[first + position] = ",".join(row)
        checksum = 0
        for row in lines:
            if row.startswith("DECISION_SAMPLE,"):
                _, index, block, position, kind, ticks = row.split(",")
                checksum += (int(index) + 1) * int(ticks) + int(block) + \
                    int(position) + decision.KIND_INDEX[kind]
        end = next(i for i, row in enumerate(lines)
                   if row.startswith("DECISION_END,"))
        lines[end] = f"DECISION_END,count=128,checksum={checksum},sink=16"
        with self.assertRaisesRegex(ValueError, "class order does not match seed"):
            parse_fixture("\n".join(lines))

    def test_failed_negative_or_timer_control_does_not_erase_primary(self):
        fixed = decision.summarize(parse_fixture(fixture(fixed_effect=16)))
        self.assertFalse(fixed["controls_pass"])
        self.assertFalse(fixed["negative_controls_within_tolerance"]["fixed_pattern"])
        self.assertIn("primary_interaction", fixed["contrasts"])
        timer = decision.summarize(parse_fixture(fixture(timer_effect=0)))
        self.assertFalse(timer["controls_pass"])
        self.assertFalse(timer["timer_control"]["passes"])
        mode = decision.summarize(parse_fixture(fixture(mode_offset=8)))
        self.assertFalse(mode["controls_pass"])
        self.assertFalse(mode["negative_controls_within_tolerance"]["periodic_mode"])

    def test_positive_effect_is_not_a_gate_and_outlier_is_retained(self):
        null = decision.summarize(parse_fixture(
            fixture(live_effect=0, fixed_effect=0, branchless_effect=0)))
        self.assertTrue(null["controls_pass"])
        self.assertFalse(null["primary_positive_within_run"])
        outlier = decision.summarize(parse_fixture(fixture(outlier=True)))
        self.assertEqual(outlier["contrasts"]["primary_interaction"][
            "paired_trimmed_mean_ticks_per_iteration"], 9.75)

    def test_host_binary_and_cli_strict_validation(self):
        with self.assertRaisesRegex(ValueError, "incomplete"):
            parse_fixture(fixture().split("DECISION_BINARY,")[0])
        with self.assertRaisesRegex(ValueError, "branch or data addresses coincide"):
            parse_fixture(fixture().replace("mode_addr=0x140006080",
                                            "mode_addr=0x140006000"))
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "decision.log"
            path.write_text(fixture(), encoding="utf-8")
            output = StringIO()
            with patch.object(decision, "BLOCKS", 16), \
                 patch.object(decision, "ITERATIONS", 8), \
                 patch.object(sys, "argv", ["analyze_decision_source.py",
                                            str(path), "--strict"]), \
                 redirect_stdout(output):
                self.assertEqual(decision.main(), 0)
            self.assertIn("primary_interaction", output.getvalue())
            self.assertIn("within-run 8-block bootstrap", output.getvalue())


if __name__ == "__main__":
    unittest.main()
