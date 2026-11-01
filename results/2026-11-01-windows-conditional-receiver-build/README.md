# K1 conditional receiver: failed assembly attempts

**Status:** build failures, not physical receiver outcomes. Do not count
either attempt as a cache null, a failed apparatus gate, or a result about
speculative execution.

The supplied partial diagnostic archive
`conditional-receiver-windows-20261101T170058328Z.zip`, SHA-256
`81ad2a549331531096356d20d3997a1e1556c6a6582bb595cd26a927328252b2`,
records seed `2759950707`, clean Git HEAD
`8352e598331a2897b790958385976e5c421575cf`, and MASM version
14.51.36260.0. Its ZIP CRC, two manifest member hashes and eleven recorded
source hashes pass. `ml64` stopped before linking:

```text
conditional_receiver_windows.asm(7) : error A2006:undefined symbol : conditional_receiver_target_zero
conditional_receiver_windows.asm(8) : error A2006:undefined symbol : conditional_receiver_target_one
```

The user also reported a second failed assembly attempt with seed `54826516`
and partial diagnostic ZIP
`conditional-receiver-windows-20261101T170118406Z.zip`, whose displayed
SHA-256 was
`58e2af84ee2d786451d9d555c0b161dbc32683f9b48ada7c56c3ab7ad66d7d92`.
That second ZIP has not been supplied for independent archive verification.
Its displayed `A2006` errors match the first attempt. There is no EXE, raw
receiver trace, linked disassembly, calibration result or physical target
effect in the supplied archive.

The assembly source declared both target labels `PUBLIC` while defining
them as colon labels **inside** `conditional_receiver_site PROC`. MASM
scopes those labels to the procedure, so the requested module-level exports
were undefined. The corrected source ends the site `PROC` after the
conditional jump and defines each target body as its own `PROC`/`ENDP`.
This changes symbol scope, not the planned condition matrix or analysis.
The fix has not yet been built on the Windows workstation. Its first
successful EXE still needs the linked instruction, address and receiver
control audit specified in [`CONDITIONAL_RECEIVER_V1.md`](../../CONDITIONAL_RECEIVER_V1.md).

Preserve both failed attempts in the attempt ledger. Do not replace their
status with the later repaired version's measurements.
