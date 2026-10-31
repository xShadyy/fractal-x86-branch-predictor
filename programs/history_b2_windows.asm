; Exploratory B2: one conditional jump shared by prelude, real/fixed training,
; and n=1/n=16 probes. RCX=live byte, RDX=fixed byte, R8=mode byte.
; Mode 0 follows fixed, mode 1 follows live. AL always returns live.
OPTION CASEMAP:NONE
PUBLIC history_b2_branch_site
PUBLIC history_b2_sham_site
.code
history_b2_branch_site PROC
    movzx eax, byte ptr [rcx]
    movzx r9d, byte ptr [rdx]
    movzx r10d, byte ptr [r8]
    test r10d, r10d
    cmovne r9d, eax
    test r9d, r9d
    jz SHORT history_b2_zero
    nop
history_b2_zero:
    ret
history_b2_branch_site ENDP

; Sham preserves the live-value read and return but has a different site/path.
history_b2_sham_site PROC
    movzx eax, byte ptr [rcx]
    ret
history_b2_sham_site ENDP
END
