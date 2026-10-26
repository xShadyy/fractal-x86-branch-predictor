#include "cpu_features.h"

#include <string.h>

static void cpuid(uint32_t leaf, uint32_t subleaf, uint32_t *a,
                  uint32_t *b, uint32_t *c, uint32_t *d) {
    __asm__ __volatile__("cpuid"
                         : "=a"(*a), "=b"(*b), "=c"(*c), "=d"(*d)
                         : "a"(leaf), "c"(subleaf)
                         : "memory");
}

void cache_detect_cpu(struct cache_cpu_features *features) {
    uint32_t max_leaf, a, b, c, d;
    uint32_t max_extended;

    memset(features, 0, sizeof(*features));
    cpuid(0, 0, &max_leaf, &b, &c, &d);
    memcpy(features->vendor, &b, sizeof(b));
    memcpy(features->vendor + 4, &d, sizeof(d));
    memcpy(features->vendor + 8, &c, sizeof(c));

    if (max_leaf >= 1) {
        cpuid(1, 0, &a, &b, &c, &d);
        features->signature = a;
        features->has_tsc = (d >> 4) & 1u;
        features->has_clflush = (d >> 19) & 1u;
        features->clflush_bytes = ((b >> 8) & 0xffu) * 8u;
    }

    cpuid(UINT32_C(0x80000000), 0, &max_extended, &b, &c, &d);
    if (max_extended >= UINT32_C(0x80000007)) {
        cpuid(UINT32_C(0x80000007), 0, &a, &b, &c, &d);
        features->invariant_tsc = (d >> 8) & 1u;
    }
}
