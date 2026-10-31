/* Exploratory same-site branch-history probe with two probe lengths. */
#include "cpu_features.h"

#include <errno.h>
#include <intrin.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <windows.h>

#define BLOCKS 720u
#define CONDITIONS 36u
#define WARMUP_BLOCKS 36u
#define EPISODES 128u
#define RESET_CALLS 256u
#define TRAIN_CALLS 256u
#define MAX_PROBE_CALLS 16u
#define FNV_OFFSET UINT64_C(14695981039346656037)
#define FNV_PRIME UINT64_C(1099511628211)

/* In each 18-condition length stratum, arms r/f/s have four t,p pairs,
   followed by fast/small/pause timer controls for p0,p1. */
enum { ARM_REAL, ARM_FIXED, ARM_SHAM, ARM_FAST, ARM_SMALL, ARM_PAUSE };

struct sample {
    uint64_t ticks;
    uint16_t block;
    uint8_t position;
    uint8_t kind;
};

extern uint8_t history_b2_branch_site(const volatile uint8_t *live,
                                      const volatile uint8_t *fixed,
                                      const volatile uint8_t *mode);
extern uint8_t history_b2_sham_site(const volatile uint8_t *live);

static __declspec(align(64)) volatile uint8_t live_line[64];
static __declspec(align(64)) volatile uint8_t mode_line[64];
static __declspec(align(64)) volatile uint8_t fixed_values[TRAIN_CALLS];
static __declspec(align(64)) uint8_t prelude_values[RESET_CALLS];
static __declspec(align(64)) uint8_t train_values[TRAIN_CALLS];
static __declspec(align(64)) uint8_t probe_values[MAX_PROBE_CALLS];
static struct sample samples[BLOCKS * CONDITIONS];
static volatile uint32_t sink;
static volatile uint32_t timer_small_sink;
static int architectural_error;
static const char *const labels[CONDITIONS] = {
    "r_t0_p0_n1", "r_t0_p1_n1", "r_t1_p0_n1", "r_t1_p1_n1",
    "f_t0_p0_n1", "f_t0_p1_n1", "f_t1_p0_n1", "f_t1_p1_n1",
    "s_t0_p0_n1", "s_t0_p1_n1", "s_t1_p0_n1", "s_t1_p1_n1",
    "fast_p0_n1", "fast_p1_n1", "small_p0_n1", "small_p1_n1",
    "pause_p0_n1", "pause_p1_n1",
    "r_t0_p0_n16", "r_t0_p1_n16", "r_t1_p0_n16", "r_t1_p1_n16",
    "f_t0_p0_n16", "f_t0_p1_n16", "f_t1_p0_n16", "f_t1_p1_n16",
    "s_t0_p0_n16", "s_t0_p1_n16", "s_t1_p0_n16", "s_t1_p1_n16",
    "fast_p0_n16", "fast_p1_n16", "small_p0_n16", "small_p1_n16",
    "pause_p0_n16", "pause_p1_n16"
};

static uint32_t next_random(uint32_t *state) {
    uint32_t x = *state;
    x ^= x << 13;
    x ^= x >> 17;
    x ^= x << 5;
    *state = x;
    return x;
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

/* Exactly one direct branch-site call in this runner's loop must serve all
   prelude, real/fixed training and timed-probe phases in the actual EXE. */
static __declspec(noinline) uint32_t run_branch(const uint8_t *values,
                                                uint32_t count) {
    uint32_t i, total = 0;
    for (i = 0; i < count; ++i) {
        live_line[0] = values[i];
        total += history_b2_branch_site(live_line, &fixed_values[i], mode_line);
    }
    return total;
}

static __declspec(noinline) uint32_t run_sham(const uint8_t *values,
                                              uint32_t count) {
    uint32_t i, total = 0;
    for (i = 0; i < count; ++i) {
        live_line[0] = values[i];
        total += history_b2_sham_site(live_line);
    }
    return total;
}

/* The length argument and the mode value are identical in matched timer
   comparisons. The small/PAUSE wrappers are separate physical code paths. */
static __declspec(noinline) uint64_t timed_fast(uint32_t count,
                                                uint32_t *result) {
    uint64_t start, end;
    _mm_lfence();
    start = __rdtsc();
    _mm_lfence();
    *result = run_branch(probe_values, count);
    _mm_lfence();
    end = __rdtsc();
    return end - start;
}

static __declspec(noinline) uint64_t timed_small(uint32_t count,
                                                 uint32_t *result) {
    uint64_t start, end;
    uint32_t value;
    _mm_lfence();
    start = __rdtsc();
    _mm_lfence();
    *result = run_branch(probe_values, count);
    value = *result;
    value = (value ^ UINT32_C(0x9e3779b9)) + 1u;
    timer_small_sink = value;
    _mm_lfence();
    end = __rdtsc();
    return end - start;
}

static __declspec(noinline) uint64_t timed_pause(uint32_t count,
                                                 uint32_t *result) {
    uint64_t start, end;
    _mm_lfence();
    start = __rdtsc();
    _mm_lfence();
    *result = run_branch(probe_values, count);
    _mm_pause();
    _mm_lfence();
    end = __rdtsc();
    return end - start;
}

static uint64_t measure(uint8_t kind) {
    const uint32_t length = kind < 18u ? 1u : 16u;
    const uint8_t within = (uint8_t)(kind % 18u);
    const uint8_t arm = (uint8_t)(within < 12u ? within / 4u :
                                ARM_FAST + (within - 12u) / 2u);
    const uint8_t train_bit = (uint8_t)(within < 12u ? (within % 4u) / 2u : 0u);
    const uint8_t probe_bit = (uint8_t)(within < 12u ? within % 2u :
                                       (within - 12u) % 2u);
    uint32_t episode, prelude_sum = 0, train_sum = 0, probe_sum = 0;
    uint32_t result, expected_train;
    uint64_t ticks = 0;

    memset(train_values, train_bit, TRAIN_CALLS);
    memset(probe_values, probe_bit, MAX_PROBE_CALLS);
    /* The 0011 prelude standardizes preceding activity, not predictor state. */
    for (episode = 0; episode < EPISODES; ++episode) {
        mode_line[0] = 1;
        prelude_sum += run_branch(prelude_values, RESET_CALLS);
        if (arm == ARM_SHAM) {
            train_sum += run_sham(train_values, TRAIN_CALLS);
        } else {
            mode_line[0] = arm == ARM_FIXED ? 0 : 1;
            train_sum += run_branch(train_values, TRAIN_CALLS);
        }
        mode_line[0] = 1; /* Probe always uses live decisions at the same site. */
        if (arm == ARM_SMALL)
            ticks += timed_small(length, &result);
        else if (arm == ARM_PAUSE)
            ticks += timed_pause(length, &result);
        else
            ticks += timed_fast(length, &result);
        probe_sum += result;
    }
    /* Both branch-site modes return the live byte, even when the conditional
       decision follows the fixed periodic stream. */
    expected_train = EPISODES * TRAIN_CALLS * (uint32_t)train_bit;
    if (prelude_sum != EPISODES * RESET_CALLS / 2u ||
        train_sum != expected_train ||
        probe_sum != EPISODES * length * (uint32_t)probe_bit)
        architectural_error = 1;
    sink += prelude_sum + train_sum + probe_sum;
    return ticks;
}

/* Seeded Fisher-Yates once per 36-block cycle, followed by full rotation.
   Replay both warm-up and recorded schedules in the analyzer. */
static uint64_t collect_block(uint32_t block, uint32_t *state,
                              uint8_t base_order[CONDITIONS], int store,
                              uint64_t hash) {
    uint32_t i, position;
    if (block % CONDITIONS == 0u) {
        for (i = 0; i < CONDITIONS; ++i) base_order[i] = (uint8_t)i;
        for (i = CONDITIONS - 1u; i > 0; --i) {
            uint32_t j = next_random(state) % (i + 1u);
            uint8_t temp = base_order[i];
            base_order[i] = base_order[j];
            base_order[j] = temp;
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
            hash = (hash ^ kind) * FNV_PRIME;
        }
    }
    return hash;
}

int main(int argc, char **argv) {
    struct cache_cpu_features cpu;
    int cpuid[4];
    char *end_seed;
    uint8_t order[CONDITIONS] = { 0 };
    uint32_t state, seed, block, index, i;
    uint64_t checksum = 0, schedule_hash = FNV_OFFSET;
    uint64_t pattern_hash = FNV_OFFSET;
    unsigned long long parsed_seed;

    if (argc != 2 || argv[1][0] == '-') {
        fputs("Usage: history-b2-windows.exe <nonzero decimal uint32 seed>\n", stderr);
        return 1;
    }
    errno = 0;
    parsed_seed = strtoull(argv[1], &end_seed, 10);
    if (errno || end_seed == argv[1] || *end_seed != '\0' ||
        parsed_seed == 0 || parsed_seed > UINT32_MAX) {
        fputs("B2_ERROR: expected nonzero decimal uint32 seed\n", stderr);
        return 1;
    }
    seed = (uint32_t)parsed_seed;
    state = seed;
    cache_detect_cpu(&cpu);
    if (!cpu.has_tsc || !cpu.invariant_tsc) {
        fputs("B2_ERROR: invariant TSC is required\n", stderr);
        return 1;
    }
    if (!pin_first_allowed_cpu()) {
        fputs("B2_ERROR: cannot pin one logical CPU\n", stderr);
        return 1;
    }
    for (i = 0; i < RESET_CALLS; ++i) {
        uint8_t value = (uint8_t)((i >> 1) & 1u);
        prelude_values[i] = value;
        fixed_values[i] = value;
        pattern_hash = (pattern_hash ^ value) * FNV_PRIME;
    }
    for (i = 0; i < TRAIN_CALLS; ++i)
        pattern_hash = (pattern_hash ^ fixed_values[i]) * FNV_PRIME;
    __cpuid(cpuid, 1);
    for (block = 0; block < WARMUP_BLOCKS; ++block)
        (void)collect_block(block, &state, order, 0, 0);
    for (block = 0; block < BLOCKS; ++block)
        schedule_hash = collect_block(block, &state, order, 1, schedule_hash);
    if (architectural_error) {
        fputs("B2_ERROR: prelude, train or probe output mismatch\n", stderr);
        return 1;
    }

    printf("B2_CPU,vendor=%s,signature=0x%08x,invariant_tsc=%u,hypervisor=%u\n",
           cpu.vendor, cpu.signature, cpu.invariant_tsc,
           ((uint32_t)cpuid[2] >> 31) & 1u);
    printf("B2_RUN,version=1,blocks=%u,episodes=%u,reset_calls=%u,"
           "train_calls=%u,probe_lengths=1:16,warmup_blocks=%u,seed=%u,"
           "branch_addr=0x%llx,sham_addr=0x%llx,"
           "live_addr=0x%llx,fixed_addr=0x%llx,mode_addr=0x%llx,"
           "probe_addr=0x%llx,prelude_addr=0x%llx,"
           "timer=lfence_rdtsc_lfence,"
           "protocol=history_same_site_fixed_probe_length,compiler=msvc_O2,"
           "schedule_hash=%llu,pattern_hash=%llu\n",
           BLOCKS, EPISODES, RESET_CALLS, TRAIN_CALLS, WARMUP_BLOCKS, seed,
           (unsigned long long)(uintptr_t)history_b2_branch_site,
           (unsigned long long)(uintptr_t)history_b2_sham_site,
           (unsigned long long)(uintptr_t)live_line,
           (unsigned long long)(uintptr_t)fixed_values,
           (unsigned long long)(uintptr_t)mode_line,
           (unsigned long long)(uintptr_t)probe_values,
           (unsigned long long)(uintptr_t)prelude_values,
           (unsigned long long)schedule_hash,
           (unsigned long long)pattern_hash);
    for (index = 0; index < BLOCKS * CONDITIONS; ++index) {
        const struct sample *entry = &samples[index];
        checksum += (uint64_t)(index + 1u) * entry->ticks + entry->block +
                    entry->position + entry->kind;
        printf("B2_SAMPLE,%u,%u,%u,%s,%llu\n", index,
               (unsigned)entry->block, (unsigned)entry->position,
               labels[entry->kind], (unsigned long long)entry->ticks);
    }
    printf("B2_END,count=%u,checksum=%llu,sink=%u\n",
           BLOCKS * CONDITIONS, (unsigned long long)checksum, sink);
    fflush(stdout);
    return 0;
}
