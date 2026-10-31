; One fixed branch site. Every call reads the live input, periodic control,
; and runtime source flag. Only the selected decision controls this jz.
; RCX: live input, RDX: periodic control, R8: source flag (1=live),
; return EAX: live input (0/1), regardless of source and branch outcome.
OPTION CASEMAP:NONE
PUBLIC pattern_complexity_branch
PUBLIC pattern_complexity_branchless
.code
pattern_complexity_branch PROC
    movzx eax, byte ptr [rcx]
    movzx r10d, byte ptr [rdx]
    movzx r11d, byte ptr [r8]
    test r11d, r11d
    cmovnz r10d, eax
    test r10d, r10d
    jz SHORT decision_skip
    nop
decision_skip:
    ret
pattern_complexity_branch ENDP

; Same three reads and selection, but no conditional jump.
pattern_complexity_branchless PROC
    movzx eax, byte ptr [rcx]
    movzx r10d, byte ptr [rdx]
    movzx r11d, byte ptr [r8]
    test r11d, r11d
    cmovnz r10d, eax
    test r10d, r10d
    setnz r10b
    ret
pattern_complexity_branchless ENDP
END
