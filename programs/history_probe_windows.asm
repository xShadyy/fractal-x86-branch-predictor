; Same user-mode conditional branch for reset, training, and measured probe.
; RCX points to one volatile 0/1 byte; AL returns the architectural value.
OPTION CASEMAP:NONE
PUBLIC history_no_load_site
PUBLIC history_sham_site
.code
history_no_load_site PROC
    movzx eax, byte ptr [rcx]
    test eax, eax
    jz SHORT history_zero
    mov al, 1
    nop
    ret
history_zero:
    xor eax, eax
    ret
history_no_load_site ENDP

; Input-matched trainer with no data-dependent branch or target-byte load.
history_sham_site PROC
    movzx eax, byte ptr [rcx]
    ret
history_sham_site ENDP
END
