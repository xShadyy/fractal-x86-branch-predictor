"""Complete-block and control checks for the batched branch trace."""

from contextlib import redirect_stdout
from io import StringIO
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import analyze_branch_batch as batch  # noqa: E402
from analyze_branch_batch import KIND_INDEX, KINDS, interval, summarize  # noqa: E402


def parse_fixture(content):
    with patch.object(batch, "EXPECTED_ITERATIONS", 8), \
         patch.object(batch, "EXPECTED_BLOCKS", 12), \
         patch.object(batch, "EXPECTED_SEED", 7):
        return batch.parse_trace(content)


def serial_trace(*, branch_effect=80, branchless_effect=20, timer_extra=300,
                 outlier=False):
    orders, pattern_hash = batch.replay_patterns(8, 12, 7)
    rows = [
        "HOST_AFFINITY_CPU=0",
        "BATCH_CPU,vendor=AuthenticAMD,signature=0x00b40f40,"
        "invariant_tsc=1,hypervisor=1",
        "BATCH_RUN,version=1,blocks=12,iterations=8,warmup_blocks=6,seed=7,"
        "branch_addr=0x140001560,branchless_addr=0x140001590,"
        "timer=lfence_rdtsc_lfence,"
        "pattern=periodic0011_vs_fresh_balanced_shuffle,compiler=msvc_O2,"
        f"pattern_hash={pattern_hash}",
    ]
    checksum = 0
    index = 0
    for block, order in enumerate(orders):
        for position, kind in enumerate(order):
            kind_index = KIND_INDEX[kind]
            values = (1000, 1000 + branch_effect, 900,
                      900 + branchless_effect, 500, 500 + timer_extra)
            ticks = values[kind_index] + block * 3
            if outlier and block == 11 and kind == "branch_random":
                ticks += 100000
            rows.append(f"BATCH_SAMPLE,{index},{block},{position},{kind},{ticks}")
            checksum += (index + 1) * ticks + block + position + KIND_INDEX[kind]
            index += 1
    rows.append(f"BATCH_END,count={index},checksum={checksum},sink=12")
    rows.append("BATCH_BINARY,sha256=" + "a" * 64)
    return "\r\n".join(rows) + "\r\n"


def serial_trace_v2(*, seed=7, branch_effect=80, no_load_effect=48,
                    branchless_effect=20, timer_extra=300):
    kinds = batch.KINDS_V2
    orders, pattern_hash = batch.replay_patterns(
        8, 16, seed, kinds, batch.WARMUP_BLOCKS_V2)
    rows = [
        "HOST_AFFINITY_CPU=0",
        "BATCH_CPU,vendor=AuthenticAMD,signature=0x00b40f40,"
        "invariant_tsc=1,hypervisor=1",
        "BATCH_RUN,version=2,blocks=16,iterations=8,warmup_blocks=8,"
        f"seed={seed},branch_addr=0x140001560,"
        "branch_no_load_addr=0x140001580,branchless_addr=0x140001590,"
        "timer=lfence_rdtsc_lfence,"
        "pattern=periodic0011_vs_fresh_balanced_shuffle,compiler=msvc_O2,"
        f"pattern_hash={pattern_hash}",
    ]
    checksum = 0
    index = 0
    values = (1000, 1000 + branch_effect, 960, 960 + no_load_effect,
              900, 900 + branchless_effect, 500, 500 + timer_extra)
    kind_index = {kind: i for i, kind in enumerate(kinds)}
    for block, order in enumerate(orders):
        for position, kind in enumerate(order):
            ticks = values[kind_index[kind]] + block * 3
            rows.append(f"BATCH_SAMPLE,{index},{block},{position},{kind},{ticks}")
            checksum += (index + 1) * ticks + block + position + kind_index[kind]
            index += 1
    rows.append(f"BATCH_END,count={index},checksum={checksum},sink=16")
    rows.append("BATCH_HOST,windows_build=26100,run_utc=20261030T010203Z")
    rows.append("BATCH_BINARY,sha256=" + "b" * 64)
    return "\r\n".join(rows) + "\r\n"


def parse_fixture_v2(content):
    with patch.object(batch, "EXPECTED_ITERATIONS", 8), \
         patch.object(batch, "EXPECTED_BLOCKS", 16):
        return batch.parse_trace(content)


class BranchBatchTests(unittest.TestCase):
    def test_production_seed_replay_vector(self):
        orders, pattern_hash = batch.replay_patterns(
            batch.EXPECTED_ITERATIONS, batch.EXPECTED_BLOCKS,
            batch.EXPECTED_SEED)
        self.assertEqual(pattern_hash, 11498097490340967081)
        self.assertEqual(orders[0], (
            "branch_random", "branchless_random", "timer_fast",
            "branch_periodic", "timer_slow", "branchless_periodic"))

    def test_interaction_and_positive_control(self):
        result = summarize(parse_fixture(serial_trace()))
        self.assertTrue(result["timer_control"]["passes"])
        self.assertEqual(result["contrasts"]["branch"][
            "paired_trimmed_mean_ticks_per_iteration"], 10)
        self.assertEqual(result["contrasts"]["branchless"][
            "paired_trimmed_mean_ticks_per_iteration"], 2.5)
        self.assertEqual(result["contrasts"]["adjusted"][
            "paired_trimmed_mean_ticks_per_iteration"], 7.5)
        self.assertTrue(result["branchless_contrast_detectable"])
        self.assertEqual(result["timer_control"]["within_run_cycle_bootstrap_95_ticks"],
                         (300, 300))

    def test_bootstrap_resamples_whole_position_cycles(self):
        self.assertEqual(interval([0] * 6 + [100] * 6), (0, 100))

    def test_null_interaction(self):
        result = summarize(parse_fixture(serial_trace(branch_effect=20)))
        self.assertEqual(result["contrasts"]["adjusted"][
            "paired_trimmed_mean_ticks_per_iteration"], 0)

    def test_timer_positive_control_failure(self):
        result = summarize(parse_fixture(serial_trace(timer_extra=0)))
        self.assertFalse(result["timer_control"]["passes"])

    def test_cli_labels_timer_estimator_and_branchless_magnitude(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "batch.log"
            path.write_text(serial_trace(), encoding="utf-8")
            output = StringIO()
            with patch.object(batch, "EXPECTED_ITERATIONS", 8), \
                 patch.object(batch, "EXPECTED_BLOCKS", 12), \
                 patch.object(batch, "EXPECTED_SEED", 7), \
                 patch.object(sys, "argv", ["analyze_branch_batch.py", str(path)]), \
                 redirect_stdout(output):
                self.assertEqual(batch.main(), 0)
            lines = output.getvalue()
            self.assertIn("slow - fast trimmed mean +300.0 ticks ", lines)
            self.assertIn("paired median +300.0", lines)
            self.assertIn("within this run; inspect its magnitude and repeat runs", lines)
            self.assertIn("absolute point-estimate ratio to branch contrast: 25.00%", lines)
            self.assertNotIn("interpretation is confounded", lines)

    def test_one_large_outlier_does_not_move_trimmed_point_estimate(self):
        result = summarize(parse_fixture(serial_trace(outlier=True)))
        self.assertEqual(result["contrasts"]["adjusted"][
            "paired_trimmed_mean_ticks_per_iteration"], 7.5)

    def test_truncated_trace_rejected(self):
        with self.assertRaisesRegex(ValueError, "incomplete"):
            parse_fixture(serial_trace().split("BATCH_END")[0])

    def test_corrupted_ticks_rejected_by_checksum(self):
        with self.assertRaisesRegex(ValueError, "checksum"):
            parse_fixture(serial_trace().replace("branch_periodic,1000",
                                               "branch_periodic,1001", 1))

    def test_missing_class_rejected_even_with_valid_checksum(self):
        trace = serial_trace()
        original_label = batch.replay_patterns(8, 12, 7)[0][0][0]
        original_ticks = (1000, 1080, 900, 920, 500, 800)[KIND_INDEX[original_label]]
        original = f"BATCH_SAMPLE,0,0,0,{original_label},{original_ticks}"
        replacement_label = KINDS[(KIND_INDEX[original_label] + 1) % len(KINDS)]
        replacement = f"BATCH_SAMPLE,0,0,0,{replacement_label},{original_ticks}"
        trace = trace.replace(original, replacement, 1)
        raw_checksum = int(trace.split("checksum=", 1)[1].split(",", 1)[0])
        trace = trace.replace(f"checksum={raw_checksum}",
                              f"checksum={raw_checksum + (KIND_INDEX[replacement_label] - KIND_INDEX[original_label])}")
        with self.assertRaisesRegex(ValueError, "unbalanced conditions"):
            parse_fixture(trace)

    def test_seeded_order_rejected_even_with_valid_checksum(self):
        # Change one complete block's order while preserving its six samples.
        trace = serial_trace()
        lines = trace.splitlines()
        block = 1
        sample_start = 3 + block * len(KINDS)
        swapped = lines[sample_start:sample_start + len(KINDS)]
        for i, source in enumerate((1, 0, 2, 3, 4, 5)):
            parts = swapped[source].split(",")
            parts[1] = str(sample_start - 3 + i)
            parts[3] = str(i)
            lines[sample_start + i] = ",".join(parts)
        checksum = 0
        for line in lines:
            if not line.startswith("BATCH_SAMPLE,"):
                continue
            _, index, block_id, position, kind, ticks = line.split(",")
            checksum += (int(index) + 1) * int(ticks) + int(block_id) + \
                int(position) + KIND_INDEX[kind]
        lines[-2] = f"BATCH_END,count=72,checksum={checksum},sink=12"
        with self.assertRaisesRegex(ValueError, "class order does not match seed"):
            parse_fixture("\n".join(lines))

    def test_pattern_hash_mutation_rejected(self):
        trace = serial_trace()
        metadata = trace.split("pattern_hash=", 1)[1].split("\r", 1)[0]
        with self.assertRaisesRegex(ValueError, "pattern hash"):
            parse_fixture(trace.replace(f"pattern_hash={metadata}",
                                        f"pattern_hash={int(metadata) + 1}", 1))

    def test_seed_mutation_rejected(self):
        with self.assertRaisesRegex(ValueError, "unexpected version 1"):
            parse_fixture(serial_trace().replace("seed=7,", "seed=8,", 1))

    def test_missing_affinity_rejected(self):
        with self.assertRaisesRegex(ValueError, "incomplete"):
            parse_fixture(serial_trace().replace("HOST_AFFINITY_CPU=0\r\n", "", 1))

    def test_missing_binary_provenance_rejected(self):
        with self.assertRaisesRegex(ValueError, "incomplete"):
            parse_fixture(serial_trace().split("BATCH_BINARY")[0])

    def test_duplicate_binary_provenance_rejected(self):
        trace = serial_trace() + "BATCH_BINARY,sha256=" + "a" * 64 + "\n"
        with self.assertRaisesRegex(ValueError, "duplicate BATCH_BINARY"):
            parse_fixture(trace)

    def test_malformed_binary_provenance_rejected(self):
        trace = serial_trace().replace("BATCH_BINARY,sha256=" + "a" * 64,
                                       "BATCH_BINARY,sha256=" + "A" * 64)
        with self.assertRaisesRegex(ValueError, "invalid binary SHA256"):
            parse_fixture(trace)

    def test_version_2_different_seeds_and_ablation(self):
        first = parse_fixture_v2(serial_trace_v2(seed=7))
        second = parse_fixture_v2(serial_trace_v2(seed=987654321))
        self.assertNotEqual(first.run["pattern_hash"], second.run["pattern_hash"])
        self.assertEqual(first.kinds, batch.KINDS_V2)
        self.assertEqual(first.host["windows_build"], "26100")
        result = summarize(first)
        self.assertTrue(result["timer_control"]["passes"])
        values = result["contrasts"]
        for name, expected in (("branch", 10), ("branch_no_load", 6),
                               ("branchless", 2.5), ("adjusted", 7.5),
                               ("no_load_adjusted", 3.5),
                               ("load_minus_no_load", 4)):
            self.assertEqual(values[name]["paired_trimmed_mean_ticks_per_iteration"],
                             expected)
        self.assertEqual(result["split_half_no_load_trimmed_mean_ticks_per_iteration"],
                         (6, 6))

    def test_version_2_position_cycles_and_cli(self):
        self.assertEqual(interval([0] * 8 + [100] * 8, cycle_size=8), (0, 100))
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "v2.log"
            path.write_text(serial_trace_v2(seed=123), encoding="utf-8")
            output = StringIO()
            with patch.object(batch, "EXPECTED_ITERATIONS", 8), \
                 patch.object(batch, "EXPECTED_BLOCKS", 16), \
                 patch.object(sys, "argv", ["analyze_branch_batch.py", str(path)]), \
                 redirect_stdout(output):
                self.assertEqual(batch.main(), 0)
            self.assertIn("trace version 2; seed 123", output.getvalue())
            self.assertIn("within-run 8-block cycle bootstrap", output.getvalue())
            self.assertIn("branch_no_load", output.getvalue())
            self.assertIn("different addresses", output.getvalue())

    def test_version_2_seed_range_and_replay_validation(self):
        trace = serial_trace_v2(seed=7)
        for replacement in ("0", str(1 << 32)):
            with self.subTest(seed=replacement), self.assertRaisesRegex(
                    ValueError, "invalid version 2 seed"):
                parse_fixture_v2(trace.replace("seed=7,", f"seed={replacement},", 1))
        with self.assertRaisesRegex(ValueError, "pattern hash"):
            parse_fixture_v2(trace.replace("seed=7,", "seed=8,", 1))

    def test_version_2_requires_distinct_no_load_branch_address(self):
        trace = serial_trace_v2()
        with self.assertRaisesRegex(ValueError, "branch addresses coincide"):
            parse_fixture_v2(trace.replace("branch_no_load_addr=0x140001580",
                                           "branch_no_load_addr=0x140001560"))
        with self.assertRaisesRegex(ValueError, "missing no-load branch address"):
            parse_fixture_v2(trace.replace(
                "branch_no_load_addr=0x140001580,", ""))

    def test_version_2_requires_valid_host_metadata(self):
        trace = serial_trace_v2()
        with self.assertRaisesRegex(ValueError, "missing BATCH_HOST"):
            parse_fixture_v2(trace.replace(
                "BATCH_HOST,windows_build=26100,run_utc=20261030T010203Z\r\n", ""))
        with self.assertRaisesRegex(ValueError, "invalid Windows build"):
            parse_fixture_v2(trace.replace("windows_build=26100", "windows_build=foo"))
        with self.assertRaisesRegex(ValueError, "invalid BATCH_HOST timestamp"):
            parse_fixture_v2(trace.replace("20261030T010203Z", "20261330T010203Z"))

    def test_version_2_rejects_reordered_sample_with_recomputed_checksum(self):
        lines = serial_trace_v2().splitlines()
        first = 3 + len(batch.KINDS_V2)
        rows = [line.split(",") for line in lines[first:first + 2]]
        for position, row in enumerate(reversed(rows)):
            row[1] = str(first - 3 + position)
            row[3] = str(position)
            lines[first + position] = ",".join(row)
        indices = {kind: i for i, kind in enumerate(batch.KINDS_V2)}
        checksum = 0
        for line in lines:
            if line.startswith("BATCH_SAMPLE,"):
                _, index, block_id, position, kind, ticks = line.split(",")
                checksum += (int(index) + 1) * int(ticks) + int(block_id) + \
                    int(position) + indices[kind]
        end = next(i for i, line in enumerate(lines) if line.startswith("BATCH_END,"))
        lines[end] = f"BATCH_END,count=128,checksum={checksum},sink=16"
        with self.assertRaisesRegex(ValueError, "class order does not match seed"):
            parse_fixture_v2("\n".join(lines))

    def test_version_2_ablation_can_be_null_independently(self):
        result = summarize(parse_fixture_v2(serial_trace_v2(no_load_effect=0)))
        self.assertEqual(result["contrasts"]["branch_no_load"][
            "paired_trimmed_mean_ticks_per_iteration"], 0)
        self.assertEqual(result["contrasts"]["branch"][
            "paired_trimmed_mean_ticks_per_iteration"], 10)


if __name__ == "__main__":
    unittest.main()
