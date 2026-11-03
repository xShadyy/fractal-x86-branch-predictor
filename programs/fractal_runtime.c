#include "fractal_runtime.h"
#include <stdarg.h>
void *memcpy(void *dst, const void *src, size_t n) {
    unsigned char *d = dst; const unsigned char *s = src;
    for (size_t i=0; i<n; ++i) d[i]=s[i];
    return dst;
}
void *memset(void *dst, int value, size_t n) {
    unsigned char *d=dst;
    for (size_t i=0; i<n; ++i) d[i]=(unsigned char)value;
    return dst;
}
int memcmp(const void *a, const void *b, size_t n) {
    const unsigned char *x=a,*y=b;
    for (size_t i=0; i<n; ++i) if (x[i]!=y[i]) return x[i]<y[i]?-1:1;
    return 0;
}
size_t strlen(const char *s) { size_t n=0; while(s[n]) ++n; return n; }
int fr_printf(const char *format, ...) {
    char buffer[8192]; size_t used=0;
    va_list args; va_start(args,format);
    while (*format) {
        if (used+80>=sizeof buffer) fr_fail("output line exceeds fixed buffer");
        if (*format!='%') {buffer[used++]=*format++;continue;}
        ++format;
        if (*format=='%') {buffer[used++]='%';++format;continue;}
        int wide=0;
        if (*format=='l') {++format;wide=1;if(*format=='l'){++format;wide=2;}}
        char type=*format++;
        if (type=='s') {
            const char *p=va_arg(args,const char *);
            while(*p) {if(used+1>=sizeof buffer)fr_fail("string too long");buffer[used++]=*p++;}
        } else if(type=='u'||type=='x'||type=='d') {
            uint64_t value;
            if (type=='d') {int n=va_arg(args,int);if(n<0){buffer[used++]='-';value=(uint64_t)(-(int64_t)n);}else value=(uint64_t)n;}
            else value=wide==2?(uint64_t)va_arg(args,unsigned long long):
                       wide==1?(uint64_t)va_arg(args,unsigned long):(uint64_t)va_arg(args,unsigned);
            const unsigned base=type=='x'?16u:10u;
            char digits[32];unsigned count=0;
            do {digits[count++]="0123456789abcdef"[value%base];value/=base;}while(value);
            while(count)buffer[used++]=digits[--count];
        } else fr_fail("unsupported output format");
    }
    va_end(args);
    long result=fr_syscall(5,1,(uint64_t)(uintptr_t)buffer,used,0);
    if (result!=(long)used) fr_syscall(2,2,0,0,0);
    return (int)used;
}
void fr_fail(const char *message) {
    const char prefix[]="K6_ERROR: ";
    fr_syscall(5,1,(uint64_t)(uintptr_t)prefix,sizeof prefix-1,0);
    fr_syscall(5,1,(uint64_t)(uintptr_t)message,strlen(message),0);
    fr_syscall(5,1,(uint64_t)(uintptr_t)"\n",1,0);
    fr_syscall(2,1,0,0,0);
    for(;;)__asm__ __volatile__("pause");
}
