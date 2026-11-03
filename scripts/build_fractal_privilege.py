#!/usr/bin/env python3
"""Build isolated, pinned Fractal K6 smoke and physical payloads on Linux/WSL.

Requires git, GNU gcc/g++, make, objcopy/objdump/strings and mke2fs. An
existing upstream checkout is a read-only clone source, never the build tree.
"""
from __future__ import annotations
import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess

ROOT = Path(__file__).resolve().parents[1]
COMMON = "-Iinc -nostdlib -ffreestanding -fPIE -mcmodel=large -c -MMD -Wno-write-strings -Wno-address-of-packed-member -Wno-multichar -DBOARD_QEMU -DSOC_M1"
LINK = "-nostdlib -ffreestanding -fPIE -no-pie -Wl,--build-id=none"
FLAGS = ["-std=c11", "-O2", "-Wall", "-Wextra", "-Werror", "-ffreestanding",
         "-fno-builtin", "-fno-pie", "-no-pie", "-fno-stack-protector",
         "-mno-red-zone", "-mno-sse", "-fno-asynchronous-unwind-tables",
         "-fno-unwind-tables", "-nostdlib", "-static",
         "-Wl,-e,_start,-Ttext=0x400000,-z,max-page-size=0x1000,--build-id=none"]
SOURCES = ["programs/fractal_privilege_receiver.c", "programs/fractal_runtime.c",
           "programs/fractal_start.S", "programs/cpu_features.c"]


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--output",type=Path)
    p.add_argument("--upstream",type=Path,default=ROOT/"upstream/fractal")
    p.add_argument("--seed",type=int,default=2180673261)
    p.add_argument("--jobs",type=int,default=4)
    a=p.parse_args()
    if not 0<a.seed<2**32 or not 1<=a.jobs<=64:p.error("invalid seed or job count")
    pin=(ROOT/"UPSTREAM_FRACTAL_REVISION").read_text().strip()
    stamp=datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    out=(a.output or ROOT/"out"/("fractal-k6-"+stamp)).resolve()
    out.mkdir(parents=True,exist_ok=False)
    commands=[]
    with (out/"build.log").open("w") as log:
        def run(command,cwd=ROOT):
            command=[str(v) for v in command];commands.append(command)
            log.write(json.dumps(command)+"\n");log.flush()
            subprocess.run(command,cwd=cwd,stdout=log,stderr=subprocess.STDOUT,check=True)
        source=a.upstream.resolve()
        origin=str(source) if (source/".git").exists() else "https://github.com/jprx/fractal.git"
        tree=out/"fractal-source"
        run(["git","clone","--no-hardlinks","--no-checkout",origin,tree])
        run(["git","checkout","--detach",pin],tree)
        actual=subprocess.check_output(["git","rev-parse","HEAD"],cwd=tree,text=True).strip()
        if actual!=pin:raise ValueError("upstream pin mismatch")
        patch=ROOT/"patches/fractal-host-init-array.patch"
        run(["git","apply","--check",patch],tree)
        run(["git","apply",patch],tree)
        boot_patch=ROOT/"patches/fractal-multiboot2-k6.patch"
        run(["git","apply","--check",boot_patch],tree)
        run(["git","apply",boot_patch],tree)
        run(["make","-B",f"-j{a.jobs}","BOARD=QEMU","CC=gcc","CXX=g++","AS=gcc",
             "LD=g++","OBJDUMP=objdump","OBJCOPY=objcopy","STRINGS=strings",
             "CFLAGS_COMMON="+COMMON,"LDFLAGS1="+LINK,"x86"],tree)
        shutil.copy2(tree/"bin/fractal.release.qemu.x86_qemu",out/"fractal-k6.multiboot")
        shutil.copy2(tree/"bin/fractal.release.qemu.x86",out/"fractal-k6.elf64")
        shutil.copy2(tree/"LICENSE",out/"FRACTAL-LICENSE.txt")
        run(["git","archive","--format=tar.gz","--output",out/"fractal-upstream-source.tar.gz",pin],tree)
        shutil.copy2(patch,out/patch.name)
        shutil.copy2(boot_patch,out/boot_patch.name)
        for physical,name in ((0,"smoke"),(1,"physical")):
            fs=out/(name+"-fs");(fs/"bin").mkdir(parents=True)
            elf=out/("k6-"+name+".elf")
            run(["gcc",*FLAGS,"-I"+str(ROOT/"programs"),f"-DK6_PHYSICAL={physical}",
                 f"-DK6_SEED={a.seed}u",*(ROOT/s for s in SOURCES),"-o",elf])
            for file in ("utest","dash"):shutil.copy2(elf,fs/"bin"/file)
            image=out/("k6-"+name+".ext2")
            run(["mke2fs","-q","-F","-t","ext2","-b","4096","-I","128",
                 "-O","none,filetype","-m","0","-d",fs,image,"4096"])
        boot=out/"boot-files";(boot/"boot/grub").mkdir(parents=True)
        for name in ("fractal-k6.multiboot","k6-smoke.ext2","k6-physical.ext2"):
            shutil.copy2(out/name,boot/name)
        (boot/"boot/grub/grub.cfg").write_text('''set timeout=-1
set default=0
serial --unit=0 --speed=115200
terminal_input console serial
terminal_output console serial
menuentry "K6 functional smoke (emulation only)" {
    multiboot2 /fractal-k6.multiboot
    module2 /k6-smoke.ext2
    boot
}
menuentry "K6 physical Ryzen pilot: requires serial capture" {
    multiboot2 /fractal-k6.multiboot
    module2 /k6-physical.ext2
    boot
}
''')
    versions={name:subprocess.check_output([name,"--version"],text=True).splitlines()[0]
              for name in ("gcc","g++","make","objcopy")}
    source_files=SOURCES+["programs/fractal_runtime.h","programs/dependency_receiver_code.h",
                          "programs/dependency_receiver_layout.S","scripts/build_fractal_privilege.py",
                          "scripts/analyze_fractal_privilege.py","scripts/analyze_dependency_receiver.py",
                          "scripts/analyze_cache_probe.py","scripts/package_fractal_privilege_windows.ps1",
                          "scripts/run_fractal_privilege_smoke.py","programs/cpu_features.h",
                          "scripts/build_fractal_privilege_iso.py",
                          "scripts/dependency_receiver_contract.py","patches/fractal-host-init-array.patch",
                          "patches/fractal-multiboot2-k6.patch",
                          "protocols/FRACTAL_PRIVILEGE_K6.md","protocols/DEPENDENCY_RECEIVER_K5.md"]
    manifest=dict(schema=1,study="fractal_privilege_k6_v1",upstream_revision=pin,seed=a.seed,
                  build_utc=stamp,tools=versions,commands=commands,
                  source_hash_format="UTF-8 text with CRLF normalized to LF",
                  source_sha256={s:hashlib.sha256((ROOT/s).read_text(encoding="utf-8").encode("utf-8")).hexdigest() for s in source_files},
                  files_sha256={f.name:digest(f) for f in sorted(out.iterdir()) if f.is_file()},
                  physical_result="not_collected",smoke_scope="functional_only",
                  patch_reason=["collect host GCC .init_array constructors in Fractal .ctors",
                                "add bounded Multiboot2 module/ACPI handoff for UEFI, retaining Multiboot1 direct boot"])
    (out/"manifest.json").write_text(json.dumps(manifest,indent=2)+"\n")
    print(out)


if __name__=="__main__":main()
