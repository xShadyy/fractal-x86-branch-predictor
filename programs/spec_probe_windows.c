/* Single-process train/probe experiment on a fixed conditional branch site. */
#include "cache_probe.h"
#include "cpu_features.h"

#include <stdint.h>
#include <stdio.h>
#include <windows.h>

#define BLOCKS 1024u
#define TRAIN_CALLS 128u
#define WARMUP_BLOCKS 32u
#define SEED UINT32_C(0x5d17b4c3)
#define CLASS_COUNT 4u

enum sample_kind { TRAIN_TAKEN = 0, TRAIN_NOT_TAKEN = 1,
                   HOT = 2, COLD = 3 };

struct sample {
    uint64_t cycles;
    uint16_t block;
    uint8_t position;
    uint8_t kind;
};

extern uint8_t spec_branch_site(const volatile uint8_t *condition,
                                const volatile uint8_t *target);

static __declspec(align(4096)) volatile uint8_t condition_line[4096];
static __declspec(align(4096)) volatile uint8_t sentinel_line[4096];
static uint8_t pair_order[BLOCKS];
static struct sample samples[BLOCKS * CLASS_COUNT];
static volatile uint32_t sink;
static const char *const kind_names[CLASS_COUNT] = {
    "train_taken", "train_not_taken", "hot", "cold"
};

static uint32_t next_random(uint32_t *state) {
    uint32_t value = *state;
    value ^= value << 13;
    value ^= value >> 17;
    value ^= value << 5;
    *state = value;
    return value;
}

static void prepare_order(void) {
    uint32_t state = SEED;
    uint32_t i;
    for (i = 0; i < BLOCKS; ++i) pair_order[i] = (uint8_t)(i & 1u);
    for (i = BLOCKS - 1u; i > 0; --i) {
        uint32_t j = next_random(&state) % (i + 1u);
        uint8_t temporary = pair_order[i];
        pair_order[i] = pair_order[j];
        pair_order[j] = temporary;
    }
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

static uint64_t speculative_trial(uint8_t train_taken) {
    uint32_t training_sum = 0;
    uint32_t i;
    uint8_t probe_result;
    uint64_t cycles;

    condition_line[0] = train_taken;
    for (i = 0; i < TRAIN_CALLS; ++i)
        training_sum += spec_branch_site(condition_line, sentinel_line);

    /* The observed call always skips the target. Delay branch resolution. */
    condition_line[0] = 0;
    cache_flush_line(condition_line);
    cache_flush_line(sentinel_line);
    probe_result = spec_branch_site(condition_line, sentinel_line);
    cycles = cache_reload_cycles(sentinel_line);
    sink += training_sum + probe_result;
    return cycles;
}

static uint64_t calibration_trial(uint8_t hot) {
    uint8_t touched = 0;
    uint64_t cycles;
    cache_flush_line(sentinel_line);
    if (hot) touched = cache_touch_line(sentinel_line);
    cycles = cache_reload_cycles(sentinel_line);
    sink += touched;
    return cycles;
}

static void collect_block(uint32_t block, uint8_t order, int store) {
    uint32_t position;
    for (position = 0; position < CLASS_COUNT; ++position) {
        uint8_t kind = (uint8_t)(position < 2u ? (position ^ order) : position);
        uint64_t cycles = kind < 2u ? speculative_trial(kind == TRAIN_TAKEN) :
                          calibration_trial(kind == HOT);
        if (store) {
            struct sample *entry = &samples[block * CLASS_COUNT + position];
            entry->cycles = cycles;
            entry->block = (uint16_t)block;
            entry->position = (uint8_t)position;
            entry->kind = kind;
        }
    }
}

int main(void) {
    struct cache_cpu_features cpu;
    uint64_t checksum = 0;
    uint32_t block, index;
    cache_detect_cpu(&cpu);
    if (!cpu.has_tsc || !cpu.has_clflush || cpu.clflush_bytes == 0 ||
        cpu.clflush_bytes > sizeof(sentinel_line)) {
        fputs("SPEC_ERROR: TSC and CLFLUSH are required\n", stderr);
        return 1;
    }
    if (!pin_first_allowed_cpu()) {
        fputs("SPEC_ERROR: cannot pin one logical CPU\n", stderr);
        return 1;
    }
    condition_line[0] = 0;
    sentinel_line[0] = 1;
    for (block = 0; block < WARMUP_BLOCKS; ++block)
        collect_block(0, (uint8_t)(block & 1u), 0);
    prepare_order();
    for (block = 0; block < BLOCKS; ++block)
        collect_block(block, pair_order[block], 1);

    printf("SPEC_CPU,vendor=%s,signature=0x%08x,clflush_bytes=%u,"
           "invariant_tsc=%u\n", cpu.vendor, cpu.signature,
           cpu.clflush_bytes, cpu.invariant_tsc);
    printf("SPEC_RUN,version=1,blocks=%u,training=%u,warmup_blocks=%u,seed=%u,"
           "branch_addr=0x%llx,timer=lfence_rdtsc_lfence,flush=clflush_mfence\n",
           BLOCKS, TRAIN_CALLS, WARMUP_BLOCKS, SEED,
           (unsigned long long)(uintptr_t)spec_branch_site);
    for (index = 0; index < BLOCKS * CLASS_COUNT; ++index) {
        const struct sample *entry = &samples[index];
        checksum += (uint64_t)(index + 1u) * entry->cycles +
                    entry->block + entry->position + entry->kind;
        printf("SPEC_SAMPLE,%u,%u,%u,%s,%llu\n", index,
               (unsigned)entry->block, (unsigned)entry->position,
               kind_names[entry->kind], (unsigned long long)entry->cycles);
    }
    printf("SPEC_END,count=%u,checksum=%llu,sink=%u\n",
           BLOCKS * CLASS_COUNT, (unsigned long long)checksum, sink);
    fflush(stdout);
    return 0;
}
