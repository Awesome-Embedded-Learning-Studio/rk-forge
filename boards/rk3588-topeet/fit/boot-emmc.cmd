# boot-emmc.cmd — u-boot boot script source for RK3588 topeet eMMC boot.
#
# WHY THIS EXISTS: forge's eMMC boot partition is RAW — assemble-update.sh writes boot.img
# (the kernel FIT) whole-partition (truncated+padded to 64 MiB), NOT as a file on a
# filesystem. So u-boot's bootflow (bootcmd = "bootflow scan -lb") cannot load boot.img as a
# file — its bootmeths need a filesystem.
#
# RESOLUTION: bootflow's SCRIPT bootmeth finds /boot/boot.scr on the ext4 ROOTFS partition,
# runs it, and THIS script does a raw `mmc read` of the boot partition into RAM and `bootm`s
# the FIT. Boot flow:
#   BootROM → idbloader (@0x40) → SPL → u-boot.itb (uboot part)
#   → bootflow scan → mounts rootfs p3 (ext4) → finds /boot/boot.scr
#   → mmc read boot-img-raw → bootm FIT (kernel + rk3588-evb1-v10 dtb) → kernel mounts p3.
#
# ADDRS (rk3588_common.h): kernel_addr_r=0x02000000, fdt_addr_r=0x12000000 — IDENTICAL to
# RK3568. FIT is loaded to 0x08000000 (free DRAM, NOT kernel_addr_r: loading the FIT at
# 0x02000000 would make bootm abort "new format image overwritten" when it copies the kernel
# subimage to its load address). UART2 is owned by the vendor Rockchip FIQ
# debugger stack and exposed as ttyFIQ0 @115200; uart2 itself stays disabled so
# the DesignWare 8250 driver cannot bind the same registers.
#
# root= device number: mmcblk1p3 by analogy with rk3568-atk; RK3588 may enumerate eMMC as
# mmcblk0 depending on SDHCI probe order — if boot fails at root mount, switch to mmcblk0p3.
#
# mmc read args: <ram-addr> <start-sector> <count>; 0x6000=boot part LBA, 0x20000=64MiB.

mmc dev 0
# NFS root (2026-10-31): board eth0 (gmac0/RTL8211F) DIRECT-CABLED to the PC's wired NIC
# (no DHCP on that link) — static 192.168.50.0/24 both ends. PC NIC = 192.168.50.5 (static,
# mirrored into WSL); board = 192.168.50.99. Link verified layer-by-layer: PHY autoneg OK,
# ARP both ways, TFTP OK, ICMP allowed (netsh ICMP-in-50 rule). WSL side needs nfsd exporting
# out/rk3588-topeet/rootfs (the forge source tree — single source of truth with rootfs.ext4).
# ip= static syntax: <client>:<server>:<gw>:<mask>:<host>:<dev>:<autoconf>; direct link has
# no gateway → gw empty; autoconf=off (no DHCP on this link).
# eMMC root, clean bootargs (2026-11-01): the diagnostic-era helpers are gone —
# earlycon, irqchip.gicv3_pseudo_nmi=1 (wedge-era NMI console), rcupdate.rcu_expedited=1 /
# rcu_nocbs=all (iteration aids) — none masked the root causes, which are fixed in the patch
# stack (notes/118-121: GPLL relock + TC358775 lifecycle). NFS iteration runs via tftp +
# bootargs set in U-Boot, not from this script. The NFS history block below is retained
# for the 2026-10-31 bring-up record only.
setenv bootargs console=ttyFIQ0 root=/dev/mmcblk0p3 rw rootwait
mmc read 0x08000000 0x6000 0x20000
bootm 0x08000000
