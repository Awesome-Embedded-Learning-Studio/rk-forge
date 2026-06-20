// SPDX-License-Identifier: GPL-2.0
/*
 * mtdbb — SPI-NAND bad-block forensics + management for the write-path saga.
 *
 * Subcommands (all operate on a raw MTD char device, e.g. /dev/mtd5):
 *
 *   mtdbb scan  <dev>                 ECC-read every erase block; list blocks
 *                                    with uncorrectable ECC errors (the
 *                                    "hidden bad blocks" UBI never marks because
 *                                    programs report success).
 *   mtdbb isbad <dev> <offset>        MEMGETBADBLOCK: is this block marked bad?
 *   mtdbb mark   <dev> <offset>       MEMSETBADBLOCK: mark a block bad (sets the
 *                                    bad-block marker in OOB so UBI's next
 *                                    attach excludes it).
 *   mtdbb erase  <dev> <offset>       MEMERASE64 one erase block.
 *   mtdbb test   <dev> <offset>       erase + write a known pattern (on-die ECC
 *                                    on) + read back + compare + ecc_stats.
 *                                    readback clean → block writes reliably
 *                                    (was soft-bad / fine); readback wrong or
 *                                    uncorrectable → hard bad (mark it).
 *
 * offset is a byte offset within the MTD; one erase block is expected for
 * erase/test/mark (size from MEMGETINFO).
 *
 * Structs/ioctls copied verbatim from include/uapi/mtd/mtd-abi.h (Linux 7.x).
 *
 * Build (static, armhf):
 *   arm-none-linux-gnueabihf-gcc -O2 -static -s -o mtdbb mtdbb.c
 */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <stdint.h>
#include <fcntl.h>
#include <unistd.h>
#include <errno.h>
#include <sys/ioctl.h>

/* __kernel_loff_t isn't always exposed to userspace; it's a 64-bit signed. */
typedef long long __kernel_loff_t;

/* ---- copied from include/uapi/mtd/mtd-abi.h ---- */
struct mtd_info_user {
	uint8_t  type;
	uint32_t flags;
	uint32_t size;
	uint32_t erasesize;
	uint32_t writesize;
	uint32_t oobsize;
	uint64_t padding;
};

struct erase_info_user64 {
	uint64_t start;
	uint64_t length;
};

struct mtd_read_req_ecc_stats {
	uint32_t uncorrectable_errors;
	uint32_t corrected_bitflips;
	uint32_t max_bitflips;
};

struct mtd_read_req {
	uint64_t start;
	uint64_t len;
	uint64_t ooblen;
	uint64_t usr_data;
	uint64_t usr_oob;
	uint8_t  mode;
	uint8_t  padding[7];
	struct mtd_read_req_ecc_stats ecc_stats;
};

struct mtd_write_req {
	uint64_t start;
	uint64_t len;
	uint64_t ooblen;
	uint64_t usr_data;
	uint64_t usr_oob;
	uint8_t  mode;
	uint8_t  padding[7];
};

#define MEMGETINFO    _IOR('M', 1, struct mtd_info_user)
#define MEMERASE64    _IOW('M', 20, struct erase_info_user64)
#define MEMGETBADBLOCK _IOW('M', 11, __kernel_loff_t)
#define MEMSETBADBLOCK _IOW('M', 12, __kernel_loff_t)
#define MEMREAD       _IOWR('M', 26, struct mtd_read_req)
#define MEMWRITE      _IOWR('M', 24, struct mtd_write_req)

#define MTD_OPS_PLACE_OOB 0   /* ECC on */
#define MTD_OPS_RAW       2   /* ECC off */

static int get_info(int fd, struct mtd_info_user *m)
{
	if (ioctl(fd, MEMGETINFO, m) < 0) { perror("MEMGETINFO"); return -1; }
	return 0;
}

/* MEMREAD one region; returns 0 ok, fills ecc_stats. buf is caller-owned. */
static int memread(int fd, uint64_t off, uint32_t len, uint8_t mode, uint8_t *buf,
		   struct mtd_read_req_ecc_stats *ecc)
{
	struct mtd_read_req r;
	memset(&r, 0, sizeof(r));
	r.start = off; r.len = len; r.mode = mode;
	r.usr_data = (uint64_t)(uintptr_t)buf;
	r.usr_oob = 0; r.ooblen = 0;
	int ret = ioctl(fd, MEMREAD, &r);
	if (ecc) *ecc = r.ecc_stats;
	return ret;
}

static uint64_t peb_to_off(int peb, uint32_t erasesize) { return (uint64_t)peb * erasesize; }

/* ---- scan ---- */
static int cmd_scan(int fd, struct mtd_info_user *m)
{
	uint8_t *buf = malloc(m->erasesize);
	int npeb = m->size / m->erasesize, bad = 0;
	if (!buf) { fprintf(stderr, "oom\n"); return 1; }
	fprintf(stderr, "mtdbb scan: %d PEBs (erasesize=%u)…\n", npeb, m->erasesize);
	for (int peb = 0; peb < npeb; peb++) {
		struct mtd_read_req_ecc_stats e;
		int ret = memread(fd, peb_to_off(peb, m->erasesize), m->erasesize,
				  MTD_OPS_PLACE_OOB, buf, &e);
		if (ret < 0 || e.uncorrectable_errors > 0) {
			printf("BAD peb=%d off=0x%llx uncorr=%u corrected=%u maxflip=%u ret=%d(%s)\n",
			       peb, (unsigned long long)peb_to_off(peb, m->erasesize),
			       e.uncorrectable_errors, e.corrected_bitflips, e.max_bitflips,
			       ret, ret < 0 ? strerror(errno) : "ok");
			bad++;
		}
	}
	fprintf(stderr, "mtdbb scan done: %d bad / %d PEBs\n", bad, npeb);
	free(buf);
	return 0;
}

/* ---- isbad / mark ---- */
static int cmd_isbad(int fd, uint64_t off)
{
	/* MEMGETBADBLOCK returns 1 if the block is bad, 0 if not. */
	loff_t o = (loff_t)off;
	int r = ioctl(fd, MEMGETBADBLOCK, &o);
	printf("off=0x%llx marked_bad=%d (ret=%d, %s)\n",
	       (unsigned long long)off, r > 0 ? 1 : 0, r,
	       r < 0 ? strerror(errno) : (r ? "BAD" : "good"));
	return 0;
}

static int cmd_mark(int fd, uint64_t off)
{
	loff_t o = (loff_t)off;
	if (ioctl(fd, MEMSETBADBLOCK, &o) < 0) {
		fprintf(stderr, "MEMSETBADBLOCK failed: %s\n", strerror(errno));
		return 1;
	}
	printf("marked bad: off=0x%llx\n", (unsigned long long)off);
	return 0;
}

/* ---- erase ---- */
static int cmd_erase(int fd, uint64_t off, uint32_t erasesize)
{
	struct erase_info_user64 e = { .start = off, .length = erasesize };
	if (ioctl(fd, MEMERASE64, &e) < 0) {
		fprintf(stderr, "MEMERASE64 failed: %s\n", strerror(errno));
		return 1;
	}
	printf("erased: off=0x%llx len=%u\n", (unsigned long long)off, erasesize);
	return 0;
}

/* ---- test: erase + write pattern + readback + compare ---- */
static int cmd_test(int fd, uint64_t off, uint32_t erasesize)
{
	uint8_t *wbuf = malloc(erasesize), *rbuf = malloc(erasesize);
	struct mtd_write_req w;
	struct mtd_read_req_ecc_stats e;
	int i, ret, mism = 0, firstbad = -1;
	if (!wbuf || !rbuf) { fprintf(stderr, "oom\n"); return 1; }

	/* deterministic pattern exercising all byte values */
	for (i = 0; i < (int)erasesize; i++) wbuf[i] = (uint8_t)((i * 131 + 17) & 0xff);

	/* 1. erase */
	struct erase_info_user64 er = { .start = off, .length = erasesize };
	if (ioctl(fd, MEMERASE64, &er) < 0) {
		fprintf(stderr, "erase failed: %s\n", strerror(errno));
		return 1;
	}

	/* 2. write full block, on-die ECC on (data-only; chip generates ECC) */
	memset(&w, 0, sizeof(w));
	w.start = off; w.len = erasesize; w.mode = MTD_OPS_PLACE_OOB;
	w.usr_data = (uint64_t)(uintptr_t)wbuf; w.usr_oob = 0; w.ooblen = 0;
	ret = ioctl(fd, MEMWRITE, &w);
	if (ret < 0) {
		fprintf(stderr, "MEMWRITE failed: %s (offset may be under UBI — detach first)\n",
			strerror(errno));
		return 1;
	}

	/* 3. read back with ECC */
	ret = memread(fd, off, erasesize, MTD_OPS_PLACE_OOB, rbuf, &e);
	/* even if ret<0 (-EBADMSG on uncorrectable), buf may hold partial data */

	/* 4. compare */
	for (i = 0; i < (int)erasesize; i++) {
		if (rbuf[i] != wbuf[i]) {
			mism++;
			if (firstbad < 0) firstbad = i;
		}
	}

	printf("TEST off=0x%llx len=%u: readback %s, mismatches=%d firstbad=0x%x "
	       "ecc{uncorr=%u corrected=%u maxflip=%u} read_ret=%d(%s)\n",
	       (unsigned long long)off, erasesize,
	       mism == 0 && e.uncorrectable_errors == 0 ? "CLEAN" : "BAD",
	       mism, firstbad,
	       e.uncorrectable_errors, e.corrected_bitflips, e.max_bitflips,
	       ret, ret < 0 ? strerror(errno) : "ok");
	printf("  → %s\n",
	       (mism == 0 && e.uncorrectable_errors == 0)
		   ? "block writes reliably (soft-bad recovered or was fine; no need to mark)"
		   : "HARD BAD — write does not stick reliably; mark this block bad");
	free(wbuf); free(rbuf);
	return 0;
}

int main(int argc, char **argv)
{
	if (argc < 3) {
		fprintf(stderr,
			"usage:\n"
			"  mtdbb scan  <dev>\n"
			"  mtdbb isbad <dev> <offset>\n"
			"  mtdbb mark  <dev> <offset>\n"
			"  mtdbb erase <dev> <offset>\n"
			"  mtdbb test  <dev> <offset>\n");
		return 2;
	}
	const char *cmd = argv[1], *dev = argv[2];
	int fd = open(dev, O_RDWR);
	if (fd < 0) { perror("open"); return 1; }

	struct mtd_info_user m;
	if (get_info(fd, &m) < 0) return 1;
	fprintf(stderr, "mtdbb: %s type=%u size=%u erasesize=%u writesize=%u oobsize=%u\n",
		dev, m.type, m.size, m.erasesize, m.writesize, m.oobsize);

	if (!strcmp(cmd, "scan"))       return cmd_scan(fd, &m);
	if (argc < 4) { fprintf(stderr, "need <offset> for %s\n", cmd); return 2; }
	uint64_t off = strtoull(argv[3], NULL, 0);

	if (!strcmp(cmd, "isbad"))      return cmd_isbad(fd, off);
	if (!strcmp(cmd, "mark"))       return cmd_mark(fd, off);
	if (!strcmp(cmd, "erase"))      return cmd_erase(fd, off, m.erasesize);
	if (!strcmp(cmd, "test"))       return cmd_test(fd, off, m.erasesize);

	fprintf(stderr, "unknown cmd: %s\n", cmd);
	return 2;
}
