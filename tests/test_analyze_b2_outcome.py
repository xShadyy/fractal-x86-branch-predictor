"""Offline trace replay, control gates, and a preselected B2 v4 endpoint."""

from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import analyze_b2_outcome as outcome  # noqa: E402


BLOCKS = 80  # Two complete 40-position cycles; hardware default is 3,200.
EPISODES = 4


def fixture(*, seed=2357, real_t1_extra=16, real_stratum=(0, 1),
            fixed_t1_extra=0, fast_b_extra=0, dose4_extra=12,
            pause_extra=160, dose4_problem_stratum=None):
    """Internally consistent synthetic trace, never physical CPU evidence.

    Timer offsets are totals across four episodes; a +16 offset yields a
    +4-tick-per-probe adjusted training association in the chosen stratum.
    """
    orders, schedule_hash = outcome.replay_schedule(BLOCKS, seed)
    run = (
        f"B2OUT_RUN,version=4,blocks={BLOCKS},conditions=40,pairs=20,"
        f"episodes={EPISODES},reset_calls=256,train_calls=256,"
        f"probe_lengths=1:16,warmup_blocks=40,seed={seed},"
        "branch_addr=0x140001f70,live_addr=0x140023b00,"
        "fixed_addr=0x140023b40,mode_addr=0x140023b80,"
        "probe_addr=0x140023bc0,prelude_addr=0x140023c00,"
        "timer=lfence_rdtsc_lfence,"
        "protocol=b2_adjacent_same_site_outcome,compiler=msvc_O2,"
        f"schedule_hash={schedule_hash},pattern_hash={outcome.replay_pattern_hash()}"
    )
    rows = [
        "HOST_AFFINITY_CPU=0",
        "B2OUT_CPU,vendor=AuthenticAMD,signature=0x00b40f40,"
        "invariant_tsc=1,hypervisor=1",
        run,
    ]
    offsets = {"fast_a": 0, "fast_b": fast_b_extra, "fast_c": 0,
               "dose4": dose4_extra, "fast_d": 0, "pause": pause_extra}
    checksum = 0
    for block, kinds in enumerate(orders):
        for position, kind in enumerate(kinds):
            index = block * len(outcome.KINDS) + position
            n = 16 if kind.endswith("_n16") else 1
            p = 1 if "_p1_" in kind else 0
            name = kind.split("_p", 1)[0]
            # Adjacent pairs share this artificial pair-slot drift.
            baseline = (2000 if n == 16 else 1000) + 20 * p + 3 * block + 13 * (position // 2)
            if name == "fixed_t1":
                ticks = baseline + fixed_t1_extra
            elif name == "real_t1":
                ticks = baseline + (real_t1_extra if (p, n) == real_stratum else 0)
            else:
                ticks = baseline + offsets.get(name, 0)
                if name == "dose4" and (p, n) == dose4_problem_stratum:
                    ticks = baseline
            rows.append(f"B2OUT_SAMPLE,{index},{block},{position},{kind},{ticks}")
            checksum = (checksum + (index + 1) * ticks + block + position +
                        outcome.KIND_INDEX[kind]) & outcome.MAX_U64
    prelude = BLOCKS * 40 * EPISODES * 256 // 2
    training = BLOCKS * 8 * EPISODES * 256
    probing = BLOCKS * 10 * EPISODES * 17
    sink = (prelude + training + probing) & (2**32 - 1)
    rows.extend((
        f"B2OUT_END,count={BLOCKS * 40},checksum={checksum},sink={sink},"
        f"prelude_total={prelude},train_total={training},probe_total={probing}",
        "B2OUT_HOST,windows_build=26200,run_utc=20261101T170038Z",
        "B2OUT_BINARY,sha256=" + "a" * 64,
    ))
    return "\r\n".join(rows) + "\r\n"


def parse_fixture(data):
    with patch.object(outcome, "EXPECTED_BLOCKS", BLOCKS), \
         patch.object(outcome, "EPISODES", EPISODES):
        return outcome.parse_trace(data)


def summarize_fixture(data):
    parsed = parse_fixture(data)
    real_interval = outcome.interval

    def quick_interval(values, **kwargs):
        return real_interval(values, iterations=120, **kwargs)

    with patch.object(outcome, "EPISODES", EPISODES), \
         patch.object(outcome, "interval", quick_interval):
        return outcome.summarize(parsed)


class B2OutcomeTests(unittest.TestCase):
    def test_all_pairs_adjacent_and_balanced_after_seeded_warmup(self):
        orders, schedule_hash = outcome.replay_schedule(BLOCKS, 2357)
        self.assertGreater(schedule_hash, 0)
        self.assertEqual(len(orders), BLOCKS)
        for order in orders:
            self.assertEqual(set(order), set(outcome.KINDS))
            for pos in range(0, 40, 2):
                self.assertEqual(outcome.KIND_INDEX[order[pos]] // 2,
                                 outcome.KIND_INDEX[order[pos + 1]] // 2)
        for name in outcome.KINDS:
            for cycle in (orders[:40], orders[40:]):
                self.assertEqual([sum(row[pos] == name for row in cycle)
                                  for pos in range(40)], [1] * 40)

    def test_complete_trace_primary_adjusted_effect_and_secondary_reporting(self):
        result = summarize_fixture(fixture())
        self.assertTrue(result["apparatus_controls_pass"])
        self.assertTrue(result["primary_practical_association"])
        self.assertEqual(result["primary_direction"], "positive")
        self.assertEqual(result["primary_endpoint"], "F_p0_n1")
        self.assertEqual(len(result["outcomes"]), 4)
        self.assertEqual(result["outcomes"]["p0_n1"]["D_real"]["paired_trimmed_mean_ticks_per_probe"], 4)
        self.assertEqual(result["outcomes"]["p0_n1"]["F"]["paired_trimmed_mean_ticks_per_probe"], 4)
        self.assertEqual(result["outcomes"]["p1_n1"]["F"]["paired_trimmed_mean_ticks_per_probe"], 0)
        self.assertEqual(result["length_interactions"]["p0_n1_minus_n16"]["paired_trimmed_mean_ticks_per_probe"], 4)
        self.assertTrue(all(gate["passes"] for row in result["controls"].values()
                            for gate in row.values()))

    def test_valid_null_and_negative_primary_are_retained(self):
        null = summarize_fixture(fixture(real_t1_extra=0))
        self.assertTrue(null["apparatus_controls_pass"])
        self.assertFalse(null["primary_practical_association"])
        self.assertEqual(null["primary_direction"], "none")
        small = summarize_fixture(fixture(real_t1_extra=2))
        self.assertEqual(small["outcomes"]["p0_n1"]["F"]["paired_trimmed_mean_ticks_per_probe"], 0.5)
        self.assertFalse(small["primary_practical_association"])
        negative = summarize_fixture(fixture(real_t1_extra=-16))
        self.assertTrue(negative["primary_practical_association"])
        self.assertEqual(negative["primary_direction"], "negative")

    def test_fixed_comparator_adjustment_and_gate_withholding(self):
        # Matched small real/fixed effects cancel; both remain within ±1.
        result = summarize_fixture(fixture(real_t1_extra=2, fixed_t1_extra=2))
        self.assertTrue(result["apparatus_controls_pass"])
        self.assertEqual(result["outcomes"]["p0_n1"]["F"]["paired_trimmed_mean_ticks_per_probe"], 0)
        self.assertFalse(result["primary_practical_association"])
        failing = summarize_fixture(fixture(fixed_t1_extra=8))
        self.assertFalse(failing["apparatus_controls_pass"])
        self.assertIsNone(failing["primary_practical_association"])
        self.assertIsNone(failing["primary_direction"])

    def test_one_stratum_timer_failure_blocks_primary_classification(self):
        result = summarize_fixture(fixture(dose4_problem_stratum=(1, 16)))
        self.assertFalse(result["apparatus_controls_pass"])
        self.assertFalse(result["controls"]["p1_n16"]["dose4"]["passes"])
        self.assertIsNone(result["primary_practical_association"])
        self.assertEqual(result["outcomes"]["p0_n1"]["F"]["paired_trimmed_mean_ticks_per_probe"], 4)

    def test_rechecksummed_swap_still_fails_seed_schedule(self):
        rows = fixture().splitlines()
        first, second = rows[3].split(","), rows[4].split(",")
        first[4:], second[4:] = second[4:], first[4:]
        rows[3], rows[4] = ",".join(first), ",".join(second)
        checksum = 0
        for row in rows:
            if row.startswith("B2OUT_SAMPLE,"):
                _, index, block, position, kind, ticks = row.split(",")
                checksum += ((int(index) + 1) * int(ticks) + int(block) +
                             int(position) + outcome.KIND_INDEX[kind])
        rows[-3] = rows[-3].replace(rows[-3].split("checksum=")[1].split(",")[0],
                                   str(checksum & outcome.MAX_U64), 1)
        with self.assertRaisesRegex(ValueError, "order does not match seed"):
            parse_fixture("\n".join(rows))

    def test_reject_tampered_hash_architecture_and_checksum(self):
        data = fixture()
        with self.assertRaisesRegex(ValueError, "schedule hash"):
            parse_fixture(data.replace("seed=2357", "seed=2358", 1))
        with self.assertRaisesRegex(ValueError, "architectural output totals"):
            parse_fixture(data.replace("probe_total=54400", "probe_total=54401"))
        with self.assertRaisesRegex(ValueError, "END fields"):
            parse_fixture(data.replace("prelude_total=1638400,", ""))
        rows = data.splitlines()
        head, ticks = rows[3].rsplit(",", 1)
        rows[3] = f"{head},{int(ticks) + 1}"
        with self.assertRaisesRegex(ValueError, "checksum"):
            parse_fixture("\n".join(rows))

    def test_strict_exits_for_gates_not_for_a_null_outcome(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "outcome.log"
            real_interval = outcome.interval

            def quick_interval(values, **kwargs):
                return real_interval(values, iterations=120, **kwargs)

            with patch.object(outcome, "EXPECTED_BLOCKS", BLOCKS), \
                 patch.object(outcome, "EPISODES", EPISODES), \
                 patch.object(outcome, "interval", quick_interval), \
                 patch.object(sys, "argv", ["analyze_b2_outcome.py", str(path), "--strict"]), \
                 redirect_stdout(StringIO()):
                path.write_text(fixture(real_t1_extra=0), encoding="utf-8")
                self.assertEqual(outcome.main(), 0)
                path.write_text(fixture(fast_b_extra=8), encoding="utf-8")
                self.assertEqual(outcome.main(), 1)


if __name__ == "__main__":
    unittest.main()
