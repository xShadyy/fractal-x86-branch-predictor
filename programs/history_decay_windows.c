/* Fixed-work intervening-branch study, native Windows user mode. */
#include "cpu_features.h"

#include <errno.h>
#include <intrin.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <windows.h>

#define CONDITIONS 44u
#define MAIN_CONDITIONS 32u
#define BLOCKS 704u
#define WARMUP_BLOCKS 44u
#define EPISODES 128u
#define PRELUDE_CALLS 256u
#define TRAIN_CALLS 256u
#define FILLER_CALLS 256u
#define PROBE_CALLS 1u
#define FNV_OFFSET UINT64_C(14695981039346656037)
#define FNV_PRIME UINT64_C(1099511628211)

struct sample {
    uint64_t ticks;
    uint16_t block;
    uint8_t position;
    uint8_t kind;
};

extern uint8_t decay_branch_site(const volatile uint8_t *live,
                                  const volatile uint8_t *fixed,
                                  const volatile uint8_t *mode);
extern uint32_t decay_small_work(uint32_t result);

static const uint16_t lags[4] = { 0u, 16u, 64u, 256u };
static __declspec(align(64)) volatile uint8_t live_line[64];
static __declspec(align(64)) volatile uint8_t control_line[64];
static __declspec(align(64)) volatile uint8_t mode_line[64];
static __declspec(align(64)) uint8_t balanced_values[FILLER_CALLS];
static __declspec(align(64)) uint8_t train_values[TRAIN_CALLS];
static __declspec(align(64)) uint8_t probe_values[PROBE_CALLS];
static struct sample samples[BLOCKS * CONDITIONS];
static volatile uint32_t sink;
static int architectural_error;

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

/* Exactly one direct branch-site call instruction inside the shared runner.
   Verify this property in the optimized Windows PE before interpreting data. */
static __declspec(noinline) uint32_t run_site(const uint8_t *values,
                                               uint32_t count) {
    uint32_t i, total = 0;
    for (i = 0; i < count; ++i) {
        live_line[0] = values[i];
        control_line[0] = balanced_values[i & (FILLER_CALLS - 1u)];
        total += decay_branch_site(live_line, control_line, mode_line);
    }
    return total;
}

/* Each timed wrapper measures the same one-call runner. The wrappers are
   separate calibrations, not isolated instruction costs. */
static __declspec(noinline) uint64_t timed_fast(uint32_t *result) {
    uint64_t start, end;
    _mm_lfence();
    start = __rdtsc();
    _mm_lfence();
    *result = run_site(probe_values, PROBE_CALLS);
    _mm_lfence();
    end = __rdtsc();
    return end - start;
}

static __declspec(noinline) uint64_t timed_small(uint32_t *result,
                                                   uint32_t *work) {
    uint64_t start, end;
    _mm_lfence();
    start = __rdtsc();
    _mm_lfence();
    *result = run_site(probe_values, PROBE_CALLS);
    *work = decay_small_work(*result);
    _mm_lfence();
    end = __rdtsc();
    return end - start;
}

static __declspec(noinline) uint64_t timed_pause(uint32_t *result) {
    uint64_t start, end;
    _mm_lfence();
    start = __rdtsc();
    _mm_lfence();
    *result = run_site(probe_values, PROBE_CALLS);
    _mm_pause();
    _mm_lfence();
    end = __rdtsc();
    return end - start;
}

static uint64_t measure(uint8_t kind) {
    uint32_t episode, prelude_sum = 0, filler_sum = 0, train_sum = 0;
    uint32_t probe_sum = 0, probe_result = 0, work = 0;
    uint32_t lag_index, train_bit, probe_bit, arm, timer;
    uint32_t before, after;
    uint64_t total_ticks = 0;

    if (kind < MAIN_CONDITIONS) {
        lag_index = kind / 8u;
        arm = (kind / 4u) % 2u; /* 0=real, 1=same-site fixed */
        train_bit = (kind / 2u) % 2u;
        probe_bit = kind % 2u;
        timer = 0u;
    } else {
        uint32_t timer_index = kind - MAIN_CONDITIONS;
        lag_index = (timer_index / 6u) == 0u ? 0u : 3u;
        arm = 0u;
        train_bit = 0u;
        probe_bit = (timer_index / 3u) % 2u;
        timer = timer_index % 3u; /* fast, small, PAUSE */
    }
    after = lags[lag_index];
    before = FILLER_CALLS - after;
    memset(train_values, (int)train_bit, TRAIN_CALLS);
    probe_values[0] = (uint8_t)probe_bit;

    /* The same 256 balanced filler bytes are consumed in order in every
       condition. Only their placement around the trainer is changed. */
    for (episode = 0; episode < EPISODES; ++episode) {
        mode_line[0] = 1u;
        prelude_sum += run_site(balanced_values, PRELUDE_CALLS);
        filler_sum += run_site(balanced_values, before);
        mode_line[0] = arm == 0u ? 1u : 0u;
        train_sum += run_site(train_values, TRAIN_CALLS);
        mode_line[0] = 1u;
        filler_sum += run_site(balanced_values + before, after);
        if (timer == 2u) total_ticks += timed_pause(&probe_result);
        else if (timer == 1u) total_ticks += timed_small(&probe_result, &work);
        else total_ticks += timed_fast(&probe_result);
        probe_sum += probe_result;
        sink += work;
    }
    if (prelude_sum != EPISODES * PRELUDE_CALLS / 2u ||
        filler_sum != EPISODES * FILLER_CALLS / 2u ||
        train_sum != EPISODES * TRAIN_CALLS * train_bit ||
        probe_sum != EPISODES * PROBE_CALLS * probe_bit)
        architectural_error = 1;
    sink += prelude_sum + filler_sum + train_sum + probe_sum;
    return total_ticks;
}

static uint64_t collect_block(uint32_t block, uint32_t *state,
                              uint8_t base_order[CONDITIONS], int store,
                              uint64_t schedule_hash) {
    uint32_t i, position;
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
            schedule_hash = (schedule_hash ^ kind) * FNV_PRIME;
        }
    }
    return schedule_hash;
}

static void print_kind(uint8_t kind) {
    if (kind < MAIN_CONDITIONS) {
        printf("l%u_%s_t%u_p%u", (unsigned)lags[kind / 8u],
               (kind / 4u) % 2u == 0u ? "real" : "fixed",
               (unsigned)(kind / 2u) % 2u, (unsigned)kind % 2u);
    } else {
        uint8_t index = (uint8_t)(kind - MAIN_CONDITIONS);
        printf("l%u_timer_%s_p%u", (index / 6u) == 0u ? 0u : 256u,
               (index % 3u) == 0u ? "fast" :
               (index % 3u) == 1u ? "small" : "pause",
               (unsigned)(index / 3u) % 2u);
    }
}

int main(int argc, char **argv) {
    struct cache_cpu_features cpu;
    int cpuid[4];
    char *end_seed;
    uint8_t order[CONDITIONS] = { 0 };
    uint32_t state, seed, block, index, i;
    uint64_t checksum = 0, schedule_hash = FNV_OFFSET;
    unsigned long long parsed_seed;
    if (argc != 2 || argv[1][0] == '-') {
        fputs("Usage: history-decay-windows.exe <nonzero decimal uint32 seed>\n", stderr);
        return 1;
    }
    errno = 0;
    parsed_seed = strtoull(argv[1], &end_seed, 10);
    if (errno || end_seed == argv[1] || *end_seed != '\0' ||
        parsed_seed == 0 || parsed_seed > UINT32_MAX) {
        fputs("DECAY_ERROR: expected nonzero decimal uint32 seed\n", stderr);
        return 1;
    }
    seed = (uint32_t)parsed_seed;
    state = seed;
    cache_detect_cpu(&cpu);
    if (!cpu.has_tsc || !cpu.invariant_tsc || !pin_first_allowed_cpu()) {
        fputs("DECAY_ERROR: invariant TSC and single-CPU affinity required\n", stderr);
        return 1;
    }
    for (i = 0; i < FILLER_CALLS; ++i)
        balanced_values[i] = (uint8_t)((i >> 1) & 1u);
    __cpuid(cpuid, 1);
    for (block = 0; block < WARMUP_BLOCKS; ++block)
        (void)collect_block(block, &state, order, 0, 0);
    for (block = 0; block < BLOCKS; ++block)
        schedule_hash = collect_block(block, &state, order, 1, schedule_hash);
    if (architectural_error) {
        fputs("DECAY_ERROR: architectural output mismatch\n", stderr);
        return 1;
    }
    printf("DECAY_CPU,vendor=%s,signature=0x%08x,invariant_tsc=%u,hypervisor=%u\n",
           cpu.vendor, cpu.signature, cpu.invariant_tsc,
           ((uint32_t)cpuid[2] >> 31) & 1u);
    printf("DECAY_RUN,version=1,blocks=%u,conditions=%u,episodes=%u,"
           "prelude_calls=%u,filler_calls=%u,train_calls=%u,probe_calls=%u,"
           "warmup_blocks=%u,seed=%u,lags=0_16_64_256,"
           "branch_addr=0x%llx,small_addr=0x%llx,"
           "timer=lfence_rdtsc_lfence,protocol=balanced_filler_position,"
           "compiler=msvc_O2,schedule_hash=%llu\n",
           BLOCKS, CONDITIONS, EPISODES, PRELUDE_CALLS, FILLER_CALLS,
           TRAIN_CALLS, PROBE_CALLS, WARMUP_BLOCKS, seed,
           (unsigned long long)(uintptr_t)decay_branch_site,
           (unsigned long long)(uintptr_t)decay_small_work,
           (unsigned long long)schedule_hash);
    for (index = 0; index < BLOCKS * CONDITIONS; ++index) {
        const struct sample *entry = &samples[index];
        checksum += (uint64_t)(index + 1u) * entry->ticks +
                    entry->block + entry->position + entry->kind;
        printf("DECAY_SAMPLE,%u,%u,%u,", index, (unsigned)entry->block,
               (unsigned)entry->position);
        print_kind(entry->kind);
        printf(",%llu\n", (unsigned long long)entry->ticks);
    }
    printf("DECAY_END,count=%u,checksum=%llu,sink=%u\n",
           BLOCKS * CONDITIONS, (unsigned long long)checksum, sink);
    fflush(stdout);
    return 0;
}
