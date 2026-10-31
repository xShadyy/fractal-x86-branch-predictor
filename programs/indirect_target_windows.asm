; One fixed indirect JMP dispatches to two distinct address targets.
; Both targets have byte-identical bodies and return the live input in EAX.
; RCX=live byte, RDX=fixed periodic byte, R8=mode (1=live, 0=fixed).
OPTION CASEMAP:NONE
PUBLIC indirect_target_site
PUBLIC indirect_target_zero
PUBLIC indirect_target_one
PUBLIC indirect_target_sham_site
.code
indirect_target_site PROC
    movzx r9d, byte ptr [rcx]
    movzx r10d, byte ptr [rdx]
    movzx r11d, byte ptr [r8]
    test r11d, r11d
    cmovne r10d, r9d
    lea r11, indirect_target_zero
    lea rax, indirect_target_one
    test r10d, r10d
    cmovne r11, rax
    jmp r11
indirect_target_site ENDP

ALIGN 16
indirect_target_zero PROC
    mov eax, r9d
    ret
indirect_target_zero ENDP
indirect_target_one PROC
    mov eax, r9d
    ret
indirect_target_one ENDP

; Separate branchless sham returns the same live byte.
indirect_target_sham_site PROC
    movzx eax, byte ptr [rcx]
    ret
indirect_target_sham_site ENDP
END
