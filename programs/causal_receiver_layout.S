.intel_syntax noprefix
.text
.global causal_start, causal_branch, causal_patch_one, causal_patch_zero
.global causal_mask_one, causal_mask_zero, causal_load_one, causal_load_zero
.global causal_target_one, causal_target_zero, causal_reload, causal_serial, causal_hot, causal_end
causal_start:
    /* Fixed K5 history prefix. This is not a predictor reset. */
    xor eax,eax
    .rept 256
        test eax,eax
        jz 1f
        int3
    1:
    .endr
    .fill 62,1,0x90
    push rbx
    push rsi
    push rdi
    xor esi,esi
    mov edi,1
    xor eax,eax
    mov ax,cs
    and eax,3
    mov [rcx+40],eax
    lea rax,[rip+.Lcausal_branch]
    mov [rcx+48],rax
    mov rdx,[rcx]
    mov r8,[rcx+8]
    mov r9,[rcx+16]
    mov r10,[rcx+24]
    mov r11,[rcx+32]
    xor eax,eax
    movzx edx,byte ptr [rdx]
    test edx,edx
.Lcausal_branch:
causal_branch:
    jz causal_target_zero
causal_target_one:
causal_patch_one:
    .fill 3,1,0x90
    movzx eax,byte ptr [r9]
    shl rax,12
causal_mask_one:
    .fill 11,1,0x90
causal_load_one:
    movzx eax,byte ptr [r11+rax]
    pop rdi
    pop rsi
    pop rbx
    ret
    int3
    .fill 128,1,0xcc
causal_target_zero:
causal_patch_zero:
    .fill 3,1,0x90
    movzx eax,byte ptr [r8]
    shl rax,12
causal_mask_zero:
    .fill 11,1,0x90
causal_load_zero:
    movzx eax,byte ptr [r10+rax]
    pop rdi
    pop rsi
    pop rbx
    ret
    int3
    .balign 64,0xcc
causal_reload:
    push rbx
    mov r10,rcx
    mov r9,rdx
    xor eax,eax
    cpuid
    rdtscp
    mov r11d,ecx
    shl rdx,32
    or rax,rdx
    mov r8,rax
    lfence
    movzx eax,byte ptr [r10]
    rdtscp
    lfence
    /* Record both AUX values after the timed load; R9 survives CPUID/RDTSCP. */
    mov [r9],r11d
    mov [r9+4],ecx
    shl rdx,32
    or rax,rdx
    sub rax,r8
    pop rbx
    ret
    int3
    .balign 64,0xcc
causal_serial:
    push rbx
    xor eax,eax
    cpuid
    pop rbx
    ret
    int3
    .balign 64,0xcc
causal_hot:
    push rbx
    mov r10,rcx
    xor eax,eax
    cpuid
    movzx eax,byte ptr [r10]
    pop rbx
    ret
    int3
causal_end:
.section .note.GNU-stack,"",@progbits
