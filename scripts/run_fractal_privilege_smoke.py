#!/usr/bin/env python3
"""Run K6 in QEMU TCG and validate actual privilege changes, never hardware timing."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import time
from analyze_fractal_privilege import analyze


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("assets",type=Path)
    p.add_argument("--qemu",default="qemu-system-x86_64")
    p.add_argument("--output",type=Path,required=True)
    p.add_argument("--firmware-dir",type=Path,help="optional QEMU firmware directory")
    p.add_argument("--timeout",type=int,default=180)
    a=p.parse_args();assets=a.assets.resolve()
    manifest=json.loads((assets/"manifest.json").read_text(encoding="utf-8-sig"))
    for name in ("fractal-k6.multiboot","k6-smoke.ext2"):
        if hashlib.sha256((assets/name).read_bytes()).hexdigest()!=manifest["files_sha256"][name]:
            p.error("boot artifact SHA256 mismatch: "+name)
    executable=shutil.which(a.qemu)
    if executable is None:p.error("QEMU x86_64 is required for the functional smoke; the physical boot kit is separate")
    a.output.mkdir(parents=True,exist_ok=False)
    command=[executable,"-machine","q35","-m","4096","-smp","1","-accel","tcg",
             "-cpu","max,vendor=AuthenticAMD","-kernel",str(assets/"fractal-k6.multiboot"),
             "-initrd",str(assets/"k6-smoke.ext2"),"-display","none","-monitor","none",
             "-serial","stdio","-nic","none","-no-reboot"]
    if a.firmware_dir:command[1:1]=["-L",str(a.firmware_dir.resolve())]
    log=a.output/"k6-smoke.log";complete=False
    with log.open("wb") as stream:
        process=subprocess.Popen(command,stdout=stream,stderr=subprocess.STDOUT)
        try:
            deadline=time.monotonic()+a.timeout
            while time.monotonic()<deadline:
                content=log.read_text(encoding="utf-8",errors="replace")
                if "FRACTAL_K6_OK: privilege transitions and complete trace collected" in content:
                    complete=True;break
                if process.poll() is not None:break
                time.sleep(.25)
        finally:
            if process.poll() is None:
                process.terminate()
                try:process.wait(timeout=5)
                except subprocess.TimeoutExpired:process.kill();process.wait(timeout=5)
    record=dict(command=command,qemu_version=subprocess.check_output([executable,"--version"],text=True).splitlines()[0],
                complete_marker=complete,scope="functional_only",log_sha256=hashlib.sha256(log.read_bytes()).hexdigest())
    (a.output/"invocation.json").write_text(json.dumps(record,indent=2)+"\n")
    result=analyze(log.read_text(encoding="utf-8",errors="strict"),development=True)
    (a.output/"analysis.json").write_text(json.dumps(result,indent=2)+"\n")
    print("K6 functional validation complete:",result["actual_cpl_counts"])
    print("Physical user-to-kernel influence remains unmeasured. Retain",a.output)


if __name__=="__main__":main()
