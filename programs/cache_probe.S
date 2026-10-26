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

    .section .note.GNU-stack,"",@progbits
