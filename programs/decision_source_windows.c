/* One branch address with a runtime-selected decision source. */
#include "cpu_features.h"

#include <errno.h>
#include <intrin.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <windows.h>

#define BLOCKS 144u
#define ITERATIONS 8192u
#define WARMUP_BLOCKS 8u
#define CONDITIONS 8u

enum sample_kind {
    LIVE_PERIODIC = 0, LIVE_RANDOM = 1,
    FIXED_PERIODIC = 2, FIXED_RANDOM = 3,
    BRANCHLESS_PERIODIC = 4, BRANCHLESS_RANDOM = 5,
    TIMER_FAST = 6, TIMER_SLOW = 7
};

struct sample {
    uint64_t ticks;
    uint16_t block;
    uint8_t position;
    uint8_t kind;
};

extern uint8_t decision_source_branch(const volatile uint8_t *input,
                                      const volatile uint8_t *control,
                                      const volatile uint8_t *use_live);
extern uint8_t decision_source_branchless(const volatile uint8_t *input,
                                          const volatile uint8_t *control,
                                          const volatile uint8_t *use_live);

static __declspec(align(64)) volatile uint8_t input_line[64];
static __declspec(align(64)) volatile uint8_t control_line[64];
static __declspec(align(64)) volatile uint8_t mode_line[64];
static __declspec(align(64)) uint8_t pattern[ITERATIONS];
static __declspec(align(64)) uint8_t periodic_template[ITERATIONS];
static __declspec(align(64)) uint8_t random_template[ITERATIONS];
static struct sample samples[BLOCKS * CONDITIONS];
static volatile uint32_t sink;
static volatile uint8_t timer_slow_flag;
static int architectural_error;
static const char *const labels[CONDITIONS] = {
    "live_periodic", "live_random", "fixed_periodic", "fixed_random",
    "branchless_periodic", "branchless_random", "timer_fast", "timer_slow"
};

static uint32_t next_random(uint32_t *state) {
    uint32_t value = *state;
    value ^= value << 13;
    value ^= value >> 17;
    value ^= value << 5;
    *state = value;
    return value;
}

static int pin_first_allowed_cpu(void) {
    DWORD_PTR process_mask, system_mask, chosen;
    unsigned cpu = 0;
    if (!GetProcessAffinityMask(GetCurrentProcess(), &process_mask, &system_mask) ||
        process_mask == 0) return 0;
    chosen = process_mask & (~process_mask + 1);
    while ((chosen >> cpu) != 1) ++cpu;
    if (!SetProcessAffinityMask(GetCurrentProcess(), chosen)) return 0;
    printf("HOST_AFFINITY_CPU=%u\n", cpu);
    return 1;
}

/* All four primary conditions enter one branch site from this call site. */
static __declspec(noinline) uint32_t run_branch(const uint8_t *values) {
    uint32_t i, sum = 0;
    for (i = 0; i < ITERATIONS; ++i) {
        input_line[0] = values[i];
        control_line[0] = periodic_template[i];
        sum += decision_source_branch(input_line, control_line, mode_line);
    }
    return sum;
}

static __declspec(noinline) uint32_t run_branchless(const uint8_t *values) {
    uint32_t i, sum = 0;
    for (i = 0; i < ITERATIONS; ++i) {
        input_line[0] = values[i];
        control_line[0] = periodic_template[i];
        sum += decision_source_branchless(input_line, control_line, mode_line);
    }
    return sum;
}

/* One timer loop and call site; the volatile flag is assigned before timing. */
static __declspec(noinline) uint32_t timer_control(const uint8_t *values) {
    uint32_t i, sum = 0;
    for (i = 0; i < ITERATIONS; ++i) {
        sum += values[i];
        if ((i & 127u) == 0u && timer_slow_flag) _mm_pause();
    }
    return sum;
}

static void prepare_random_template(uint32_t *state) {
    uint32_t i;
    memcpy(random_template, periodic_template, ITERATIONS);
    for (i = ITERATIONS - 1u; i > 0; --i) {
        uint32_t j = next_random(state) % (i + 1u);
        uint8_t temporary = random_template[i];
        random_template[i] = random_template[j];
        random_template[j] = temporary;
    }
}

static uint64_t hash_template(uint64_t hash) {
    uint32_t i;
    for (i = 0; i < ITERATIONS; ++i)
        hash = (hash ^ random_template[i]) * UINT64_C(1099511628211);
    return hash;
}

static uint64_t measure(uint8_t kind) {
    uint32_t touched = 0, output, i;
    uint64_t start, end;
    uint32_t (*runner)(const uint8_t *) =
        kind < 4u ? run_branch : kind < 6u ? run_branchless : timer_control;
    const uint8_t *source = (kind == LIVE_RANDOM ||
                             kind == FIXED_RANDOM ||
                             kind == BRANCHLESS_RANDOM) ?
                            random_template : periodic_template;

    /* Copy outside the timed region: every class uses the same input address. */
    memcpy(pattern, source, ITERATIONS);
    input_line[0] = 0;
    control_line[0] = 0;
    mode_line[0] = (kind == LIVE_PERIODIC || kind == LIVE_RANDOM ||
                    kind == BRANCHLESS_PERIODIC || kind == BRANCHLESS_RANDOM);
    timer_slow_flag = kind == TIMER_SLOW;
    for (i = 0; i < ITERATIONS; i += 64u) touched += pattern[i];
    sink += touched + control_line[0] + mode_line[0];

    _mm_lfence();
    start = __rdtsc();
    _mm_lfence();
    output = runner(pattern);
    _mm_lfence();
    end = __rdtsc();
    if (output != ITERATIONS / 2u) architectural_error = 1;
    sink += output;
    return end - start;
}

/* Rotate each shuffled permutation to balance position across eight blocks. */
static uint64_t collect_block(uint32_t block, uint32_t *state,
                              uint8_t base_order[CONDITIONS], int store,
                              uint64_t pattern_hash) {
    uint32_t i, position;
    prepare_random_template(state);
    if (store) pattern_hash = hash_template(pattern_hash);
    if (block % CONDITIONS == 0u) {
        for (i = 0; i < CONDITIONS; ++i) base_order[i] = (uint8_t)i;
        for (i = CONDITIONS - 1u; i > 0; --i) {
            uint32_t j = next_random(state) % (i + 1u);
            uint8_t temporary = base_order[i];
            base_order[i] = base_order[j];
            base_order[j] = temporary;
        }
    }
    for (position = 0; position < CONDITIONS; ++position) {
        uint8_t kind = base_order[(position + block % CONDITIONS) % CONDITIONS];
        uint64_t ticks = measure(kind);
        if (store) {
            struct sample *entry = &samples[block * CONDITIONS + position];
            entry->ticks = ticks;
            entry->block = (uint16_t)block;
            entry->position = (uint8_t)position;
            entry->kind = kind;
        }
    }
    return pattern_hash;
}

int main(int argc, char **argv) {
    struct cache_cpu_features cpu;
    int cpuid[4];
    char *end_seed;
    uint8_t order[CONDITIONS] = { 0 };
    uint32_t state, seed, block, index, i;
    uint64_t checksum = 0;
    uint64_t pattern_hash = UINT64_C(14695981039346656037);
    unsigned long long parsed_seed;
    if (argc != 2 || argv[1][0] == '-') {
        fputs("Usage: decision-source-windows.exe <nonzero decimal uint32 seed>\n", stderr);
        return 1;
    }
    errno = 0;
    parsed_seed = strtoull(argv[1], &end_seed, 10);
    if (errno || end_seed == argv[1] || *end_seed != '\0' ||
        parsed_seed == 0 || parsed_seed > UINT32_MAX) {
        fputs("DECISION_ERROR: expected a nonzero decimal uint32 seed\n", stderr);
        return 1;
    }
    seed = (uint32_t)parsed_seed;
    state = seed;
    cache_detect_cpu(&cpu);
    if (!cpu.has_tsc || !cpu.invariant_tsc) {
        fputs("DECISION_ERROR: invariant TSC is required\n", stderr);
        return 1;
    }
    if (!pin_first_allowed_cpu()) {
        fputs("DECISION_ERROR: cannot pin one logical CPU\n", stderr);
        return 1;
    }
    for (i = 0; i < ITERATIONS; ++i)
        periodic_template[i] = (uint8_t)((i >> 1) & 1u);
    __cpuid(cpuid, 1);
    for (block = 0; block < WARMUP_BLOCKS; ++block)
        (void)collect_block(block, &state, order, 0, 0);
    for (block = 0; block < BLOCKS; ++block)
        pattern_hash = collect_block(block, &state, order, 1, pattern_hash);
    if (architectural_error) {
        fputs("DECISION_ERROR: branch results or balanced inputs were incorrect\n",
              stderr);
        return 1;
    }

    printf("DECISION_CPU,vendor=%s,signature=0x%08x,invariant_tsc=%u,hypervisor=%u\n",
           cpu.vendor, cpu.signature, cpu.invariant_tsc,
           ((uint32_t)cpuid[2] >> 31) & 1u);
    printf("DECISION_RUN,version=1,blocks=%u,iterations=%u,warmup_blocks=%u,"
           "seed=%u,branch_addr=0x%llx,branchless_addr=0x%llx,"
           "input_addr=0x%llx,control_addr=0x%llx,mode_addr=0x%llx,"
           "timer=lfence_rdtsc_lfence,pattern=periodic0011_vs_fresh_balanced_shuffle,"
           "decision=runtime_cmov_live_vs_fixed_periodic,"
           "compiler=msvc_O2,pattern_hash=%llu\n",
           BLOCKS, ITERATIONS, WARMUP_BLOCKS, seed,
           (unsigned long long)(uintptr_t)decision_source_branch,
           (unsigned long long)(uintptr_t)decision_source_branchless,
           (unsigned long long)(uintptr_t)input_line,
           (unsigned long long)(uintptr_t)control_line,
           (unsigned long long)(uintptr_t)mode_line,
           (unsigned long long)pattern_hash);
    for (index = 0; index < BLOCKS * CONDITIONS; ++index) {
        const struct sample *entry = &samples[index];
        checksum += (uint64_t)(index + 1u) * entry->ticks +
                    entry->block + entry->position + entry->kind;
        printf("DECISION_SAMPLE,%u,%u,%u,%s,%llu\n", index,
               (unsigned)entry->block, (unsigned)entry->position,
               labels[entry->kind], (unsigned long long)entry->ticks);
    }
    printf("DECISION_END,count=%u,checksum=%llu,sink=%u\n",
           BLOCKS * CONDITIONS, (unsigned long long)checksum, sink);
    fflush(stdout);
    return 0;
}
