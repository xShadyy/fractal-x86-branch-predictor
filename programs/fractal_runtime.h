/* Minimal bindings for the pinned MIT Fractal public syscall ABI.
 * Fractal and its syscall design are Joseph Ravichandran and Mengjia Yan's work.
 * No Linux or Windows kernel is modified by this program.
 */
#ifndef RESEARCH_FRACTAL_RUNTIME_H
#define RESEARCH_FRACTAL_RUNTIME_H
#include <stddef.h>
#include <stdint.h>
long fr_syscall(uint64_t number, uint64_t a, uint64_t b, uint64_t c, uint64_t d);
int fr_printf(const char *format, ...);
void fr_fail(const char *message) __attribute__((noreturn));
void *memcpy(void *dst, const void *src, size_t n);
void *memset(void *dst, int value, size_t n);
int memcmp(const void *a, const void *b, size_t n);
size_t strlen(const char *s);
#define FR_USER 0x10u
#define FR_KERNEL 0x20u
#define FR_COOPERATIVE 0x80u
static inline unsigned fr_cpl(void) {
    uint16_t cs;
    __asm__ __volatile__("mov %%cs,%0" : "=r"(cs));
    return cs & 3u;
}
static inline uint64_t fr_flags(void) {
    uint64_t flags;
    __asm__ __volatile__("pushfq; popq %0" : "=r"(flags));
    return flags;
}
#endif
