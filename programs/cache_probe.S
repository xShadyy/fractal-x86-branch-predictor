/* x86-64 cache probe primitives. The timer brackets only the reload. */

    .text
    .p2align 6
    .globl cache_reload_cycles
    .type cache_reload_cycles, @function
cache_reload_cycles:
    lfence
    rdtsc
    shlq $32, %rdx
    orq %rax, %rdx
    movq %rdx, %r8
    lfence
    movzbl (%rdi), %eax
    lfence
    rdtsc
    shlq $32, %rdx
    orq %rax, %rdx
    subq %r8, %rdx
    movq %rdx, %rax
    ret
    .size cache_reload_cycles, .-cache_reload_cycles

    .p2align 6
    .globl cache_flush_line
    .type cache_flush_line, @function
cache_flush_line:
    clflush (%rdi)
    mfence
    ret
    .size cache_flush_line, .-cache_flush_line

    .p2align 6
    .globl cache_touch_line
    .type cache_touch_line, @function
cache_touch_line:
    movzbl (%rdi), %eax
    ret
    .size cache_touch_line, .-cache_touch_line

    .section .note.GNU-stack,"",@progbits
