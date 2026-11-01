# boot-tftp.cmd — TFTP kernel + NFS root: the no-reflash iteration loop (2026-11-01).
#
# Board side (U-Boot prompt, after interrupting autoboot):
#   setenv ipaddr 192.168.50.99
#   setenv serverip 192.168.50.5
#   tftp ${scriptaddr} boot-tftp.scr
#   source ${scriptaddr}
#
# Network: board eth0 (gmac0/RTL8211F) direct-cabled to the PC wired NIC,
# static 192.168.50.0/24, no DHCP on the link (PC .5 static, mirrored into
# WSL; board .99). Host side: tftpd-hpa serves out/rk3588-topeet/tftpboot
# (--secure --verbose), nfsd exports out/rk3588-topeet/rootfs (the same tree
# rootfs.ext4/update.img are packed from — single source of truth). Full
# bring-up log: notes/117.
#
# ADDRS (rk3588_common.h, same as boot-emmc.cmd): kernel_addr_r=0x02000000,
# fdt_addr_r=0x12000000. Raw Image + dtb with booti — no FIT repack per
# iteration; the Image/dtb in tftpboot/ are whatever `forge build linux`
# last produced (copied there by the staging step, see notes/122).
#
# ip= static syntax: <client>:<server>:<gw>:<mask>:<host>:<dev>:<autoconf>;
# direct link has no gateway → gw empty; autoconf=off (no DHCP on this link).
#
# kernel.config is all-=y (zero modules — the busybox-no-modprobe trap note),
# so a freshly TFTP'd kernel needs no matching /lib/modules in the NFS root.

setenv bootargs console=ttyFIQ0 root=/dev/nfs nfsroot=192.168.50.5:/home/charliechen/rk-forge/out/rk3588-topeet/rootfs,vers=3,tcp ip=192.168.50.99:192.168.50.5::255.255.255.0::eth0:off rw
tftpboot ${kernel_addr_r} Image
tftpboot ${fdt_addr_r} rk3588-topeet.dtb
booti ${kernel_addr_r} - ${fdt_addr_r}
