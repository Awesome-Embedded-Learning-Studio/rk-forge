/* RK3588 physical-core smoke tests: RGA identity, JPEG encode, H264 IDR decode.
 * All workers open one frontend before a pipe barrier; validate real buffers.
 */
#define _GNU_SOURCE
#include <errno.h>
#include <fcntl.h>
#include <glob.h>
#include <linux/media.h>
#include <linux/v4l2-controls.h>
#include <linux/videodev2.h>
#include <poll.h>
#include <signal.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/ioctl.h>
#include <sys/mman.h>
#include <sys/wait.h>
#include <time.h>
#include <unistd.h>

#define W 128
#define H 128
#define BUFS 4
struct queue {
    unsigned type, planes, stride, height, last_flags;
    struct { void *data[VIDEO_MAX_PLANES]; size_t size[VIDEO_MAX_PLANES]; } buf[BUFS];
};
static void die(const char *what) { perror(what); exit(1); }
static void require(int ok, const char *what) { if (!ok) { fprintf(stderr,"FAIL %s\n",what); exit(1); } }
static int xi(int fd,unsigned long cmd,void *arg) { int r;do {r=ioctl(fd,cmd,arg);}while(r<0&&errno==EINTR);return r; }
static void must(int fd,unsigned long cmd,void *arg,const char *what) { if(xi(fd,cmd,arg)<0)die(what); }
static void wait_fd(int fd,short events,int ms) { struct pollfd p={fd,events,0};int r;do {r=poll(&p,1,ms);}while(r<0&&errno==EINTR);require(r>0&&!(p.revents&(POLLERR|POLLNVAL)),"poll timeout/error"); }
static double now(void) { struct timespec t;clock_gettime(CLOCK_MONOTONIC,&t);return t.tv_sec+t.tv_nsec/1e9; }
static void read_exact(int fd,void *data,size_t size) { size_t n=0;while(n<size){ssize_t r=read(fd,(char*)data+n,size-n);if(r<0&&errno==EINTR)continue;require(r>0,"read fixture/barrier");n+=(size_t)r;} }
static size_t load(const char *path,void *data,size_t max) { int fd=open(path,O_RDONLY);if(fd<0)die(path);size_t n=0;while(n<max){ssize_t r=read(fd,(char*)data+n,max-n);if(r<0&&errno==EINTR)continue;if(r<0)die("read fixture");if(!r)break;n+=(size_t)r;}close(fd);return n; }
static void save(const char *path,const void *data,size_t size) { FILE *f=fopen(path,"wb");if(!f)die(path);require(fwrite(data,1,size,f)==size,"write output");if(fclose(f))die("close output"); }
static void format_queue(int fd,struct queue *q,unsigned type,unsigned fourcc,unsigned input_size) {
    struct v4l2_format f={.type=type};
    f.fmt.pix_mp.width=W;f.fmt.pix_mp.height=H;f.fmt.pix_mp.pixelformat=fourcc;f.fmt.pix_mp.field=V4L2_FIELD_NONE;
    f.fmt.pix_mp.colorspace=V4L2_COLORSPACE_REC709;
    if(input_size)f.fmt.pix_mp.plane_fmt[0].sizeimage=input_size;
    must(fd,VIDIOC_S_FMT,&f,"S_FMT");require(f.fmt.pix_mp.pixelformat==fourcc,"requested format unavailable");
    require(f.fmt.pix_mp.width==W&&f.fmt.pix_mp.height==H,"unexpected image dimensions");
    q->type=type;q->planes=f.fmt.pix_mp.num_planes;q->stride=f.fmt.pix_mp.plane_fmt[0].bytesperline;q->height=f.fmt.pix_mp.height;
    require(q->planes==1,"demo requires one memory plane");
    printf("format %.4s stride=%u sizeimage=%u\n",(char*)&fourcc,q->stride,f.fmt.pix_mp.plane_fmt[0].sizeimage);
}
static void allocate_queue(int fd,struct queue *q) {
    struct v4l2_requestbuffers rb={.count=BUFS,.type=q->type,.memory=V4L2_MEMORY_MMAP};must(fd,VIDIOC_REQBUFS,&rb,"REQBUFS");require(rb.count>=BUFS,"too few buffers");
    for(unsigned i=0;i<BUFS;i++) {
        struct v4l2_plane p[VIDEO_MAX_PLANES]={0};struct v4l2_buffer b={.index=i,.type=q->type,.memory=V4L2_MEMORY_MMAP,.length=q->planes,.m.planes=p};
        must(fd,VIDIOC_QUERYBUF,&b,"QUERYBUF");
        for(unsigned j=0;j<q->planes;j++){q->buf[i].size[j]=p[j].length;q->buf[i].data[j]=mmap(NULL,p[j].length,PROT_READ|PROT_WRITE,MAP_SHARED,fd,p[j].m.mem_offset);if(q->buf[i].data[j]==MAP_FAILED)die("mmap");}
    }
    printf("buffers type=%u count=%u plane_size=%zu\n",q->type,rb.count,q->buf[0].size[0]);
}
static void queue_buf(int fd,struct queue *q,unsigned index,size_t bytes,int request,unsigned frame) {
    struct v4l2_plane p[VIDEO_MAX_PLANES]={0};p[0].bytesused=bytes;p[0].length=q->buf[index].size[0];
    struct v4l2_buffer b={.index=index,.type=q->type,.memory=V4L2_MEMORY_MMAP,.length=q->planes,.m.planes=p,.field=V4L2_FIELD_NONE};
    b.timestamp.tv_sec=frame+1;
    if(request>=0){b.flags=V4L2_BUF_FLAG_REQUEST_FD|V4L2_BUF_FLAG_KEYFRAME;b.request_fd=request;}
    must(fd,VIDIOC_QBUF,&b,"QBUF");
}
static size_t dequeue(int fd,struct queue *q,unsigned *index) {
    struct v4l2_plane p[VIDEO_MAX_PLANES]={0};struct v4l2_buffer b={.type=q->type,.memory=V4L2_MEMORY_MMAP,.length=q->planes,.m.planes=p};
    double end=now()+5;
    while(xi(fd,VIDIOC_DQBUF,&b)<0){if(errno!=EAGAIN)die("DQBUF");require(now()<end,"DQBUF timeout");wait_fd(fd,q->type==V4L2_BUF_TYPE_VIDEO_CAPTURE_MPLANE?POLLIN:POLLOUT,1000);}
    q->last_flags=b.flags;require(b.index<BUFS,"unexpected buffer index");*index=b.index;return p[0].bytesused;
}
static int media_fd(void) {
    glob_t g={0};require(!glob("/dev/media*",0,NULL,&g),"no media device");int found=-1;
    for(size_t i=0;i<g.gl_pathc;i++){int fd=open(g.gl_pathv[i],O_RDWR);if(fd<0)continue;struct media_device_info info={0};if(!xi(fd,MEDIA_IOC_DEVICE_INFO,&info)&&!strcmp(info.model,"rkvdec")){found=fd;break;}close(fd);}
    globfree(&g);require(found>=0,"rkvdec media request device not found");return found;
}
static void h264_controls(int fd,int request) {
    struct v4l2_ctrl_h264_sps s={.profile_idc=66,.level_idc=30,.chroma_format_idc=1,.pic_order_cnt_type=2,.max_num_ref_frames=1,.pic_width_in_mbs_minus1=W/16-1,.pic_height_in_map_units_minus1=H/16-1,.flags=V4L2_H264_SPS_FLAG_FRAME_MBS_ONLY|V4L2_H264_SPS_FLAG_DIRECT_8X8_INFERENCE};
    struct v4l2_ctrl_h264_pps p={.flags=V4L2_H264_PPS_FLAG_DEBLOCKING_FILTER_CONTROL_PRESENT};
    struct v4l2_ctrl_h264_decode_params d={.nal_ref_idc=3,.dec_ref_pic_marking_bit_size=2,.flags=V4L2_H264_DECODE_PARAM_FLAG_IDR_PIC};
    struct v4l2_ctrl_h264_scaling_matrix scaling;memset(&scaling,16,sizeof(scaling));
    struct v4l2_ext_control a[]={
        {.id=V4L2_CID_STATELESS_H264_SPS,.size=sizeof(s),.ptr=&s},
        {.id=V4L2_CID_STATELESS_H264_PPS,.size=sizeof(p),.ptr=&p},
        {.id=V4L2_CID_STATELESS_H264_DECODE_PARAMS,.size=sizeof(d),.ptr=&d},
        {.id=V4L2_CID_STATELESS_H264_SCALING_MATRIX,.size=sizeof(scaling),.ptr=&scaling},
    };
    struct v4l2_ext_controls c={.which=request<0?V4L2_CTRL_WHICH_CUR_VAL:V4L2_CTRL_WHICH_REQUEST_VAL,.count=4,.request_fd=request<0?0:request,.controls=a};
    must(fd,VIDIOC_S_EXT_CTRLS,&c,request<0?"H264 initial controls":"H264 request controls");
}
static unsigned char y_value(unsigned x,unsigned y,unsigned worker_id) { return 16+(x*3+y*5+worker_id*13)%220; }
static void save_decode_evidence(const char *outdir,unsigned worker_id,unsigned frame,
                                 const struct queue *src,const struct queue *dst,
                                 unsigned si,unsigned di,size_t used,size_t bytes) {
    char path[1024];
    int n=snprintf(path,sizeof(path),"%s/h264-worker%u-frame%u.input.slice",outdir,worker_id,frame);
    require(n>0&&(size_t)n<sizeof(path),"diagnostic path");save(path,src->buf[si].data[0],used);
    n=snprintf(path,sizeof(path),"%s/h264-worker%u-frame%u.capture.bin",outdir,worker_id,frame);
    require(n>0&&(size_t)n<sizeof(path),"diagnostic path");save(path,dst->buf[di].data[0],dst->buf[di].size[0]);
    n=snprintf(path,sizeof(path),"%s/h264-worker%u-frame%u.json",outdir,worker_id,frame);
    require(n>0&&(size_t)n<sizeof(path),"diagnostic path");FILE *f=fopen(path,"w");if(!f)die(path);
    require(fprintf(f,"{\"width\":%u,\"height\":%u,\"stride\":%u,\"capture_height\":%u,\"allocation\":%zu,\"bytesused\":%zu,\"capture_flags\":%u,\"output_flags\":%u,\"worker\":%u,\"frame\":%u}\n",W,H,dst->stride,dst->height,dst->buf[di].size[0],bytes,dst->last_flags,src->last_flags,worker_id,frame)>0,"write diagnostic metadata");
    if(fclose(f))die("close diagnostic metadata");
}
static int decoded_pixels_match(const unsigned char *output,unsigned stride,unsigned worker_id) {
    unsigned mismatches=0;
    for(unsigned y=0;y<H+H/2;y++)for(unsigned x=0;x<W;x++) {
        unsigned expected=y<H?y_value(x,y,worker_id):128;
        if(output[y*stride+x]==expected)continue;
        if(!mismatches)fprintf(stderr,"FAIL decoded %s mismatch: x=%u y=%u offset=%u actual=%u expected=%u\n",y<H?"luma":"chroma",x,y<H?y:y-H,y*stride+x,output[y*stride+x],expected);
        mismatches++;
    }
    if(mismatches)fprintf(stderr,"decoded mismatches=%u/%u (strict byte comparison)\n",mismatches,W*H*3/2);
    return mismatches==0;
}
static void worker(const char *mode,const char *device,unsigned worker_id,unsigned frames,const char *outdir,int ready,int go) {
    alarm(60);int fd=open(device,O_RDWR|O_NONBLOCK);if(fd<0)die(device);
    struct queue src={0},dst={0};int dec=!strcmp(mode,"h264"),jpeg=!strcmp(mode,"jpeg");
    unsigned srcfmt=dec?V4L2_PIX_FMT_H264_SLICE:jpeg?V4L2_PIX_FMT_YUYV:V4L2_PIX_FMT_ABGR32;
    unsigned dstfmt=dec?V4L2_PIX_FMT_NV12:jpeg?V4L2_PIX_FMT_JPEG:V4L2_PIX_FMT_ABGR32;
    // Encoders reset OUTPUT when CAPTURE changes. Negotiate both formats before
    // allocating either queue; for JPEG set the coded CAPTURE format first.
    if(jpeg) {
        format_queue(fd,&dst,V4L2_BUF_TYPE_VIDEO_CAPTURE_MPLANE,dstfmt,W*H*4);
        format_queue(fd,&src,V4L2_BUF_TYPE_VIDEO_OUTPUT_MPLANE,srcfmt,0);
    } else {
        format_queue(fd,&src,V4L2_BUF_TYPE_VIDEO_OUTPUT_MPLANE,srcfmt,dec?65536:0);
        // Stateless decoder initialization: headers establish the image format
        // before CAPTURE negotiation and REQBUFS. Request-only SPS is too late:
        // rkvdec_s_ctrl() rejects an image-format change once CAPTURE is busy.
        if(dec)h264_controls(fd,-1);
        format_queue(fd,&dst,V4L2_BUF_TYPE_VIDEO_CAPTURE_MPLANE,dstfmt,0);
    }
    allocate_queue(fd,&src);allocate_queue(fd,&dst);
    int mfd=dec?media_fd():-1;
    if(jpeg){struct v4l2_control c={.id=V4L2_CID_JPEG_COMPRESSION_QUALITY,.value=90};must(fd,VIDIOC_S_CTRL,&c,"JPEG quality");}
    require(write(ready,"R",1)==1,"ready barrier");close(ready);char token;read_exact(go,&token,1);close(go);
    double start=now();
    for(unsigned frame=0;frame<frames;frame++) {
        unsigned i=frame%BUFS;unsigned char *input=src.buf[i].data[0],*output=dst.buf[i].data[0];
        memset(input,0,src.buf[i].size[0]);memset(output,0xa5,dst.buf[i].size[0]);
        size_t used=src.buf[i].size[0];
        if(dec){char fixture[128];snprintf(fixture,sizeof(fixture),"assets/idr128-worker%u.slice",worker_id);used=load(fixture,input,used);require(used==24712,"unexpected H264 fixture size");}
        else if(jpeg){require(src.stride>=W*2,"YUYV stride");for(unsigned y=0;y<H;y++)for(unsigned x=0;x<W;x++){input[y*src.stride+x*2]=y_value(x,y,worker_id);input[y*src.stride+x*2+1]=128;}}
        else {require(src.stride>=W*4,"RGB stride");for(unsigned y=0;y<H;y++)for(unsigned x=0;x<W;x++){unsigned char *p=input+y*src.stride+x*4;p[0]=(x+worker_id*17+frame)%256;p[1]=(y*3+frame)%256;p[2]=(x+y+worker_id)%256;p[3]=255;}}
        int request=-1;if(dec){must(mfd,MEDIA_IOC_REQUEST_ALLOC,&request,"REQUEST_ALLOC");h264_controls(fd,request);}
        queue_buf(fd,&dst,i,0,-1,frame);queue_buf(fd,&src,i,used,request,frame);
        if(!frame){unsigned type=dst.type;must(fd,VIDIOC_STREAMON,&type,"STREAMON capture");type=src.type;must(fd,VIDIOC_STREAMON,&type,"STREAMON output");}
        if(dec)must(request,MEDIA_REQUEST_IOC_QUEUE,NULL,"REQUEST_QUEUE");
        unsigned capture_index,output_index;size_t bytes=dequeue(fd,&dst,&capture_index);dequeue(fd,&src,&output_index);
        require(capture_index==i&&output_index==i,"queue returned unexpected index");
        if(dec)save_decode_evidence(outdir,worker_id,frame,&src,&dst,output_index,capture_index,used,bytes);
        require(!((src.last_flags|dst.last_flags)&V4L2_BUF_FLAG_ERROR),"hardware returned buffer error");
        if(dec){require(dst.stride>=W && dst.buf[i].size[0]>=dst.stride*H*3/2,"NV12 layout");require(decoded_pixels_match(output,dst.stride,worker_id),"decoded pixels (raw evidence retained)");wait_fd(request,POLLPRI,1000);close(request);}
        else if(jpeg){require(bytes>100&&bytes<=dst.buf[i].size[0],"invalid JPEG size");require(output[0]==0xff&&output[1]==0xd8,"JPEG SOI missing");require(output[bytes-2]==0xff&&output[bytes-1]==0xd9,"JPEG EOI missing");}
        else {require(dst.stride>=W*4,"RGB capture stride");for(unsigned y=0;y<H;y++)require(!memcmp(input+y*src.stride,output+y*dst.stride,W*4),"RGA pixel mismatch");}
        if(frame==frames-1){char path[1024];int n=snprintf(path,sizeof(path),"%s/%s-worker%u.%s",outdir,mode,worker_id,jpeg?"jpg":dec?"nv12":"rgba");require(n>0&&(size_t)n<sizeof(path),"output path");save(path,output,jpeg?bytes:dec?dst.stride*H*3/2:dst.stride*H);}
    }
    unsigned type=src.type;must(fd,VIDIOC_STREAMOFF,&type,"STREAMOFF output");type=dst.type;must(fd,VIDIOC_STREAMOFF,&type,"STREAMOFF capture");
    for(unsigned i=0;i<BUFS;i++){munmap(src.buf[i].data[0],src.buf[i].size[0]);munmap(dst.buf[i].data[0],dst.buf[i].size[0]);}
    if(mfd>=0) { close(mfd); }
    close(fd);printf("PASS %s worker=%u frames=%u elapsed=%.3f\n",mode,worker_id,frames,now()-start);fflush(stdout);exit(0);
}
int main(int argc,char **argv) {
    if(argc!=6){fprintf(stderr,"usage: %s rga|jpeg|h264 /dev/videoN workers frames outdir\n",argv[0]);return 2;}
    require(!strcmp(argv[1],"rga")||!strcmp(argv[1],"jpeg")||!strcmp(argv[1],"h264"),"mode");
    unsigned n=(unsigned)strtoul(argv[3],NULL,10),frames=(unsigned)strtoul(argv[4],NULL,10);require(n>0&&n<=8&&frames>0&&frames<=1000,"workers/frames limits");
    require(n<=(!strcmp(argv[1],"jpeg")?4u:2u),"physical core count");
    setvbuf(stdout,NULL,_IOLBF,0);printf("media_demo revision=20261104-init2\n");int ready[2],go[2];if(pipe(ready)||pipe(go))die("pipe");pid_t children[8];
    for(unsigned i=0;i<n;i++){pid_t p=fork();if(p<0)die("fork");if(!p){close(ready[0]);close(go[1]);worker(argv[1],argv[2],i,frames,argv[5],ready[1],go[0]);}children[i]=p;}
    close(ready[1]);close(go[0]);
    for(unsigned i=0;i<n;i++){wait_fd(ready[0],POLLIN,15000);char token;read_exact(ready[0],&token,1);}close(ready[0]);
    for(unsigned i=0;i<n;i++) { require(write(go[1],"G",1)==1,"start barrier"); }
    close(go[1]);
    int failed=0;for(unsigned i=0;i<n;i++){int status;while(waitpid(children[i],&status,0)<0){if(errno!=EINTR)die("waitpid");}if(!WIFEXITED(status)||WEXITSTATUS(status))failed=1;}
    printf("%s %s workers=%u frames/worker=%u\n",failed?"FAIL":"PASS",argv[1],n,frames);return failed;
}
