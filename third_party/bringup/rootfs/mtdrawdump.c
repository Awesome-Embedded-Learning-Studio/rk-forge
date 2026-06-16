// SPDX-License-Identifier: GPL-2.0
/*
 * mtdrawdump — minimal raw-dump inspector for SPI-NAND write-path forensics.
 *
 * Reads a region of an MTD char device via the MEMREAD ioctl, either with
 * on-die ECC (default) or raw/no-ECC (-r). In raw mode the bytes are the
 * literal silicon contents, so a partially-erased block (sparse 0xFF mixed
 * with stale data) is distinguishable from a cleanly-programmed block whose
 * bits flipped beyond ECC strength.
 *
 * A one-line summary goes to stderr (length, #0xFF bytes = erased, ECC stats);
 * the raw bytes go to stdout so the caller can hash or capture them.
 *
 * Structs/ioctls copied verbatim from include/uapi/mtd/mtd-abi.h (Linux 7.x)
 * so the tool compiles with no kernel header path setup.
 *
 * Usage:
 *   mtdrawdump [-r] <mtddev> <offset> [length]
 *     -r   raw mode, on-die ECC disabled (see actual stored bits)
 *     offset/length in bytes; length defaults to one erase block
 *
 * Build (static, armhf):
 *   arm-none-linux-gnueabihf-gcc -O2 -static -s -o mtdrawdump mtdrawdump.c
 */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <stdint.h>
#include <fcntl.h>
#include <unistd.h>
#include <sys/ioctl.h>

/* ---- copied from include/uapi/mtd/mtd-abi.h ---- */
struct mtd_info_user {
	uint8_t type;
	uint32_t flags;
	uint32_t size;   /* total size in bytes */
	uint32_t erasesize;
	uint32_t writesize;
	uint32_t oobsize;
	uint64_t padding;
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

#define MEMGETINFO  _IOR('M', 1, struct mtd_info_user)
#define MEMREAD     _IOWR('M', 26, struct mtd_read_req)
#define MTD_OPS_PLACE_OOB 0   /* ECC on */
#define MTD_OPS_RAW       2   /* ECC off */

int main(int argc, char **argv)
{
	const char *dev;
	int raw = 0, fd, argi = 1;
	uint64_t off, len;
	uint32_t erasesize = 0;
	uint8_t *buf;
	struct mtd_info_user mtd;
	struct mtd_read_req req;

	if (argi < argc && strcmp(argv[argi], "-r") == 0) {
		raw = 1;
		argi++;
	}
	if (argc - argi < 2) {
		fprintf(stderr, "usage: mtdrawdump [-r] <mtddev> <offset> [length]\n");
		return 2;
	}
	dev = argv[argi++];
	off = strtoull(argv[argi++], NULL, 0);
	len = (argi < argc) ? strtoull(argv[argi], NULL, 0) : 0;

	fd = open(dev, O_RDONLY);
	if (fd < 0) { perror("open"); return 1; }

	if (ioctl(fd, MEMGETINFO, &mtd) == 0) {
		erasesize = mtd.erasesize;
		if (len == 0)
			len = erasesize;
		fprintf(stderr, "mtdrawdump: %s type=%u size=%u erasesize=%u "
			"writesize=%u oobsize=%u\n", dev, mtd.type,
			mtd.size, mtd.erasesize, mtd.writesize, mtd.oobsize);
	} else if (len == 0) {
		fprintf(stderr, "MEMGETINFO failed and no length given\n");
		return 1;
	}

	buf = malloc(len);
	if (!buf) { fprintf(stderr, "oom\n"); return 1; }

	memset(&req, 0, sizeof(req));
	req.start = off;
	req.len = len;
	req.usr_data = (uint64_t)(uintptr_t)buf;
	req.usr_oob = 0;
	req.ooblen = 0;
	req.mode = raw ? MTD_OPS_RAW : MTD_OPS_PLACE_OOB;

	if (ioctl(fd, MEMREAD, &req) < 0) {
		perror("MEMREAD");
		/* Still dump whatever the kernel returned; a raw read of a
		 * bad block returns -EBADMSG in ECC mode but the buffer may
		 * hold partial data. */
	}

	/* Summary to stderr: how much looks erased + ECC verdict. */
	{
		uint64_t i, ff = 0, nonff = 0, first_nonff = 0, last_nonff = 0;
		for (i = 0; i < len; i++) {
			if (buf[i] == 0xff) ff++;
			else {
				nonff++;
				if (nonff == 1) first_nonff = i;
				last_nonff = i;
			}
		}
		fprintf(stderr, "mtdrawdump: off=0x%llx len=%llu mode=%s "
			"0xFF=%llu (%.1f%%) non-0xFF=%llu first=0x%llx last=0x%llx "
			"ecc: uncorr=%u corrected=%u maxflip=%u\n",
			(unsigned long long)off, (unsigned long long)len,
			raw ? "RAW(no-ECC)" : "ECC",
			(unsigned long long)ff, 100.0 * ff / len,
			(unsigned long long)nonff,
			(unsigned long long)first_nonff,
			(unsigned long long)last_nonff,
			req.ecc_stats.uncorrectable_errors,
			req.ecc_stats.corrected_bitflips,
			req.ecc_stats.max_bitflips);
	}

	/* Raw bytes to stdout for hashing/capture. */
	if (write(STDOUT_FILENO, buf, len) != (ssize_t)len)
		perror("write");

	free(buf);
	close(fd);
	return 0;
}
