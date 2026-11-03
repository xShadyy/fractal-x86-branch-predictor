/* K6: Fractal x86 user/user, kernel/kernel, user/kernel and kernel/user pilot.
 * Uses the pinned Fractal fthread API, not a Windows kernel driver.
 * The actual measured routine records CS.RPL and its instruction address.
 * TCG smoke output validates control flow only; it is never physical evidence.
 */
#include "fractal_runtime.h"
#include "dependency_receiver_code.h"
#include "cpu_features.h"
#ifndef K6_PHYSICAL
#define K6_PHYSICAL 0
#endif
#ifndef K6_SEED
#define K6_SEED 2180673261u
#endif
#if K6_PHYSICAL
#define BLOCKS 256u
#define EPISODES 8u
#define WARMUP 16u
#define PRELUDE 128u
#define TRAIN 256u
#else
#define BLOCKS 2u
#define EPISODES 1u
#define WARMUP 1u
#define PRELUDE 8u
#define TRAIN 8u
#endif
#define PAGES 64u
#define STRIDE 4096u
#define CONDITIONS 16u
#define MODES 3u
#define PAIRS 4u
#define FNV_OFFSET UINT64_C(14695981039346656037)
#define FNV_PRIME UINT64_C(1099511628211)
#define ALIGN(n) __attribute__((aligned(n)))
#define NOINLINE __attribute__((noinline))
enum {CAND_T0,CAND_T1,NO_PROBE_T0,NO_PROBE_T1,HOT,COLD,ARCH_LOAD,WARM_MISMATCH};
struct context {
    volatile uint8_t *condition,*token0,*token1,*bank0,*bank1;
    volatile uint32_t sampled_cpl;
    volatile uint64_t sampled_pc;
};
typedef uint32_t (__attribute__((ms_abi)) *site_fn)(const struct context *);
typedef uint64_t (__attribute__((ms_abi)) *reload_fn)(const volatile uint8_t *);
typedef void (__attribute__((ms_abi)) *serial_fn)(void);
typedef uint32_t (__attribute__((ms_abi)) *touch_fn)(const volatile uint8_t *);
union code_pointer {void *object;site_fn site;reload_fn reload;serial_fn serial;touch_fn touch;};
struct sample {
    uint64_t wanted,decoy,train_pc,probe_pc;
    uint32_t prelude,train,probe;
    uint16_t block;
    uint8_t pair,mode,round,position,kind,tag0,tag1,other,order;
    uint8_t train_cpl,receiver_cpl,probe_cpl;
};
static ALIGN(4096) volatile uint8_t condition_line[4096],token0[4096],token1[4096];
static ALIGN(4096) volatile uint8_t banks[2][PAGES*STRIDE];
static ALIGN(4096) unsigned char runtime_code[4096];
static struct context context;
static unsigned char *code;
static site_fn branch_site;
static reload_fn reload;
static serial_fn serialize;
static touch_fn touch;
static struct sample samples[BLOCKS*PAIRS*MODES*CONDITIONS*EPISODES];
static struct sample scratch;
static volatile struct sample *active;
static volatile unsigned phase;
static uint64_t senders[2],receivers[2];
static volatile unsigned architecture_errors;
static uint64_t event_hash=FNV_OFFSET;
static uint64_t observed_cr4;
static const char *const pairs[4]={"uu","kk","uk","ku"};
static const unsigned sender_cpl[4]={3,0,3,0},receiver_cpl[4]={3,0,0,3};
static const char *const modes[3]={"plain","mask","cpuid"};
static const char *const names[16]={
    "candidate_t0_p0","candidate_t1_p0","no_probe_t0_p0","no_probe_t1_p0",
    "hot_p0","cold_p0","arch_load_p0","warm_mismatch_p0",
    "candidate_t0_p1","candidate_t1_p1","no_probe_t0_p1","no_probe_t1_p1",
    "hot_p1","cold_p1","arch_load_p1","warm_mismatch_p1"};
extern void k6_worker_entry(void);
static uint32_t next32(uint32_t *state){uint32_t x=*state;x^=x<<13;x^=x>>17;x^=x<<5;*state=x;return x;}
static uint64_t mix(uint64_t h,uint64_t v){return(h^v)*FNV_PRIME;}
static void switch_to(uint64_t tid){if(fr_syscall(39,tid,0,0,0)<0)fr_fail("fthread_switch failed");}
static void cpuid(uint32_t leaf,uint32_t w[4]){
    __asm__ __volatile__("cpuid":"=a"(w[0]),"=b"(w[1]),"=c"(w[2]),"=d"(w[3]):"a"(leaf),"c"(0):"memory");
}
static NOINLINE uint32_t invoke_shared(unsigned expected_cpl){
    uint32_t value=branch_site(&context);
    if(context.sampled_cpl!=expected_cpl||context.sampled_pc!=(uint64_t)(uintptr_t)(code+K5_BRANCH))
        ++architecture_errors;
    return value;
}
static void install_mode(unsigned mode){
    memcpy(code,dependency_code_template,sizeof dependency_code_template);
    if(mode==2u){code[K5_PATCH_ONE]=code[K5_PATCH_ZERO]=0x0f;code[K5_PATCH_ONE+1]=code[K5_PATCH_ZERO+1]=0xa2;}
    else if(mode==1u){
        static const unsigned char one[11]={0x85,0xd2,0x0f,0x44,0xc2,0x90,0x90,0x90,0x90,0x90,0x90};
        static const unsigned char zero[11]={0x85,0xd2,0xb9,0,0,0,0,0x0f,0x45,0xc1,0x90};
        memcpy(code+K5_MASK_ONE,one,11);memcpy(code+K5_MASK_ZERO,zero,11);
    }
    serialize();
}
static void snapshot(unsigned mode){
    static char hex[sizeof dependency_code_template*2+1];
    const char digits[]="0123456789abcdef";
    for(size_t i=0;i<sizeof dependency_code_template;++i){hex[2*i]=digits[code[i]>>4];hex[2*i+1]=digits[code[i]&15];}
    hex[sizeof hex-1]=0;
    fr_printf("K6_CODE,mode=%s,hex=%s\n",modes[mode],hex);
}
static inline void flush(const volatile void *p){__asm__ __volatile__("clflush (%0)"::"r"(p):"memory");}
#define FLUSH_PAGE(n) flush(&context.bank0[(n)*STRIDE]);flush(&context.bank1[(n)*STRIDE])
#define EIGHT(n) FLUSH_PAGE((n)+0u);FLUSH_PAGE((n)+1u);FLUSH_PAGE((n)+2u);FLUSH_PAGE((n)+3u);FLUSH_PAGE((n)+4u);FLUSH_PAGE((n)+5u);FLUSH_PAGE((n)+6u);FLUSH_PAGE((n)+7u)
static NOINLINE void train_prepare(struct sample *s){
    unsigned p=s->kind/8u,member=s->kind%8u;
    unsigned t=member<4u?member&1u:(member==WARM_MISMATCH?1u-p:p);
    unsigned cpl=sender_cpl[s->pair];
    uint32_t a=0,b=0;
    context.token0[0]=context.token1[0]=0;
    for(unsigned i=0;i<PRELUDE;++i){context.condition[0]=(uint8_t)((i>>1)&1u);a+=invoke_shared(cpl);}
    for(unsigned i=0;i<TRAIN;++i){context.condition[0]=(uint8_t)t;b+=invoke_shared(cpl);}
    s->prelude=a;s->train=b;s->train_cpl=(uint8_t)context.sampled_cpl;s->train_pc=context.sampled_pc;
    if(a!=PRELUDE*3u/2u||b!=TRAIN*(1u+t))++architecture_errors;
    context.token0[0]=s->tag0;context.token1[0]=s->tag1;
    context.condition[0]=(uint8_t)(member==ARCH_LOAD?1u-p:p);
    EIGHT(0u);EIGHT(8u);EIGHT(16u);EIGHT(24u);EIGHT(32u);EIGHT(40u);EIGHT(48u);EIGHT(56u);
    if(member!=WARM_MISMATCH)flush(context.condition);
    __asm__ __volatile__("mfence":::"memory");
    serialize();
}
static NOINLINE void probe_receive(struct sample *s){
    unsigned p=s->kind/8u,member=s->kind%8u;
    const volatile uint8_t *wanted=&(p?context.bank0:context.bank1)[(unsigned)(p?s->tag0:s->tag1)*STRIDE];
    const volatile uint8_t *other=&(p?context.bank0:context.bank1)[(unsigned)s->other*STRIDE];
    s->probe=0;s->probe_cpl=255u;s->probe_pc=0;
    s->receiver_cpl=(uint8_t)fr_cpl();
    if(member==HOT)(void)touch(wanted);
    else if(member!=COLD&&member!=NO_PROBE_T0&&member!=NO_PROBE_T1){
        s->probe=invoke_shared(receiver_cpl[s->pair]);
        s->probe_cpl=(uint8_t)context.sampled_cpl;s->probe_pc=context.sampled_pc;
    }
    if(s->order){s->decoy=reload(other);s->wanted=reload(wanted);}
    else{s->wanted=reload(wanted);s->decoy=reload(other);}
    unsigned expected=member==CAND_T0||member==CAND_T1||member==WARM_MISMATCH?1u+p:(member==ARCH_LOAD?2u-p:0u);
    if(s->probe!=expected||s->receiver_cpl!=receiver_cpl[s->pair])++architecture_errors;
}
void k6_worker(void){
    for(;;){
        unsigned current=phase;
        if(current==0u){switch_to(0);continue;}
        struct sample *s=(struct sample *)active;
        unsigned expected=current==1u?sender_cpl[s->pair]:receiver_cpl[s->pair];
        if(fr_cpl()!=expected||(fr_flags()&(1u<<9)))fr_fail("worker CPL or cooperative state mismatch");
        if(fr_cpl()==0)__asm__ __volatile__("mov %%cr4,%0":"=r"(observed_cr4));
        if(current==1u){
            train_prepare(s);phase=2u;
            switch_to(receivers[receiver_cpl[s->pair]==0u]);
        }else if(current==2u){probe_receive(s);phase=3u;switch_to(0);}
        else fr_fail("worker phase mismatch");
    }
}
static void shuffle(uint8_t *order,unsigned count,uint32_t *state){
    for(unsigned i=0;i<count;++i)order[i]=(uint8_t)i;
    for(unsigned i=count-1;i;--i){unsigned j=next32(state)%(i+1u);uint8_t v=order[i];order[i]=order[j];order[j]=v;}
}
static size_t collect(unsigned blocks,unsigned keep,uint32_t *schedule,uint32_t *tags){
    size_t index=0;uint8_t domain_order[4],mode_order[3],order[16];
    for(unsigned block=0;block<blocks;++block){
        shuffle(domain_order,4,schedule);
        for(unsigned dp=0;dp<4;++dp){
            unsigned pair=domain_order[dp];shuffle(mode_order,3,schedule);
            for(unsigned mp=0;mp<3;++mp){
                unsigned mode=mode_order[mp];install_mode(mode);
                for(unsigned round=0;round<EPISODES;++round){
                    shuffle(order,16,schedule);
                    for(unsigned position=0;position<16;++position){
                        unsigned kind=order[position],p=kind/8u;
                        struct sample *s=keep?&samples[index]:&scratch;memset(s,0,sizeof *s);
                        s->block=(uint16_t)block;s->pair=(uint8_t)pair;s->mode=(uint8_t)mode;s->kind=(uint8_t)kind;
                        s->round=(uint8_t)round;s->position=(uint8_t)position;
                        s->tag0=(uint8_t)(1u+next32(tags)%63u);s->tag1=(uint8_t)(1u+next32(tags)%63u);
                        unsigned wanted=p?s->tag0:s->tag1;unsigned other=1u+next32(tags)%62u;if(other>=wanted)++other;
                        s->other=(uint8_t)other;s->order=(uint8_t)(next32(tags)&1u);
                        active=s;phase=1u;switch_to(senders[sender_cpl[pair]==0u]);
                        if(phase!=3u)fr_fail("incomplete sender/receiver episode");
                        if(keep){
                            event_hash=mix(event_hash,(uint64_t)pair*65536u+mode*4096u+kind*16u+round);
                            event_hash=mix(event_hash,(uint64_t)s->tag0*65536u+s->tag1*256u+s->other*2u+s->order);
                        }
                        ++index;
                    }
                }
            }
        }
    }
    return index;
}
int main(void){
    _Static_assert(offsetof(struct context,sampled_cpl)==40&&offsetof(struct context,sampled_pc)==48,"runtime context layout");
    struct cache_cpu_features cpu;uint32_t w[4];
    cache_detect_cpu(&cpu);cpuid(1,w);unsigned hypervisor=w[2]>>31;
    cpuid(0x80000001u,w);if(!(w[3]&(1u<<27))||!cpu.has_clflush)fr_fail("RDTSCP and CLFLUSH required");
    if(cpu.vendor[0]!='A')fr_fail("AMD timing contract required");
    if(K6_PHYSICAL&&(hypervisor||!cpu.invariant_tsc||cpu.signature!=0x00b40f40u))
        fr_fail("physical pilot requires documented Ryzen, invariant TSC and no reported hypervisor");
    if(fr_cpl()!=3u)fr_fail("controller must start in user mode");
    (void)fr_syscall(29,5,1,0,0); /* Upstream returns -1 even after changing this flag. */
    if(fr_flags()&(1u<<9))fr_fail("controller is not cooperative");
    (void)fr_syscall(29,6,0,0,0);
    for(unsigned i=0;i<2u;++i){
        unsigned attrs=(i?FR_KERNEL:FR_USER)|FR_COOPERATIVE;
        if(fr_syscall(36,(uint64_t)(uintptr_t)&senders[i],attrs,(uint64_t)(uintptr_t)k6_worker_entry,0)<0||
           fr_syscall(36,(uint64_t)(uintptr_t)&receivers[i],attrs,(uint64_t)(uintptr_t)k6_worker_entry,0)<0)
            fr_fail("cannot create Fractal fthreads");
    }
    context.condition=condition_line;context.token0=token0;context.token1=token1;context.bank0=banks[0];context.bank1=banks[1];
    for(unsigned p=0;p<2;++p)for(unsigned i=0;i<PAGES;++i)banks[p][i*STRIDE]=(uint8_t)(1u+p);
    union code_pointer ptr;code=runtime_code;
    ptr.object=code;branch_site=ptr.site;ptr.object=code+K5_RELOAD;reload=ptr.reload;
    ptr.object=code+K5_SERIAL;serialize=ptr.serial;ptr.object=code+K5_HOT;touch=ptr.touch;
    fr_printf("K6_CPU,vendor=%s,signature=0x%x,clflush_bytes=%u,invariant_tsc=%u,rdtscp=1,hypervisor=%u\n",
              cpu.vendor,cpu.signature,cpu.clflush_bytes,cpu.invariant_tsc,hypervisor);
    fr_printf("K6_RUN,version=1,protocol=fractal_privilege_k6_v1,scope=%s,blocks=%u,episodes=%u,warmup=%u,prelude=%u,train=%u,seed=%u,code_addr=0x%llx,branch_offset=%u,code_bytes=%u,domains=4,modes=3,conditions=16,controller_cpl=3,condition_addr=0x%llx,token0_addr=0x%llx,token1_addr=0x%llx,bank0_addr=0x%llx,bank1_addr=0x%llx,upstream=03ad1c5b7c33621e7529ac6403eb9b1de4f8722f\n",
              K6_PHYSICAL?"physical_pilot":"development_only",BLOCKS,EPISODES,WARMUP,PRELUDE,TRAIN,(unsigned)K6_SEED,
              (unsigned long long)(uintptr_t)code,K5_BRANCH,(unsigned)sizeof dependency_code_template,
              (unsigned long long)(uintptr_t)condition_line,(unsigned long long)(uintptr_t)token0,
              (unsigned long long)(uintptr_t)token1,(unsigned long long)(uintptr_t)banks[0],(unsigned long long)(uintptr_t)banks[1]);
    for(unsigned m=0;m<3;++m){install_mode(m);snapshot(m);}
    uint32_t schedule=K6_SEED,tags=K6_SEED^0xa5f1523du;if(!tags)tags=1;
    (void)collect(WARMUP,0,&schedule,&tags);
    size_t count=collect(BLOCKS,1,&schedule,&tags);uint64_t checksum=0;
    for(size_t i=0;i<count;++i){
        struct sample *s=&samples[i];checksum=mix(mix(mix(checksum,i+1u),s->wanted),s->decoy);
        fr_printf("K6_SAMPLE,%llu,%u,%s,%s,%u,%u,%s,%u,%u,%u,%u,%llu,%llu,%u,%u,%u,%u,%u,%u,0x%llx,0x%llx\n",
                  (unsigned long long)i,(unsigned)s->block,pairs[s->pair],modes[s->mode],(unsigned)s->round,(unsigned)s->position,
                  names[s->kind],(unsigned)s->tag0,(unsigned)s->tag1,(unsigned)s->other,(unsigned)s->order,
                  (unsigned long long)s->wanted,(unsigned long long)s->decoy,s->prelude,s->train,s->probe,
                  (unsigned)s->train_cpl,(unsigned)s->receiver_cpl,(unsigned)s->probe_cpl,
                  (unsigned long long)s->train_pc,(unsigned long long)s->probe_pc);
    }
    fr_printf("K6_END,count=%llu,checksum=%llu,event_hash=%llu,architecture_errors=%u,observed_cr4=0x%llx\n",
              (unsigned long long)count,(unsigned long long)checksum,(unsigned long long)event_hash,
              architecture_errors,(unsigned long long)observed_cr4);
    if(architecture_errors)fr_fail("actual CPL, site, or architectural return validation failed");
    fr_printf("FRACTAL_K6_OK: privilege transitions and complete trace collected\n");
    return 0;
}
