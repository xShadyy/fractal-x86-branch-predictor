/* User-mode branch-history crossover with an identical timed probe per pair. */
#include "cpu_features.h"

#include <errno.h>
#include <intrin.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <windows.h>

#define BLOCKS 320u
#define CONDITIONS 10u
#define WARMUP_BLOCKS 10u
#define EPISODES 128u
#define RESET_CALLS 256u
#define TRAIN_CALLS 256u
#define PROBE_CALLS 16u
#define FNV_OFFSET UINT64_C(14695981039346656037)
#define FNV_PRIME UINT64_C(1099511628211)

enum sample_kind {
    BRANCH_T0_P0, BRANCH_T1_P0, BRANCH_T0_P1, BRANCH_T1_P1,
    SHAM_T0_P0, SHAM_T1_P0, SHAM_T0_P1, SHAM_T1_P1,
    TIMER_FAST, TIMER_SLOW
};

struct sample {
    uint64_t ticks;
    uint16_t block;
    uint8_t position;
    uint8_t kind;
};

extern uint8_t history_no_load_site(const volatile uint8_t *condition);
extern uint8_t history_sham_site(const volatile uint8_t *condition);

static __declspec(align(64)) volatile uint8_t condition_line[64];
static __declspec(align(64)) uint8_t reset_values[RESET_CALLS];
static __declspec(align(64)) uint8_t train_values[TRAIN_CALLS];
static __declspec(align(64)) uint8_t probe_values[PROBE_CALLS];
static struct sample samples[BLOCKS * CONDITIONS];
static volatile uint32_t sink;
static int architectural_error;
static const char *const labels[CONDITIONS] = {
    "b_t0_p0", "b_t1_p0", "b_t0_p1", "b_t1_p1",
    "s_t0_p0", "s_t1_p0", "s_t0_p1", "s_t1_p1",
    "timer_fast", "timer_slow"
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

/* The conditional assembly instruction and its direct callsite serve all phases. */
static __declspec(noinline) uint32_t run_branch(const uint8_t *values,
                                                uint32_t count) {
    uint32_t i, total = 0;
    for (i = 0; i < count; ++i) {
        condition_line[0] = values[i];
        total += history_no_load_site(condition_line);
    }
    return total;
}

static __declspec(noinline) uint32_t run_sham(const uint8_t *values,
                                              uint32_t count) {
    uint32_t i, total = 0;
    for (i = 0; i < count; ++i) {
        condition_line[0] = values[i];
        total += history_sham_site(condition_line);
    }
    return total;
}

/* No extra conditional branch between training and the measured branch loop. */
static __declspec(noinline) uint64_t timed_probe(uint32_t *result) {
    uint64_t start, end;
    _mm_lfence();
    start = __rdtsc();
    _mm_lfence();
    *result = run_branch(probe_values, PROBE_CALLS);
    _mm_lfence();
    end = __rdtsc();
    return end - start;
}

/* Positive timer control: separate wrapper adds known work inside its interval. */
static __declspec(noinline) uint64_t timed_probe_slow(uint32_t *result) {
    uint64_t start, end;
    _mm_lfence();
    start = __rdtsc();
    _mm_lfence();
    _mm_pause();
    *result = run_branch(probe_values, PROBE_CALLS);
    _mm_lfence();
    end = __rdtsc();
    return end - start;
}

static uint64_t measure(uint8_t kind) {
    uint32_t episode, reset_sum = 0, train_sum = 0, probe_sum = 0;
    uint32_t probe_result, expected_train, expected_probe;
    uint8_t train_bit, probe_bit, sham;
    uint64_t total_ticks = 0;

    /* The two timer controls have the same training/probe inputs. */
    train_bit = kind == BRANCH_T1_P0 || kind == BRANCH_T1_P1 ||
                kind == SHAM_T1_P0 || kind == SHAM_T1_P1;
    probe_bit = kind == BRANCH_T0_P1 || kind == BRANCH_T1_P1 ||
                kind == SHAM_T0_P1 || kind == SHAM_T1_P1;
    sham = kind >= SHAM_T0_P0 && kind <= SHAM_T1_P1;
    memset(train_values, train_bit, TRAIN_CALLS);
    memset(probe_values, probe_bit, PROBE_CALLS);

    /* The same periodic prelude precedes every intervention; it does not
       guarantee erased hardware predictor state. Select paths outside the
       episode loop so the primary timed probe has no extra conditional. */
    if (sham) {
        for (episode = 0; episode < EPISODES; ++episode) {
            reset_sum += run_branch(reset_values, RESET_CALLS);
            train_sum += run_sham(train_values, TRAIN_CALLS);
            total_ticks += timed_probe(&probe_result);
            probe_sum += probe_result;
        }
    } else if (kind == TIMER_SLOW) {
        for (episode = 0; episode < EPISODES; ++episode) {
            reset_sum += run_branch(reset_values, RESET_CALLS);
            train_sum += run_branch(train_values, TRAIN_CALLS);
            total_ticks += timed_probe_slow(&probe_result);
            probe_sum += probe_result;
        }
    } else {
        for (episode = 0; episode < EPISODES; ++episode) {
            reset_sum += run_branch(reset_values, RESET_CALLS);
            train_sum += run_branch(train_values, TRAIN_CALLS);
            total_ticks += timed_probe(&probe_result);
            probe_sum += probe_result;
        }
    }

    expected_train = EPISODES * TRAIN_CALLS * (uint32_t)train_bit;
    expected_probe = EPISODES * PROBE_CALLS * (uint32_t)probe_bit;
    if (reset_sum != EPISODES * RESET_CALLS / 2u ||
        train_sum != expected_train || probe_sum != expected_probe)
        architectural_error = 1;
    sink += reset_sum + train_sum + probe_sum;
    return total_ticks;
}

/* One shuffled order per 10-block cycle, then complete position rotation. */
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

int main(int argc, char **argv) {
    struct cache_cpu_features cpu;
    int cpuid[4];
    char *end_seed;
    uint8_t order[CONDITIONS] = { 0 };
    uint32_t state, seed, block, index, i;
    uint64_t checksum = 0, schedule_hash = FNV_OFFSET;
    unsigned long long parsed_seed;
    if (argc != 2 || argv[1][0] == '-') {
        fputs("Usage: history-probe-windows.exe <nonzero decimal uint32 seed>\n", stderr);
        return 1;
    }
    errno = 0;
    parsed_seed = strtoull(argv[1], &end_seed, 10);
    if (errno || end_seed == argv[1] || *end_seed != '\0' ||
        parsed_seed == 0 || parsed_seed > UINT32_MAX) {
        fputs("HISTORY_ERROR: expected a nonzero decimal uint32 seed\n", stderr);
        return 1;
    }
    seed = (uint32_t)parsed_seed;
    state = seed;
    cache_detect_cpu(&cpu);
    if (!cpu.has_tsc || !cpu.invariant_tsc) {
        fputs("HISTORY_ERROR: invariant TSC is required\n", stderr);
        return 1;
    }
    if (!pin_first_allowed_cpu()) {
        fputs("HISTORY_ERROR: cannot pin one logical CPU\n", stderr);
        return 1;
    }
    for (i = 0; i < RESET_CALLS; ++i)
        reset_values[i] = (uint8_t)((i >> 1) & 1u);
    __cpuid(cpuid, 1);
    for (block = 0; block < WARMUP_BLOCKS; ++block)
        (void)collect_block(block, &state, order, 0, 0);
    for (block = 0; block < BLOCKS; ++block)
        schedule_hash = collect_block(block, &state, order, 1, schedule_hash);
    if (architectural_error) {
        fputs("HISTORY_ERROR: reset, train or probe outputs were incorrect\n", stderr);
        return 1;
    }

    printf("HISTORY_CPU,vendor=%s,signature=0x%08x,invariant_tsc=%u,hypervisor=%u\n",
           cpu.vendor, cpu.signature, cpu.invariant_tsc,
           ((uint32_t)cpuid[2] >> 31) & 1u);
    printf("HISTORY_RUN,version=1,blocks=%u,episodes=%u,reset_calls=%u,"
           "train_calls=%u,probe_calls=%u,warmup_blocks=%u,seed=%u,"
           "branch_addr=0x%llx,sham_addr=0x%llx,"
           "timer=lfence_rdtsc_lfence,protocol=reset_train_fixed_probe_crossover,"
           "compiler=msvc_O2,schedule_hash=%llu\n",
           BLOCKS, EPISODES, RESET_CALLS, TRAIN_CALLS, PROBE_CALLS,
           WARMUP_BLOCKS, seed,
           (unsigned long long)(uintptr_t)history_no_load_site,
           (unsigned long long)(uintptr_t)history_sham_site,
           (unsigned long long)schedule_hash);
    for (index = 0; index < BLOCKS * CONDITIONS; ++index) {
        const struct sample *entry = &samples[index];
        checksum += (uint64_t)(index + 1u) * entry->ticks + entry->block +
                    entry->position + entry->kind;
        printf("HISTORY_SAMPLE,%u,%u,%u,%s,%llu\n", index,
               (unsigned)entry->block, (unsigned)entry->position,
               labels[entry->kind], (unsigned long long)entry->ticks);
    }
    printf("HISTORY_END,count=%u,checksum=%llu,sink=%u\n",
           BLOCKS * CONDITIONS, (unsigned long long)checksum, sink);
    fflush(stdout);
    return 0;
}
