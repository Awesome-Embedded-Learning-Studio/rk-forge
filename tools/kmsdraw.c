// kmsdraw — zero-dependency KMS pipe test: CPU dumb-buffer test pattern.
// Usage: kmsdraw [card]   (default /dev/dri/card0)
// Needs DRM master: run with the display manager STOPPED.
// Draws 4 quadrants + a flashing frame stripe for 12 s, prints the pipe it drove.
#define _GNU_SOURCE
#include <fcntl.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <errno.h>
#include <unistd.h>
#include <sys/mman.h>
#include <xf86drm.h>
#include <xf86drmMode.h>

int main(int argc, char **argv)
{
	const char *card = argc > 1 ? argv[1] : "/dev/dri/card0";
	drmModeRes *res;
	drmModeConnector *conn = NULL;
	drmModeCrtc *crtc_info = NULL;
	uint32_t crtc_id = 0, conn_id = 0, fb = 0, handle = 0, pitch = 0;
	drmModeModeInfo *mode = NULL;
	uint32_t *map = MAP_FAILED;
	uint64_t size = 0;
	int fd, i, j, c;

	fd = open(card, O_RDWR | O_CLOEXEC);
	if (fd < 0) { perror("open card"); return 2; }
	if (drmSetMaster(fd))
		fprintf(stderr, "WARN drmSetMaster: %s (compositor running? stop gdm first)\n",
			strerror(errno));

	res = drmModeGetResources(fd);
	if (!res) { fprintf(stderr, "drmModeGetResources: %s\n", strerror(errno)); return 2; }

	for (i = 0; i < res->count_connectors; i++) {
		conn = drmModeGetConnector(fd, res->connectors[i]);
		if (conn && conn->connection == DRM_MODE_CONNECTED && conn->count_modes > 0)
			break;
		drmModeFreeConnector(conn);
		conn = NULL;
	}
	if (!conn) { fprintf(stderr, "no connected connector with modes\n"); return 2; }
	conn_id = conn->connector_id;
	mode = &conn->modes[0];
	for (i = 0; i < conn->count_modes; i++)
		if (conn->modes[i].type & DRM_MODE_TYPE_PREFERRED)
			mode = &conn->modes[i];

	for (i = 0; i < res->count_crtcs; i++) {
		crtc_info = drmModeGetCrtc(fd, res->crtcs[i]);
		if (crtc_info && crtc_info->buffer_id)
			break; /* CRTC currently in use — the live one */
		drmModeFreeCrtc(crtc_info);
		crtc_info = NULL;
	}
	if (crtc_info)
		crtc_id = crtc_info->crtc_id;
	else if (conn->encoder_id) {
		drmModeEncoder *enc = drmModeGetEncoder(fd, conn->encoder_id);
		if (enc) { crtc_id = enc->crtc_id; drmModeFreeEncoder(enc); }
	}
	if (!crtc_id && res->count_crtcs)
		crtc_id = res->crtcs[0];
	if (!crtc_id) { fprintf(stderr, "no crtc\n"); return 2; }

	printf("card=%s connector=%u crtc=%u mode=%ux%u@%u flags=%x\n",
	       card, conn_id, crtc_id, mode->hdisplay, mode->vdisplay,
	       mode->clock, mode->flags);

	struct drm_mode_create_dumb creq = {
		.width = mode->hdisplay, .height = mode->vdisplay, .bpp = 32,
	};
	if (drmIoctl(fd, DRM_IOCTL_MODE_CREATE_DUMB, &creq)) {
		perror("CREATE_DUMB"); return 2;
	}
	handle = creq.handle; pitch = creq.pitch; size = creq.size;

	if (drmModeAddFB(fd, creq.width, creq.height, 24, 32, pitch, handle, &fb)) {
		perror("AddFB"); return 2;
	}

	struct drm_mode_map_dumb mreq = { .handle = handle };
	if (drmIoctl(fd, DRM_IOCTL_MODE_MAP_DUMB, &mreq)) {
		perror("MAP_DUMB"); return 2;
	}
	map = mmap(NULL, size, PROT_READ | PROT_WRITE, MAP_SHARED, fd, mreq.offset);
	if (map == MAP_FAILED) { perror("mmap"); return 2; }

	for (c = 0; c < 12; c++) {
		/* flashing stripe: alternate black/white full rows */
		uint32_t stripe = (c & 1) ? 0xFFFFFFFF : 0xFF000000;
		for (j = 0; j < (int)creq.height; j++) {
			for (i = 0; i < (int)creq.width; i++) {
				uint32_t v;
				if (j < 10 || j >= (int)creq.height - 10) v = stripe;
				else if (i < (int)creq.width / 2 && j < (int)creq.height / 2) v = 0xFF0000FF; /* red */
				else if (i >= (int)creq.width / 2 && j < (int)creq.height / 2) v = 0xFF00FF00; /* green */
				else if (i < (int)creq.width / 2) v = 0xFFFF0000; /* blue */
				else v = 0xFFFFFFFF; /* white */
				map[j * (pitch / 4) + i] = v;
			}
		}
		if (drmModeSetCrtc(fd, crtc_id, fb, 0, 0, &conn_id, 1, mode)) {
			fprintf(stderr, "SetCrtc: %s\n", strerror(errno));
			break;
		}
		printf("frame %d shown\n", c);
		sleep(1);
	}

	munmap(map, size);
	drmModeRmFB(fd, fb);
	struct drm_mode_destroy_dumb dreq = { .handle = handle };
	drmIoctl(fd, DRM_IOCTL_MODE_DESTROY_DUMB, &dreq);
	drmDropMaster(fd);
	close(fd);
	printf("done — did the panel show quadrants + flashing top/bottom stripes?\n");
	return 0;
}
