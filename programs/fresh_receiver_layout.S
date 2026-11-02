.intel_syntax noprefix
.text
.global fresh_start, fresh_branch, fresh_patch_one, fresh_patch_zero
.global fresh_target_one, fresh_target_zero, fresh_reload, fresh_serial, fresh_hot, fresh_end
fresh_start:
    push rbx
    mov rdx, [rcx]
    mov r8, [rcx+8]
    mov r9, [rcx+16]
    mov r10, [rcx+24]
    mov r11, [rcx+32]
    xor eax, eax
    movzx edx, byte ptr [rdx]
    test edx, edx
fresh_branch:
    jz fresh_target_zero
fresh_target_one:
fresh_patch_one:
    nop
    nop
    movzx eax, byte ptr [r9]
    shl rax, 12
    movzx eax, byte ptr [r11+rax]
    pop rbx
    ret
    int3
    .fill 128,1,0xcc
fresh_target_zero:
fresh_patch_zero:
    nop
    nop
    movzx eax, byte ptr [r8]
    shl rax, 12
    movzx eax, byte ptr [r10+rax]
    pop rbx
    ret
    int3
    .balign 64,0xcc
fresh_reload:
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
fresh_serial:
    push rbx
    xor eax,eax
    cpuid
    pop rbx
    ret
    int3
    .balign 64,0xcc
fresh_hot:
    push rbx
    mov r10,rcx
    xor eax,eax
    cpuid
    movzx eax,byte ptr [r10]
    pop rbx
    ret
    int3
fresh_end:
.section .note.GNU-stack,"",@progbits
