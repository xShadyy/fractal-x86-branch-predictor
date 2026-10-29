/* Balanced branch-predictability contrast with a branchless input control. */
#include "cpu_features.h"

#include <intrin.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#include <windows.h>

#define BLOCKS 144u
#define ITERATIONS 8192u
#define WARMUP_BLOCKS 6u
#define CONDITIONS 6u
#define SEED UINT32_C(0x3127f49b)

enum sample_kind {
    BRANCH_PERIODIC = 0, BRANCH_RANDOM = 1,
    BRANCHLESS_PERIODIC = 2, BRANCHLESS_RANDOM = 3,
    TIMER_FAST = 4, TIMER_SLOW = 5
};

struct sample {
    uint64_t ticks;
    uint16_t block;
    uint8_t position;
    uint8_t kind;
};

extern uint8_t spec_branch_site(const volatile uint8_t *condition,
                                const volatile uint8_t *target);
extern uint8_t branchless_site(const volatile uint8_t *condition,
                               const volatile uint8_t *target);

static __declspec(align(64)) volatile uint8_t condition_line[64];
static __declspec(align(64)) volatile uint8_t target_line[64];
static __declspec(align(64)) uint8_t pattern[ITERATIONS];
static __declspec(align(64)) uint8_t periodic_template[ITERATIONS];
static __declspec(align(64)) uint8_t random_template[ITERATIONS];
static struct sample samples[BLOCKS * CONDITIONS];
static volatile uint32_t sink;
static int architectural_error;
static const char *const labels[CONDITIONS] = {
    "branch_periodic", "branch_random", "branchless_periodic",
    "branchless_random", "timer_fast", "timer_slow"
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

/* Each runner contains exactly one call site for all values of its pattern. */
static __declspec(noinline) uint32_t run_branch(const uint8_t *values) {
    uint32_t i, sum = 0;
    for (i = 0; i < ITERATIONS; ++i) {
        condition_line[0] = values[i];
        sum += spec_branch_site(condition_line, target_line);
    }
    return sum;
}

static __declspec(noinline) uint32_t run_branchless(const uint8_t *values) {
    uint32_t i, sum = 0;
    for (i = 0; i < ITERATIONS; ++i) {
        condition_line[0] = values[i];
        sum += branchless_site(condition_line, target_line);
    }
    return sum;
}

/* A known extra instruction every 128 iterations checks timer sensitivity. */
static __declspec(noinline) uint32_t timer_control(const uint8_t *values,
                                                   uint8_t slow) {
    uint32_t i, sum = 0;
    for (i = 0; i < ITERATIONS; ++i) {
        sum += values[i];
        if (slow && (i & 127u) == 0u) _mm_pause();
    }
    return sum;
}

static __declspec(noinline) uint32_t run_timer_fast(const uint8_t *values) {
    return timer_control(values, 0);
}

static __declspec(noinline) uint32_t run_timer_slow(const uint8_t *values) {
    return timer_control(values, 1);
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
        kind < 2u ? run_branch : kind < 4u ? run_branchless :
        kind == TIMER_FAST ? run_timer_fast : run_timer_slow;
    const uint8_t *source = (kind == BRANCH_RANDOM ||
                             kind == BRANCHLESS_RANDOM) ?
                            random_template : periodic_template;

    /* Copy outside the timed region: every class uses the same input address. */
    memcpy(pattern, source, ITERATIONS);
    condition_line[0] = 0;
    for (i = 0; i < ITERATIONS; i += 64u) touched += pattern[i];
    sink += touched + target_line[0];

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

/* Rotate each shuffled permutation to balance position across six blocks. */
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

int main(void) {
    struct cache_cpu_features cpu;
    int cpuid[4];
    uint8_t order[CONDITIONS] = { 0 };
    uint32_t state = SEED, block, index, i;
    uint64_t checksum = 0;
    uint64_t pattern_hash = UINT64_C(14695981039346656037);
    cache_detect_cpu(&cpu);
    if (!cpu.has_tsc || !cpu.invariant_tsc) {
        fputs("BATCH_ERROR: invariant TSC is required\n", stderr);
        return 1;
    }
    if (!pin_first_allowed_cpu()) {
        fputs("BATCH_ERROR: cannot pin one logical CPU\n", stderr);
        return 1;
    }
    target_line[0] = 1;
    for (i = 0; i < ITERATIONS; ++i)
        periodic_template[i] = (uint8_t)((i >> 1) & 1u);
    __cpuid(cpuid, 1);
    for (block = 0; block < WARMUP_BLOCKS; ++block)
        (void)collect_block(block, &state, order, 0, 0);
    for (block = 0; block < BLOCKS; ++block)
        pattern_hash = collect_block(block, &state, order, 1, pattern_hash);
    if (architectural_error) {
        fputs("BATCH_ERROR: branch results or balanced inputs were incorrect\n",
              stderr);
        return 1;
    }

    printf("BATCH_CPU,vendor=%s,signature=0x%08x,invariant_tsc=%u,hypervisor=%u\n",
           cpu.vendor, cpu.signature, cpu.invariant_tsc,
           ((uint32_t)cpuid[2] >> 31) & 1u);
    printf("BATCH_RUN,version=1,blocks=%u,iterations=%u,warmup_blocks=%u,"
           "seed=%u,branch_addr=0x%llx,branchless_addr=0x%llx,"
           "timer=lfence_rdtsc_lfence,pattern=periodic0011_vs_fresh_balanced_shuffle,"
           "compiler=msvc_O2,pattern_hash=%llu\n",
           BLOCKS, ITERATIONS, WARMUP_BLOCKS, SEED,
           (unsigned long long)(uintptr_t)spec_branch_site,
           (unsigned long long)(uintptr_t)branchless_site,
           (unsigned long long)pattern_hash);
    for (index = 0; index < BLOCKS * CONDITIONS; ++index) {
        const struct sample *entry = &samples[index];
        checksum += (uint64_t)(index + 1u) * entry->ticks +
                    entry->block + entry->position + entry->kind;
        printf("BATCH_SAMPLE,%u,%u,%u,%s,%llu\n", index,
               (unsigned)entry->block, (unsigned)entry->position,
               labels[entry->kind], (unsigned long long)entry->ticks);
    }
    printf("BATCH_END,count=%u,checksum=%llu,sink=%u\n",
           BLOCKS * CONDITIONS, (unsigned long long)checksum, sink);
    fflush(stdout);
    return 0;
}
