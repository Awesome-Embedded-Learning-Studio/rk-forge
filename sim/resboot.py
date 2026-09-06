#!/usr/bin/env python3
"""研究机冷启：起 QEMU（SCMIDBG=1，panthor 在，GDM mask），串口 4446、
监视 4449，stderr 落 /tmp/scmi-dbg.log，限时自杀。
用法：nohup python3 sim/resboot.py <秒> &"""
import os
import subprocess
import sys
import time
from pathlib import Path

SIM = Path(__file__).resolve().parent
sys.path.insert(0, str(SIM))
os.chdir(SIM.parent)
import engine  # noqa: E402

ARGV = [
    engine.find_qemu(), "-M", "rk3588-lite", "-smp", "8", "-m", "2G",
    "-display", "none", "-no-reboot",
    "-serial", "null",
    "-chardev", "socket,id=ser0,host=127.0.0.1,port=4446,server=on,"
                "wait=off,logfile=/tmp/scmi-serial.log",
    "-device", "virtio-serial-device",
    "-device", "virtconsole,chardev=ser0",
    "-monitor", "tcp:127.0.0.1:4449,server,nowait",
    "-kernel", str(engine.ROOT / "third_party/src/rk3588-topeet/linux/"
                 "arch/arm64/boot/Image"),
    "-drive", f"if=none,id=hd,file={engine.ROOT}/out/rk3588-topeet/rootfs.ext4,"
              "format=raw",
    "-device", "virtio-blk-device,drive=hd",
    "-dtb", str(engine.ROOT / "third_party/src/rk3588-topeet/linux/"
                "arch/arm64/boot/dts/rockchip/rk3588-topeet.dtb"),
    "-append",
    "console=hvc0 "
    + " ".join(f"virtio_mmio.device=0x200@0x{0xfea00000 + i * 0x200:x}:"
               f"spi{160 + i}:{i}" for i in range(6))
    + " root=/dev/vda rw rootwait init=/sbin/init panic=-1 cpuidle.off=1 "
      "drm_client_lib.active=none quiet loglevel=3 fw_devlink=off"
    + ("" if os.environ.get("GDM") else " systemd.mask=gdm.service"),
]

DUR = float(sys.argv[1]) if len(sys.argv) > 1 else 600
LOG = open("/tmp/scmi-dbg.log", "w")
env = dict(os.environ, SCMIDBG="1")
p = subprocess.Popen(ARGV, stdout=subprocess.DEVNULL, stderr=LOG, env=env)
time.sleep(DUR)
p.kill()
