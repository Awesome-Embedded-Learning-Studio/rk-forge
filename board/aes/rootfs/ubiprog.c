// SPDX-License-Identifier: GPL-2.0
/*
 * ubiprog — re-flash an MTD partition from Linux with a reliable write path.
 *
 * Problem this solves: on the RK3506B "aes" board the rkbin loader programs
 * some erase blocks of our SPI-NAND rootfs weakly (PEBs 3/4/30/32 ...). The
 * data reads back fine on the FIRST boot (on-die ECC still corrects the weak
 * bits) but degrades to ECC-uncorrectable after a power cycle, so the 2nd
 * boot can't mount UBIFS. Our mainline SFC driver (DLL tuning + powergood +
 * WPEN) writes reliably, but the loader is a black box we can't fix.
 *
 * ubiprog runs from an initramfs on the FIRST boot (while the loader-written
 * data is still fresh/readable): it reads every non-erased (non-0xFF) erase
 * block into RAM, then erases + re-programs each one through the kernel's own
 * write path (on-die ECC on). The bytes are identical, but now every block is
 * Linux-written and survives reboots. Subsequent boots mount this reliable
 * copy and RW works.
 *
 * Only data blocks are rewritten — fully-erased (all-0xFF) blocks are left
 * alone (they hold no data; UBI/UBIFS will write them later via the same
 * reliable path). This keeps RAM use and time proportional to the image size,
 * not the whole partition.
 *
 * Usage:  ubiprog <mtd-dev>          e.g. ubiprog /dev/mtd5
 *
 * Build (static, armhf):
 *   arm-none-linux-gnueabihf-gcc -O2 -static -s -o ubiprog ubiprog.c
 *
 * Structs/ioctls copied from include/uapi/mtd/mtd-abi.h (Linux 7.x), same as
 * mtdbb.c.
 */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <stdint.h>
#include <fcntl.h>
#include <unistd.h>
#include <errno.h>
#include <sys/ioctl.h>

typedef long long __kernel_loff_t;

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

#define MEMGETINFO  _IOR('M', 1, struct mtd_info_user)
#define MEMERASE64  _IOW('M', 20, struct erase_info_user64)
#define MEMREAD     _IOWR('M', 26, struct mtd_read_req)
#define MEMWRITE    _IOWR('M', 24, struct mtd_write_req)

#define MTD_OPS_PLACE_OOB 0   /* ECC on (data-only; chip generates ECC) */

#ifndef EUCLEAN
#define EUCLEAN 117   /* "Structure needs cleaning": correctable bit flips, data is valid */
#endif

/* Read one erase block with on-die ECC into buf. Returns 0 ok, <0 error.
 * Fills ecc_stats. On -EBADMSG (uncorrectable) buf holds best-effort data. */
static int memread_peb(int fd, uint64_t off, uint32_t len, uint8_t *buf,
		       struct mtd_read_req_ecc_stats *ecc)
{
	struct mtd_read_req r;
	memset(&r, 0, sizeof(r));
	r.start = off;
	r.len = len;
	r.mode = MTD_OPS_PLACE_OOB;
	r.usr_data = (uint64_t)(uintptr_t)buf;
	r.ooblen = 0;
	r.usr_oob = 0;
	int ret = ioctl(fd, MEMREAD, &r);
	if (ecc) *ecc = r.ecc_stats;
	return ret;
}

static int memwrite_peb(int fd, uint64_t off, uint32_t len, const uint8_t *buf)
{
	struct mtd_write_req w;
	memset(&w, 0, sizeof(w));
	w.start = off;
	w.len = len;
	w.mode = MTD_OPS_PLACE_OOB;
	w.usr_data = (uint64_t)(uintptr_t)buf;
	w.ooblen = 0;
	w.usr_oob = 0;
	return ioctl(fd, MEMWRITE, &w);
}

static int memerase_peb(int fd, uint64_t off, uint32_t len)
{
	struct erase_info_user64 e = { .start = off, .length = len };
	return ioctl(fd, MEMERASE64, &e);
}

static int block_is_erased(const uint8_t *buf, uint32_t len)
{
	/* An erased NAND block reads as all 0xFF. */
	for (uint32_t i = 0; i < len; i += 4096)
		if (buf[i] != 0xFF)
			return 0;
	/* confirm a sample across the whole block */
	for (uint32_t i = 0; i < len; i += (len > 8192 ? len / 8 : 1))
		if (buf[i] != 0xFF)
			return 0;
	return 1;
}

int main(int argc, char **argv)
{
	if (argc < 2) {
		fprintf(stderr, "usage: ubiprog <mtd-dev>   (e.g. /dev/mtd5)\n");
		return 2;
	}
	const char *dev = argv[1];
	int fd = open(dev, O_RDWR);
	if (fd < 0) { perror("open"); return 1; }

	struct mtd_info_user m;
	if (ioctl(fd, MEMGETINFO, &m) < 0) { perror("MEMGETINFO"); return 1; }

	int npeb = m.size / m.erasesize;
	fprintf(stderr, "ubiprog: %s  size=%u  erasesize=%u  PEBs=%d  writesize=%u\n",
		dev, m.size, m.erasesize, npeb, m.writesize);

	uint32_t es = m.erasesize;
	uint8_t *buf = malloc((size_t)es);
	if (!buf) { fprintf(stderr, "oom (peb buffer)\n"); return 1; }

	/* Read→erase→write ONE block at a time (per-block read-modify-write never
	 * touches any other block, so it's safe and uses only one PEB of RAM). */
	int rewrote = 0, recovered = 0, skipped_erased = 0, failed = 0;

	for (int peb = 0; peb < npeb; peb++) {
		uint64_t off = (uint64_t)peb * es;
		struct mtd_read_req_ecc_stats ecc;
		int r = memread_peb(fd, off, es, buf, &ecc);
		if (r < 0 && errno != EUCLEAN && ecc.uncorrectable_errors == 0) {
			/* read error that isn't ECC — bail, something's wrong.
			 * (-EUCLEAN is NOT an error: it means on-die ECC corrected ≤N bit
			 * flips — the data in buf is valid, just had wear. The rkbin loader's
			 * weak rootfs write is jittery, so a PEB can read back with correctable
			 * flips on one flash and uncorrectable on another; treat correctable as
			 * good data and let the kernel rewrite it, instead of aborting.) */
			fprintf(stderr, "  peb=%d read error: %s\n", peb, strerror(errno));
			failed++;
			continue;
		}
		if (block_is_erased(buf, es)) {
			skipped_erased++;
			continue;
		}
		if (ecc.uncorrectable_errors > 0) {
			/* Full-PEB read is ECC-uncorrectable (loader wrote it weakly).
			 * Page-level recovery: read the block page-by-page (writesize).
			 * The pages that on-die ECC CAN correct are kept verbatim — this
			 * includes the small master/superblock node at the head of the
			 * block, which UBIFS needs. The pages ECC CANNOT correct are filled
			 * with 0xFF: for a master-area block those are the unused tail
			 * (which a clean image has as 0xFF anyway); for a data block that
			 * data was already unrecoverable. Then erase + re-program the whole
			 * block through the kernel → the block becomes Linux-written
			 * (reliable) with the master node preserved and a clean tail. No
			 * more -74 on this block, ever. */
			int bad_pages = 0, npg = es / m.writesize;
			for (int pg = 0; pg < npg; pg++) {
				uint32_t plen = m.writesize;
				struct mtd_read_req_ecc_stats pecc;
				uint8_t *p = buf + (uint32_t)pg * plen;
				int pr = memread_peb(fd, off + (uint32_t)pg * plen, plen, p, &pecc);
				if (pr < 0 || pecc.uncorrectable_errors > 0) {
					memset(p, 0xFF, plen);
					bad_pages++;
				}
			}
			fprintf(stderr, "  peb=%d full-read uncorrectable → page recovery "
				"(%d/%d pages unreadable → 0xFF, rest kept)\n", peb, bad_pages, npg);
			recovered++;
		} else {
			rewrote++;
		}
		/* common path: erase + re-program through the kernel (reliable write) */
		if (memerase_peb(fd, off, es) < 0) {
			fprintf(stderr, "  peb=%d erase failed: %s\n", peb, strerror(errno));
			failed++;
			continue;
		}
		if (memwrite_peb(fd, off, es, buf) < 0) {
			fprintf(stderr, "  peb=%d write failed: %s\n", peb, strerror(errno));
			failed++;
			continue;
		}
		if (((rewrote + recovered) % 8) == 0)
			fprintf(stderr, "  ... %d blocks written\n", rewrote + recovered);
	}

	free(buf);
	fprintf(stderr, "ubiprog done: rewrote=%d recovered(page-level)=%d "
		"skipped(erased)=%d failed=%d (of %d PEBs)\n",
		rewrote, recovered, skipped_erased, failed, npeb);
	return failed ? 1 : 0;
}
