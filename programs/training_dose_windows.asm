; One conditional branch for every prelude, fixed prefix, real/fixed training,
; and one-call probe. Mode 0 selects periodic control, mode 1 selects live.
; RCX: live byte, RDX: periodic byte, R8: mode byte; AL returns live byte.
OPTION CASEMAP:NONE
PUBLIC training_dose_branch_site
.code
training_dose_branch_site PROC
    movzx eax, byte ptr [rcx]
    movzx r10d, byte ptr [rdx]
    movzx r11d, byte ptr [r8]
    test r11d, r11d
    cmovnz r10d, eax
    test r10d, r10d
    jz SHORT dose_zero
    nop
dose_zero:
    ret
training_dose_branch_site ENDP
END
