#ifndef FRACTAL_X86_CACHE_PROBE_H
#define FRACTAL_X86_CACHE_PROBE_H

#include <stdint.h>

/* Each primitive is out of line so the C compiler cannot fold away a load. */
void cache_flush_line(const volatile uint8_t *line);
uint64_t cache_reload_cycles(const volatile uint8_t *line);
uint8_t cache_touch_line(const volatile uint8_t *line);

/* A guarded architectural control. execute_target=0 skips the only load. */
uint8_t cache_control_branch(const volatile uint8_t *line,
                             uint32_t execute_target);

#endif
