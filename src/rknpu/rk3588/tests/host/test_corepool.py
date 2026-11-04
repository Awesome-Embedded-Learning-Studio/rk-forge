"""在主机执行实际 corepool header,模拟 OF/sysfs/device ref,检查调度与失败回收。"""
from pathlib import Path
import os
import subprocess

import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from paths import REPO, KERNEL, artifact_dir

stubs = r'''
#include <assert.h>
#include <errno.h>
#include <pthread.h>
#include <stddef.h>
#include <stdint.h>
#include <stdbool.h>
#include <stdio.h>
#include <stdatomic.h>
#include <string.h>
#include <sys/types.h>
#include <stdarg.h>
#include <stdlib.h>
typedef unsigned long long u64;
typedef struct { atomic_llong value; } atomic64_t;
#define atomic64_read(a) atomic_load(&(a)->value)
#define atomic64_set(a,v) atomic_store(&(a)->value,(v))
#define atomic64_inc(a) atomic_fetch_add(&(a)->value,1)
#define ARRAY_SIZE(a) (sizeof(a)/sizeof((a)[0]))
#define container_of(p,t,m) ((t *)((char *)(p)-offsetof(t,m)))
#define EPROBE_DEFER 517
#define DL_FLAG_AUTOREMOVE_CONSUMER 1
struct list_head { struct list_head *next,*prev; };
#define LIST_HEAD_INIT(n) { &(n), &(n) }
#define INIT_LIST_HEAD(p) ((p)->next=(p),(p)->prev=(p))
static void list_del_init(struct list_head *p) { p->prev->next=p->next;p->next->prev=p->prev;INIT_LIST_HEAD(p); }
static void list_add_tail(struct list_head *p,struct list_head *h) { p->prev=h->prev;p->next=h;h->prev->next=p;h->prev=p; }
static void list_move_tail(struct list_head *p,struct list_head *h) { list_del_init(p);list_add_tail(p,h); }
#define list_for_each_entry(p,h,m) for (p=container_of((h)->next,__typeof__(*p),m); &(p)->m!=(h); p=container_of((p)->m.next,__typeof__(*p),m))
struct mutex { pthread_mutex_t value; };
#define __MUTEX_INITIALIZER(n) {PTHREAD_MUTEX_INITIALIZER}
#define mutex_lock(m) pthread_mutex_lock(&(m)->value)
#define mutex_unlock(m) pthread_mutex_unlock(&(m)->value)
struct device_node { const char *type; int available; };
static struct device_node nodes[]={{"rga3",1},{"rga3",1},{"rga2",1},{"rga3",0}};
struct device { struct device_node *of_node; atomic_int refs; int files; };
struct attribute { const char *name; int mode; };
struct device_attribute { struct attribute attr; ssize_t (*show)(struct device*,struct device_attribute*,char*); };
static int fail_attr=-1,attr_calls,fail_link;
#define sysfs_attr_init(a) ((void)(a))
static int device_create_file(struct device *d,struct device_attribute *a) { (void)a;if (attr_calls++==fail_attr)return -ENOMEM;d->files++;return 0; }
static void device_remove_file(struct device *d,struct device_attribute *a) { (void)a;d->files--;assert(d->files>=0); }
static void get_device(struct device *d) { atomic_fetch_add(&d->refs,1); }
static void put_device(struct device *d) { assert(atomic_fetch_sub(&d->refs,1)>0); }
static void *device_link_add(struct device *a,struct device *b,int flags) { (void)a;(void)b;(void)flags;return fail_link?NULL:(void*)1; }
static const char *dev_name(struct device *d) { return d->of_node->type; }
static void dev_info(struct device *d,const char *fmt,...) { (void)d;(void)fmt; }
static int of_property_read_string(struct device_node *n,const char *key,const char **s) { (void)key;*s=n->type;return 0; }
static struct device_node *of_find_compatible_node(struct device_node *n,void *unused,const char *s) { (void)unused;size_t start=n?(size_t)(n-nodes)+1:0;for(size_t i=start;i<ARRAY_SIZE(nodes);i++)if(!strcmp(nodes[i].type,s))return &nodes[i];return NULL; }
static int of_device_is_available(struct device_node *n) { return n->available; }
static void of_node_put(struct device_node *n) { (void)n; }
static ssize_t sysfs_emit(char *b,const char *fmt,...) { va_list a;va_start(a,fmt);int n=vsprintf(b,fmt,a);va_end(a);return n; }
'''
tests = r'''
static DEFINE_V4L2_M2M_CORE_POOL(pool);
static struct v4l2_m2m_core a,b,c;
static void *thread_run(void *unused) { (void)unused;for(int i=0;i<1000;i++){struct v4l2_m2m_core *p=v4l2_m2m_core_acquire(&a);assert(p==&a || p==&b);v4l2_m2m_core_release(p);}return NULL; }
int main(void) {
 struct device da={&nodes[0],0,0},db={&nodes[1],0,0},dc={&nodes[2],0,0};
 assert(v4l2_m2m_core_init(&pool,&b,&db)==-EPROBE_DEFER);
 assert(!v4l2_m2m_core_init(&pool,&a,&da));assert(v4l2_m2m_core_is_leader(&a));
 assert(!v4l2_m2m_core_register(&a));assert(da.files==4);
 fail_link=1;assert(v4l2_m2m_core_init(&pool,&b,&db)==-ENOMEM);assert(!da.refs);fail_link=0;
 assert(!v4l2_m2m_core_init(&pool,&b,&db));assert(b.leader==&a);assert(!v4l2_m2m_core_register(&b));
 assert(!v4l2_m2m_core_init(&pool,&c,&dc));assert(!v4l2_m2m_core_register(&c));
 struct v4l2_m2m_core *leases[8];
 for(int i=0;i<8;i++) leases[i]=v4l2_m2m_core_acquire(&a);
 assert(a.users==4 && b.users==4 && !c.users);
 for(int i=0;i<8;i++)v4l2_m2m_core_release(leases[i]);
 assert(!a.users && !b.users && !da.refs && !db.refs);
 pthread_t threads[8];for(int i=0;i<8;i++)assert(!pthread_create(&threads[i],NULL,thread_run,NULL));
 for(int i=0;i<8;i++)assert(!pthread_join(threads[i],NULL));
 assert(!a.users && !b.users && !da.refs && !db.refs);
 atomic64_inc(&a.submitted);atomic64_inc(&a.completed);char text[64];
 assert(v4l2_m2m_core_stat_show(&da,&a.attrs[1].attr,text)>0 && !strcmp(text,"1\n"));
 v4l2_m2m_core_remove(&b);assert(!db.files);
 assert(v4l2_m2m_core_acquire(&a)==&a);v4l2_m2m_core_release(&a);
 v4l2_m2m_core_remove(&a);v4l2_m2m_core_remove(&c);assert(!da.files && !dc.files);
 assert(!v4l2_m2m_core_acquire(&a));
 assert(!v4l2_m2m_core_init(&pool,&a,&da));attr_calls=0;fail_attr=2;
 assert(v4l2_m2m_core_register(&a)==-ENOMEM);assert(!da.files);assert(!v4l2_m2m_core_acquire(&a));
 puts("OK: leader deferral, link failure, type isolation, balanced leases, 8000 concurrent acquire/release, sysfs counters, removal, partial registration rollback");
}
'''
def main():
    header = KERNEL / 'include/media/v4l2-m2m-corepool.h'
    if header.is_file():
        production = header.read_text()
    else:
        patch = REPO / 'boards/rk3588-topeet/patches/linux/0041-media-rockchip-enable-multicore-session-pools.patch'
        section = patch.read_text().split('+++ b/include/media/v4l2-m2m-corepool.h\n', 1)[1].split('\ndiff --git ', 1)[0]
        production = '\n'.join(line[1:] for line in section.splitlines() if line.startswith('+'))
    source = '\n'.join(line for line in production.splitlines() if not line.startswith('#include '))
    assert 'v4l2_m2m_core_acquire' in source
    out = artifact_dir('corepool')
    p = out / 'corepool.c'
    p.write_text(stubs + source + tests)
    binary = out / 'corepool'
    subprocess.run(['cc', '-std=gnu11', '-O1', '-g', '-Wall', '-Wextra', '-Werror',
                    '-Wno-unused-parameter', '-fsanitize=address,undefined', '-pthread',
                    str(p), '-o', str(binary)], check=True)
    subprocess.run([str(binary)], env=dict(os.environ, ASAN_OPTIONS='detect_leaks=0'), check=True)
    print('Evidence:', out)
    return 0


def test_corepool():
    main()


if __name__ == '__main__':
    raise SystemExit(main())
