/* Fractal syscall convention from libc/fractal/crt0_x86.S at 03ad1c5.
 * This adapter and startup are for this experiment's freestanding payload.
 */
.intel_syntax noprefix
.text
.global _start,fr_syscall
_start:
    and rsp,-16
    call main
    mov edi,eax
    mov eax,2
    syscall
1:  pause
    jmp 1b
fr_syscall:
    mov rax,rdi
    mov rdi,rsi
    mov rsi,rdx
    mov rdx,rcx
    mov r10,r8
    syscall
    ret
    int3
.global k6_worker_entry
k6_worker_entry:
    and rsp,-16
    call k6_worker
    mov eax,38
    xor edi,edi
    syscall
2:  pause
    jmp 2b
.section .note.GNU-stack,"",@progbits
