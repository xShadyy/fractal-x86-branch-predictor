"""Recorded guest transitions, evidence corruption, and same-domain gating."""
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import analyze_fractal_privilege as k6


class FractalPrivilegeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.trace = (ROOT / "results/k5-k6-development/k6-qemu-smoke.log").read_text()

    def test_recorded_guest_really_changes_cpl_at_same_measured_pc(self):
        result = k6.analyze(self.trace, development=True)
        self.assertEqual(result["actual_cpl_counts"], {"3->3":96,"0->0":96,"3->0":96,"0->3":96})
        self.assertTrue(result["same_measured_instruction_address_verified"])
        self.assertFalse(result["hardware_eligible"])
        self.assertIsNone(result["numerical_outcomes"])
        self.assertFalse(result["physical_mechanism_proven"])

    def test_bios_and_uefi_multiboot2_recordings_validate(self):
        for name in ("k6-bios-mb2-smoke.log","k6-uefi-mb2-smoke.log"):
            result=k6.analyze((ROOT/"results/k5-k6-development"/name).read_text(),development=True)
            self.assertEqual(result["samples"],384)
            self.assertFalse(result["hardware_eligible"])

    def test_emulation_cannot_be_promoted_to_physical_result(self):
        with self.assertRaisesRegex(ValueError,"development"):
            k6.analyze(self.trace)
        with self.assertRaisesRegex(ValueError,"platform"):
            k6.analyze(self.trace.replace("scope=development_only","scope=physical_pilot"),development=True)

    def test_actual_cpl_and_instruction_address_corruption_rejected(self):
        lines=self.trace.splitlines()
        index=next(i for i,s in enumerate(lines) if s.startswith("K6_SAMPLE,") and ",uk," in s and ",255," not in s)
        for column,value in ((17,"0"),(18,"3"),(19,"3"),(20,"0xdead"),(21,"0xbeef")):
            rows=lines.copy();c=rows[index].split(",");c[column]=value;rows[index]=",".join(c)
            with self.assertRaisesRegex(ValueError,"privilege|address"):
                k6.analyze("\n".join(rows),development=True)

    def test_incomplete_or_corrupted_collection_rejected(self):
        for before,after in (("FRACTAL_K6_OK: privilege transitions and complete trace collected",""),
                             ("architecture_errors=0","architecture_errors=1"),
                             ("count=384","count=383"),
                             ("hex=31c0","hex=00c0"),
                             ("K6_SAMPLE,0,","K6_SAMPLE,1,")):
            with self.subTest(before=before),self.assertRaises(ValueError):
                k6.analyze(self.trace.replace(before,after,1),development=True)

    def test_user_to_kernel_claim_requires_same_domain_positive_controls(self):
        def outcome(signature=True, controls=True):
            return dict(apparatus_controls_pass=controls,gates={},thresholds={},heldout_hit_rates={},
                        heldout_decoy_hit_rates={},outcomes={},numerical_signature_detected=signature)
        for bad_pair in (None,"uu","kk","uk"):
            items=[outcome(signature=p!=bad_pair,controls=p!=bad_pair) for p in k6.PAIRS]
            with patch.object(k6.k5,"summarize",side_effect=items):
                _,eligible,signature=k6.physical_outcomes({},dict(blocks="256",episodes="8"),dict.fromkeys(k6.PAIRS,[]))
            self.assertEqual(eligible,bad_pair is None)
            self.assertEqual(signature,bad_pair is None)

    def test_full_physical_protocol_with_synthetic_timings_exercises_outcome_path(self):
        # Generated values test analysis only. They are never saved or reported
        # as collected evidence, and cannot establish a hardware observation.
        header=[s for s in self.trace.splitlines() if s.startswith(("K6_CPU,","K6_RUN,","K6_CODE,"))]
        header[0]="K6_CPU,vendor=AuthenticAMD,signature=0x00b40f40,clflush_bytes=64,invariant_tsc=1,rdtscp=1,hypervisor=0"
        header[1]=header[1].replace("scope=development_only","scope=physical_pilot").replace("blocks=2,episodes=1,warmup=1,prelude=8,train=8,","blocks=256,episodes=8,warmup=16,prelude=128,train=256,")
        checksum=0;event=k6.k5.FNV_OFFSET;lines=header
        for i,plan in enumerate(k6.replay(256,8,16,2180673261)):
            block,pair,mode,round_number,position,kind,tag0,tag1,decoy,order=plan
            kind_id=k6.k5.KINDS.index(kind);p,member=divmod(kind_id,8)
            t=member&1 if member<4 else (1-p if member==7 else p)
            hot=member in (4,6) or (member in (0,1) and t!=p and mode=="plain")
            ticks=80 if hot else 500;probed=member in (0,1,6,7)
            probe=1+p if member in (0,1,7) else (2-p if member==6 else 0)
            sender,receiver=k6.CPL[pair]
            lines.append(f"K6_SAMPLE,{i},{block},{pair},{mode},{round_number},{position},{kind},{tag0},{tag1},{decoy},{order},{ticks},500,192,{256*(1+t)},{probe},{sender},{receiver},{receiver if probed else 255},0x40b571,{'0x40b571' if probed else '0x0'}")
            checksum=k6.k5.mix(k6.k5.mix(k6.k5.mix(checksum,i+1),ticks),500)
            event=k6.k5.mix(event,k6.PAIRS.index(pair)*65536+k6.k5.MODES.index(mode)*4096+kind_id*16+round_number)
            event=k6.k5.mix(event,tag0*65536+tag1*256+decoy*2+order)
        lines.extend((f"K6_END,count=393216,checksum={checksum},event_hash={event},architecture_errors=0,observed_cr4=0x220",
                      "FRACTAL_K6_OK: privilege transitions and complete trace collected"))
        result=k6.analyze("\n".join(lines))
        self.assertTrue(result["hardware_eligible"])
        self.assertTrue(result["user_to_kernel_numerical_signature_detected"])
        self.assertFalse(result["physical_mechanism_proven"])
        self.assertTrue(all(len(s["gates"])==88 for s in result["numerical_outcomes"].values()))


if __name__=="__main__":unittest.main()
