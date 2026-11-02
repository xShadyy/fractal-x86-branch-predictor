.intel_syntax noprefix
.text
.global context_start, context_branch, context_patch_one, context_patch_zero
.global context_target_one, context_target_zero, context_reload, context_serial, context_hot, context_end
context_start:
    /* Identical fixed branch prefix before every training and probe call.
     * This constrains local context; it is not a verified predictor reset. */
    xor eax,eax
    .rept 256
        test eax,eax
        jz 1f
        int3
    1:
    .endr
    .fill 62,1,0x90
    push rbx
    mov rdx, [rcx]
    mov r8, [rcx+8]
    mov r9, [rcx+16]
    mov r10, [rcx+24]
    mov r11, [rcx+32]
    xor eax, eax
    movzx edx, byte ptr [rdx]
    test edx, edx
context_branch:
    jz context_target_zero
context_target_one:
context_patch_one:
    nop
    nop
    movzx eax, byte ptr [r9]
    shl rax, 12
    movzx eax, byte ptr [r11+rax]
    pop rbx
    ret
    int3
    .fill 128,1,0xcc
context_target_zero:
context_patch_zero:
    nop
    nop
    movzx eax, byte ptr [r8]
    shl rax, 12
    movzx eax, byte ptr [r10+rax]
    pop rbx
    ret
    int3
    .balign 64,0xcc
context_reload:
    push rbx
    mov r10, rcx
    xor eax, eax
    cpuid
    rdtscp
    shl rdx,32
    or rax,rdx
    mov r8,rax
    lfence
    movzx eax,byte ptr [r10]
    rdtscp
    lfence
    shl rdx,32
    or rax,rdx
    sub rax,r8
    pop rbx
    ret
    int3
    .balign 64,0xcc
context_serial:
    push rbx
    xor eax,eax
    cpuid
    pop rbx
    ret
    int3
    .balign 64,0xcc
context_hot:
    push rbx
    mov r10,rcx
    xor eax,eax
    cpuid
    movzx eax,byte ptr [r10]
    pop rbx
    ret
    int3
context_end:
.section .note.GNU-stack,"",@progbits
