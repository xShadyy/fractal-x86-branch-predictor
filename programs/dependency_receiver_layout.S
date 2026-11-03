.intel_syntax noprefix
.text
.global dependency_start, dependency_branch, dependency_patch_one, dependency_patch_zero
.global dependency_mask_one, dependency_mask_zero
.global dependency_target_one, dependency_target_zero, dependency_reload, dependency_serial, dependency_hot, dependency_end
dependency_start:
    /* K5/K6: identical fixed branch prefix before every training and probe call.
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
    xor eax,eax
    mov ax,cs
    and eax,3
    mov [rcx+40],eax
    lea rax,[rip+.Ldependency_branch]
    mov [rcx+48],rax
    mov rdx, [rcx]
    mov r8, [rcx+8]
    mov r9, [rcx+16]
    mov r10, [rcx+24]
    mov r11, [rcx+32]
    xor eax, eax
    movzx edx, byte ptr [rdx]
    test edx, edx
.Ldependency_branch:
dependency_branch:
    jz dependency_target_zero
dependency_target_one:
dependency_patch_one:
    .fill 3,1,0x90
    movzx eax, byte ptr [r9]
    shl rax, 12
dependency_mask_one:
    .fill 11,1,0x90
    movzx eax, byte ptr [r11+rax]
    pop rbx
    ret
    int3
    .fill 128,1,0xcc
dependency_target_zero:
dependency_patch_zero:
    .fill 3,1,0x90
    movzx eax, byte ptr [r8]
    shl rax, 12
dependency_mask_zero:
    .fill 11,1,0x90
    movzx eax, byte ptr [r10+rax]
    pop rbx
    ret
    int3
    .balign 64,0xcc
dependency_reload:
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
dependency_serial:
    push rbx
    xor eax,eax
    cpuid
    pop rbx
    ret
    int3
    .balign 64,0xcc
dependency_hot:
    push rbx
    mov r10,rcx
    xor eax,eax
    cpuid
    movzx eax,byte ptr [r10]
    pop rbx
    ret
    int3
dependency_end:
.section .note.GNU-stack,"",@progbits
