/* Same-address conditional branch timing with a balanced 2x2 train/probe design. */
#include "cpu_features.h"

#include <intrin.h>
#include <stdint.h>
#include <stdio.h>
#include <windows.h>

#define BLOCKS 4096u
#define TRAIN_CALLS 128u
#define WARMUP_BLOCKS 32u
#define SEED UINT32_C(0x6e43d1a9)
#define CONDITIONS 4u

struct sample {
    uint64_t ticks;
    uint16_t block;
    uint8_t position;
    uint8_t kind;
};

extern uint8_t spec_branch_site(const volatile uint8_t *condition,
                                const volatile uint8_t *target);

static __declspec(align(64)) volatile uint8_t condition_line[64];
static __declspec(align(64)) volatile uint8_t target_line[64];
static struct sample samples[BLOCKS * CONDITIONS];
static volatile uint32_t sink;
static const char *const labels[CONDITIONS] = {
    "train0_probe0", "train1_probe0", "train0_probe1", "train1_probe1"
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

static uint64_t trial(uint8_t train, uint8_t probe) {
    uint32_t i, training_sum = 0;
    uint8_t result;
    uint64_t start, end;

    condition_line[0] = train;
    for (i = 0; i < TRAIN_CALLS; ++i)
        training_sum += spec_branch_site(condition_line, target_line);

    condition_line[0] = probe;
    /* Keep both data lines resident. Only the final call is timed. */
    training_sum += target_line[0];
    training_sum += condition_line[0];
    _mm_lfence();
    start = __rdtsc();
    _mm_lfence();
    result = spec_branch_site(condition_line, target_line);
    _mm_lfence();
    end = __rdtsc();
    sink += training_sum + result;
    return end - start;
}

static void collect_block(uint32_t block, uint32_t *state, int store) {
    uint8_t order[CONDITIONS] = { 0, 1, 2, 3 };
    uint32_t i;
    for (i = CONDITIONS - 1u; i > 0; --i) {
        uint32_t j = next_random(state) % (i + 1u);
        uint8_t temporary = order[i];
        order[i] = order[j];
        order[j] = temporary;
    }
    for (i = 0; i < CONDITIONS; ++i) {
        uint8_t kind = order[i];
        uint64_t ticks = trial((uint8_t)(kind & 1u), (uint8_t)(kind >> 1));
        if (store) {
            struct sample *entry = &samples[block * CONDITIONS + i];
            entry->ticks = ticks;
            entry->block = (uint16_t)block;
            entry->position = (uint8_t)i;
            entry->kind = kind;
        }
    }
}

int main(void) {
    struct cache_cpu_features cpu;
    uint64_t checksum = 0;
    uint32_t block, index, state = SEED;
    cache_detect_cpu(&cpu);
    if (!cpu.has_tsc) {
        fputs("LAT_ERROR: TSC is required\n", stderr);
        return 1;
    }
    if (!pin_first_allowed_cpu()) {
        fputs("LAT_ERROR: cannot pin one logical CPU\n", stderr);
        return 1;
    }
    condition_line[0] = 0;
    target_line[0] = 1;
    for (block = 0; block < WARMUP_BLOCKS; ++block)
        collect_block(0, &state, 0);
    for (block = 0; block < BLOCKS; ++block)
        collect_block(block, &state, 1);

    printf("LAT_CPU,vendor=%s,signature=0x%08x,invariant_tsc=%u\n",
           cpu.vendor, cpu.signature, cpu.invariant_tsc);
    printf("LAT_RUN,version=1,blocks=%u,training=%u,warmup_blocks=%u,seed=%u,"
           "branch_addr=0x%llx,timer=lfence_rdtsc_lfence\n",
           BLOCKS, TRAIN_CALLS, WARMUP_BLOCKS, SEED,
           (unsigned long long)(uintptr_t)spec_branch_site);
    for (index = 0; index < BLOCKS * CONDITIONS; ++index) {
        const struct sample *entry = &samples[index];
        checksum += (uint64_t)(index + 1u) * entry->ticks +
                    entry->block + entry->position + entry->kind;
        printf("LAT_SAMPLE,%u,%u,%u,%s,%llu\n", index,
               (unsigned)entry->block, (unsigned)entry->position,
               labels[entry->kind], (unsigned long long)entry->ticks);
    }
    printf("LAT_END,count=%u,checksum=%llu,sink=%u\n",
           BLOCKS * CONDITIONS, (unsigned long long)checksum, sink);
    fflush(stdout);
    return 0;
}
