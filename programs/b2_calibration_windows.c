/* Exploratory, same-process timer calibration for the B2 history pilot.
   Only t=0 live training and fixed-decision neutral controls are exercised;
   no real-arm outcome or cross-privilege effect is estimated here. */
#include "cpu_features.h"

#include <errno.h>
#include <intrin.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <windows.h>

#define BLOCKS 1280u
#define CONDITIONS 32u
#define WARMUP_BLOCKS 32u
#define EPISODES 128u
#define RESET_CALLS 256u
#define TRAIN_CALLS 256u
#define MAX_PROBE_CALLS 16u
#define FNV_OFFSET UINT64_C(14695981039346656037)
#define FNV_PRIME UINT64_C(1099511628211)

enum { FAST_A, FAST_B, OLDSMALL, DOSE4, DOSE8, PAUSE };

struct sample {
    uint64_t ticks;
    uint16_t block;
    uint8_t position;
    uint8_t kind;
};

extern uint8_t history_b2_branch_site(const volatile uint8_t *live,
                                      const volatile uint8_t *fixed,
                                      const volatile uint8_t *mode);

static __declspec(align(64)) volatile uint8_t live_line[64];
static __declspec(align(64)) volatile uint8_t mode_line[64];
static __declspec(align(64)) volatile uint8_t fixed_values[TRAIN_CALLS];
static __declspec(align(64)) uint8_t prelude_values[RESET_CALLS];
static __declspec(align(64)) uint8_t train_values[TRAIN_CALLS];
static __declspec(align(64)) uint8_t probe_values[MAX_PROBE_CALLS];
static struct sample samples[BLOCKS * CONDITIONS];
static volatile uint32_t sink;
static volatile uint32_t timer_work_sink;
static uint64_t prelude_total, train_total, probe_total;
static int architectural_error;

/* Every group has exactly six timer variants after the same t=0 live
   training. Last eight groups have t=0/1 live values with fixed periodic
   branch decisions; their probes always use the live decision. */
static const char *const labels[CONDITIONS] = {
    "fast_a_p0_n1", "fast_b_p0_n1", "oldsmall_p0_n1",
    "dose4_p0_n1", "dose8_p0_n1", "pause_p0_n1",
    "fast_a_p1_n1", "fast_b_p1_n1", "oldsmall_p1_n1",
    "dose4_p1_n1", "dose8_p1_n1", "pause_p1_n1",
    "fast_a_p0_n16", "fast_b_p0_n16", "oldsmall_p0_n16",
    "dose4_p0_n16", "dose8_p0_n16", "pause_p0_n16",
    "fast_a_p1_n16", "fast_b_p1_n16", "oldsmall_p1_n16",
    "dose4_p1_n16", "dose8_p1_n16", "pause_p1_n16",
    "fixed_t0_p0_n1", "fixed_t1_p0_n1",
    "fixed_t0_p1_n1", "fixed_t1_p1_n1",
    "fixed_t0_p0_n16", "fixed_t1_p0_n16",
    "fixed_t0_p1_n16", "fixed_t1_p1_n16"
};

struct condition {
    uint32_t length;
    uint8_t probe_bit;
    uint8_t train_bit;
    uint8_t timer;
    uint8_t is_fixed;
};

static struct condition decode_condition(uint8_t kind) {
    struct condition decoded;
    uint8_t timer_group = (uint8_t)(kind / 6u);
    uint8_t fixed_index = (uint8_t)(kind >= 24u ? kind - 24u : 0u);
    uint8_t fixed_group = (uint8_t)(fixed_index / 4u);
    decoded.is_fixed = (uint8_t)(kind >= 24u);
    decoded.length = decoded.is_fixed ? (fixed_group == 0u ? 1u : 16u) :
                                        (timer_group < 2u ? 1u : 16u);
    decoded.probe_bit = (uint8_t)(decoded.is_fixed ? (fixed_index / 2u) % 2u :
                                                      timer_group % 2u);
    decoded.train_bit = (uint8_t)(decoded.is_fixed ? fixed_index % 2u : 0u);
    decoded.timer = (uint8_t)(kind % 6u);
    return decoded;
}

/* Guard against accidental condition-map drift, especially fixed n=16. */
static int check_condition_map(void) {
    static const char *const timer_names[6] = {
        "fast_a", "fast_b", "oldsmall", "dose4", "dose8", "pause"
    };
    uint32_t n_index, p, t, timer;
    char expected[64];
    for (n_index = 0; n_index < 2u; ++n_index) {
        uint32_t length = n_index == 0u ? 1u : 16u;
        for (p = 0; p < 2u; ++p) {
            for (timer = 0; timer < 6u; ++timer) {
                uint8_t kind = (uint8_t)(12u * n_index + 6u * p + timer);
                struct condition decoded = decode_condition(kind);
                (void)snprintf(expected, sizeof(expected), "%s_p%u_n%u",
                               timer_names[timer], p, length);
                if (decoded.is_fixed || decoded.length != length ||
                    decoded.probe_bit != p || decoded.train_bit != 0u ||
                    decoded.timer != timer || strcmp(labels[kind], expected) != 0)
                    return 0;
            }
            for (t = 0; t < 2u; ++t) {
                uint8_t kind = (uint8_t)(24u + 4u * n_index + 2u * p + t);
                struct condition decoded = decode_condition(kind);
                (void)snprintf(expected, sizeof(expected), "fixed_t%u_p%u_n%u",
                               t, p, length);
                if (!decoded.is_fixed || decoded.length != length ||
                    decoded.probe_bit != p || decoded.train_bit != t ||
                    strcmp(labels[kind], expected) != 0)
                    return 0;
            }
        }
    }
    return 1;
}

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

/* The same branch-site call serves all prelude, training, and timed probes.
   The compiled EXE must still be audited to verify this physical path. */
static __declspec(noinline) uint32_t run_branch(const uint8_t *values,
                                                uint32_t count) {
    uint32_t i, total = 0;
    for (i = 0; i < count; ++i) {
        live_line[0] = values[i];
        total += history_b2_branch_site(live_line, &fixed_values[i], mode_line);
    }
    return total;
}

/* Both independently labeled fast observations call this exact function.
   Neither label inserts any operation into the timed interval. */
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

/* Existing B2 small wrapper retained as a diagnostic, ineligible for selection. */
static __declspec(noinline) uint64_t timed_oldsmall(uint32_t count,
                                                   uint32_t *result) {
    uint64_t start, end;
    uint32_t value;
    _mm_lfence();
    start = __rdtsc();
    _mm_lfence();
    *result = run_branch(probe_values, count);
    value = *result;
    value = (value ^ UINT32_C(0x9e3779b9)) + 1u;
    timer_work_sink = value;
    _mm_lfence();
    end = __rdtsc();
    return end - start;
}

/* Four serial source-dependent rotate/add-or-XOR steps after the probe.
   "dose4" describes source steps, not instructions, TSC ticks or cycles. */
static __declspec(noinline) uint64_t timed_dose4(uint32_t count,
                                                 uint32_t *result) {
    uint64_t start, end;
    uint32_t value;
    _mm_lfence();
    start = __rdtsc();
    _mm_lfence();
    *result = run_branch(probe_values, count);
    value = *result;
    value = _rotl(value, 5) + UINT32_C(0x9e3779b9);
    value = _rotl(value, 7) ^ UINT32_C(0x7f4a7c15);
    value = _rotl(value, 11) + UINT32_C(0x85ebca6b);
    value = _rotl(value, 13) ^ UINT32_C(0xc2b2ae35);
    timer_work_sink = value;
    _mm_lfence();
    end = __rdtsc();
    return end - start;
}

/* Eight serial source-dependent steps; same first four as dose4. */
static __declspec(noinline) uint64_t timed_dose8(uint32_t count,
                                                 uint32_t *result) {
    uint64_t start, end;
    uint32_t value;
    _mm_lfence();
    start = __rdtsc();
    _mm_lfence();
    *result = run_branch(probe_values, count);
    value = *result;
    value = _rotl(value, 5) + UINT32_C(0x9e3779b9);
    value = _rotl(value, 7) ^ UINT32_C(0x7f4a7c15);
    value = _rotl(value, 11) + UINT32_C(0x85ebca6b);
    value = _rotl(value, 13) ^ UINT32_C(0xc2b2ae35);
    value = _rotl(value, 17) + UINT32_C(0x27d4eb2f);
    value = _rotl(value, 19) ^ UINT32_C(0x165667b1);
    value = _rotl(value, 23) + UINT32_C(0xd3a2646c);
    value = _rotl(value, 29) ^ UINT32_C(0xfd7046c5);
    timer_work_sink = value;
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
    const struct condition condition = decode_condition(kind);
    uint32_t episode, prelude_sum = 0, train_sum = 0, probe_sum = 0;
    uint32_t result;
    uint64_t ticks = 0;

    memset(train_values, condition.train_bit, TRAIN_CALLS);
    memset(probe_values, condition.probe_bit, MAX_PROBE_CALLS);
    for (episode = 0; episode < EPISODES; ++episode) {
        mode_line[0] = 1;
        prelude_sum += run_branch(prelude_values, RESET_CALLS);
        mode_line[0] = condition.is_fixed ? 0 : 1;
        train_sum += run_branch(train_values, TRAIN_CALLS);
        mode_line[0] = 1;
        if (condition.is_fixed || condition.timer == FAST_A || condition.timer == FAST_B)
            ticks += timed_fast(condition.length, &result);
        else if (condition.timer == OLDSMALL)
            ticks += timed_oldsmall(condition.length, &result);
        else if (condition.timer == DOSE4)
            ticks += timed_dose4(condition.length, &result);
        else if (condition.timer == DOSE8)
            ticks += timed_dose8(condition.length, &result);
        else
            ticks += timed_pause(condition.length, &result);
        probe_sum += result;
    }
    /* The assembly always returns live even when the conditional follows
       fixed periodic decisions. Fail before producing a trace if mismatched. */
    if (prelude_sum != EPISODES * RESET_CALLS / 2u ||
        train_sum != EPISODES * TRAIN_CALLS * (uint32_t)condition.train_bit ||
        probe_sum != EPISODES * condition.length * (uint32_t)condition.probe_bit)
        architectural_error = 1;
    prelude_total += prelude_sum;
    train_total += train_sum;
    probe_total += probe_sum;
    sink += prelude_sum + train_sum + probe_sum;
    return ticks;
}

/* Seeded Fisher-Yates per 32-block cycle and full position rotation.
   Replay warm-up and recorded schedules with one continuous RNG state. */
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
        fputs("Usage: b2-calibration-windows.exe <nonzero decimal uint32 seed>\n", stderr);
        return 1;
    }
    errno = 0;
    parsed_seed = strtoull(argv[1], &end_seed, 10);
    if (errno || end_seed == argv[1] || *end_seed != '\0' ||
        parsed_seed == 0 || parsed_seed > UINT32_MAX) {
        fputs("B2CAL_ERROR: expected nonzero decimal uint32 seed\n", stderr);
        return 1;
    }
    seed = (uint32_t)parsed_seed;
    state = seed;
    if (!check_condition_map()) {
        fputs("B2CAL_ERROR: condition mapping does not match labels\n", stderr);
        return 1;
    }
    cache_detect_cpu(&cpu);
    if (!cpu.has_tsc || !cpu.invariant_tsc) {
        fputs("B2CAL_ERROR: invariant TSC is required\n", stderr);
        return 1;
    }
    if (!pin_first_allowed_cpu()) {
        fputs("B2CAL_ERROR: cannot pin one logical CPU\n", stderr);
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
    /* Warm-up architectural sums are excluded from recorded END totals. */
    prelude_total = train_total = probe_total = 0;
    sink = 0;
    for (block = 0; block < BLOCKS; ++block)
        schedule_hash = collect_block(block, &state, order, 1, schedule_hash);
    if (architectural_error) {
        fputs("B2CAL_ERROR: prelude, train or probe output mismatch\n", stderr);
        return 1;
    }

    printf("B2CAL_CPU,vendor=%s,signature=0x%08x,invariant_tsc=%u,hypervisor=%u\n",
           cpu.vendor, cpu.signature, cpu.invariant_tsc,
           ((uint32_t)cpuid[2] >> 31) & 1u);
    printf("B2CAL_RUN,version=2,blocks=%u,conditions=%u,episodes=%u,reset_calls=%u,"
           "train_calls=%u,probe_lengths=1:16,warmup_blocks=%u,seed=%u,"
           "branch_addr=0x%llx,live_addr=0x%llx,fixed_addr=0x%llx,"
           "mode_addr=0x%llx,probe_addr=0x%llx,prelude_addr=0x%llx,"
           "timer=lfence_rdtsc_lfence,"
           "protocol=b2_calibration_same_site_fixed_neutral,compiler=msvc_O2,"
           "schedule_hash=%llu,pattern_hash=%llu\n",
           BLOCKS, CONDITIONS, EPISODES, RESET_CALLS, TRAIN_CALLS,
           WARMUP_BLOCKS, seed,
           (unsigned long long)(uintptr_t)history_b2_branch_site,
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
        printf("B2CAL_SAMPLE,%u,%u,%u,%s,%llu\n", index,
               (unsigned)entry->block, (unsigned)entry->position,
               labels[entry->kind], (unsigned long long)entry->ticks);
    }
    printf("B2CAL_END,count=%u,checksum=%llu,sink=%u,"
           "prelude_total=%llu,train_total=%llu,probe_total=%llu\n",
           BLOCKS * CONDITIONS, (unsigned long long)checksum, sink,
           (unsigned long long)prelude_total, (unsigned long long)train_total,
           (unsigned long long)probe_total);
    fflush(stdout);
    return 0;
}
