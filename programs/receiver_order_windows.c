/* K2: condition-entry diagnostic after K1's exploratory early skip hits.
 * Grouped and interleaved schedules use the same assembly branch site and
 * per-episode work. K2 cannot by itself establish transient execution.
 */
#include "cache_probe.h"
#include "cpu_features.h"

#include <errno.h>
#include <intrin.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <windows.h>

#define BLOCKS 256u
#define MODES 2u
#define CONDITIONS 16u
#define EPISODES 64u
#define WARMUP_BLOCKS 16u
#define PRELUDE_CALLS 128u
#define TRAIN_CALLS 256u
#define FNV_OFFSET UINT64_C(14695981039346656037)
#define FNV_PRIME UINT64_C(1099511628211)

enum { CAND_T0, CAND_T1, NO_PROBE_T0, NO_PROBE_T1,
       HOT, COLD, ARCH_LOAD, ARCH_SKIP };
enum { GROUPED, INTERLEAVED };

struct sample {
    uint64_t reload[EPISODES];
    uint16_t block;
    uint8_t mode;
    uint8_t position;
    uint8_t kind;
};

extern uint8_t conditional_receiver_site(const volatile uint8_t *condition,
                                         const volatile uint8_t *target0,
                                         const volatile uint8_t *target1);
extern uint8_t conditional_receiver_target_zero(void);
extern uint8_t conditional_receiver_target_one(void);

static __declspec(align(4096)) volatile uint8_t condition_line[4096];
static __declspec(align(4096)) volatile uint8_t target_zero[4096];
static __declspec(align(4096)) volatile uint8_t target_one[4096];
static const uint8_t prelude_pattern[PRELUDE_CALLS] = {
    0, 0, 1, 1, 0, 0, 1, 1, 0, 0, 1, 1, 0, 0, 1, 1,
    0, 0, 1, 1, 0, 0, 1, 1, 0, 0, 1, 1, 0, 0, 1, 1,
    0, 0, 1, 1, 0, 0, 1, 1, 0, 0, 1, 1, 0, 0, 1, 1,
    0, 0, 1, 1, 0, 0, 1, 1, 0, 0, 1, 1, 0, 0, 1, 1,
    0, 0, 1, 1, 0, 0, 1, 1, 0, 0, 1, 1, 0, 0, 1, 1,
    0, 0, 1, 1, 0, 0, 1, 1, 0, 0, 1, 1, 0, 0, 1, 1,
    0, 0, 1, 1, 0, 0, 1, 1, 0, 0, 1, 1, 0, 0, 1, 1,
    0, 0, 1, 1, 0, 0, 1, 1, 0, 0, 1, 1, 0, 0, 1, 1
};
static __declspec(align(64)) uint8_t fixed_pattern[TRAIN_CALLS];
static struct sample samples[BLOCKS * MODES * CONDITIONS];
static volatile uint32_t sink;
static uint64_t prelude_total, train_total, probe_total;
static int architectural_error;
static const char *const labels[CONDITIONS] = {
    "candidate_t0_p0", "candidate_t1_p0", "no_probe_t0_p0", "no_probe_t1_p0",
    "hot_p0", "cold_p0", "arch_load_p0", "arch_skip_p0",
    "candidate_t0_p1", "candidate_t1_p1", "no_probe_t0_p1", "no_probe_t1_p1",
    "hot_p1", "cold_p1", "arch_load_p1", "arch_skip_p1"
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

/* This is the sole C call site to the assembly branch. Its body is used for
 * prelude, training, and probes. Probe condition is set before any flush.
 */
static __declspec(noinline) uint32_t invoke_shared(void) {
    return conditional_receiver_site(condition_line, target_zero, target_one);
}

static __declspec(noinline) uint32_t run_pattern(const uint8_t *pattern,
                                                uint32_t count) {
    uint32_t i, total = 0;
    for (i = 0; i < count; ++i) {
        condition_line[0] = pattern[i];
        total += invoke_shared();
    }
    return total;
}

static __declspec(noinline) uint32_t train_constant(uint8_t bit) {
    uint32_t i, total = 0;
    for (i = 0; i < TRAIN_CALLS; ++i) {
        condition_line[0] = bit;
        total += invoke_shared();
    }
    return total;
}

/* Flush both target data lines after the trainer's architectural loads, then
 * flush the condition line last. Do not write/dereference condition or target
 * data between this function and the optional branch probe/reload. */
static __declspec(noinline) void flush_probe_lines(void) {
    _mm_clflush((const void *)target_zero);
    _mm_clflush((const void *)target_one);
    _mm_clflush((const void *)condition_line);
    _mm_mfence();
}

/* All choices of episode kind occur before this function flushes the lines.
 * The candidate/skip post-flush path cannot branch into the HOT touch in its
 * own function. Linked-code inspection is still required on the host.
 */
static __declspec(noinline) void prepare_episode(uint8_t kind,
                                                 uint32_t *prelude,
                                                 uint32_t *train,
                                                 uint8_t *probe_bit) {
    const uint8_t p = (uint8_t)(kind / 8u);
    const uint8_t member = (uint8_t)(kind % 8u);
    const uint8_t t = (uint8_t)(member == CAND_T1 || member == NO_PROBE_T1);
    *probe_bit = (uint8_t)(member == ARCH_LOAD ? 1u - p : p);
    *prelude = run_pattern(prelude_pattern, PRELUDE_CALLS);
    if (member == HOT || member == COLD)
        *train = run_pattern(fixed_pattern, TRAIN_CALLS);
    else
        *train = train_constant((uint8_t)(member == ARCH_LOAD ||
                                         member == ARCH_SKIP ? p : t));
    condition_line[0] = *probe_bit;
    flush_probe_lines();
}

static void account_episode(uint8_t kind, uint32_t prelude, uint32_t train,
                            uint32_t observed, uint8_t probe_bit,
                            uint32_t *prelude_sum, uint32_t *train_sum,
                            uint32_t *probe_sum) {
    const uint8_t p = (uint8_t)(kind / 8u);
    const uint8_t member = (uint8_t)(kind % 8u);
    const uint8_t t = (uint8_t)(member == CAND_T1 || member == NO_PROBE_T1);
    const uint32_t expected_train = member == HOT || member == COLD ?
                                    TRAIN_CALLS * 3u / 2u :
                                    TRAIN_CALLS * (1u + (member == ARCH_LOAD ||
                                                        member == ARCH_SKIP ? p : t));
    const uint32_t expected_probe = member == CAND_T0 || member == CAND_T1 ||
                                    member == ARCH_LOAD || member == ARCH_SKIP ?
                                    1u + probe_bit : 0u;
    if (prelude != PRELUDE_CALLS * 3u / 2u || train != expected_train ||
        observed != expected_probe) architectural_error = 1;
    *prelude_sum += prelude;
    *train_sum += train;
    *probe_sum += observed;
}

static __declspec(noinline) uint64_t episode_branch(
    uint8_t kind, uint32_t *prelude_sum, uint32_t *train_sum,
    uint32_t *probe_sum) {
    const volatile uint8_t *opposite = kind / 8u == 0u ? target_one : target_zero;
    uint32_t prelude, train, observed;
    uint8_t probe_bit;
    uint64_t ticks;
    prepare_episode(kind, &prelude, &train, &probe_bit);
    observed = invoke_shared();
    ticks = cache_reload_cycles(opposite);
    account_episode(kind, prelude, train, observed, probe_bit,
                    prelude_sum, train_sum, probe_sum);
    return ticks;
}

static __declspec(noinline) uint64_t episode_no_probe(
    uint8_t kind, uint32_t *prelude_sum, uint32_t *train_sum,
    uint32_t *probe_sum) {
    const volatile uint8_t *opposite = kind / 8u == 0u ? target_one : target_zero;
    uint32_t prelude, train;
    uint8_t probe_bit;
    uint64_t ticks;
    prepare_episode(kind, &prelude, &train, &probe_bit);
    ticks = cache_reload_cycles(opposite);
    account_episode(kind, prelude, train, 0u, probe_bit,
                    prelude_sum, train_sum, probe_sum);
    return ticks;
}

static __declspec(noinline) uint64_t episode_hot(
    uint8_t kind, uint32_t *prelude_sum, uint32_t *train_sum,
    uint32_t *probe_sum) {
    const volatile uint8_t *opposite = kind / 8u == 0u ? target_one : target_zero;
    uint32_t prelude, train;
    uint8_t probe_bit;
    uint64_t ticks;
    prepare_episode(kind, &prelude, &train, &probe_bit);
    (void)cache_touch_line(opposite);
    ticks = cache_reload_cycles(opposite);
    account_episode(kind, prelude, train, 0u, probe_bit,
                    prelude_sum, train_sum, probe_sum);
    return ticks;
}

static uint64_t episode(uint8_t kind, uint32_t *prelude_sum,
                        uint32_t *train_sum, uint32_t *probe_sum) {
    const uint8_t member = (uint8_t)(kind % 8u);
    if (member == HOT)
        return episode_hot(kind, prelude_sum, train_sum, probe_sum);
    if (member == COLD || member == NO_PROBE_T0 || member == NO_PROBE_T1)
        return episode_no_probe(kind, prelude_sum, train_sum, probe_sum);
    return episode_branch(kind, prelude_sum, train_sum, probe_sum);
}

/* One shuffle per 16-block cycle. Mode order alternates with seed parity.
 * Both modes use the same rotated condition order in a block. */
static uint64_t collect_block(uint32_t block, uint32_t *state,
                              uint8_t base_order[CONDITIONS],
                              uint32_t seed, int store, uint64_t hash) {
    uint32_t i, mode_position, position;
    if (block % CONDITIONS == 0u) {
        for (i = 0; i < CONDITIONS; ++i) base_order[i] = (uint8_t)i;
        for (i = CONDITIONS - 1u; i > 0; --i) {
            const uint32_t j = next_random(state) % (i + 1u);
            const uint8_t tmp = base_order[i];
            base_order[i] = base_order[j];
            base_order[j] = tmp;
        }
    }
    for (mode_position = 0; mode_position < MODES; ++mode_position) {
        const uint8_t mode = (uint8_t)(((block + (seed & 1u)) & 1u) ^ mode_position);
        struct sample *cell = store ? &samples[(block * MODES + mode_position) *
                                               CONDITIONS] : NULL;
        for (position = 0; position < CONDITIONS; ++position) {
            const uint8_t kind = base_order[(position + block % CONDITIONS) % CONDITIONS];
            if (cell) {
                cell[position].block = (uint16_t)block;
                cell[position].mode = mode;
                cell[position].position = (uint8_t)position;
                cell[position].kind = kind;
            }
        }
        for (i = 0; i < CONDITIONS * EPISODES; ++i) {
            const uint32_t idx = mode == GROUPED ? i / EPISODES : i % CONDITIONS;
            const uint32_t occurrence = mode == GROUPED ? i % EPISODES : i / CONDITIONS;
            const uint8_t kind = base_order[(idx + block % CONDITIONS) % CONDITIONS];
            uint32_t prelude_sum = 0, train_sum = 0, probe_sum = 0;
            const uint64_t ticks = episode(kind, &prelude_sum, &train_sum, &probe_sum);
            if (cell) cell[idx].reload[occurrence] = ticks;
            if (store) {
                const uint64_t event_tag = (uint64_t)mode * 1024u +
                                           (uint64_t)kind * 64u + occurrence;
                hash = (hash ^ event_tag) * FNV_PRIME;
                prelude_total += prelude_sum;
                train_total += train_sum;
                probe_total += probe_sum;
                sink += prelude_sum + train_sum + probe_sum;
            }
        }
    }
    return hash;
}

int main(int argc, char **argv) {
    struct cache_cpu_features cpu;
    int cpuid[4];
    char *end_seed;
    uint8_t order[CONDITIONS] = { 0 };
    uint32_t state, seed, block, index, repeat;
    uint64_t checksum = 0, schedule_hash = FNV_OFFSET;
    unsigned long long parsed_seed;

    if (argc != 2 || argv[1][0] == '-') {
        fputs("Usage: receiver-order-windows.exe <nonzero decimal uint32 seed>\n", stderr);
        return 1;
    }
    errno = 0;
    parsed_seed = strtoull(argv[1], &end_seed, 10);
    if (errno || end_seed == argv[1] || *end_seed != '\0' ||
        parsed_seed == 0 || parsed_seed > UINT32_MAX) {
        fputs("KORD_ERROR: expected nonzero decimal uint32 seed\n", stderr);
        return 1;
    }
    seed = (uint32_t)parsed_seed;
    state = seed;
    cache_detect_cpu(&cpu);
    if (!cpu.has_tsc || !cpu.invariant_tsc || !cpu.has_clflush ||
        cpu.clflush_bytes != 64u) {
        fputs("KORD_ERROR: invariant TSC and 64-byte CLFLUSH required\n", stderr);
        return 1;
    }
    if (!pin_first_allowed_cpu()) {
        fputs("KORD_ERROR: cannot pin a logical CPU\n", stderr);
        return 1;
    }
    target_zero[0] = 1;
    target_one[0] = 2;
    condition_line[0] = 0;
    for (index = 0; index < TRAIN_CALLS; ++index)
        fixed_pattern[index] = (uint8_t)((index >> 1) & 1u);
    if (((uintptr_t)target_zero & 63u) != 0u ||
        ((uintptr_t)target_one & 63u) != 0u ||
        ((uintptr_t)condition_line & 63u) != 0u ||
        ((uintptr_t)target_zero >> 12) == ((uintptr_t)target_one >> 12) ||
        ((uintptr_t)condition_line >> 12) == ((uintptr_t)target_zero >> 12) ||
        ((uintptr_t)condition_line >> 12) == ((uintptr_t)target_one >> 12)) {
        fputs("KORD_ERROR: condition and target lines overlap or are misaligned\n", stderr);
        return 1;
    }
    if (((uintptr_t)conditional_receiver_target_zero >> 6) ==
        ((uintptr_t)conditional_receiver_target_one >> 6)) {
        fputs("KORD_ERROR: conditional target code bodies share a cache line\n", stderr);
        return 1;
    }
    __cpuid(cpuid, 1);
    for (block = 0; block < WARMUP_BLOCKS; ++block)
        (void)collect_block(block, &state, order, seed, 0, 0);
    sink = 0;
    for (block = 0; block < BLOCKS; ++block)
        schedule_hash = collect_block(block, &state, order, seed, 1, schedule_hash);
    if (architectural_error) {
        fputs("KORD_ERROR: observed branch return disagrees with intended path\n", stderr);
        return 1;
    }

    printf("KORD_CPU,vendor=%s,signature=0x%08x,clflush_bytes=%u,"
           "invariant_tsc=%u,hypervisor=%u\n", cpu.vendor, cpu.signature,
           cpu.clflush_bytes, cpu.invariant_tsc, ((uint32_t)cpuid[2] >> 31) & 1u);
    printf("KORD_RUN,version=1,blocks=%u,modes=%u,conditions=%u,episodes=%u,"
           "prelude_calls=%u,train_calls=%u,warmup_blocks=%u,seed=%u,"
           "branch_addr=0x%llx,condition_addr=0x%llx,"
           "target0_addr=0x%llx,target1_addr=0x%llx,"
           "line0_addr=0x%llx,line1_addr=0x%llx,"
           "timer=lfence_rdtsc_lfence,flush=clflush_mfence,"
           "protocol=receiver_order_diagnostic,compiler=msvc_O2,"
           "schedule_hash=%llu\n",
           BLOCKS, MODES, CONDITIONS, EPISODES, PRELUDE_CALLS, TRAIN_CALLS,
           WARMUP_BLOCKS, seed,
           (unsigned long long)(uintptr_t)conditional_receiver_site,
           (unsigned long long)(uintptr_t)condition_line,
           (unsigned long long)(uintptr_t)conditional_receiver_target_zero,
           (unsigned long long)(uintptr_t)conditional_receiver_target_one,
           (unsigned long long)(uintptr_t)target_zero,
           (unsigned long long)(uintptr_t)target_one,
           (unsigned long long)schedule_hash);
    for (index = 0; index < BLOCKS * MODES * CONDITIONS; ++index) {
        const struct sample *entry = &samples[index];
        printf("KORD_SAMPLE,%u,%u,%s,%u,%s,", index, (unsigned)entry->block,
               entry->mode == GROUPED ? "grouped" : "interleaved",
               (unsigned)entry->position, labels[entry->kind]);
        for (repeat = 0; repeat < EPISODES; ++repeat) {
            const uint64_t ticks = entry->reload[repeat];
            checksum += (uint64_t)(index + 1u) * ticks + entry->block +
                        entry->mode + entry->position + entry->kind;
            printf("%s%llu", repeat ? ";" : "", (unsigned long long)ticks);
        }
        putchar('\n');
    }
    printf("KORD_END,count=%u,checksum=%llu,sink=%u,prelude_total=%llu,"
           "train_total=%llu,probe_total=%llu\n",
           BLOCKS * MODES * CONDITIONS, (unsigned long long)checksum, sink,
           (unsigned long long)prelude_total, (unsigned long long)train_total,
           (unsigned long long)probe_total);
    fflush(stdout);
    return 0;
}
