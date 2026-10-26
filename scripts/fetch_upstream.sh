#!/usr/bin/env bash
set -euo pipefail

project_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
upstream_dir="$project_root/upstream/fractal"
revision="$(tr -d '[:space:]' < "$project_root/UPSTREAM_FRACTAL_REVISION")"

if [[ ! -d "$upstream_dir/.git" ]]; then
    mkdir -p "$(dirname "$upstream_dir")"
    git clone https://github.com/jprx/fractal.git "$upstream_dir"
fi

if [[ -n "$(git -C "$upstream_dir" status --porcelain --untracked-files=no)" ]]; then
    echo "Upstream checkout has local changes; refusing to switch revisions." >&2
    exit 1
fi

if ! git -C "$upstream_dir" cat-file -e "$revision^{commit}" 2>/dev/null; then
    git -C "$upstream_dir" fetch origin "$revision"
fi
git -C "$upstream_dir" checkout --detach "$revision"
actual="$(git -C "$upstream_dir" rev-parse HEAD)"
[[ "$actual" == "$revision" ]] || { echo "Unexpected upstream revision: $actual" >&2; exit 1; }
echo "Fractal pinned at $actual"
