#!/usr/bin/env bash
set -euo pipefail

project_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
upstream_dir="$project_root/upstream/fractal"
toolchain_bin="$upstream_dir/toolchain/out/bin"

[[ -d "$upstream_dir/.git" ]] || { echo "Run scripts/fetch_upstream.sh first." >&2; exit 1; }
expected="$(tr -d '[:space:]' < "$project_root/UPSTREAM_FRACTAL_REVISION")"
actual="$(git -C "$upstream_dir" rev-parse HEAD)"
[[ "$actual" == "$expected" ]] || { echo "Upstream revision mismatch: $actual" >&2; exit 1; }

export PATH="$toolchain_bin:$PATH"
for program in x86_64-fractal-elf-gcc x86_64-fractal-elf-g++ genext2fs; do
    command -v "$program" >/dev/null || {
        echo "Missing $program. From upstream/fractal/toolchain run ./mk_toolchain.sh all, then retry." >&2
        exit 1
    }
done

make -C "$upstream_dir" BOARD=QEMU x86
mkdir -p "$upstream_dir/filesys/fs_x86_64/bin"
x86_64-fractal-elf-gcc -std=c11 -O2 -Wall -Wextra -static \
    "$project_root/programs/utest.c" \
    -o "$upstream_dir/filesys/fs_x86_64/bin/utest"

# Upstream's filesystem Makefile watches the fs_x86_64 directory, not its contents.
# Force a new image after replacing the test binary.
rm -f "$upstream_dir/filesys/disk.x86_64.tar" "$upstream_dir/filesys/disk.x86_64.ext2"
make -C "$upstream_dir/filesys" disk.x86_64.ext2

echo "Kernel: $upstream_dir/bin/fractal.release.qemu.x86_qemu"
echo "Initrd: $upstream_dir/filesys/disk.x86_64.ext2"
