/* Cache probe calibration and architectural controls for x86 Fractal. */
#include "cache_probe.h"
#include "cpu_features.h"

#include <stdint.h>
#include <stdio.h>

#define SAMPLES_PER_CLASS 1024u
#define WARMUP_PER_CLASS 32u
#define SAMPLE_COUNT (SAMPLES_PER_CLASS * CACHE_CLASS_COUNT)
#define SCHEDULE_SEED UINT32_C(0x71c4a925)

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

struct cache_sample {
    uint64_t cycles;
    uint8_t sample_class;
    uint8_t phase;
};

static uint8_t class_schedule[SAMPLE_COUNT];
static struct cache_sample samples[SAMPLE_COUNT];

static uint32_t next_random(uint32_t *state) {
    uint32_t x = *state;
    x ^= x << 13;
    x ^= x >> 17;
    x ^= x << 5;
    *state = x;
    return x;
}

static void prepare_schedule(void) {
    uint32_t state = SCHEDULE_SEED;
    for (uint32_t i = 0; i < SAMPLE_COUNT; ++i) {
        class_schedule[i] = (uint8_t)(i % CACHE_CLASS_COUNT);
    }
    for (uint32_t i = SAMPLE_COUNT - 1; i > 0; --i) {
        uint32_t j = next_random(&state) % (i + 1);
        uint8_t swap = class_schedule[i];
        class_schedule[i] = class_schedule[j];
        class_schedule[j] = swap;
    }
}

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
