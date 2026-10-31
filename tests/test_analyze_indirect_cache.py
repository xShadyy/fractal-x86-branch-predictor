"""Replayed schedule, raw episodes, receiver controls, and conservative gates."""

from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import analyze_indirect_cache as cache  # noqa: E402


BLOCKS = 44
EPISODES = 8
SEED = 1732072136


def fixture(*, corrupt_order=False, heated_skip=False, real_effect=True) -> str:
    orders, schedule_hash = cache.replay_schedule(BLOCKS, SEED, cache.WARMUP_BLOCKS)
    lines = [
        "HOST_AFFINITY_CPU=2",
        "ICACHE_CPU,vendor=AuthenticAMD,signature=0x00b40f40,clflush_bytes=64,"
        "invariant_tsc=1,hypervisor=1",
        f"ICACHE_RUN,version=1,blocks={BLOCKS},episodes={EPISODES},"
        f"prelude_calls={cache.PRELUDE_CALLS},train_calls={cache.TRAIN_CALLS},"
        f"probe_calls=1,warmup_blocks={cache.WARMUP_BLOCKS},seed={SEED},"
        "site_addr=0x140001000,target0_addr=0x140001080,"
        "target1_addr=0x140001100,sham_addr=0x140001200,"
        "data0_addr=0x180000000,data1_addr=0x180001000,"
        "slot_addr=0x180002000,timer=lfence_rdtsc_lfence,"
        "flush=clflush_mfence,protocol=indirect_target_cache_receiver,"
        f"compiler=msvc_O2,schedule_hash={schedule_hash}",
    ]
    checksum = 0
    index = 0
    for block, original_order in enumerate(orders):
        order = list(original_order)
        if corrupt_order and block == 2:
            order[0], order[1] = order[1], order[0]
        for position, kind in enumerate(order):
            p = int(kind[-1])
            if kind.startswith("hot_"):
                ticks = 40 + p
            elif kind.startswith("r_t"):
                t = int(kind[3])
                ticks = 50 if real_effect and t != p else 400
            elif heated_skip and kind == "skipr_t1_p0":
                ticks = 40
            else:
                ticks = 400
            episodes = [ticks + i % 3 for i in range(EPISODES)]
            checksum = ((checksum + index + 1 + block + position +
                         cache.KIND_INDEX[kind]) * cache.FNV_PRIME) & cache.MAX_U64
            for value in episodes:
                checksum = ((checksum ^ value) * cache.FNV_PRIME) & cache.MAX_U64
            lines.append(f"ICACHE_SAMPLE,{index},{block},{position},{kind}," +
                         ";".join(str(value) for value in episodes))
            index += 1
    sink = cache.expected_sink(BLOCKS, cache.WARMUP_BLOCKS, EPISODES,
                               cache.PRELUDE_CALLS, cache.TRAIN_CALLS)
    lines += [f"ICACHE_END,count={index},checksum={checksum},sink={sink}",
              "ICACHE_HOST,windows_build=26200,run_utc=20261031T120000Z",
              "ICACHE_BINARY,sha256=" + "a" * 64]
    return "\n".join(lines) + "\n"


class IndirectCacheTraceTests(unittest.TestCase):
    def parsed(self, content: str) -> cache.Trace:
        with patch.object(cache, "BLOCKS", BLOCKS), \
             patch.object(cache, "EPISODES", EPISODES):
            return cache.parse_trace(content)

    def test_complete_trace_and_paired_contrasts(self):
        trace = self.parsed(fixture())
        with patch.object(cache, "EPISODES", EPISODES):
            result = cache.summarize(trace)
        self.assertTrue(result["controls_pass"])
        self.assertEqual(len(trace.blocks), BLOCKS)
        self.assertGreater(result["contrasts"]["r_p0"]["mismatch_minus_match"], .9)
        self.assertGreater(result["contrasts"]["r_p1"]["mismatch_minus_match"], .9)
        self.assertGreater(result["contrasts"]["real_minus_f_p0"]["difference_of_differences"], .9)
        self.assertEqual(result["heldout_hit_rates"]["skipr_t1_p0"], 0.0)
        self.assertIn("physical PE audit pending", result["interpretation"])

    def test_train_matched_no_call_gate_catches_residual_heat(self):
        trace = self.parsed(fixture(heated_skip=True))
        with patch.object(cache, "EPISODES", EPISODES):
            result = cache.summarize(trace)
        self.assertFalse(result["controls_pass"])
        self.assertGreater(result["heldout_hit_rates"]["skipr_t1_p0"], .95)
        self.assertGreater(result["contrasts"]["r_p0"]["mismatch_minus_match"], .9)

    def test_null_result_can_pass_receiver_controls(self):
        trace = self.parsed(fixture(real_effect=False))
        with patch.object(cache, "EPISODES", EPISODES):
            result = cache.summarize(trace)
        self.assertTrue(result["controls_pass"])
        self.assertEqual(result["contrasts"]["r_p0"]["mismatch_minus_match"], 0)

    def test_reject_schedule_checksum_sink_and_target_layout(self):
        with self.assertRaisesRegex(ValueError, "randomized order"):
            self.parsed(fixture(corrupt_order=True))
        with self.assertRaisesRegex(ValueError, "checksum"):
            self.parsed(fixture().replace("r_t1_p0,50", "r_t1_p0,51", 1))
        with self.assertRaisesRegex(ValueError, "architectural sink"):
            content = fixture()
            sink = cache.expected_sink(BLOCKS, cache.WARMUP_BLOCKS, EPISODES,
                                       cache.PRELUDE_CALLS, cache.TRAIN_CALLS)
            self.parsed(content.replace(f"sink={sink}", f"sink={sink + 1}"))
        with self.assertRaisesRegex(ValueError, "separate I-cache lines"):
            self.parsed(fixture().replace("target1_addr=0x140001100",
                                          "target1_addr=0x1400010c0"))
        with self.assertRaisesRegex(ValueError, "incomplete"):
            self.parsed(fixture().split("ICACHE_BINARY,")[0])

    def test_cli_strict_returns_inconclusive_with_contrast_display(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "indirect-cache.log"
            path.write_text(fixture(heated_skip=True), encoding="utf-8")
            stream = StringIO()
            with patch.object(cache, "BLOCKS", BLOCKS), \
                 patch.object(cache, "EPISODES", EPISODES), \
                 patch.object(sys, "argv", ["analyze_indirect_cache.py", str(path), "--strict"]), \
                 redirect_stdout(stream):
                self.assertEqual(cache.main(), 1)
            self.assertIn("real train no-call t0/t1", stream.getvalue())
            self.assertIn("INCONCLUSIVE", stream.getvalue())
            self.assertIn("cache hits do not establish transient execution", stream.getvalue())


if __name__ == "__main__":
    unittest.main()
