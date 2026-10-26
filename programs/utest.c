/* Fractal x86 boot smoke test. No branch predictor result is produced here. */
#include <stdio.h>

int main(void) {
    puts("FRACTAL_UTEST_OK: x86 userspace program started");
    fflush(stdout);
    return 0;
}
