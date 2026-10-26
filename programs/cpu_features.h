#ifndef FRACTAL_X86_CPU_FEATURES_H
#define FRACTAL_X86_CPU_FEATURES_H

#include <stdint.h>

struct cache_cpu_features {
    char vendor[13];
    uint32_t signature;
    uint32_t clflush_bytes;
    uint32_t has_tsc;
    uint32_t has_clflush;
    uint32_t invariant_tsc;
};

void cache_detect_cpu(struct cache_cpu_features *features);

#endif
