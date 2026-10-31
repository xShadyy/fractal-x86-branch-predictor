/* Pre-training path-history preparation sweep in one Windows user process.
 * Fixed work within each prelude length; no direct PHR-length inference.
 */
#include "cpu_features.h"

#include <errno.h>
#include <intrin.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <windows.h>

#define PATTERNS 4u
#define LENGTHS 2u
#define ARMS 3u
#define MAIN_CONDITIONS (LENGTHS * PATTERNS * ARMS * 2u * 2u)
#define CONDITIONS (MAIN_CONDITIONS + LENGTHS * 2u * 3u)
#define BLOCKS 864u
#define WARMUP_BLOCKS 108u
#define EPISODES 32u
#define TRAIN_CALLS 32u
#define PROBE_CALLS 1u
#define MAX_PRELUDE 256u
#define FNV_OFFSET UINT64_C(14695981039346656037)
#define FNV_PRIME UINT64_C(1099511628211)

struct sample {
    uint64_t ticks;
    uint16_t block;
    uint8_t position;
    uint8_t kind;
};

extern uint8_t prelude_branch_site(const volatile uint8_t *live,
                                   const volatile uint8_t *fixed,
                                   const volatile uint8_t *mode);
extern uint8_t prelude_sham_site(const volatile uint8_t *live);
extern uint32_t prelude_small_work(uint32_t result);

static const uint16_t lengths[LENGTHS] = { 128u, 256u };
static const char *const pattern_names[PATTERNS] = { "p4", "p32", "c0", "c1" };
static __declspec(align(64)) volatile uint8_t live_line[64];
static __declspec(align(64)) volatile uint8_t fixed_line[64];
static __declspec(align(64)) volatile uint8_t mode_line[64];
static __declspec(align(64)) uint8_t prelude_values[PATTERNS][MAX_PRELUDE];
static __declspec(align(64)) uint8_t fixed_values[MAX_PRELUDE];
static __declspec(align(64)) uint8_t train_values[TRAIN_CALLS];
static __declspec(align(64)) uint8_t probe_values[PROBE_CALLS];
static struct sample samples[BLOCKS * CONDITIONS];
static volatile uint32_t sink;
static int architectural_error;

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

/* One physical C direct-call site for every prelude, real/fixed training and
 * measured probe. Distinct noinline sham routine is secondary only.
 */
static __declspec(noinline) uint32_t run_site(const uint8_t *values,
                                               uint32_t count) {
    uint32_t i, total = 0;
    for (i = 0; i < count; ++i) {
        live_line[0] = values[i];
        fixed_line[0] = fixed_values[i & (MAX_PRELUDE - 1u)];
        total += prelude_branch_site(live_line, fixed_line, mode_line);
    }
    return total;
}

static __declspec(noinline) uint32_t run_sham(const uint8_t *values,
                                               uint32_t count) {
    uint32_t i, total = 0;
    for (i = 0; i < count; ++i) {
        live_line[0] = values[i];
        total += prelude_sham_site(live_line);
    }
    return total;
}

static __declspec(noinline) uint64_t timed_fast(uint32_t *result) {
    uint64_t start, end;
    _mm_lfence(); start = __rdtsc(); _mm_lfence();
    *result = run_site(probe_values, PROBE_CALLS);
    _mm_lfence(); end = __rdtsc();
    return end - start;
}

static __declspec(noinline) uint64_t timed_small(uint32_t *result,
                                                  uint32_t *work) {
    uint64_t start, end;
    _mm_lfence(); start = __rdtsc(); _mm_lfence();
    *result = run_site(probe_values, PROBE_CALLS);
    *work = prelude_small_work(*result);
    _mm_lfence(); end = __rdtsc();
    return end - start;
}

static __declspec(noinline) uint64_t timed_pause(uint32_t *result) {
    uint64_t start, end;
    _mm_lfence(); start = __rdtsc(); _mm_lfence();
    *result = run_site(probe_values, PROBE_CALLS);
    _mm_pause();
    _mm_lfence(); end = __rdtsc();
    return end - start;
}

static uint32_t prelude_sum_expected(uint32_t pattern, uint32_t length) {
    if (pattern == 2u) return 0u;
    if (pattern == 3u) return length;
    return length / 2u;
}

static uint64_t measure(uint8_t kind) {
    uint32_t length_index, pattern, arm, train_bit, probe_bit, timer;
    uint32_t episode, prelude_sum = 0, train_sum = 0, probe_sum = 0;
    uint32_t result = 0, work = 0;
    uint64_t ticks = 0;
    if (kind < MAIN_CONDITIONS) {
        length_index = kind / (PATTERNS * ARMS * 4u);
        pattern = (kind / (ARMS * 4u)) % PATTERNS;
        arm = (kind / 4u) % ARMS;
        train_bit = (kind / 2u) % 2u;
        probe_bit = kind % 2u;
        timer = 0u;
    } else {
        uint32_t timer_index = kind - MAIN_CONDITIONS;
        length_index = timer_index / 6u;
        pattern = 0u; /* p4 reference at both prelude lengths. */
        arm = 0u;
        train_bit = 0u;
        probe_bit = (timer_index / 3u) % 2u;
        timer = timer_index % 3u;
    }
    memset(train_values, (int)train_bit, TRAIN_CALLS);
    probe_values[0] = (uint8_t)probe_bit;
    for (episode = 0; episode < EPISODES; ++episode) {
        mode_line[0] = 1u;
        prelude_sum += run_site(prelude_values[pattern], lengths[length_index]);
        mode_line[0] = arm == 1u ? 0u : 1u;
        train_sum += arm == 2u ? run_sham(train_values, TRAIN_CALLS) :
                                  run_site(train_values, TRAIN_CALLS);
        mode_line[0] = 1u;
        work = 0u;
        if (timer == 1u) ticks += timed_small(&result, &work);
        else if (timer == 2u) ticks += timed_pause(&result);
        else ticks += timed_fast(&result);
        probe_sum += result;
        sink += work;
    }
    if (prelude_sum != EPISODES * prelude_sum_expected(pattern, lengths[length_index]) ||
        train_sum != EPISODES * TRAIN_CALLS * train_bit ||
        probe_sum != EPISODES * PROBE_CALLS * probe_bit)
        architectural_error = 1;
    sink += prelude_sum + train_sum + probe_sum;
    return ticks;
}

static uint64_t collect_block(uint32_t block, uint32_t *state,
                              uint8_t base[CONDITIONS], int store,
                              uint64_t hash) {
    uint32_t i, position;
    if (block % CONDITIONS == 0u) {
        for (i = 0; i < CONDITIONS; ++i) base[i] = (uint8_t)i;
        for (i = CONDITIONS - 1u; i > 0; --i) {
            uint32_t j = next_random(state) % (i + 1u);
            uint8_t value = base[i];
            base[i] = base[j];
            base[j] = value;
        }
    }
    for (position = 0; position < CONDITIONS; ++position) {
        uint8_t kind = base[(position + block % CONDITIONS) % CONDITIONS];
        uint64_t ticks = measure(kind);
        if (store) {
            struct sample *row = &samples[block * CONDITIONS + position];
            row->ticks = ticks;
            row->block = (uint16_t)block;
            row->position = (uint8_t)position;
            row->kind = kind;
            hash = (hash ^ kind) * FNV_PRIME;
        }
    }
    return hash;
}

static void print_kind(uint8_t kind) {
    if (kind < MAIN_CONDITIONS) {
        uint32_t n = kind / (PATTERNS * ARMS * 4u);
        uint32_t pat = (kind / (ARMS * 4u)) % PATTERNS;
        uint32_t arm = (kind / 4u) % ARMS;
        printf("n%u_%s_%s_t%u_p%u", (unsigned)lengths[n],
               pattern_names[pat], arm == 0u ? "real" :
               arm == 1u ? "fixed" : "sham",
               (unsigned)(kind / 2u) % 2u, (unsigned)kind % 2u);
    } else {
        uint32_t x = kind - MAIN_CONDITIONS;
        printf("n%u_p4_timer_%s_p%u", (unsigned)lengths[x / 6u],
               (x % 3u) == 0u ? "fast" : (x % 3u) == 1u ? "small" : "pause",
               (unsigned)(x / 3u) % 2u);
    }
}

int main(int argc, char **argv) {
    struct cache_cpu_features cpu;
    int cpuid[4];
    char *end_seed;
    uint8_t order[CONDITIONS] = { 0 };
    uint32_t state, seed, block, index, i;
    uint64_t checksum = 0, hash = FNV_OFFSET;
    unsigned long long parsed_seed;
    if (argc != 2 || argv[1][0] == '-') {
        fputs("Usage: prelude-sweep-windows.exe <nonzero decimal uint32 seed>\n", stderr);
        return 1;
    }
    errno = 0;
    parsed_seed = strtoull(argv[1], &end_seed, 10);
    if (errno || end_seed == argv[1] || *end_seed != '\0' ||
        parsed_seed == 0 || parsed_seed > UINT32_MAX) {
        fputs("PRELUDE_ERROR: expected nonzero decimal uint32 seed\n", stderr);
        return 1;
    }
    seed = (uint32_t)parsed_seed;
    state = seed;
    cache_detect_cpu(&cpu);
    if (!cpu.has_tsc || !cpu.invariant_tsc || !pin_first_allowed_cpu()) {
        fputs("PRELUDE_ERROR: invariant TSC and single-CPU affinity required\n", stderr);
        return 1;
    }
    for (i = 0; i < MAX_PRELUDE; ++i) {
        prelude_values[0][i] = (uint8_t)((i >> 1) & 1u);
        prelude_values[1][i] = (uint8_t)((i >> 4) & 1u);
        prelude_values[2][i] = 0;
        prelude_values[3][i] = 1;
        fixed_values[i] = prelude_values[0][i];
    }
    __cpuid(cpuid, 1);
    for (block = 0; block < WARMUP_BLOCKS; ++block)
        (void)collect_block(block, &state, order, 0, 0);
    for (block = 0; block < BLOCKS; ++block)
        hash = collect_block(block, &state, order, 1, hash);
    if (architectural_error) {
        fputs("PRELUDE_ERROR: architectural return mismatch\n", stderr);
        return 1;
    }
    printf("PRELUDE_CPU,vendor=%s,signature=0x%08x,invariant_tsc=%u,hypervisor=%u\n",
           cpu.vendor, cpu.signature, cpu.invariant_tsc,
           ((uint32_t)cpuid[2] >> 31) & 1u);
    printf("PRELUDE_RUN,version=1,blocks=%u,conditions=%u,episodes=%u,"
           "prelude_lengths=128_256,patterns=p4_p32_c0_c1,train_calls=%u,"
           "probe_calls=%u,warmup_blocks=%u,seed=%u,"
           "branch_addr=0x%llx,sham_addr=0x%llx,small_addr=0x%llx,"
           "timer=lfence_rdtsc_lfence,protocol=prelude_pattern_by_length,"
           "compiler=msvc_O2,schedule_hash=%llu\n",
           BLOCKS, CONDITIONS, EPISODES, TRAIN_CALLS, PROBE_CALLS,
           WARMUP_BLOCKS, seed,
           (unsigned long long)(uintptr_t)prelude_branch_site,
           (unsigned long long)(uintptr_t)prelude_sham_site,
           (unsigned long long)(uintptr_t)prelude_small_work,
           (unsigned long long)hash);
    for (index = 0; index < BLOCKS * CONDITIONS; ++index) {
        const struct sample *row = &samples[index];
        checksum += (uint64_t)(index + 1u) * row->ticks +
                    row->block + row->position + row->kind;
        printf("PRELUDE_SAMPLE,%u,%u,%u,", index, (unsigned)row->block,
               (unsigned)row->position);
        print_kind(row->kind);
        printf(",%llu\n", (unsigned long long)row->ticks);
    }
    printf("PRELUDE_END,count=%u,checksum=%llu,sink=%u\n",
           BLOCKS * CONDITIONS, (unsigned long long)checksum, sink);
    fflush(stdout);
    return 0;
}
