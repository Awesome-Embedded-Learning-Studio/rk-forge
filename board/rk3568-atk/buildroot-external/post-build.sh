#!/bin/sh
# post-build.sh — rootfs post-build fixes for rk3568-atk.
# Called by buildroot with TARGET_DIR set to the staged rootfs.
set -eu

# sshd requires /var/empty owned by root, mode 0755 (not group/world-writable).
# buildroot's openssh creates it but perms can drift; enforce here.
if [ -d "$TARGET_DIR/var/empty" ]; then
	chmod 0755 "$TARGET_DIR/var/empty"
	chown 0:0 "$TARGET_DIR/var/empty" 2>/dev/null || true
fi

# Populate /etc/ld.so.cache for the external glibc toolchain (no GLIBC_UTILS
# available for external toolchains). Helps mesa3d/gstreamer/Qt plugin dlopen.
if command -v ldconfig >/dev/null 2>&1; then
	ldconfig -r "$TARGET_DIR" 2>/dev/null || true
fi
