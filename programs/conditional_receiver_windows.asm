; K1: one conditional branch shared by balanced prelude, training, probe.
; RCX=flushable condition line, RDX=target0 data line, R8=target1 data line.
; The two target paths read different, page-separated data lines and return
; their 1/2 byte values. Audit the linked PE for path exclusivity.
OPTION CASEMAP:NONE
.code
conditional_receiver_site PROC PUBLIC
    movzx r9d, byte ptr [rcx]
    test r9d, r9d
    jz conditional_receiver_target_zero
conditional_receiver_site ENDP

; Fall-through from the not-zero decision. A separate PROC makes the target
; a module-level symbol that ml64 can export for linked/runtime address audit.
conditional_receiver_target_one PROC PUBLIC
    movzx eax, byte ptr [r8]
    ret
conditional_receiver_target_one ENDP
; The two target code bodies cannot share a 64-byte fetch line. This is a
; candidate data-cache receiver, not an instruction-fetch measurement.
DB 128 DUP (90h)
conditional_receiver_target_zero PROC PUBLIC
    movzx eax, byte ptr [rdx]
    ret
conditional_receiver_target_zero ENDP
END
