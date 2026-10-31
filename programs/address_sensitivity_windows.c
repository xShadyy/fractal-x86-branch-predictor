/* Exploratory fixed-receiver address-sensitivity study on native Windows. */
#include "cpu_features.h"

#include <errno.h>
#include <intrin.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <windows.h>

#define CONDITIONS 34u
#define BLOCKS 680u
#define WARMUP_BLOCKS 34u
#define EPISODES 128u
#define PRELUDE_CALLS 256u
#define TRAIN_CALLS 256u
#define PROBE_CALLS 1u
#define SITE_COUNT 3u
#define TEMPLATE_BYTES 25u
#define FNV_OFFSET UINT64_C(14695981039346656037)
#define FNV_PRIME UINT64_C(1099511628211)

typedef uint8_t (*branch_fn)(const volatile uint8_t *,
                             const volatile uint8_t *,
                             const volatile uint8_t *);

extern const uint8_t address_branch_template[];
extern const uint8_t address_branch_template_end[];
extern uint8_t address_sham_site(const volatile uint8_t *live);

/* Independently verify that the copied MASM template is relocation free and
   contains exactly one chosen conditional jump and one return. */
static const uint8_t expected_template[TEMPLATE_BYTES] = {
    0x0f, 0xb6, 0x01, 0x44, 0x0f, 0xb6, 0x12, 0x45, 0x0f, 0xb6, 0x18,
    0x45, 0x85, 0xdb, 0x44, 0x0f, 0x45, 0xd0, 0x45, 0x85, 0xd2,
    0x74, 0x01, 0x90, 0xc3
};

struct sample {
    uint64_t ticks;
    uint16_t block;
    uint8_t position;
    uint8_t kind;
};

static const char *const labels[CONDITIONS] = {
    "r_target_t0_p0", "r_target_t0_p1", "r_target_t1_p0", "r_target_t1_p1",
    "f_target_t0_p0", "f_target_t0_p1", "f_target_t1_p0", "f_target_t1_p1",
    "r_same4k_t0_p0", "r_same4k_t0_p1", "r_same4k_t1_p0", "r_same4k_t1_p1",
    "f_same4k_t0_p0", "f_same4k_t0_p1", "f_same4k_t1_p0", "f_same4k_t1_p1",
    "r_offset128_t0_p0", "r_offset128_t0_p1", "r_offset128_t1_p0", "r_offset128_t1_p1",
    "f_offset128_t0_p0", "f_offset128_t0_p1", "f_offset128_t1_p0", "f_offset128_t1_p1",
    "s_t0_p0", "s_t0_p1", "s_t1_p0", "s_t1_p1",
    "fast_p0", "fast_p1", "small_p0", "small_p1", "pause_p0", "pause_p1"
};

static __declspec(align(64)) volatile uint8_t live_line[64];
static __declspec(align(64)) volatile uint8_t mode_line[64];
static __declspec(align(64)) volatile uint8_t fixed_values[TRAIN_CALLS];
static __declspec(align(64)) uint8_t prelude_values[PRELUDE_CALLS];
static __declspec(align(64)) uint8_t train_values[TRAIN_CALLS];
static __declspec(align(64)) uint8_t probe_values[PROBE_CALLS];
static struct sample samples[BLOCKS * CONDITIONS];
static volatile uint32_t sink;
static volatile uint32_t small_sink;
static int architectural_error;
static branch_fn sites[SITE_COUNT];
static uintptr_t site_addresses[SITE_COUNT];
static void *rx_region;

static uint32_t next_random(uint32_t *state) {
    uint32_t x = *state;
    x ^= x << 13;
    x ^= x >> 17;
    x ^= x << 5;
    *state = x;
    return x;
}

static uint64_t template_hash(void) {
    uint64_t hash = FNV_OFFSET;
    uint32_t i;
    for (i = 0; i < TEMPLATE_BYTES; ++i)
        hash = (hash ^ expected_template[i]) * FNV_PRIME;
    return hash;
}

static int prepare_rx_clones(void) {
    static const size_t offsets[SITE_COUNT] = { 0x100u, 0x1100u, 0x1180u };
    uint8_t *region;
    DWORD old_protection;
    uint32_t i;
    if (sizeof(branch_fn) != sizeof(void *) ||
        (uintptr_t)address_branch_template_end < (uintptr_t)address_branch_template ||
        (uintptr_t)address_branch_template_end -
            (uintptr_t)address_branch_template != TEMPLATE_BYTES ||
        memcmp(address_branch_template, expected_template, TEMPLATE_BYTES) != 0)
        return 0;
    region = (uint8_t *)VirtualAlloc(NULL, 3u * 4096u,
                                     MEM_COMMIT | MEM_RESERVE, PAGE_READWRITE);
    if (region == NULL) return 0;
    rx_region = region;
    for (i = 0; i < SITE_COUNT; ++i) {
        void *address = region + offsets[i];
        memcpy(address, address_branch_template, TEMPLATE_BYTES);
        memcpy(&sites[i], &address, sizeof(address));
        site_addresses[i] = (uintptr_t)address;
    }
    if (!VirtualProtect(region, 3u * 4096u, PAGE_EXECUTE_READ,
                        &old_protection) ||
        !FlushInstructionCache(GetCurrentProcess(), region, 3u * 4096u))
        return 0;
    for (i = 0; i < SITE_COUNT; ++i) {
        MEMORY_BASIC_INFORMATION info;
        if (memcmp((const void *)site_addresses[i], expected_template,
                   TEMPLATE_BYTES) != 0 ||
            VirtualQuery((const void *)site_addresses[i], &info,
                         sizeof(info)) != sizeof(info) ||
            (info.Protect & 0xffu) != PAGE_EXECUTE_READ)
            return 0;
    }
    if (site_addresses[1] - site_addresses[0] != 4096u ||
        site_addresses[2] - site_addresses[1] != 128u ||
        (site_addresses[0] & 4095u) != (site_addresses[1] & 4095u) ||
        (site_addresses[2] & 4095u) == (site_addresses[1] & 4095u))
        return 0;
    return 1;
}

static int pin_first_allowed_cpu(void) {
    DWORD_PTR process_mask, system_mask, chosen;
    unsigned cpu = 0;
    if (!GetProcessAffinityMask(GetCurrentProcess(), &process_mask,
                                &system_mask) || process_mask == 0) return 0;
    chosen = process_mask & (~process_mask + 1);
    while ((chosen >> cpu) != 1) ++cpu;
    if (!SetProcessAffinityMask(GetCurrentProcess(), chosen)) return 0;
    printf("HOST_AFFINITY_CPU=%u\n", cpu);
    return 1;
}

/* One shared indirect call instruction must serve prelude, all trainers and
   the fixed receiver. The indirect target changes for non-target trainers;
   fixed-decision arms control this path only imperfectly. Audit the EXE. */
static __declspec(noinline) uint32_t run_site(branch_fn site,
                                              const uint8_t *values,
                                              uint32_t count) {
    uint32_t i, total = 0;
    for (i = 0; i < count; ++i) {
        live_line[0] = values[i];
        total += site(live_line, &fixed_values[i & 255u], mode_line);
    }
    return total;
}

static __declspec(noinline) uint32_t run_sham(const uint8_t *values,
                                              uint32_t count) {
    uint32_t i, total = 0;
    for (i = 0; i < count; ++i) {
        live_line[0] = values[i];
        total += address_sham_site(live_line);
    }
    return total;
}

static __declspec(noinline) uint64_t timed_fast(uint32_t *result) {
    uint64_t start, end;
    _mm_lfence(); start = __rdtsc(); _mm_lfence();
    *result = run_site(sites[0], probe_values, PROBE_CALLS);
    _mm_lfence(); end = __rdtsc();
    return end - start;
}

static __declspec(noinline) uint64_t timed_small(uint32_t *result) {
    uint64_t start, end;
    uint32_t work;
    _mm_lfence(); start = __rdtsc(); _mm_lfence();
    *result = run_site(sites[0], probe_values, PROBE_CALLS);
    work = (*result ^ UINT32_C(0x9e3779b9)) + 1u;
    small_sink = work;
    _mm_lfence(); end = __rdtsc();
    return end - start;
}

static __declspec(noinline) uint64_t timed_pause(uint32_t *result) {
    uint64_t start, end;
    _mm_lfence(); start = __rdtsc(); _mm_lfence();
    *result = run_site(sites[0], probe_values, PROBE_CALLS);
    _mm_pause();
    _mm_lfence(); end = __rdtsc();
    return end - start;
}

static uint64_t measure(uint8_t kind) {
    uint32_t site_index = kind < 24u ? kind / 8u : 0u;
    uint32_t arm = kind < 24u ? (kind / 4u) % 2u :
                   kind < 28u ? 2u : 0u;
    uint32_t train_bit = kind < 28u ? (kind % 4u) / 2u : 0u;
    uint32_t probe_bit = kind < 28u ? kind % 2u : (kind - 28u) % 2u;
    uint32_t timer = kind < 28u ? 0u : (kind - 28u) / 2u;
    uint32_t episode, prelude_sum = 0, train_sum = 0, probe_sum = 0;
    uint32_t result = 0;
    uint64_t ticks = 0;
    memset(train_values, (int)train_bit, TRAIN_CALLS);
    probe_values[0] = (uint8_t)probe_bit;
    for (episode = 0; episode < EPISODES; ++episode) {
        mode_line[0] = 1u;
        prelude_sum += run_site(sites[0], prelude_values, PRELUDE_CALLS);
        if (arm == 2u) {
            train_sum += run_sham(train_values, TRAIN_CALLS);
        } else {
            mode_line[0] = arm == 0u ? 1u : 0u;
            train_sum += run_site(sites[site_index], train_values, TRAIN_CALLS);
        }
        mode_line[0] = 1u;
        if (timer == 1u) ticks += timed_small(&result);
        else if (timer == 2u) ticks += timed_pause(&result);
        else ticks += timed_fast(&result);
        probe_sum += result;
    }
    if (prelude_sum != EPISODES * PRELUDE_CALLS / 2u ||
        train_sum != EPISODES * TRAIN_CALLS * train_bit ||
        probe_sum != EPISODES * PROBE_CALLS * probe_bit)
        architectural_error = 1;
    sink += prelude_sum + train_sum + probe_sum;
    return ticks;
}

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
    unsigned long long parsed_seed;
    if (argc != 2 || argv[1][0] == '-') {
        fputs("Usage: address-sensitivity-windows.exe <nonzero decimal uint32 seed>\n", stderr);
        return 1;
    }
    errno = 0;
    parsed_seed = strtoull(argv[1], &end_seed, 10);
    if (errno || end_seed == argv[1] || *end_seed != '\0' ||
        parsed_seed == 0 || parsed_seed > UINT32_MAX) {
        fputs("ADDR_ERROR: expected nonzero decimal uint32 seed\n", stderr);
        return 1;
    }
    seed = (uint32_t)parsed_seed;
    state = seed;
    cache_detect_cpu(&cpu);
    if (!cpu.has_tsc || !cpu.invariant_tsc || !pin_first_allowed_cpu()) {
        fputs("ADDR_ERROR: invariant TSC and single-CPU affinity required\n", stderr);
        return 1;
    }
    if (!prepare_rx_clones()) {
        fputs("ADDR_ERROR: RX branch clones or template verification failed\n", stderr);
        if (rx_region != NULL) VirtualFree(rx_region, 0, MEM_RELEASE);
        return 1;
    }
    for (i = 0; i < PRELUDE_CALLS; ++i) {
        uint8_t value = (uint8_t)((i >> 1) & 1u);
        prelude_values[i] = value;
        fixed_values[i] = value;
    }
    __cpuid(cpuid, 1);
    for (block = 0; block < WARMUP_BLOCKS; ++block)
        (void)collect_block(block, &state, order, 0, 0);
    for (block = 0; block < BLOCKS; ++block)
        schedule_hash = collect_block(block, &state, order, 1, schedule_hash);
    if (architectural_error) {
        fputs("ADDR_ERROR: architectural output mismatch\n", stderr);
        VirtualFree(rx_region, 0, MEM_RELEASE);
        return 1;
    }
    printf("ADDR_CPU,vendor=%s,signature=0x%08x,invariant_tsc=%u,hypervisor=%u\n",
           cpu.vendor, cpu.signature, cpu.invariant_tsc,
           ((uint32_t)cpuid[2] >> 31) & 1u);
    printf("ADDR_RUN,version=1,blocks=%u,episodes=%u,prelude_calls=%u,"
           "train_calls=%u,probe_calls=%u,warmup_blocks=%u,seed=%u,"
           "template_bytes=%u,template_hash=%llu,"
           "template_addr=0x%llx,branch_jcc_offset=21,"
           "target_addr=0x%llx,same4k_addr=0x%llx,offset128_addr=0x%llx,"
           "sham_addr=0x%llx,mode_addr=0x%llx,live_addr=0x%llx,"
           "fixed_addr=0x%llx,timer=lfence_rdtsc_lfence,"
           "protocol=rx_clone_address_sensitivity,compiler=msvc_O2,"
           "schedule_hash=%llu\n",
           BLOCKS, EPISODES, PRELUDE_CALLS, TRAIN_CALLS, PROBE_CALLS,
           WARMUP_BLOCKS, seed, TEMPLATE_BYTES, (unsigned long long)template_hash(),
           (unsigned long long)(uintptr_t)address_branch_template,
           (unsigned long long)site_addresses[0],
           (unsigned long long)site_addresses[1],
           (unsigned long long)site_addresses[2],
           (unsigned long long)(uintptr_t)address_sham_site,
           (unsigned long long)(uintptr_t)mode_line,
           (unsigned long long)(uintptr_t)live_line,
           (unsigned long long)(uintptr_t)fixed_values,
           (unsigned long long)schedule_hash);
    for (index = 0; index < BLOCKS * CONDITIONS; ++index) {
        const struct sample *entry = &samples[index];
        checksum += (uint64_t)(index + 1u) * entry->ticks + entry->block +
                    entry->position + entry->kind;
        printf("ADDR_SAMPLE,%u,%u,%u,%s,%llu\n", index,
               (unsigned)entry->block, (unsigned)entry->position,
               labels[entry->kind], (unsigned long long)entry->ticks);
    }
    printf("ADDR_END,count=%u,checksum=%llu,sink=%u\n",
           BLOCKS * CONDITIONS, (unsigned long long)checksum, sink);
    fflush(stdout);
    if (!VirtualFree(rx_region, 0, MEM_RELEASE)) return 1;
    return 0;
}
