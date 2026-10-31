; Audited, relocation-free branch template copied to three executable addresses.
; RCX=live byte, RDX=fixed byte, R8=mode (1=live, 0=fixed).
; All paths return the live byte in AL. The caller uses one indirect callsite.
OPTION CASEMAP:NONE
PUBLIC address_branch_template
PUBLIC address_branch_template_end
PUBLIC address_sham_site
.code
address_branch_template PROC
    movzx eax, byte ptr [rcx]
    movzx r10d, byte ptr [rdx]
    movzx r11d, byte ptr [r8]
    test r11d, r11d
    cmovne r10d, eax
    test r10d, r10d
    jz SHORT address_zero
    nop
address_zero:
    ret
address_branch_template ENDP
address_branch_template_end LABEL BYTE

address_sham_site PROC
    movzx eax, byte ptr [rcx]
    ret
address_sham_site ENDP
END
