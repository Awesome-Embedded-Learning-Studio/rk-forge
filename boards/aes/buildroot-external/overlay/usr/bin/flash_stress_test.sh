#!/bin/sh
# flash_stress_test.sh — NAND/UBIFS write-reliability stress test (forge).
# Adapted from vendor external/rockchip-test/flash_test/flash_stress_test.sh.
#
# Writes random data to a NAND-backed dir (the UBIFS rootfs), syncs, drops
# caches, reads back and md5-verifies. A write-time bit-flip on the SFC path
# shows up as an md5 mismatch (the file reads back with a flipped bit). Loop
# until a mismatch (FAIL) or the count is reached (PASS).
#
# Usage: flash_stress_test.sh [loops]   (default 1000)
# Writes ~30 MB/loop to /root/flash_test (the UBIFS NAND). Keep loops modest
# unless you have headroom.
set -eu

TEST_DIR=/root/flash_test
LOOPS=${1:-1000}

SRC=$TEST_DIR/src
DST=$TEST_DIR/dst
MD5=$TEST_DIR/src.md5

mkdir -p "$SRC"
rm -rf "$SRC"/* "$DST" 2>/dev/null || true

# Seed files: a few MB of random data, mixed sizes (like the vendor test).
echo "[stress] generating source files (~10 MB random)..."
dd if=/dev/urandom of="$SRC/a.bin" bs=1024 count=5120 2>/dev/null   # 5 MB
dd if=/dev/urandom of="$SRC/b.bin" bs=1024 count=2048 2>/dev/null   # 2 MB
dd if=/dev/urandom of="$SRC/c.bin" bs=1024 count=3072 2>/dev/null   # 3 MB
( cd "$SRC" && md5sum ./* ) > "$MD5"
echo "[stress] source md5:"
cat "$MD5"

i=0
while [ "$i" -lt "$LOOPS" ]; do
	rm -rf "$DST"
	mkdir -p "$DST"
	cp -a "$SRC"/. "$DST"/ || { echo "[stress] loop $i: cp FAILED"; exit 1; }
	sync
	echo 3 > /proc/sys/vm/drop_caches 2>/dev/null || true
	sleep 1
	( cd "$DST" && md5sum ./* ) > "$DST.md5"
	if diff "$MD5" "$DST.md5" >/dev/null; then
		echo "[stress] loop $i/$LOOPS: OK"
	else
		echo "[stress] !!! loop $i: MD5 MISMATCH — write bit-flip reproduced !!!"
		echo "[stress] expected:"; cat "$MD5"
		echo "[stress] got:";      cat "$DST.md5"
		echo "[stress] keeping $DST for forensics (mtdrawdump / dmesg)"
		exit 2
	fi
	i=$((i + 1))
done

echo "[stress] ===== PASS: $LOOPS loops, no md5 mismatch ====="
