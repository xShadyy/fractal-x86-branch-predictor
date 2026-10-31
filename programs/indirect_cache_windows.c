/* Exploratory same-process indirect-target cache receiver, native Windows x64.
 * A cache hit is an observation, not proof that a wrong-path target ran.
 * Inspect the exact archived PE before attempting any speculative inference.
 */
#include "cache_probe.h"
#include "cpu_features.h"

#include <errno.h>
#include <intrin.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <windows.h>

#define BLOCKS 220u
#define CONDITIONS 22u
#define EPISODES 64u
#define WARMUP_BLOCKS 22u
#define PRELUDE_CALLS 128u
#define TRAIN_CALLS 256u
#define FNV_OFFSET UINT64_C(14695981039346656037)
#define FNV_PRIME UINT64_C(1099511628211)

/* 12 factorial cells, four hot/cold controls, two fixed-training no-call
 * controls, four real-training no-call controls for residual-cache heating. */
enum { ARM_REAL, ARM_FIXED, ARM_SHAM, ARM_HOT, ARM_COLD,
       ARM_SKIP_FIXED, ARM_SKIP_REAL };

struct sample {
    uint64_t reload[EPISODES];
    uint16_t block;
    uint8_t position;
    uint8_t kind;
};

extern uint8_t indirect_cache_site(const volatile uintptr_t *slot,
                                   const volatile uint8_t *zero,
                                   const volatile uint8_t *one);
extern uint8_t indirect_cache_target_zero(void);
extern uint8_t indirect_cache_target_one(void);
extern uint8_t indirect_cache_sham_train(const volatile uint8_t *live);

static __declspec(align(4096)) volatile uint8_t data_zero[4096];
static __declspec(align(4096)) volatile uint8_t data_one[4096];
static __declspec(align(4096)) volatile uintptr_t target_slot[512];
static __declspec(align(64)) uintptr_t target_table[2];
static __declspec(align(64)) volatile uint8_t sham_label[64];
static __declspec(align(64)) uint8_t prelude_pattern[PRELUDE_CALLS];
static __declspec(align(64)) uint8_t fixed_pattern[TRAIN_CALLS];
static __declspec(align(64)) uint8_t constant_pattern[2][TRAIN_CALLS];
static struct sample samples[BLOCKS * CONDITIONS];
static volatile uint32_t sink;
static int architectural_error;

static const char *const labels[CONDITIONS] = {
    "r_t0_p0", "r_t0_p1", "r_t1_p0", "r_t1_p1",
    "f_t0_p0", "f_t0_p1", "f_t1_p0", "f_t1_p1",
    "s_t0_p0", "s_t0_p1", "s_t1_p0", "s_t1_p1",
    "hot_p0", "hot_p1", "cold_p0", "cold_p1",
    "skip_p0", "skip_p1",
    "skipr_t0_p0", "skipr_t0_p1", "skipr_t1_p0", "skipr_t1_p1"
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

static uintptr_t target_address(unsigned bit) {
    return target_table[bit];
}

/* The *same* assembly JMP is reached by the reset, train, and probe phases.
 * The volatile pointer is consumed inside assembly, after we flush its line.
 * Verify the actual physical call path from the archived Windows binary.
 */
static __declspec(noinline) uint32_t invoke_shared(void) {
    return indirect_cache_site(target_slot, data_zero, data_one);
}

static __declspec(noinline) uint32_t run_pattern(const uint8_t *pattern,
                                                 uint32_t count) {
    uint32_t i, total = 0;
    for (i = 0; i < count; ++i) {
        target_slot[0] = target_address(pattern[i]);
        total += invoke_shared();
    }
    return total;
}

static __declspec(noinline) uint32_t run_sham(uint8_t bit) {
    uint32_t i, total = 0;
    sham_label[0] = bit;
    for (i = 0; i < TRAIN_CALLS; ++i)
        total += indirect_cache_sham_train(sham_label);
    return total;
}

/* Flush the two data lines *after* training, and the pointer slot *after*
 * selecting the architectural target. It must be cold when the JMP reads it.
 * Neither the C harness nor the timed reload intentionally accesses the
 * opposite data line between this fence and the indirect call.
 */
static __declspec(noinline) void flush_for_probe(void) {
    _mm_clflush((const void *)data_zero);
    _mm_clflush((const void *)data_one);
    _mm_clflush((const void *)target_slot);
    _mm_mfence();
}

static uint64_t episode(uint8_t kind) {
    uint32_t prelude, train, observed, expected_train;
    unsigned arm = kind < 12u ? kind / 4u :
                   kind < 18u ? ARM_HOT + (kind - 12u) / 2u : ARM_SKIP_REAL;
    unsigned train_bit = kind < 12u ? (kind % 4u) / 2u :
                         kind >= 18u ? (kind - 18u) / 2u : 0u;
    unsigned probe_bit = kind < 12u ? kind % 2u :
                         kind < 18u ? (kind - 12u) % 2u : (kind - 18u) % 2u;
    unsigned architect = arm == ARM_HOT ? 1u - probe_bit : probe_bit;
    const volatile uint8_t *opposite = probe_bit == 0u ? data_one : data_zero;

    /* 0011 activity is a standardized prelude, not a predictor reset. */
    prelude = run_pattern(prelude_pattern, PRELUDE_CALLS);
    if (arm == ARM_REAL || arm == ARM_SKIP_REAL)
        train = run_pattern(constant_pattern[train_bit], TRAIN_CALLS);
    else if (arm == ARM_SHAM) train = run_sham((uint8_t)train_bit);
    else train = run_pattern(fixed_pattern, TRAIN_CALLS);

    target_slot[0] = target_address(architect);
    flush_for_probe();
    observed = arm == ARM_SKIP_FIXED || arm == ARM_SKIP_REAL ? 0u : invoke_shared();
    {
        uint64_t ticks = cache_reload_cycles(opposite);
        expected_train = (arm == ARM_REAL || arm == ARM_SHAM ||
                          arm == ARM_SKIP_REAL) ?
                         TRAIN_CALLS * (1u + train_bit) : TRAIN_CALLS * 3u / 2u;
        if (prelude != PRELUDE_CALLS * 3u / 2u ||
            train != expected_train ||
            observed != (arm == ARM_SKIP_FIXED || arm == ARM_SKIP_REAL ?
                         0u : 1u + architect))
            architectural_error = 1;
        sink += prelude + train + observed;
        return ticks;
    }
}

/* A seeded Fisher-Yates permutation starts each complete 22-block cycle.
 * Rotating all 22 positions across the cycle balances temporal position.
 */
static uint64_t collect_block(uint32_t block, uint32_t *state,
                              uint8_t base_order[CONDITIONS], int store,
                              uint64_t hash) {
    uint32_t i, position, episode_index;
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
        struct sample *entry = store ? &samples[block * CONDITIONS + position] : NULL;
        if (entry) {
            entry->block = (uint16_t)block;
            entry->position = (uint8_t)position;
            entry->kind = kind;
            hash = (hash ^ kind) * FNV_PRIME;
        }
        for (episode_index = 0; episode_index < EPISODES; ++episode_index) {
            uint64_t ticks = episode(kind);
            if (entry) entry->reload[episode_index] = ticks;
        }
    }
    return hash;
}

int main(int argc, char **argv) {
    struct cache_cpu_features cpu;
    int cpuid[4];
    char *end_seed;
    uint8_t order[CONDITIONS] = { 0 };
    uint32_t state, seed, block, index, episode_index, i;
    uint64_t checksum = 0, schedule_hash = FNV_OFFSET;
    unsigned long long parsed_seed;

    if (argc != 2 || argv[1][0] == '-') {
        fputs("Usage: indirect-cache-windows.exe <nonzero decimal uint32 seed>\n", stderr);
        return 1;
    }
    errno = 0;
    parsed_seed = strtoull(argv[1], &end_seed, 10);
    if (errno || end_seed == argv[1] || *end_seed != '\0' ||
        parsed_seed == 0 || parsed_seed > UINT32_MAX) {
        fputs("ICACHE_ERROR: expected a nonzero decimal uint32 seed\n", stderr);
        return 1;
    }
    seed = (uint32_t)parsed_seed;
    state = seed;
    cache_detect_cpu(&cpu);
    if (!cpu.has_tsc || !cpu.invariant_tsc || !cpu.has_clflush ||
        cpu.clflush_bytes != 64u) {
        fputs("ICACHE_ERROR: invariant TSC and 64-byte CLFLUSH are required\n", stderr);
        return 1;
    }
    if (!pin_first_allowed_cpu()) {
        fputs("ICACHE_ERROR: cannot pin one logical CPU\n", stderr);
        return 1;
    }
    data_zero[0] = 1;
    data_one[0] = 2;
    target_table[0] = (uintptr_t)indirect_cache_target_zero;
    target_table[1] = (uintptr_t)indirect_cache_target_one;
    for (i = 0; i < PRELUDE_CALLS; ++i) prelude_pattern[i] = (uint8_t)((i >> 1) & 1u);
    for (i = 0; i < TRAIN_CALLS; ++i) {
        fixed_pattern[i] = (uint8_t)((i >> 1) & 1u);
        constant_pattern[0][i] = 0;
        constant_pattern[1][i] = 1;
    }
    __cpuid(cpuid, 1);
    for (block = 0; block < WARMUP_BLOCKS; ++block)
        (void)collect_block(block, &state, order, 0, 0);
    for (block = 0; block < BLOCKS; ++block)
        schedule_hash = collect_block(block, &state, order, 1, schedule_hash);
    if (architectural_error) {
        fputs("ICACHE_ERROR: wrong architectural reset/train/probe return\n", stderr);
        return 1;
    }

    printf("ICACHE_CPU,vendor=%s,signature=0x%08x,clflush_bytes=%u,"
           "invariant_tsc=%u,hypervisor=%u\n", cpu.vendor, cpu.signature,
           cpu.clflush_bytes, cpu.invariant_tsc, ((uint32_t)cpuid[2] >> 31) & 1u);
    printf("ICACHE_RUN,version=1,blocks=%u,episodes=%u,prelude_calls=%u,"
           "train_calls=%u,probe_calls=1,warmup_blocks=%u,seed=%u,"
           "site_addr=0x%llx,target0_addr=0x%llx,target1_addr=0x%llx,"
           "sham_addr=0x%llx,data0_addr=0x%llx,data1_addr=0x%llx,"
           "slot_addr=0x%llx,timer=lfence_rdtsc_lfence,flush=clflush_mfence,"
           "protocol=indirect_target_cache_receiver,compiler=msvc_O2,"
           "schedule_hash=%llu\n", BLOCKS, EPISODES, PRELUDE_CALLS,
           TRAIN_CALLS, WARMUP_BLOCKS, seed,
           (unsigned long long)(uintptr_t)indirect_cache_site,
           (unsigned long long)(uintptr_t)indirect_cache_target_zero,
           (unsigned long long)(uintptr_t)indirect_cache_target_one,
           (unsigned long long)(uintptr_t)indirect_cache_sham_train,
           (unsigned long long)(uintptr_t)data_zero,
           (unsigned long long)(uintptr_t)data_one,
           (unsigned long long)(uintptr_t)target_slot,
           (unsigned long long)schedule_hash);
    for (index = 0; index < BLOCKS * CONDITIONS; ++index) {
        const struct sample *entry = &samples[index];
        checksum = (checksum + (uint64_t)(index + 1u) + entry->block +
                    entry->position + entry->kind) * FNV_PRIME;
        printf("ICACHE_SAMPLE,%u,%u,%u,%s,", index, (unsigned)entry->block,
               (unsigned)entry->position, labels[entry->kind]);
        for (episode_index = 0; episode_index < EPISODES; ++episode_index) {
            uint64_t ticks = entry->reload[episode_index];
            checksum = (checksum ^ ticks) * FNV_PRIME;
            printf("%s%llu", episode_index == 0 ? "" : ";",
                   (unsigned long long)ticks);
        }
        putchar('\n');
    }
    printf("ICACHE_END,count=%u,checksum=%llu,sink=%u\n",
           BLOCKS * CONDITIONS, (unsigned long long)checksum, sink);
    fflush(stdout);
    return 0;
}
