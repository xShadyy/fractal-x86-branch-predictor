/* K7/K8: bounded user-mode dependency and receiver follow-up.
 * Windows is the collection platform. Linux builds are development only.
 * No secret, privilege change, predictor reset, or hardware proof is assumed.
 */
#ifndef _WIN32
#define _GNU_SOURCE
#endif
#include "cpu_features.h"
#include "causal_receiver_code.h"
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
#define K7_ABI
#define PLATFORM "windows"
#else
#include <sched.h>
#include <sys/mman.h>
#include <unistd.h>
#include <x86intrin.h>
#define NOINLINE __attribute__((noinline))
#define ALIGNED(n) __attribute__((aligned(n)))
#define K7_ABI __attribute__((ms_abi))
#define PLATFORM "native_dev"
#endif
#ifndef K7_BLOCKS
#define K7_BLOCKS 512u
#endif
#ifndef K7_EPISODES
#define K7_EPISODES 4u
#endif
#if defined(_WIN32) && (K7_BLOCKS != 512 || K7_EPISODES != 4)
#error Windows collection must use the frozen dimensions.
#endif
#define WARMUP 8u
#define CONDITIONS 16u
#define MODES 5u
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
    volatile uint32_t sampled_cpl;
    volatile uint64_t sampled_pc;
};
typedef uint32_t (K7_ABI *site_fn)(const struct context *);
struct aux_pair { uint32_t start, end; };
typedef uint64_t (K7_ABI *reload_fn)(const volatile uint8_t *, struct aux_pair *);
typedef void (K7_ABI *serial_fn)(void);
typedef uint32_t (K7_ABI *touch_fn)(const volatile uint8_t *);
union code_pointer {
    void *object;
    site_fn site;
    reload_fn reload;
    serial_fn serial;
    touch_fn touch;
};
struct sample {
    uint64_t wanted, decoy;
    struct aux_pair wanted_aux, decoy_aux;
    uint32_t prelude, train, probe;
    uint16_t block;
    uint8_t mode, position, kind, episode, tag0, tag1, other, order;
    uint8_t train_cpl, probe_cpl;
    uint64_t train_pc, probe_pc;
};
static ALIGNED(4096) volatile uint8_t condition_line[4096];
static ALIGNED(4096) volatile uint8_t token_zero[4096];
static ALIGNED(4096) volatile uint8_t token_one[4096];
static ALIGNED(4096) volatile uint8_t banks[2][PAGES * STRIDE];
static ALIGNED(4096) volatile uint8_t sinks[2][PAGES * STRIDE];
static struct context context;
static struct sample samples[K7_BLOCKS * MODES * CONDITIONS * K7_EPISODES];
static unsigned char *code;
static site_fn branch_site;
static reload_fn reload;
static serial_fn serialize;
static touch_fn touch;
static unsigned architecture_errors;
static const char *const dependency_modes[MODES] = {"plain", "true_mask", "sham_mask", "lfence", "cpuid"};
static const char *const receiver_modes[MODES] = {"plain", "ablate_zero", "ablate_one", "ablate_both", "sink_both"};
static const char *const *modes;
static const char *study;
static unsigned receiver_study;
static uint64_t event_hash = FNV_OFFSET;
static const char *const names[16] = {
    "candidate_t0_p0", "candidate_t1_p0", "no_probe_t0_p0", "no_probe_t1_p0",
    "hot_p0", "cold_p0", "arch_load_p0", "warm_mismatch_p0",
    "candidate_t0_p1", "candidate_t1_p1", "no_probe_t0_p1", "no_probe_t1_p1",
    "hot_p1", "cold_p1", "arch_load_p1", "warm_mismatch_p1"
};

static void fail(const char *message) {
    fprintf(stderr, "K7_ERROR: %s\n", message);
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
    unsigned char expected[sizeof causal_code_template];
    memcpy(expected, causal_code_template, sizeof expected);
    if (mode >= MODES) fail("invalid mode");
    if (!receiver_study) {
        if (mode == 3u || mode == 4u) {
            static const unsigned char lfence[3] = {0x0f,0xae,0xe8};
            static const unsigned char cpuid[3] = {0x0f,0xa2,0x90};
            const unsigned char *patch = mode == 3u ? lfence : cpuid;
            memcpy(expected + K7_PATCH_ONE, patch, 3);
            memcpy(expected + K7_PATCH_ZERO, patch, 3);
        } else if (mode == 1u || mode == 2u) {
            static const unsigned char true_one[11] = {0x85,0xd2,0x0f,0x44,0xc6,0x90,0x90,0x90,0x90,0x90,0x90};
            static const unsigned char true_zero[11] = {0x85,0xd2,0x0f,0x45,0xc6,0x90,0x90,0x90,0x90,0x90,0x90};
            static const unsigned char sham_one[11] = {0x85,0xff,0x0f,0x44,0xc6,0x90,0x90,0x90,0x90,0x90,0x90};
            static const unsigned char sham_zero[11] = {0x85,0xf6,0x0f,0x45,0xc6,0x90,0x90,0x90,0x90,0x90,0x90};
            memcpy(expected + K7_MASK_ONE, mode == 1u ? true_one : sham_one, 11);
            memcpy(expected + K7_MASK_ZERO, mode == 1u ? true_zero : sham_zero, 11);
        }
    } else {
        static const unsigned char zero[5] = {0xb8,1,0,0,0};
        static const unsigned char one[5] = {0xb8,2,0,0,0};
        if (mode == 1u || mode == 3u) memcpy(expected + K7_LOAD_ZERO, zero, 5);
        if (mode == 2u || mode == 3u) memcpy(expected + K7_LOAD_ONE, one, 5);
    }
    /* Binding is fixed for all training and probes of this block. There is
     * no pointer selection, RNG or remapping after training. */
    context.bank0 = receiver_study && mode == 4u ? sinks[0] : banks[0];
    context.bank1 = receiver_study && mode == 4u ? sinks[1] : banks[1];
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
    const char *name = modes[mode];
    if (snprintf(path, sizeof path, "%s.%s.bin", prefix, name) < 0 ||
        strlen(prefix) + 32 >= sizeof path) fail("snapshot prefix too long");
#ifdef _WIN32
    if (fopen_s(&file, path, "wb")) file = NULL;
#else
    file = fopen(path, "wb");
#endif
    if (!file) fail("cannot write runtime code snapshot");
    if (fwrite(code, 1, sizeof causal_code_template, file) != sizeof causal_code_template)
        fail("runtime code snapshot write failed");
    if (fclose(file)) fail("runtime code snapshot close failed");
    printf("K7_CODE,mode=%s,hex=", name);
    for (i = 0; i < sizeof causal_code_template; ++i) printf("%02x", (unsigned)code[i]);
    putchar('\n');
    printf("K7_BIND,mode=%s,bank0_addr=0x%llx,bank1_addr=0x%llx\n", name,
           (unsigned long long)(uintptr_t)context.bank0,
           (unsigned long long)(uintptr_t)context.bank1);
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
    pointer.object = code + K7_RELOAD; reload = pointer.reload;
    pointer.object = code + K7_SERIAL; serialize = pointer.serial;
    pointer.object = code + K7_HOT; touch = pointer.touch;
}
static NOINLINE uint32_t invoke_shared(void) {
    uint32_t value = branch_site(&context);
    if (context.sampled_cpl != 3u || context.sampled_pc != (uint64_t)(uintptr_t)(code + K7_BRANCH))
        ++architecture_errors;
    return value;
}
/* No flush-loop branch may overwrite the post-training branch context. */
#define FLUSH_PAGE(n) \
    _mm_clflush((const void *)&banks[0][(n) * STRIDE]); \
    _mm_clflush((const void *)&banks[1][(n) * STRIDE]); \
    _mm_clflush((const void *)&sinks[0][(n) * STRIDE]); \
    _mm_clflush((const void *)&sinks[1][(n) * STRIDE])
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
    s->train_cpl = (uint8_t)context.sampled_cpl; s->train_pc = context.sampled_pc;
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
    s->probe_cpl = (uint8_t)context.sampled_cpl; s->probe_pc = context.sampled_pc;
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
    s->probe_cpl = 255u; s->probe_pc = 0;
    if (member == HOT) probe_hot(s, wanted);
    else if (member == COLD || member == NO_PROBE_T0 || member == NO_PROBE_T1)
        probe_omitted(s);
    else probe_branch(s);
    /* First action in either reload helper is CPUID before its timed load.
     * Both wanted and decoy pointers were computed before preparation. */
    if (s->order) { s->decoy = reload(other, &s->decoy_aux); s->wanted = reload(wanted, &s->wanted_aux); }
    else { s->wanted = reload(wanted, &s->wanted_aux); s->decoy = reload(other, &s->decoy_aux); }
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
    uint8_t mode_order[MODES];
    size_t index = 0;
    (void)seed;
    for (block = 0; block < blocks; ++block) {
        for (i = 0; i < MODES; ++i) mode_order[i] = (uint8_t)i;
        for (i = MODES - 1u; i; --i) {
            const unsigned j = next32(schedule_state) % (i + 1u);
            const uint8_t tmp = mode_order[i]; mode_order[i] = mode_order[j]; mode_order[j] = tmp;
        }
        for (mpos = 0; mpos < MODES; ++mpos) {
            const unsigned mode = mode_order[mpos];
            install_mode(mode);
            /* Each round contains all cells once. Every cell contributes the
             * same number of observations; no first-episode exclusions. */
            for (e = 0; e < K7_EPISODES; ++e) {
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
    unsigned hypervisor, affinity, p, i, mode, ibs, lfence_always_serializing;
    size_t count, index;
    uint64_t checksum = 0;
    uint32_t words[4], max_extended, cpuid_80000021_eax = 0;
    _Static_assert(sizeof(void *) == 8 && offsetof(struct context, bank1) == 32 &&
                   offsetof(struct context, sampled_cpl) == 40 && offsetof(struct context, sampled_pc) == 48,
                   "x64 context layout required");
    _Static_assert(sizeof(struct aux_pair) == 8 && offsetof(struct aux_pair, end) == 4,
                   "two contiguous uint32 AUX outputs required");
    if (argc != 4 || (strcmp(argv[1], "dependency") && strcmp(argv[1], "receiver")))
        fail("usage: causal-receiver <dependency|receiver> <nonzero uint32 seed> <code snapshot prefix>");
    study = argv[1]; receiver_study = !strcmp(study, "receiver");
    modes = receiver_study ? receiver_modes : dependency_modes;
    errno = 0; parsed = strtoull(argv[2], &end, 10);
    if (errno || end == argv[2] || argv[2][0] == '-' || *end || !parsed || parsed > UINT32_MAX)
        fail("invalid seed");
    seed = (uint32_t)parsed; schedule_state = seed;
    tag_state = seed ^ UINT32_C(0xa5f1523d);
    if (!tag_state) tag_state = 1;
    cache_detect_cpu(&cpu);
    if (!cpu.has_tsc || !cpu.has_clflush || !cpu.invariant_tsc || cpu.clflush_bytes != 64u)
        fail("invariant TSC and 64-byte CLFLUSH required");
#ifdef _WIN32
    if (strcmp(cpu.vendor, "AuthenticAMD")) fail("Windows K7/K8 v1 timing contract requires AMD");
#endif
    cpuid_words(UINT32_C(0x80000000), words);
    max_extended = words[0];
    if (max_extended < UINT32_C(0x80000001)) fail("RDTSCP feature leaf unavailable");
    cpuid_words(UINT32_C(0x80000001), words);
    if (!(words[3] & (1u << 27))) fail("RDTSCP required");
    ibs = (words[2] >> 10) & 1u;
    if (!strcmp(cpu.vendor, "AuthenticAMD") && max_extended >= UINT32_C(0x80000021)) {
        cpuid_words(UINT32_C(0x80000021), words);
        cpuid_80000021_eax = words[0];
    }
    lfence_always_serializing = (cpuid_80000021_eax >> 2) & 1u;
    cpuid_words(1, words); hypervisor = (words[2] >> 31) & 1u;
    affinity = pin_cpu();
    context.condition = condition_line; context.token0 = token_zero;
    context.token1 = token_one; context.bank0 = banks[0]; context.bank1 = banks[1];
    for (p = 0; p < 2u; ++p)
        for (i = 0; i < PAGES; ++i) {
            banks[p][i * STRIDE] = (uint8_t)(1u + p);
            sinks[p][i * STRIDE] = (uint8_t)(1u + p);
        }
    allocate_code();
    printf("K7_CPU,vendor=%s,signature=0x%08x,clflush_bytes=%u,invariant_tsc=%u,rdtscp=1,hypervisor=%u,"
           "ibs=%u,lfence_always_serializing=%u,cpuid_80000021_eax=0x%08x\n",
           cpu.vendor, cpu.signature, cpu.clflush_bytes, cpu.invariant_tsc, hypervisor,
           ibs, lfence_always_serializing, cpuid_80000021_eax);
    printf("K7_RUN,version=1,protocol=causal_receiver_v1,study=%s,blocks=%u,episodes=%u,"
           "conditions=16,modes=5,warmup_blocks=8,prelude_calls=128,train_calls=256,"
           "history_prefix_branches=256,schedule=interleaved_modes_and_rounds,"
           "pages=64,stride=4096,seed=%u,affinity_cpu=%u,platform=%s,"
           "timer=cpuid_outside_rdtscp_load_rdtscp_aux,binding=mode_installed_before_training,"
           "flush=all_public_and_sink_lines,prng=xorshift32_v1,checksum=fnv64_k5_timing_v1,code_addr=0x%llx,"
           "condition_addr=0x%llx,token0_addr=0x%llx,token1_addr=0x%llx,"
           "bank0_addr=0x%llx,bank1_addr=0x%llx,sink0_addr=0x%llx,sink1_addr=0x%llx\n",
           study, K7_BLOCKS, K7_EPISODES, seed, affinity, PLATFORM,
           (unsigned long long)(uintptr_t)code,
           (unsigned long long)(uintptr_t)condition_line,
           (unsigned long long)(uintptr_t)token_zero,
           (unsigned long long)(uintptr_t)token_one,
           (unsigned long long)(uintptr_t)banks[0], (unsigned long long)(uintptr_t)banks[1],
           (unsigned long long)(uintptr_t)sinks[0], (unsigned long long)(uintptr_t)sinks[1]);
    for (mode = 0; mode < MODES; ++mode) { install_mode(mode); snapshot(mode, argv[3]); }
    fflush(stdout);
    (void)collect(WARMUP, 0, seed, &schedule_state, &tag_state);
    count = collect(K7_BLOCKS, 1, seed, &schedule_state, &tag_state);
    for (index = 0; index < count; ++index) {
        const struct sample *s = &samples[index];
        checksum = mix(mix(checksum, (uint64_t)(index + 1u)), s->wanted);
        checksum = mix(checksum, s->decoy);
        printf("K7_SAMPLE,%llu,%u,%s,%u,%s,%u,%u,%u,%u,%u,%llu,%llu,%u,%u,%u,%u,%u,0x%llx,0x%llx,%u,%u,%u,%u\n",
               (unsigned long long)index, (unsigned)s->block, modes[s->mode],
               (unsigned)s->position, names[s->kind], (unsigned)s->episode,
               (unsigned)s->tag0, (unsigned)s->tag1, (unsigned)s->other, (unsigned)s->order,
               (unsigned long long)s->wanted, (unsigned long long)s->decoy,
               s->prelude, s->train, s->probe, (unsigned)s->train_cpl, (unsigned)s->probe_cpl,
               (unsigned long long)s->train_pc, (unsigned long long)s->probe_pc,
               s->wanted_aux.start, s->wanted_aux.end, s->decoy_aux.start, s->decoy_aux.end);
    }
    printf("K7_END,count=%llu,checksum=%llu,event_hash=%llu,architecture_errors=%u\n",
           (unsigned long long)count, (unsigned long long)checksum,
           (unsigned long long)event_hash, architecture_errors);
    if (fflush(stdout)) fail("trace output failed");
    return architecture_errors ? 1 : 0;
}
