/* K4: fixed branch-context prefix and interleaved fresh-marker episodes.
 * Windows is the collection platform. Linux builds are development only.
 * No secret, privilege change, predictor reset, or hardware proof is assumed.
 */
#ifndef _WIN32
#define _GNU_SOURCE
#endif
#include "cpu_features.h"
#include "context_receiver_code.h"
#include <errno.h>
#include <stddef.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#ifdef _WIN32
#include <intrin.h>
#include <windows.h>
#define NOINLINE __declspec(noinline)
#define ALIGNED(n) __declspec(align(n))
#define K4_ABI
#define PLATFORM "windows"
#else
#include <sched.h>
#include <sys/mman.h>
#include <unistd.h>
#include <x86intrin.h>
#define NOINLINE __attribute__((noinline))
#define ALIGNED(n) __attribute__((aligned(n)))
#define K4_ABI __attribute__((ms_abi))
#define PLATFORM "native_dev"
#endif
#ifndef K4_BLOCKS
#define K4_BLOCKS 512u
#endif
#ifndef K4_EPISODES
#define K4_EPISODES 16u
#endif
#if defined(_WIN32) && (K4_BLOCKS != 512 || K4_EPISODES != 16)
#error Windows collection must use the frozen dimensions.
#endif
#define WARMUP 16u
#define CONDITIONS 16u
#define PRELUDE 128u
#define TRAIN 256u
#define PAGES 64u
#define STRIDE 4096u
#define FNV_OFFSET UINT64_C(14695981039346656037)
#define FNV_PRIME UINT64_C(1099511628211)
enum { CAND_T0, CAND_T1, NO_PROBE_T0, NO_PROBE_T1,
       HOT, COLD, ARCH_LOAD, WARM_MISMATCH };
struct context {
    volatile uint8_t *condition, *token0, *token1, *bank0, *bank1;
};
typedef uint32_t (K4_ABI *site_fn)(const struct context *);
typedef uint64_t (K4_ABI *reload_fn)(const volatile uint8_t *);
typedef void (K4_ABI *serial_fn)(void);
typedef uint32_t (K4_ABI *touch_fn)(const volatile uint8_t *);
union code_pointer {
    void *object;
    site_fn site;
    reload_fn reload;
    serial_fn serial;
    touch_fn touch;
};
struct sample {
    uint64_t wanted, decoy;
    uint32_t prelude, train, probe;
    uint16_t block;
    uint8_t mode, position, kind, episode, tag0, tag1, other, order;
};
static ALIGNED(4096) volatile uint8_t condition_line[4096];
static ALIGNED(4096) volatile uint8_t token_zero[4096];
static ALIGNED(4096) volatile uint8_t token_one[4096];
static ALIGNED(4096) volatile uint8_t banks[2][PAGES * STRIDE];
static struct context context;
static struct sample samples[K4_BLOCKS * 2u * CONDITIONS * K4_EPISODES];
static unsigned char *code;
static site_fn branch_site;
static reload_fn reload;
static serial_fn serialize;
static touch_fn touch;
static unsigned architecture_errors;
static uint64_t event_hash = FNV_OFFSET;
static const char *const names[16] = {
    "candidate_t0_p0", "candidate_t1_p0", "no_probe_t0_p0", "no_probe_t1_p0",
    "hot_p0", "cold_p0", "arch_load_p0", "warm_mismatch_p0",
    "candidate_t0_p1", "candidate_t1_p1", "no_probe_t0_p1", "no_probe_t1_p1",
    "hot_p1", "cold_p1", "arch_load_p1", "warm_mismatch_p1"
};

static void fail(const char *message) {
    fprintf(stderr, "K4_ERROR: %s\n", message);
    exit(1);
}
static uint32_t next32(uint32_t *state) {
    uint32_t x = *state;
    x ^= x << 13; x ^= x >> 17; x ^= x << 5;
    *state = x;
    return x;
}
static void cpuid_words(uint32_t leaf, uint32_t words[4]) {
#ifdef _WIN32
    int regs[4];
    __cpuidex(regs, (int)leaf, 0);
    memcpy(words, regs, sizeof regs);
#else
    __asm__ __volatile__("cpuid" : "=a"(words[0]), "=b"(words[1]),
                         "=c"(words[2]), "=d"(words[3]) : "a"(leaf), "c"(0) : "memory");
#endif
}
static unsigned pin_cpu(void) {
#ifdef _WIN32
    DWORD_PTR allowed, system, chosen;
    unsigned cpu = 0;
    if (!GetProcessAffinityMask(GetCurrentProcess(), &allowed, &system) || !allowed)
        fail("cannot read affinity");
    chosen = allowed & (~allowed + 1);
    while ((chosen >> cpu) != 1) ++cpu;
    if (!SetThreadAffinityMask(GetCurrentThread(), chosen)) fail("cannot pin thread");
    return cpu;
#else
    cpu_set_t allowed, chosen;
    int cpu;
    if (sched_getaffinity(0, sizeof allowed, &allowed)) fail("cannot read affinity");
    for (cpu = 0; cpu < CPU_SETSIZE; ++cpu) {
        if (CPU_ISSET(cpu, &allowed)) {
            CPU_ZERO(&chosen); CPU_SET(cpu, &chosen);
            if (sched_setaffinity(0, sizeof chosen, &chosen)) fail("cannot pin thread");
            return (unsigned)cpu;
        }
    }
    fail("empty affinity mask");
    return 0;
#endif
}
static void protect_code(int executable) {
#ifdef _WIN32
    DWORD previous;
    if (!VirtualProtect(code, STRIDE, executable ? PAGE_EXECUTE_READ : PAGE_READWRITE,
                        &previous)) fail("cannot change code protection");
    if (executable && !FlushInstructionCache(GetCurrentProcess(), code, STRIDE))
        fail("cannot synchronize code");
#else
    if (mprotect(code, STRIDE, executable ? PROT_READ | PROT_EXEC : PROT_READ | PROT_WRITE))
        fail("cannot change code protection");
    if (executable) __builtin___clear_cache((char *)code, (char *)code + STRIDE);
#endif
}
static void install_mode(unsigned mode) {
    unsigned char expected[sizeof context_code_template];
    memcpy(expected, context_code_template, sizeof expected);
    if (mode) {
        expected[K4_PATCH_ONE] = expected[K4_PATCH_ZERO] = 0x0f;
        expected[K4_PATCH_ONE + 1] = expected[K4_PATCH_ZERO + 1] = 0xa2;
    }
    protect_code(0);
    memcpy(code, expected, sizeof expected);
    protect_code(1);
    if (memcmp(code, expected, sizeof expected)) fail("RX code verification failed");
    serialize();
}
static void snapshot(unsigned mode, const char *prefix) {
    char path[2048];
    FILE *file;
    size_t i;
    const char *name = mode ? "cpuid" : "nop";
    if (snprintf(path, sizeof path, "%s.%s.bin", prefix, name) < 0 ||
        strlen(prefix) + 12 >= sizeof path) fail("snapshot prefix too long");
#ifdef _WIN32
    if (fopen_s(&file, path, "wb")) file = NULL;
#else
    file = fopen(path, "wb");
#endif
    if (!file) fail("cannot write runtime code snapshot");
    if (fwrite(code, 1, sizeof context_code_template, file) != sizeof context_code_template)
        fail("runtime code snapshot write failed");
    if (fclose(file)) fail("runtime code snapshot close failed");
    printf("K4_CODE,mode=%s,hex=", name);
    for (i = 0; i < sizeof context_code_template; ++i) printf("%02x", (unsigned)code[i]);
    putchar('\n');
}
static void allocate_code(void) {
    union code_pointer pointer;
#ifdef _WIN32
    SYSTEM_INFO system;
    GetSystemInfo(&system);
    if (system.dwPageSize != STRIDE) fail("4096-byte system pages required");
    code = (unsigned char *)VirtualAlloc(NULL, STRIDE, MEM_RESERVE | MEM_COMMIT, PAGE_READWRITE);
    if (!code) fail("cannot allocate code");
#else
    if (sysconf(_SC_PAGESIZE) != STRIDE) fail("4096-byte system pages required");
    code = mmap(NULL, STRIDE, PROT_READ | PROT_WRITE, MAP_PRIVATE | MAP_ANONYMOUS, -1, 0);
    if (code == MAP_FAILED) fail("cannot allocate code");
#endif
    memset(code, 0xcc, STRIDE);
    pointer.object = code; branch_site = pointer.site;
    pointer.object = code + K4_RELOAD; reload = pointer.reload;
    pointer.object = code + K4_SERIAL; serialize = pointer.serial;
    pointer.object = code + K4_HOT; touch = pointer.touch;
}
static NOINLINE uint32_t invoke_shared(void) {
    return branch_site(&context);
}
/* No flush-loop branch may overwrite the post-training branch context. */
#define FLUSH_PAGE(n) \
    _mm_clflush((const void *)&banks[0][(n) * STRIDE]); \
    _mm_clflush((const void *)&banks[1][(n) * STRIDE])
#define FLUSH_EIGHT(n) \
    FLUSH_PAGE((n) + 0u); FLUSH_PAGE((n) + 1u); \
    FLUSH_PAGE((n) + 2u); FLUSH_PAGE((n) + 3u); \
    FLUSH_PAGE((n) + 4u); FLUSH_PAGE((n) + 5u); \
    FLUSH_PAGE((n) + 6u); FLUSH_PAGE((n) + 7u)
/* Training tokens are always zero, so only page zero can be touched by
 * architectural training. Fresh probe tokens 1..63 are stored after training.
 * End preparation with a serializing instruction before any branch or HOT
 * probe. HOT and timer helpers serialize again before their marker loads.
 */
static NOINLINE void prepare(struct sample *s) {
    const unsigned p = s->kind / 8u, member = s->kind % 8u;
    const unsigned t = member < 4u ? member & 1u :
                       (member == WARM_MISMATCH ? 1u - p : p);
    unsigned i;
    uint32_t a = 0, b = 0;
    token_zero[0] = token_one[0] = 0;
    for (i = 0; i < PRELUDE; ++i) {
        condition_line[0] = (uint8_t)((i >> 1) & 1u);
        a += invoke_shared();
    }
    for (i = 0; i < TRAIN; ++i) {
        condition_line[0] = (uint8_t)t;
        b += invoke_shared();
    }
    s->prelude = a; s->train = b;
    if (a != PRELUDE * 3u / 2u || b != TRAIN * (1u + t)) ++architecture_errors;
    token_zero[0] = s->tag0;
    token_one[0] = s->tag1;
    condition_line[0] = (uint8_t)(member == ARCH_LOAD ? 1u - p : p);
    /* All possible marker lines, including page zero, are flushed every time. */
    FLUSH_EIGHT(0u); FLUSH_EIGHT(8u); FLUSH_EIGHT(16u); FLUSH_EIGHT(24u);
    FLUSH_EIGHT(32u); FLUSH_EIGHT(40u); FLUSH_EIGHT(48u); FLUSH_EIGHT(56u);
    if (member != WARM_MISMATCH) _mm_clflush((const void *)condition_line);
    _mm_mfence();
    serialize();
}
static NOINLINE void probe_branch(struct sample *s) {
    prepare(s);
    s->probe = invoke_shared();
}
static NOINLINE void probe_omitted(struct sample *s) {
    prepare(s);
    s->probe = 0;
}
static NOINLINE void probe_hot(struct sample *s, const volatile uint8_t *wanted) {
    prepare(s);
    s->probe = 0;
    (void)touch(wanted);
}
static void episode(struct sample *s) {
    const unsigned p = s->kind / 8u, member = s->kind % 8u;
    const uint8_t tag = p ? s->tag0 : s->tag1;
    const volatile uint8_t *wanted = &banks[1u - p][(unsigned)tag * STRIDE];
    const volatile uint8_t *other = &banks[1u - p][(unsigned)s->other * STRIDE];
    if (member == HOT) probe_hot(s, wanted);
    else if (member == COLD || member == NO_PROBE_T0 || member == NO_PROBE_T1)
        probe_omitted(s);
    else probe_branch(s);
    /* First action in either reload helper is CPUID before its timed load.
     * Both wanted and decoy pointers were computed before preparation. */
    if (s->order) { s->decoy = reload(other); s->wanted = reload(wanted); }
    else { s->wanted = reload(wanted); s->decoy = reload(other); }
    {
        const unsigned expected = member == CAND_T0 || member == CAND_T1 ||
                                  member == WARM_MISMATCH ? 1u + p :
                                  (member == ARCH_LOAD ? 2u - p : 0u);
        if (s->probe != expected) ++architecture_errors;
    }
}
static uint64_t mix(uint64_t hash, uint64_t value) {
    return (hash ^ value) * FNV_PRIME;
}
static size_t collect(unsigned blocks, int keep, uint32_t seed,
                      uint32_t *schedule_state, uint32_t *tag_state) {
    uint8_t order[CONDITIONS];
    unsigned block, mpos, pos, e, i;
    size_t index = 0;
    for (block = 0; block < blocks; ++block) {
        for (mpos = 0; mpos < 2u; ++mpos) {
            const unsigned mode = ((block + (seed & 1u)) & 1u) ^ mpos;
            install_mode(mode);
            /* Each round contains all cells once. Every cell contributes the
             * same number of observations; no first-episode exclusions. */
            for (e = 0; e < K4_EPISODES; ++e) {
                for (i = 0; i < CONDITIONS; ++i) order[i] = (uint8_t)i;
                for (i = CONDITIONS - 1u; i; --i) {
                    const unsigned j = next32(schedule_state) % (i + 1u);
                    const uint8_t tmp = order[i]; order[i] = order[j]; order[j] = tmp;
                }
                for (pos = 0; pos < CONDITIONS; ++pos) {
                    const uint8_t kind = order[pos];
                    struct sample scratch, *s = keep ? &samples[index] : &scratch;
                    const unsigned p = kind / 8u;
                    unsigned wanted, other;
                    memset(s, 0, sizeof *s);
                    s->block = (uint16_t)block; s->mode = (uint8_t)mode;
                    s->position = (uint8_t)pos; s->kind = kind; s->episode = (uint8_t)e;
                    s->tag0 = (uint8_t)(1u + next32(tag_state) % (PAGES - 1u));
                    s->tag1 = (uint8_t)(1u + next32(tag_state) % (PAGES - 1u));
                    wanted = p ? s->tag0 : s->tag1;
                    other = 1u + next32(tag_state) % (PAGES - 2u);
                    if (other >= wanted) ++other;
                    s->other = (uint8_t)other;
                    s->order = (uint8_t)(next32(tag_state) & 1u);
                    episode(s);
                    if (keep) {
                        event_hash = mix(event_hash, (uint64_t)mode * 256u + kind * 16u + e);
                        event_hash = mix(event_hash, (uint64_t)s->tag0 * 65536u +
                                                    s->tag1 * 256u + s->other * 2u + s->order);
                    }
                    ++index;
                }
            }
        }
    }
    return index;
}
int main(int argc, char **argv) {
    struct cache_cpu_features cpu;
    char *end;
    unsigned long long parsed;
    uint32_t seed, schedule_state, tag_state;
    unsigned hypervisor, affinity, p, i, mode;
    size_t count, index;
    uint64_t checksum = 0;
    uint32_t words[4];
    _Static_assert(sizeof(void *) == 8 && offsetof(struct context, bank1) == 32,
                   "x64 context layout required");
    if (argc != 3 || argv[1][0] == '-') fail("usage: context-receiver <nonzero uint32 seed> <code snapshot prefix>");
    errno = 0; parsed = strtoull(argv[1], &end, 10);
    if (errno || end == argv[1] || *end || !parsed || parsed > UINT32_MAX)
        fail("invalid seed");
    seed = (uint32_t)parsed; schedule_state = seed;
    tag_state = seed ^ UINT32_C(0xa5f1523d);
    if (!tag_state) tag_state = 1;
    cache_detect_cpu(&cpu);
    if (!cpu.has_tsc || !cpu.has_clflush || !cpu.invariant_tsc || cpu.clflush_bytes != 64u)
        fail("invariant TSC and 64-byte CLFLUSH required");
    if (strcmp(cpu.vendor, "AuthenticAMD")) fail("K4 v1 timing contract requires AMD");
    cpuid_words(UINT32_C(0x80000000), words);
    if (words[0] < UINT32_C(0x80000001)) fail("RDTSCP feature leaf unavailable");
    cpuid_words(UINT32_C(0x80000001), words);
    if (!(words[3] & (1u << 27))) fail("RDTSCP required");
    cpuid_words(1, words); hypervisor = (words[2] >> 31) & 1u;
    affinity = pin_cpu();
    context.condition = condition_line; context.token0 = token_zero;
    context.token1 = token_one; context.bank0 = banks[0]; context.bank1 = banks[1];
    for (p = 0; p < 2u; ++p)
        for (i = 0; i < PAGES; ++i) banks[p][i * STRIDE] = (uint8_t)(1u + p);
    allocate_code();
    printf("K4_CPU,vendor=%s,signature=0x%08x,clflush_bytes=%u,invariant_tsc=%u,rdtscp=1,hypervisor=%u\n",
           cpu.vendor, cpu.signature, cpu.clflush_bytes, cpu.invariant_tsc, hypervisor);
    printf("K4_RUN,version=1,protocol=context_marker_k4_v1,blocks=%u,episodes=%u,"
           "conditions=16,modes=2,warmup_blocks=16,prelude_calls=128,train_calls=256,"
           "history_prefix_branches=256,schedule=interleaved_round_shuffle,"
           "pages=64,stride=4096,seed=%u,affinity_cpu=%u,platform=%s,"
           "timer=cpuid_outside_rdtscp_load_rdtscp,code_addr=0x%llx,"
           "condition_addr=0x%llx,token0_addr=0x%llx,token1_addr=0x%llx,"
           "bank0_addr=0x%llx,bank1_addr=0x%llx\n",
           K4_BLOCKS, K4_EPISODES, seed, affinity, PLATFORM,
           (unsigned long long)(uintptr_t)code,
           (unsigned long long)(uintptr_t)condition_line,
           (unsigned long long)(uintptr_t)token_zero,
           (unsigned long long)(uintptr_t)token_one,
           (unsigned long long)(uintptr_t)banks[0], (unsigned long long)(uintptr_t)banks[1]);
    for (mode = 0; mode < 2u; ++mode) { install_mode(mode); snapshot(mode, argv[2]); }
    fflush(stdout);
    (void)collect(WARMUP, 0, seed, &schedule_state, &tag_state);
    count = collect(K4_BLOCKS, 1, seed, &schedule_state, &tag_state);
    for (index = 0; index < count; ++index) {
        const struct sample *s = &samples[index];
        checksum = mix(mix(checksum, (uint64_t)(index + 1u)), s->wanted);
        checksum = mix(checksum, s->decoy);
        printf("K4_SAMPLE,%llu,%u,%s,%u,%s,%u,%u,%u,%u,%u,%llu,%llu,%u,%u,%u\n",
               (unsigned long long)index, (unsigned)s->block, s->mode ? "cpuid" : "nop",
               (unsigned)s->position, names[s->kind], (unsigned)s->episode,
               (unsigned)s->tag0, (unsigned)s->tag1, (unsigned)s->other, (unsigned)s->order,
               (unsigned long long)s->wanted, (unsigned long long)s->decoy,
               s->prelude, s->train, s->probe);
    }
    printf("K4_END,count=%llu,checksum=%llu,event_hash=%llu,architecture_errors=%u\n",
           (unsigned long long)count, (unsigned long long)checksum,
           (unsigned long long)event_hash, architecture_errors);
    if (fflush(stdout)) fail("trace output failed");
    return architecture_errors ? 1 : 0;
}
