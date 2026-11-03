#!/usr/bin/env python3
"""Create BIOS and UEFI GRUB ISO files from a completed K6 build, without disk I/O.

Requires installed GRUB rescue tools, i386-pc and x86_64-efi modules, xorriso,
and mtools. --grub-root and --label-font support isolated extracted toolchains.
"""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("assets",type=Path)
    p.add_argument("--grub-mkrescue",default="grub-mkrescue")
    p.add_argument("--xorriso",default="xorriso")
    p.add_argument("--grub-root",type=Path,default=Path("/usr/lib/grub"))
    p.add_argument("--label-font",type=Path)
    a=p.parse_args();assets=a.assets.resolve()
    manifest=json.loads((assets/"manifest.json").read_text());commands=[]
    for platform,kind in (("i386-pc","bios"),("x86_64-efi","uefi")):
        image=assets/("k6-"+kind+".iso")
        if image.exists():p.error("refusing to replace existing ISO: "+str(image))
        command=[a.grub_mkrescue,"-d",str(a.grub_root.resolve()/platform),"--xorriso="+a.xorriso,
                 "--fonts=","--locales=","--themes=","-o",str(image),str(assets/"boot-files")]
        if a.label_font:command.insert(1,"--label-font="+str(a.label_font.resolve()))
        subprocess.run(command,check=True)
        commands.append(command)
        manifest["files_sha256"][image.name]=hashlib.sha256(image.read_bytes()).hexdigest()
        print(image)
    manifest["iso_build"]=dict(commands=commands,grub_version=subprocess.check_output([a.grub_mkrescue,"--version"],text=True).strip(),
                               firmware_scope="unsigned research media; firmware compatibility remains host-specific")
    (assets/"manifest.json").write_text(json.dumps(manifest,indent=2)+"\n")


if __name__=="__main__":main()
