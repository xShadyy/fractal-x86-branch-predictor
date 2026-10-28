; One fixed x64 conditional branch for training and probing.
; RCX: condition line, RDX: sentinel line; result: AL.
OPTION CASEMAP:NONE
PUBLIC spec_branch_site
.code
ALIGN 64
spec_branch_site PROC
    movzx eax, byte ptr [rcx]
    test eax, eax
    jz SHORT spec_skip_target
    movzx eax, byte ptr [rdx]
    ret
spec_skip_target:
    xor eax, eax
    ret
spec_branch_site ENDP
END
