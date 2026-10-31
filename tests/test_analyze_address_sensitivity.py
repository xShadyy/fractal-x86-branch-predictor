"""Synthetic integrity, randomized schedule and paired address-estimand tests."""

from pathlib import Path
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import analyze_address_sensitivity as addr  # noqa: E402


def fixture(*, seed=7, small_extra=16, interaction=True, corrupt=False):
    blocks = 68
    episodes = 4
    orders, schedule_hash = addr.replay_schedule(blocks, seed)
    rows = [
        "HOST_AFFINITY_CPU=0",
        "ADDR_CPU,vendor=AuthenticAMD,signature=0x00b40f40,"
        "invariant_tsc=1,hypervisor=1",
        "ADDR_RUN,version=1,blocks=68,episodes=4,prelude_calls=8,"
        "train_calls=8,probe_calls=1,warmup_blocks=34,seed=" + str(seed) +
        f",template_bytes=25,template_hash={addr._fnv_bytes(addr.BRANCH_TEMPLATE)},"
        "template_addr=0x140001c00,branch_jcc_offset=21,"
        "target_addr=0x10000100,same4k_addr=0x10001100,"
        "offset128_addr=0x10001180,sham_addr=0x10003000,"
        "mode_addr=0x10004000,live_addr=0x10005000,fixed_addr=0x10006000,"
        "timer=lfence_rdtsc_lfence,protocol=rx_clone_address_sensitivity,"
        f"compiler=msvc_O2,schedule_hash={schedule_hash}",
    ]
    checksum = 0
    for block, order in enumerate(orders):
        for position, kind in enumerate(order):
            index = block * len(addr.KINDS) + position
            ticks = 5000 + block * 7 + int(kind[-1]) * 100
            if kind.startswith(("r_", "f_")):
                arm, site, t, p = kind.split("_")
                train, probe = int(t[1:]), int(p[1:])
                if train != probe:
                    if arm == "f":
                        ticks += 2
                    elif interaction:
                        ticks += {"target": 60, "same4k": 32,
                                  "offset128": 12}[site]
                    else:
                        ticks += 2
            elif kind.startswith("s_t"):
                train, probe = int(kind[3]), int(kind[-1])
                if train != probe:
                    ticks += 3
            else:
                timer = kind.split("_p")[0]
                ticks += {"fast": 0, "small": small_extra,
                          "pause": 400}[timer]
            recorded = ticks
            if corrupt and block == 10 and kind == "r_same4k_t1_p0":
                ticks += 1
            rows.append(f"ADDR_SAMPLE,{index},{block},{position},{kind},{ticks}")
            checksum = (checksum + (index + 1) * recorded + block +
                        position + addr.KIND_INDEX[kind]) & addr.MAX_U64
    with patch.object(addr, "BLOCKS", blocks), \
         patch.object(addr, "EPISODES", episodes), \
         patch.object(addr, "PRELUDE_CALLS", 8), \
         patch.object(addr, "TRAIN_CALLS", 8):
        sink = addr.expected_sink()
    rows += [
        f"ADDR_END,count={blocks * len(addr.KINDS)},checksum={checksum},sink={sink}",
        "ADDR_HOST,windows_build=26200,run_utc=20261031T195000Z",
        "ADDR_BINARY,sha256=" + "a" * 64,
    ]
    return "\r\n".join(rows) + "\r\n"


def parse_fixture(content):
    with patch.object(addr, "BLOCKS", 68), \
         patch.object(addr, "EPISODES", 4), \
         patch.object(addr, "PRELUDE_CALLS", 8), \
         patch.object(addr, "TRAIN_CALLS", 8):
        return addr.parse_trace(content)


def summarize_fixture(trace):
    with patch.object(addr, "EPISODES", 4):
        return addr.summarize(trace)


class AddressTests(unittest.TestCase):
    def test_complete_design_and_paired_interaction(self):
        trace = parse_fixture(fixture())
        result = summarize_fixture(trace)
        self.assertEqual(len(trace.blocks), 68)
        self.assertEqual(len(addr.KINDS), 34)
        self.assertEqual(result["site_outcomes"]["same4k_p0"][
            "real_minus_fixed"]["paired_trimmed_mean_ticks_per_probe"], 7.5)
        self.assertEqual(result["address_interactions"][
            "same4k_minus_offset128_p0"][
                "paired_trimmed_mean_ticks_per_probe"], 5.0)
        self.assertEqual(result["address_interactions"][
            "target_minus_same4k_p1"]["paired_trimmed_mean_ticks_per_probe"], 7.0)
        self.assertTrue(result["timer_controls_pass"])
        self.assertTrue(result["fixed_all_within_tolerance"])

    def test_null_address_interaction_is_valid_data(self):
        result = summarize_fixture(parse_fixture(fixture(interaction=False)))
        self.assertEqual(result["address_interactions"][
            "same4k_minus_offset128_p0"][
                "paired_trimmed_mean_ticks_per_probe"], 0)
        self.assertEqual(len(result["site_outcomes"]), 8)  # six site/outcome + two sham

    def test_control_failure_retains_outcomes(self):
        result = summarize_fixture(parse_fixture(fixture(small_extra=0)))
        self.assertFalse(result["timer_controls_pass"])
        self.assertEqual(len(result["address_interactions"]), 6)
        self.assertTrue(all(c["pause_pass"] for c in
                            result["timer_controls"].values()))

    def test_checksum_seed_template_and_address_tampering(self):
        with self.assertRaisesRegex(ValueError, "checksum"):
            parse_fixture(fixture(corrupt=True))
        original = fixture()
        with self.assertRaisesRegex(ValueError, "schedule hash"):
            parse_fixture(original.replace("schedule_hash=", "schedule_hash=1", 1))
        with self.assertRaisesRegex(ValueError, "branch template"):
            parse_fixture(original.replace(
                f"template_hash={addr._fnv_bytes(addr.BRANCH_TEMPLATE)}",
                "template_hash=0", 1))
        with self.assertRaisesRegex(ValueError, "placement"):
            parse_fixture(original.replace("same4k_addr=0x10001100",
                                           "same4k_addr=0x10001200", 1))
        with self.assertRaisesRegex(ValueError, "incomplete"):
            parse_fixture(original.split("ADDR_BINARY")[0])

    def test_seed_replay_rejects_reordered_rows_even_if_rechecksummed(self):
        rows = fixture().splitlines()
        first, second = rows[3].split(","), rows[4].split(",")
        first[4], second[4] = second[4], first[4]
        rows[3], rows[4] = ",".join(first), ",".join(second)
        checksum = 0
        for row in rows:
            if row.startswith("ADDR_SAMPLE,"):
                _, index, block, position, kind, ticks = row.split(",")
                checksum = (checksum + (int(index) + 1) * int(ticks) +
                            int(block) + int(position) +
                            addr.KIND_INDEX[kind]) & addr.MAX_U64
        sink = rows[-3].split("sink=")[1]
        rows[-3] = (f"ADDR_END,count={68 * len(addr.KINDS)},"
                    f"checksum={checksum},sink={sink}")
        with self.assertRaisesRegex(ValueError, "order mismatch"):
            parse_fixture("\n".join(rows))


if __name__ == "__main__":
    unittest.main()
