; One conditional branch site for all preludes, training and probe calls.
; RCX=live byte, RDX=fixed periodic byte, R8=mode (1=live, 0=fixed).
OPTION CASEMAP:NONE
PUBLIC prelude_branch_site
PUBLIC prelude_sham_site
PUBLIC prelude_small_work
.code
prelude_branch_site PROC
    movzx eax, byte ptr [rcx]
    movzx r10d, byte ptr [rdx]
    movzx r11d, byte ptr [r8]
    test r11d, r11d
    cmovnz r10d, eax
    test r10d, r10d
    jz SHORT prelude_zero
    nop
prelude_zero:
    ret
prelude_branch_site ENDP

prelude_sham_site PROC
    movzx eax, byte ptr [rcx]
    ret
prelude_sham_site ENDP

; Result-dependent small-work timer check; audit linked PE and sensitivity.
prelude_small_work PROC
    mov eax, ecx
    imul eax, eax, 3
    imul eax, eax, 3
    xor eax, ecx
    ret
prelude_small_work ENDP
END
