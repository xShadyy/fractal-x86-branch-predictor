#!/usr/bin/env bash
set -euo pipefail

project_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
upstream_dir="$project_root/upstream/fractal"
kernel="$upstream_dir/bin/fractal.release.qemu.x86_qemu"
initrd="$upstream_dir/filesys/disk.x86_64.ext2"

command -v qemu-system-x86_64 >/dev/null || { echo "Install qemu-system-x86_64 first." >&2; exit 1; }
[[ -f "$kernel" && -f "$initrd" ]] || { echo "Run scripts/build_qemu.sh first." >&2; exit 1; }

echo "Look for FRACTAL_UTEST_OK. Press Ctrl+C to stop QEMU after the message."
exec qemu-system-x86_64 \
    -machine q35 -m 4096 -smp 1 \
    -kernel "$kernel" -initrd "$initrd" \
    -display none -monitor none -serial stdio -no-reboot
