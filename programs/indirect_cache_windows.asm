; Single user-mode indirect JMP used by prelude, training, and the measured
; architectural probe. RCX points at a dedicated, flushable pointer slot;
; RDX and R8 point at independent data lines for target zero and target one.
; Targets return different architectural values (1 and 2), allowing a C-side
; check that the selected target really executed. Audit the *linked* EXE.
OPTION CASEMAP:NONE
PUBLIC indirect_cache_site
PUBLIC indirect_cache_target_zero
PUBLIC indirect_cache_target_one
PUBLIC indirect_cache_sham_train
.code
indirect_cache_site PROC
    mov rax, qword ptr [rcx]
    jmp rax
indirect_cache_site ENDP

ALIGN 16
indirect_cache_target_zero PROC
    movzx eax, byte ptr [rdx]
    ret
indirect_cache_target_zero ENDP

; The first and second target bodies cannot share any 64-byte I-cache line,
; regardless of their actual linked image alignment. No speculative fence.
DB 128 DUP (90h)
indirect_cache_target_one PROC
    movzx eax, byte ptr [r8]
    ret
indirect_cache_target_one ENDP

; Branchless comparator reads a live label, returning the same 1/2 value.
indirect_cache_sham_train PROC
    movzx eax, byte ptr [rcx]
    inc eax
    ret
indirect_cache_sham_train ENDP
END
