/* Prospective, same-process B2 real/fixed training outcome experiment.
   The calibrated apparatus controls are measured again in this executable.
   Training/probe timing cannot count mispredictions or establish any
   cross-privilege behavior. */
#include "cpu_features.h"

#include <errno.h>
#include <intrin.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <windows.h>

#define BLOCKS 3200u
#define CONDITIONS 40u
#define PAIRS 20u
#define WARMUP_BLOCKS 40u
#define EPISODES 256u
#define RESET_CALLS 256u
#define TRAIN_CALLS 256u
#define MAX_PROBE_CALLS 16u
#define FNV_OFFSET UINT64_C(14695981039346656037)
#define FNV_PRIME UINT64_C(1099511628211)

enum { REAL_T0, REAL_T1, FIXED_T0, FIXED_T1,
       FAST_A, FAST_B, FAST_C, DOSE4, FAST_D, PAUSE };

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

/* Each p,n stratum contains adjacent real, fixed and apparatus pairs.
   The real trainer varies the branch decision at the same physical site.
   The fixed trainer varies the live byte but keeps periodic 0011 decisions.
   All timer controls have live t=0 training. */
static const char *const labels[CONDITIONS] = {
    "real_t0_p0_n1", "real_t1_p0_n1", "fixed_t0_p0_n1", "fixed_t1_p0_n1",
    "fast_a_p0_n1", "fast_b_p0_n1", "fast_c_p0_n1", "dose4_p0_n1",
    "fast_d_p0_n1", "pause_p0_n1",
    "real_t0_p1_n1", "real_t1_p1_n1", "fixed_t0_p1_n1", "fixed_t1_p1_n1",
    "fast_a_p1_n1", "fast_b_p1_n1", "fast_c_p1_n1", "dose4_p1_n1",
    "fast_d_p1_n1", "pause_p1_n1",
    "real_t0_p0_n16", "real_t1_p0_n16", "fixed_t0_p0_n16", "fixed_t1_p0_n16",
    "fast_a_p0_n16", "fast_b_p0_n16", "fast_c_p0_n16", "dose4_p0_n16",
    "fast_d_p0_n16", "pause_p0_n16",
    "real_t0_p1_n16", "real_t1_p1_n16", "fixed_t0_p1_n16", "fixed_t1_p1_n16",
    "fast_a_p1_n16", "fast_b_p1_n16", "fast_c_p1_n16", "dose4_p1_n16",
    "fast_d_p1_n16", "pause_p1_n16"
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
    uint8_t group = (uint8_t)(kind / 10u);
    decoded.timer = (uint8_t)(kind % 10u);
    decoded.is_fixed = (uint8_t)(decoded.timer == FIXED_T0 ||
                                 decoded.timer == FIXED_T1);
    decoded.length = group < 2u ? 1u : 16u;
    decoded.probe_bit = (uint8_t)(group % 2u);
    decoded.train_bit = (uint8_t)(decoded.timer == REAL_T1 ||
                                  decoded.timer == FIXED_T1);
    return decoded;
}

/* Check all 40 labels, probe lengths, trainer sources, and train bytes. */
static int check_condition_map(void) {
    static const char *const names[10] = {
        "real_t0", "real_t1", "fixed_t0", "fixed_t1", "fast_a",
        "fast_b", "fast_c", "dose4", "fast_d", "pause"
    };
    uint32_t n_index, p, member;
    char expected[64];
    for (n_index = 0; n_index < 2u; ++n_index) {
        uint32_t length = n_index == 0u ? 1u : 16u;
        for (p = 0; p < 2u; ++p) {
            for (member = 0; member < 10u; ++member) {
                uint8_t kind = (uint8_t)(20u * n_index + 10u * p + member);
                struct condition decoded = decode_condition(kind);
                (void)snprintf(expected, sizeof(expected), "%s_p%u_n%u",
                               names[member], p, length);
                if (decoded.is_fixed != (member == FIXED_T0 || member == FIXED_T1) ||
                    decoded.length != length || decoded.probe_bit != p ||
                    decoded.train_bit != (member == REAL_T1 || member == FIXED_T1) ||
                    decoded.timer != member ||
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

/* Real, fixed, and all fast control labels call this exact timed function. */
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
        if (condition.timer == REAL_T0 || condition.timer == REAL_T1 ||
            condition.is_fixed || condition.timer == FAST_A ||
            condition.timer == FAST_B || condition.timer == FAST_C ||
            condition.timer == FAST_D)
            ticks += timed_fast(condition.length, &result);
        else if (condition.timer == DOSE4)
            ticks += timed_dose4(condition.length, &result);
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

/* Within each 40-block cycle, shuffle the 20 adjacent pairs and draw one
   initial order bit per pair. Rotate pairs through all 20 pair slots in each
   half-cycle; invert every pair's member order in the second half. Each
   condition therefore occupies each absolute position once per cycle.
   Replay warm-up and recorded schedules with one continuous RNG state. */
static uint64_t collect_block(uint32_t block, uint32_t *state,
                              uint8_t base_pairs[PAIRS],
                              uint8_t pair_orientation[PAIRS],
                              int store, uint64_t hash) {
    uint32_t i, slot, member;
    if (block % CONDITIONS == 0u) {
        for (i = 0; i < PAIRS; ++i) base_pairs[i] = (uint8_t)i;
        for (i = PAIRS - 1u; i > 0; --i) {
            uint32_t j = next_random(state) % (i + 1u);
            uint8_t temp = base_pairs[i];
            base_pairs[i] = base_pairs[j];
            base_pairs[j] = temp;
        }
        for (i = 0; i < PAIRS; ++i)
            pair_orientation[i] = (uint8_t)(next_random(state) & 1u);
    }
    for (slot = 0; slot < PAIRS; ++slot) {
        const uint8_t pair = base_pairs[(slot + block % PAIRS) % PAIRS];
        const uint8_t flipped = (uint8_t)(pair_orientation[pair] ^
                                          (uint8_t)((block / PAIRS) & 1u));
        for (member = 0; member < 2u; ++member) {
            const uint32_t position = 2u * slot + member;
            const uint8_t kind = (uint8_t)(2u * pair + (member ^ flipped));
            const uint64_t ticks = measure(kind);
            if (store) {
                struct sample *entry = &samples[block * CONDITIONS + position];
                entry->ticks = ticks;
                entry->block = (uint16_t)block;
                entry->position = (uint8_t)position;
                entry->kind = kind;
                hash = (hash ^ kind) * FNV_PRIME;
            }
        }
    }
    return hash;
}

int main(int argc, char **argv) {
    struct cache_cpu_features cpu;
    int cpuid[4];
    char *end_seed;
    uint8_t pair_order[PAIRS] = { 0 };
    uint8_t pair_orientation[PAIRS] = { 0 };
    uint32_t state, seed, block, index, i;
    uint64_t checksum = 0, schedule_hash = FNV_OFFSET;
    uint64_t pattern_hash = FNV_OFFSET;
    unsigned long long parsed_seed;

    if (argc != 2 || argv[1][0] == '-') {
        fputs("Usage: b2-outcome-windows.exe <nonzero decimal uint32 seed>\n", stderr);
        return 1;
    }
    errno = 0;
    parsed_seed = strtoull(argv[1], &end_seed, 10);
    if (errno || end_seed == argv[1] || *end_seed != '\0' ||
        parsed_seed == 0 || parsed_seed > UINT32_MAX) {
        fputs("B2OUT_ERROR: expected nonzero decimal uint32 seed\n", stderr);
        return 1;
    }
    seed = (uint32_t)parsed_seed;
    state = seed;
    if (!check_condition_map()) {
        fputs("B2OUT_ERROR: condition mapping does not match labels\n", stderr);
        return 1;
    }
    cache_detect_cpu(&cpu);
    if (!cpu.has_tsc || !cpu.invariant_tsc) {
        fputs("B2OUT_ERROR: invariant TSC is required\n", stderr);
        return 1;
    }
    if (!pin_first_allowed_cpu()) {
        fputs("B2OUT_ERROR: cannot pin one logical CPU\n", stderr);
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
        (void)collect_block(block, &state, pair_order, pair_orientation, 0, 0);
    /* Warm-up architectural sums are excluded from recorded END totals. */
    prelude_total = train_total = probe_total = 0;
    sink = 0;
    for (block = 0; block < BLOCKS; ++block)
        schedule_hash = collect_block(block, &state, pair_order,
                                      pair_orientation, 1, schedule_hash);
    if (architectural_error) {
        fputs("B2OUT_ERROR: prelude, train or probe output mismatch\n", stderr);
        return 1;
    }

    printf("B2OUT_CPU,vendor=%s,signature=0x%08x,invariant_tsc=%u,hypervisor=%u\n",
           cpu.vendor, cpu.signature, cpu.invariant_tsc,
           ((uint32_t)cpuid[2] >> 31) & 1u);
    printf("B2OUT_RUN,version=4,blocks=%u,conditions=%u,pairs=%u,"
           "episodes=%u,reset_calls=%u,"
           "train_calls=%u,probe_lengths=1:16,warmup_blocks=%u,seed=%u,"
           "branch_addr=0x%llx,live_addr=0x%llx,fixed_addr=0x%llx,"
           "mode_addr=0x%llx,probe_addr=0x%llx,prelude_addr=0x%llx,"
           "timer=lfence_rdtsc_lfence,"
           "protocol=b2_adjacent_same_site_outcome,compiler=msvc_O2,"
           "schedule_hash=%llu,pattern_hash=%llu\n",
           BLOCKS, CONDITIONS, PAIRS, EPISODES, RESET_CALLS, TRAIN_CALLS,
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
        printf("B2OUT_SAMPLE,%u,%u,%u,%s,%llu\n", index,
               (unsigned)entry->block, (unsigned)entry->position,
               labels[entry->kind], (unsigned long long)entry->ticks);
    }
    printf("B2OUT_END,count=%u,checksum=%llu,sink=%u,"
           "prelude_total=%llu,train_total=%llu,probe_total=%llu\n",
           BLOCKS * CONDITIONS, (unsigned long long)checksum, sink,
           (unsigned long long)prelude_total, (unsigned long long)train_total,
           (unsigned long long)probe_total);
    fflush(stdout);
    return 0;
}
