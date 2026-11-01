"""Offline replay and preregistered control gates for the B2-only pilot."""

from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import analyze_b2_calibration as cal  # noqa: E402


BLOCKS = 64  # Two complete 32-position cycles; hardware default is 1,280.
EPISODES = 4
RESET_CALLS = 256
TRAIN_CALLS = 256


def fixture(*, seed=431, fast_b_extra=0, oldsmall_extra=0,
            dose4_extra=12, dose8_extra=20, pause_extra=160,
            fixed_t1_extra=0, dose4_problem_stratum=None):
    """Generate a complete internally consistent trace with known contrasts.

    Offsets are batch totals: a 12-tick dose4 difference here equals three
    ticks per episode/probe, regardless of whether the probe has 1 or 16 calls.
    This is synthetic protocol data, never evidence of a physical effect.
    """
    order, schedule_hash = cal.replay_schedule(BLOCKS, seed)
    run = (
        f"B2CAL_RUN,version=2,blocks={BLOCKS},conditions=32,episodes={EPISODES},"
        f"reset_calls={RESET_CALLS},train_calls={TRAIN_CALLS},"
        "probe_lengths=1:16,warmup_blocks=32,"
        f"seed={seed},branch_addr=0x140001c80,live_addr=0x140023b00,"
        "fixed_addr=0x140023b40,mode_addr=0x140023b80,"
        "probe_addr=0x140023bc0,prelude_addr=0x140023c00,"
        "timer=lfence_rdtsc_lfence,"
        "protocol=b2_calibration_same_site_fixed_neutral,compiler=msvc_O2,"
        f"schedule_hash={schedule_hash},pattern_hash={cal.replay_pattern_hash()}"
    )
    rows = [
        "HOST_AFFINITY_CPU=0",
        "B2CAL_CPU,vendor=AuthenticAMD,signature=0x00b40f40,"
        "invariant_tsc=1,hypervisor=1",
        run,
    ]
    offsets = {
        "fast_a": 0, "fast_b": fast_b_extra,
        "oldsmall": oldsmall_extra, "dose4": dose4_extra,
        "dose8": dose8_extra, "pause": pause_extra,
    }
    checksum = 0
    for block, kinds in enumerate(order):
        for position, kind in enumerate(kinds):
            index = block * len(cal.KINDS) + position
            n = 16 if kind.endswith("_n16") else 1
            p = 1 if "_p1_" in kind else 0
            baseline = (2000 if n == 16 else 1000) + 20 * p + 3 * block
            if kind.startswith("fixed_"):
                ticks = baseline + 40 + (fixed_t1_extra if "_t1_" in kind else 0)
            else:
                timer = kind.split("_p", 1)[0]
                ticks = baseline + offsets[timer]
                if timer == "dose4" and (p, n) == dose4_problem_stratum:
                    ticks = baseline
            rows.append(f"B2CAL_SAMPLE,{index},{block},{position},{kind},{ticks}")
            checksum = (checksum + (index + 1) * ticks + block + position +
                        cal.KIND_INDEX[kind]) & cal.MAX_U64
    prelude_total = BLOCKS * 32 * EPISODES * RESET_CALLS // 2
    train_total = BLOCKS * 4 * EPISODES * TRAIN_CALLS
    # Each length has eight p=1 conditions: six timer variants plus two fixed.
    probe_total = BLOCKS * EPISODES * (8 * 1 + 8 * 16)
    sink = (prelude_total + train_total + probe_total) & (2**32 - 1)
    rows.extend((
        f"B2CAL_END,count={BLOCKS * 32},checksum={checksum},sink={sink},"
        f"prelude_total={prelude_total},train_total={train_total},"
        f"probe_total={probe_total}",
        "B2CAL_HOST,windows_build=26200,run_utc=20261101T120038Z",
        "B2CAL_BINARY,sha256=" + "a" * 64,
    ))
    return "\r\n".join(rows) + "\r\n"


def parse_fixture(value):
    with patch.object(cal, "EXPECTED_BLOCKS", BLOCKS), \
         patch.object(cal, "EPISODES", EPISODES):
        return cal.parse_trace(value)


def summarize_fixture(value):
    parsed = parse_fixture(value)
    actual_interval = cal.interval

    def fast_interval(values, **kwargs):
        return actual_interval(values, iterations=120, **kwargs)

    with patch.object(cal, "EPISODES", EPISODES), \
         patch.object(cal, "interval", fast_interval):
        return cal.summarize(parsed)


class B2CalibrationAnalysisTests(unittest.TestCase):
    def test_complete_schedule_and_positive_calibration(self):
        result = summarize_fixture(fixture())
        self.assertEqual(len(result["controls"]), 4)
        self.assertTrue(result["calibration_controls_pass"])
        self.assertEqual(result["selected_candidate"], "dose4")
        for control in result["controls"].values():
            self.assertTrue(control["fast_b"]["passes"])
            self.assertEqual(control["dose4"]["paired_trimmed_mean_ticks_per_probe"], 3)
            self.assertEqual(control["dose8"]["paired_trimmed_mean_ticks_per_probe"], 5)
            self.assertTrue(control["pause"]["passes"])
            self.assertTrue(control["fixed_neutral"]["passes"])

    def test_candidate_selection_depends_on_all_four_strata(self):
        result = summarize_fixture(fixture(dose4_problem_stratum=(1, 16)))
        self.assertEqual(result["selected_candidate"], "dose8")
        self.assertTrue(result["calibration_controls_pass"])
        self.assertFalse(result["controls"]["p1_n16"]["dose4"]["passes"])
        self.assertTrue(all(c["dose4"]["passes"] for key, c in
                            result["controls"].items() if key != "p1_n16"))

    def test_same_fast_path_and_fixed_training_controls_can_fail(self):
        for change, gate in (({"fast_b_extra": 8}, "fast_b"),
                             ({"fixed_t1_extra": 8}, "fixed_neutral")):
            with self.subTest(gate=gate):
                result = summarize_fixture(fixture(**change))
                self.assertFalse(result["calibration_controls_pass"])
                self.assertIsNone(result["selected_candidate"])
                self.assertTrue(any(not c[gate]["passes"] for c in result["controls"].values()))

    def test_checksum_schedule_and_architectural_totals_are_checked(self):
        data = fixture()
        rows = data.splitlines()
        sample = rows[3].rsplit(",", 1)
        rows[3] = f"{sample[0]},{int(sample[1]) + 1}"
        with self.assertRaisesRegex(ValueError, "checksum"):
            parse_fixture("\n".join(rows))
        with self.assertRaisesRegex(ValueError, "architectural output totals"):
            parse_fixture(data.replace("probe_total=34816", "probe_total=34817"))
        with self.assertRaises(ValueError):
            parse_fixture(data.replace("prelude_total=1048576,", ""))
        with self.assertRaisesRegex(ValueError, "schedule hash"):
            parse_fixture(data.replace("seed=431", "seed=432", 1))

    def test_rechecksumming_swapped_conditions_does_not_erase_order_check(self):
        rows = fixture().splitlines()
        first, second = rows[3].split(","), rows[4].split(",")
        first[4:], second[4:] = second[4:], first[4:]
        rows[3], rows[4] = ",".join(first), ",".join(second)
        checksum = 0
        for row in rows:
            if row.startswith("B2CAL_SAMPLE,"):
                _, index, block, position, kind, ticks = row.split(",")
                checksum += ((int(index) + 1) * int(ticks) + int(block) +
                             int(position) + cal.KIND_INDEX[kind])
        rows[-3] = rows[-3].replace(
            rows[-3].split("checksum=")[1].split(",")[0],
            str(checksum & cal.MAX_U64), 1)
        with self.assertRaisesRegex(ValueError, "order does not match seed"):
            parse_fixture("\n".join(rows))

    def test_cli_strict_flags_control_failure_without_discarding_trace(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "calibration.log"
            path.write_text(fixture(fast_b_extra=8), encoding="utf-8")
            actual_interval = cal.interval

            def fast_interval(values, **kwargs):
                return actual_interval(values, iterations=120, **kwargs)

            output = StringIO()
            with patch.object(cal, "EXPECTED_BLOCKS", BLOCKS), \
                 patch.object(cal, "EPISODES", EPISODES), \
                 patch.object(cal, "interval", fast_interval), \
                 patch.object(sys, "argv", ["analyze_b2_calibration.py", str(path), "--strict"]), \
                 redirect_stdout(output):
                self.assertEqual(cal.main(), 1)
            self.assertIn("INCONCLUSIVE", output.getvalue())


if __name__ == "__main__":
    unittest.main()
