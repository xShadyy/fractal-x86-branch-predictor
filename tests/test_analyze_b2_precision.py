"""Offline paired-schedule and frozen-gate checks for the B2 v3 diagnostic."""

from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import analyze_b2_precision as prec  # noqa: E402


BLOCKS = 64  # Two 32-block pair-position cycles; physical protocol uses 2,560.
EPISODES = 4


def fixture(*, seed=2357, fast_b_extra=0, dose4_extra=12,
            pause_extra=160, fixed_t1_extra=0,
            dose4_problem_stratum=None):
    """A complete synthetic trace; source offsets do not represent hardware."""
    orders, schedule_hash = prec.replay_schedule(BLOCKS, seed)
    run = (
        f"B2PREC_RUN,version=3,blocks={BLOCKS},conditions=32,pairs=16,"
        f"episodes={EPISODES},reset_calls=256,train_calls=256,"
        f"probe_lengths=1:16,warmup_blocks=32,seed={seed},"
        "branch_addr=0x140001f70,live_addr=0x140023b00,"
        "fixed_addr=0x140023b40,mode_addr=0x140023b80,"
        "probe_addr=0x140023bc0,prelude_addr=0x140023c00,"
        "timer=lfence_rdtsc_lfence,"
        "protocol=b2_adjacent_pairs_precision,compiler=msvc_O2,"
        f"schedule_hash={schedule_hash},pattern_hash={prec.replay_pattern_hash()}"
    )
    rows = [
        "HOST_AFFINITY_CPU=0",
        "B2PREC_CPU,vendor=AuthenticAMD,signature=0x00b40f40,"
        "invariant_tsc=1,hypervisor=1",
        run,
    ]
    offsets = {"fast_a": 0, "fast_b": fast_b_extra, "fast_c": 0,
               "dose4": dose4_extra, "fast_d": 0, "pause": pause_extra}
    checksum = 0
    for block, kinds in enumerate(orders):
        for position, kind in enumerate(kinds):
            index = block * len(prec.KINDS) + position
            n = 16 if kind.endswith("_n16") else 1
            p = 1 if "_p1_" in kind else 0
            # Pair-specific drift cancels in adjacent control differences.
            baseline = (2000 if n == 16 else 1000) + 20 * p + 3 * block + 13 * (position // 2)
            name = kind.split("_p", 1)[0]
            if name.startswith("fixed_"):
                ticks = baseline + 40 + (fixed_t1_extra if name == "fixed_t1" else 0)
            else:
                ticks = baseline + offsets[name]
                if name == "dose4" and (p, n) == dose4_problem_stratum:
                    ticks = baseline
            rows.append(f"B2PREC_SAMPLE,{index},{block},{position},{kind},{ticks}")
            checksum = (checksum + (index + 1) * ticks + block + position +
                        prec.KIND_INDEX[kind]) & prec.MAX_U64
    prelude = BLOCKS * 32 * EPISODES * 256 // 2
    training = BLOCKS * 4 * EPISODES * 256
    probing = BLOCKS * 8 * EPISODES * 17
    sink = (prelude + training + probing) & (2**32 - 1)
    rows.extend((
        f"B2PREC_END,count={BLOCKS * 32},checksum={checksum},sink={sink},"
        f"prelude_total={prelude},train_total={training},probe_total={probing}",
        "B2PREC_HOST,windows_build=26200,run_utc=20261101T160038Z",
        "B2PREC_BINARY,sha256=" + "a" * 64,
    ))
    return "\r\n".join(rows) + "\r\n"


def parse_fixture(data):
    with patch.object(prec, "EXPECTED_BLOCKS", BLOCKS), \
         patch.object(prec, "EPISODES", EPISODES):
        return prec.parse_trace(data)


def summarize_fixture(data):
    parsed = parse_fixture(data)
    original_interval = prec.interval

    def quick_interval(values, **kwargs):
        return original_interval(values, iterations=120, **kwargs)

    with patch.object(prec, "EPISODES", EPISODES), \
         patch.object(prec, "interval", quick_interval):
        return prec.summarize(parsed)


class B2PrecisionTests(unittest.TestCase):
    def test_pair_schedule_is_adjacent_and_position_balanced(self):
        orders, actual_hash = prec.replay_schedule(BLOCKS, 2357)
        self.assertEqual(len(orders), BLOCKS)
        self.assertGreater(actual_hash, 0)
        for order in orders:
            self.assertEqual(set(order), set(prec.KINDS))
            for pos in range(0, 32, 2):
                self.assertEqual(prec.KIND_INDEX[order[pos]] // 2,
                                 prec.KIND_INDEX[order[pos + 1]] // 2)
        for name in prec.KINDS:
            self.assertEqual([sum(row[pos] == name for row in orders[:32])
                              for pos in range(32)], [1] * 32)
            self.assertEqual([sum(row[pos] == name for row in orders[32:])
                              for pos in range(32)], [1] * 32)

    def test_complete_trace_and_all_frozen_gates_pass(self):
        result = summarize_fixture(fixture())
        self.assertTrue(result["precision_controls_pass"])
        self.assertEqual(len(result["controls"]), 4)
        for control in result["controls"].values():
            self.assertEqual(control["dose4"]["paired_trimmed_mean_ticks_per_probe"], 3)
            self.assertEqual(control["pause"]["paired_trimmed_mean_ticks_per_probe"], 40)
            self.assertTrue(all(row["passes"] for row in control.values()))

    def test_one_stratum_dose_failure_does_not_disappear(self):
        result = summarize_fixture(fixture(dose4_problem_stratum=(1, 16)))
        self.assertFalse(result["precision_controls_pass"])
        self.assertFalse(result["controls"]["p1_n16"]["dose4"]["passes"])
        self.assertTrue(all(row["dose4"]["passes"] for key, row in
                            result["controls"].items() if key != "p1_n16"))

    def test_fast_identity_and_fixed_neutral_fail_without_re_gating(self):
        for change, gate in (({"fast_b_extra": 8}, "fast_b"),
                             ({"fixed_t1_extra": 8}, "fixed_neutral")):
            with self.subTest(gate=gate):
                result = summarize_fixture(fixture(**change))
                self.assertFalse(result["precision_controls_pass"])
                self.assertTrue(any(not row[gate]["passes"] for row in
                                    result["controls"].values()))

    def test_schedule_and_architectural_tampering_rejected(self):
        data = fixture()
        with self.assertRaisesRegex(ValueError, "schedule hash"):
            parse_fixture(data.replace("seed=2357", "seed=2358", 1))
        with self.assertRaisesRegex(ValueError, "architectural output totals"):
            parse_fixture(data.replace("probe_total=34816", "probe_total=34817"))
        with self.assertRaisesRegex(ValueError, "END fields"):
            parse_fixture(data.replace("prelude_total=1048576,", ""))
        rows = data.splitlines()
        first = rows[3].rsplit(",", 1)
        rows[3] = f"{first[0]},{int(first[1]) + 1}"
        with self.assertRaisesRegex(ValueError, "checksum"):
            parse_fixture("\n".join(rows))

    def test_rechecksummed_condition_swap_fails_schedule(self):
        rows = fixture().splitlines()
        first, second = rows[3].split(","), rows[4].split(",")
        first[4:], second[4:] = second[4:], first[4:]
        rows[3], rows[4] = ",".join(first), ",".join(second)
        checksum = 0
        for row in rows:
            if row.startswith("B2PREC_SAMPLE,"):
                _, index, block, position, kind, ticks = row.split(",")
                checksum += ((int(index) + 1) * int(ticks) + int(block) +
                             int(position) + prec.KIND_INDEX[kind])
        rows[-3] = rows[-3].replace(rows[-3].split("checksum=")[1].split(",")[0],
                                   str(checksum & prec.MAX_U64), 1)
        with self.assertRaisesRegex(ValueError, "order does not match seed"):
            parse_fixture("\n".join(rows))

    def test_strict_cli_retains_failed_control_trace(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "precision.log"
            path.write_text(fixture(fast_b_extra=8), encoding="utf-8")
            original_interval = prec.interval

            def quick_interval(values, **kwargs):
                return original_interval(values, iterations=120, **kwargs)

            output = StringIO()
            with patch.object(prec, "EXPECTED_BLOCKS", BLOCKS), \
                 patch.object(prec, "EPISODES", EPISODES), \
                 patch.object(prec, "interval", quick_interval), \
                 patch.object(sys, "argv", ["analyze_b2_precision.py", str(path), "--strict"]), \
                 redirect_stdout(output):
                self.assertEqual(prec.main(), 1)
            self.assertIn("INCONCLUSIVE", output.getvalue())


if __name__ == "__main__":
    unittest.main()
