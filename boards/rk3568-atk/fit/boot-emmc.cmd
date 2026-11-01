# boot-emmc.cmd — u-boot boot script source for RK3568 ATK eMMC boot.
#
# WHY THIS EXISTS: forge's eMMC boot partition is RAW — assemble-update.sh writes
# boot.img (the kernel FIT) whole-partition (truncated+padded to 64 MiB), NOT as a
# file on a filesystem. So u-boot's bootflow (bootcmd = "bootflow scan -lb") cannot
# load boot.img as a file — its bootmeths (extlinux/script/efi) all need a filesystem.
#
# RESOLUTION: bootflow's SCRIPT bootmeth finds /boot/boot.scr (and /boot.scr) on the
# ext4 ROOTFS partition (mmcblk1p3), runs it, and THIS script does a raw `mmc read`
# of the boot partition into RAM and `bootm`s the FIT. So the boot flow is:
#   BootROM → idbloader (@0x40) → SPL → u-boot.itb (uboot part)
#   → bootflow scan → mounts rootfs p3 (ext4) → finds /boot/boot.scr
#   → mmc read boot-img-raw → bootm FIT (kernel+evb1-v10 dtb) → kernel mounts p3.
#
# LAYOUT (parameter-emmc-atk.txt, 512 B sectors):
#   0x6000  boot   size 0x20000 (64 MiB)  — boot.img FIT, ~42 M, padded to fill
#   0x26000 rootfs size 0x200000 (1 GiB)  — ext4, mmcblk1p3 (root= below)
# ADDRS (rk3568_common.h): kernel_addr_r=0x02000000, fdt_addr_r=0x12000000.
# console from DT stdout-path "serial2:1500000n8" → Linux ttyS2.
#
# mmc read args: <ram-addr> <start-sector> <count>. 0x6000 = boot partition LBA,
# 0x20000 = 131072 sectors = 64 MiB (whole boot partition; FIT lives at its head,
# padding 0x00 after is harmless to bootm which parses the FDT header).
# Read into ${kernel_addr_r}; bootm loads kernel/fdt from the FIT's external data.

mmc dev 0
setenv bootargs console=ttyS2,115200 root=/dev/mmcblk1p3 rw rootwait
# Load the FIT to 0x08000000, NOT ${kernel_addr_r} (0x02000000): the FIT's kernel
# subimage load-address is also 0x02000000, so loading the FIT at 0x02000000 makes
# bootm abort with "new format image overwritten" (copying kernel to its load
# address would clobber the FIT image itself). 0x08000000 is free DRAM (kernel
# spans 0x02000000-0x04920000, fdt loads at 0x12000000); bootm copies kernel from
# the FIT to 0x02000000 and fdt to 0x12000000 without overlapping the FIT.
# mmc read args: <ram-addr> <start-sector> <count>; 0x6000=boot part LBA, 0x20000=64MiB.
mmc read 0x08000000 0x6000 0x20000
bootm 0x08000000
