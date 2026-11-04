#define _GNU_SOURCE
#include <dlfcn.h>
#include <stdarg.h>
#include <assert.h>
#include <errno.h>
#include <glob.h>
#include <linux/media.h>
#include <linux/videodev2.h>
#include <linux/v4l2-controls.h>
#include <poll.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/mman.h>
#include <unistd.h>
static unsigned initialized,control_setup_failed;static unsigned formatted[2],allocated[2];static int vfd=-1;static unsigned queued[2],fmt[2],stride[2];static void *maps[2][4];static size_t lens[2][4];
static void *(*next_mmap)(void*,size_t,int,int,int,off_t);static int (*next_poll)(struct pollfd*,nfds_t,int);
__attribute__((constructor)) static void init(void){next_mmap=dlsym(RTLD_NEXT,"mmap");next_poll=dlsym(RTLD_NEXT,"poll");}
void *mmap(void *a,size_t n,int p,int f,int fd,off_t off){if(fd!=vfd)return next_mmap(a,n,p,f,fd,off);unsigned q=off>=0x100000;unsigned i=(off%0x100000)/0x10000;assert(i<4);void *x=next_mmap(a,n,p,MAP_PRIVATE|MAP_ANONYMOUS,-1,0);maps[q][i]=x;lens[q][i]=n;return x;}
int poll(struct pollfd *p,nfds_t n,int timeout){if(n==1&&(p[0].fd==vfd||p[0].fd==200)){p[0].revents=p[0].events;return 1;}return next_poll(p,n,timeout);}
int glob(const char *pattern,int flags,int (*err)(const char*,int),glob_t *g){(void)flags;(void)err;assert(!strcmp(pattern,"/dev/media*"));g->gl_pathc=1;g->gl_pathv=calloc(2,sizeof(char*));g->gl_pathv[0]=strdup("/dev/null");return 0;}
static void process(void){unsigned i=queued[0];unsigned char *dst=maps[1][queued[1]],*src=maps[0][i];const char *mode=getenv("TEST_MODE");unsigned worker=0;if(!strcmp(mode,"jpeg")){assert(fmt[0]==V4L2_PIX_FMT_YUYV&&fmt[1]==V4L2_PIX_FMT_JPEG);}if(!strcmp(mode,"jpeg"))worker=(src[0]-16)/13;else if(!strcmp(mode,"h264")){for(unsigned k=5;k<40;k++){if((src[k]==16||src[k]==29)&&src[k+1]==src[k]+3&&src[k+2]==src[k]+6){worker=(src[k]-16)/13;break;}}}if(!strcmp(mode,"h264")&&control_setup_failed)return;if(!strcmp(mode,"rga")){for(unsigned y=0;y<128;y++)memcpy(dst+y*stride[1],src+y*stride[0],512);}else if(!strcmp(mode,"h264")){for(unsigned y=0;y<128;y++)for(unsigned x=0;x<128;x++)dst[y*stride[1]+x]=16+(x*3+y*5+worker*13)%220;memset(dst+stride[1]*128,128,stride[1]*64);}else{char path[128];snprintf(path,sizeof(path),"assets/mock-worker%u.jpg",worker);FILE *f=fopen(path,"rb");assert(f);size_t n=fread(dst,1,lens[1][queued[1]],f);assert(n>100);fclose(f);}if(getenv("TEST_CORRUPT"))dst[0]^=1;}
int ioctl(int fd,unsigned long cmd,...){va_list ap;va_start(ap,cmd);void *arg=va_arg(ap,void*);va_end(ap);
 if(cmd==MEDIA_IOC_DEVICE_INFO){struct media_device_info *x=arg;strcpy(x->model,"rkvdec");return 0;}
 if(cmd==MEDIA_IOC_REQUEST_ALLOC){*(int*)arg=200;return 0;}
 if(cmd==MEDIA_REQUEST_IOC_QUEUE){assert(fd==200);if(!initialized&&allocated[1])control_setup_failed=1;return 0;}
 if(cmd==VIDIOC_S_EXT_CTRLS){struct v4l2_ext_controls *c=arg;assert(c->count==4);
 if(c->which==V4L2_CTRL_WHICH_CUR_VAL){assert(!allocated[0]&&!allocated[1]&&formatted[0]);initialized=1;}
 else {assert(c->which==V4L2_CTRL_WHICH_REQUEST_VAL&&c->request_fd==200);}
 return 0;}
 if(cmd==VIDIOC_S_FMT){vfd=fd;struct v4l2_format *f=arg;unsigned q=f->type==V4L2_BUF_TYPE_VIDEO_CAPTURE_MPLANE;if(!strcmp(getenv("TEST_MODE"),"jpeg") && q && allocated[0]) {errno=EBUSY;return -1;}
 if(!strcmp(getenv("TEST_MODE"),"jpeg") && q) {fmt[0]=V4L2_PIX_FMT_NV12;stride[0]=128;}
 if(!strcmp(getenv("TEST_MODE"),"h264")&&!q){initialized=0;}
 formatted[q]=1;fmt[q]=f->fmt.pix_mp.pixelformat;stride[q]=fmt[q]==V4L2_PIX_FMT_ABGR32?512:fmt[q]==V4L2_PIX_FMT_YUYV?256:128;f->fmt.pix_mp.num_planes=1;f->fmt.pix_mp.plane_fmt[0].bytesperline=stride[q];return 0;}
 if(cmd==VIDIOC_REQBUFS){struct v4l2_requestbuffers *r=arg;allocated[r->type==V4L2_BUF_TYPE_VIDEO_CAPTURE_MPLANE]=1;r->count=4;return 0;}
 if(cmd==VIDIOC_QUERYBUF){struct v4l2_buffer *b=arg;unsigned q=b->type==V4L2_BUF_TYPE_VIDEO_CAPTURE_MPLANE;b->m.planes[0].length=65536;b->m.planes[0].m.mem_offset=q*0x100000+b->index*0x10000;return 0;}
 if(cmd==VIDIOC_QBUF){struct v4l2_buffer *b=arg;unsigned q=b->type==V4L2_BUF_TYPE_VIDEO_CAPTURE_MPLANE;queued[q]=b->index;return 0;}
 if(cmd==VIDIOC_DQBUF){struct v4l2_buffer *b=arg;unsigned q=b->type==V4L2_BUF_TYPE_VIDEO_CAPTURE_MPLANE;b->index=queued[q];b->flags=getenv("TEST_HW_ERROR")?V4L2_BUF_FLAG_ERROR:0;if(q){process();b->m.planes[0].bytesused=32768;if(!strcmp(getenv("TEST_MODE"),"jpeg")){unsigned char *data=maps[1][queued[1]];for(size_t k=2;k<lens[1][queued[1]];k++)if(data[k-1]==0xff&&data[k]==0xd9){b->m.planes[0].bytesused=k+1;break;}}}return 0;}
 if(cmd==VIDIOC_STREAMON||cmd==VIDIOC_STREAMOFF||cmd==VIDIOC_S_CTRL)return 0;
 fprintf(stderr,"mock unexpected ioctl %#lx\n",cmd);errno=ENOTTY;return -1;
}
