#!/usr/bin/env bash
set -euo pipefail

project_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
compiler="${CC:-cc}"
command -v "$compiler" >/dev/null || { echo "Missing C compiler: $compiler" >&2; exit 1; }
command -v python3 >/dev/null || { echo "Missing python3" >&2; exit 1; }

mkdir -p "$project_root/out"
binary="$project_root/out/cache-probe-native"
trace="$project_root/out/cache-probe-native-$(date -u +%Y%m%dT%H%M%SZ).log"

"$compiler" -std=c11 -O2 -Wall -Wextra -Werror -no-pie \
    "$project_root/programs/utest.c" \
    "$project_root/programs/cpu_features.c" \
    "$project_root/programs/cache_probe.S" \
    -o "$binary"

if command -v taskset >/dev/null; then
    affinity="$(taskset -pc "$$")"
    allowed="${affinity##*: }"
    first_allowed="${allowed%%[-,]*}"
    cpu="${CACHE_PROBE_CPU:-$first_allowed}"
    printf 'HOST_AFFINITY_CPU=%s\n' "$cpu" > "$trace"
    taskset -c "$cpu" "$binary" >> "$trace"
else
    printf 'HOST_AFFINITY_CPU=unavailable\n' > "$trace"
    "$binary" >> "$trace"
fi
python3 "$project_root/scripts/analyze_cache_probe.py" "$trace"
printf 'Raw trace: %s\n' "$trace"
