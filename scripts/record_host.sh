#!/usr/bin/env bash
set -euo pipefail

project_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
mkdir -p "$project_root/out"
output="$project_root/out/host-$(date -u +%Y%m%dT%H%M%SZ).txt"
{
    printf 'Captured UTC: %s\n' "$(date -u +%FT%TZ)"
    printf 'Kernel: '; uname -srvm
    printf '\nCPU summary:\n'; lscpu
    printf '\nMicrocode (first reported CPU):\n'
    awk -F: '/^microcode[[:space:]]*:/ {gsub(/^[[:space:]]+/, "", $2); print $2; exit}' /proc/cpuinfo
    printf '\nBIOS version (if exposed):\n'
    if [[ -r /sys/class/dmi/id/bios_version ]]; then cat /sys/class/dmi/id/bios_version; else echo unavailable; fi
    printf '\nReported CPU vulnerability and mitigation state:\n'
    for item in /sys/devices/system/cpu/vulnerabilities/*; do
        [[ -r "$item" ]] && printf '%s: %s\n' "$(basename "$item")" "$(cat "$item")"
    done
} > "$output"
echo "Saved $output"
echo "Review before sharing: system inventories may disclose hardware details."
