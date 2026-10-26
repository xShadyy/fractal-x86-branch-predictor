/* Cache probe calibration and architectural controls for x86 Fractal. */
#include "cache_probe.h"
#include "cpu_features.h"

#include <stdint.h>
#include <stdio.h>

/* A dedicated page keeps unrelated data outside the probed cache line. */
static uint8_t sentinel[4096] __attribute__((aligned(4096)));
static volatile uint32_t sink;

int main(void) {
    struct cache_cpu_features cpu;

    cache_detect_cpu(&cpu);
    if (!cpu.has_tsc || !cpu.has_clflush || cpu.clflush_bytes == 0 ||
        cpu.clflush_bytes > sizeof(sentinel)) {
        puts("CACHE_ERROR: TSC and CLFLUSH with a valid line size are required");
        return 1;
    }

    sentinel[0] = 1;
    sink += cache_touch_line(sentinel);
    printf("CACHE_CPU,vendor=%s,signature=0x%08x,clflush_bytes=%u,"
           "invariant_tsc=%u\n", cpu.vendor, cpu.signature,
           cpu.clflush_bytes, cpu.invariant_tsc);
    return 0;
}
