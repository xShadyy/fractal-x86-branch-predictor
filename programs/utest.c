/* Cache probe calibration and architectural controls for x86 Fractal. */
#include "cache_probe.h"
#include "cpu_features.h"

#include <stdint.h>
#include <stdio.h>

/* A dedicated page keeps unrelated data outside the probed cache line. */
static uint8_t sentinel[4096] __attribute__((aligned(4096)));
static volatile uint32_t sink;

enum cache_class {
    CACHE_HOT = 0,
    CACHE_COLD = 1,
    BRANCH_LOAD = 2,
    BRANCH_SKIP = 3,
    CACHE_CLASS_COUNT = 4
};

static uint64_t measure(enum cache_class sample_class) {
    uint8_t target_value = 0;

    cache_flush_line(sentinel);
    if (sample_class == CACHE_HOT) {
        target_value = cache_touch_line(sentinel);
    } else if (sample_class == BRANCH_LOAD) {
        target_value = cache_control_branch(sentinel, 1);
    } else if (sample_class == BRANCH_SKIP) {
        target_value = cache_control_branch(sentinel, 0);
    }

    /* The timed reload follows the branch/control without another line read. */
    uint64_t cycles = cache_reload_cycles(sentinel);
    sink += target_value;
    return cycles;
}

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
    sink += (uint32_t)measure(CACHE_HOT);
    printf("CACHE_CPU,vendor=%s,signature=0x%08x,clflush_bytes=%u,"
           "invariant_tsc=%u\n", cpu.vendor, cpu.signature,
           cpu.clflush_bytes, cpu.invariant_tsc);
    return 0;
}
