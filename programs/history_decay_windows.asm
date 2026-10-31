; Single conditional branch site for prelude, training, filler and probe.
; RCX live byte, RDX fixed periodic byte, R8 mode (1=live, 0=fixed).
; The same live byte is returned regardless of selected decision.
OPTION CASEMAP:NONE
PUBLIC decay_branch_site
PUBLIC decay_small_work
.code
decay_branch_site PROC
    movzx eax, byte ptr [rcx]
    movzx r10d, byte ptr [rdx]
    movzx r11d, byte ptr [r8]
    test r11d, r11d
    cmovnz r10d, eax
    test r10d, r10d
    jz SHORT decay_skip
    nop
decay_skip:
    ret
decay_branch_site ENDP

; A short, result-dependent operation chain for timer resolution calibration.
; Its actual cost and complete optimized call path require physical EXE audit.
decay_small_work PROC
    mov eax, ecx
    imul eax, eax, 3
    imul eax, eax, 3
    xor eax, ecx
    ret
decay_small_work ENDP
END
