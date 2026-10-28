/* Windows x64 equivalents of the cache primitives used by the Fractal build.
 * Kept out of line; inspect the optimized binary before interpreting timings.
 */
#include "cache_probe.h"

#include <intrin.h>

#if !defined(_WIN32) || !defined(_M_X64)
#error This file requires the Windows x64 MSVC toolchain.
#endif

__declspec(noinline) void cache_flush_line(const volatile uint8_t *line) {
    _mm_clflush((const void *)line);
    _mm_mfence();
}

__declspec(noinline) uint64_t cache_reload_cycles(const volatile uint8_t *line) {
    uint64_t start, end;
    _mm_lfence();
    start = __rdtsc();
    _mm_lfence();
    (void)*line;
    _mm_lfence();
    end = __rdtsc();
    return end - start;
}

__declspec(noinline) uint8_t cache_touch_line(const volatile uint8_t *line) {
    return *line;
}

__declspec(noinline) uint8_t cache_control_branch(
    const volatile uint8_t *line, uint32_t execute_target) {
    if (execute_target != 0) {
        _mm_lfence();
        return *line;
    }
    _mm_lfence();
    return 0;
}
