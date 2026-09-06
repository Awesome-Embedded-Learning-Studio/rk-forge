#!/usr/bin/env python3
"""法医 restore：snapshot.py 的 argv + 法医 cmdline（压 panic），周期采集
qom 诊断计数（diag-cpuif-N/vtimer-N、vop-fb-phys），锁死现场留存。
用法： nohup python3 sim/forensic_restore.py &（快照须已存在；输出
/tmp/forensic-diag.log）。B 役裁决工具：SMP=8 restore 5 核 cpuif 冻结
+victim 卡 arch_timer_read_cntvct/spinlock 互等（note 85）。"""
import os
import subprocess
import socket
import sys
import time
from pathlib import Path

SIM = Path("/home/charliechen/rk-forge/sim")
sys.path.insert(0, str(SIM))
os.chdir(SIM.parent)
import engine  # noqa: E402
from fbdump import qom_get  # noqa: E402

ROOT = engine.ROOT
OVERLAY = ROOT / "out/rk3588-topeet/sim-desktop.qcow2"
PORT, SPORT = 4445, 4446

ARGV = [
    engine.find_qemu(), "-M", "rk3588-lite",
    "-smp", "8", "-m", "2G", "-display", "none", "-no-reboot",
    "-chardev", f"socket,id=ser0,host=127.0.0.1,port={SPORT},server=on,"
                f"wait=off,logfile=/tmp/forensic-serial.log",
    "-device", "virtio-serial-device",
    "-device", "virtconsole,chardev=ser0",
    "-serial", "null",
    "-monitor", f"tcp:127.0.0.1:{PORT},server,nowait",
    "-kernel", str(ROOT / "third_party/src/rk3588-topeet/linux/"
                 "arch/arm64/boot/Image"),
    "-drive", f"if=none,id=hd,file={OVERLAY},format=qcow2",
    "-device", "virtio-blk-device,drive=hd",
    "-dtb", str(ROOT / "third_party/src/rk3588-topeet/linux/"
                "arch/arm64/boot/dts/rockchip/rk3588-topeet.dtb"),
    "-append",
    "console=hvc0 "
    + " ".join(f"virtio_mmio.device=0x200@0x{0xfea00000 + i * 0x200:x}:"
               f"spi{160 + i}:{i}" for i in range(6))
    + " root=/dev/vda rw rootwait init=/sbin/init panic=-1 cpuidle.off=1 "
      "drm_client_lib.active=none quiet loglevel=3 fw_devlink=off "
      # 法医开关：压住 hard/soft lockup 的 panic，让系统带伤活着
      "nmi_watchdog=0 watchdog=0 hardlockup_panic=0 softlockup_panic=0",
    "-loadvm", "desktop",
]

OUT = open("/tmp/forensic-diag.log", "w")
p = subprocess.Popen(ARGV, stdout=subprocess.DEVNULL, stderr=OUT)

t0 = time.time()
while time.time() - t0 < 900:
    time.sleep(15)
    try:
        sk = socket.create_connection(("127.0.0.1", PORT), timeout=5)
        sk.settimeout(1.5)
    except Exception:
        print(f"[{time.time()-t0:.0f}s] monitor gone", flush=True)
        break
    line = f"[{time.time()-t0:.0f}s]"
    for prop in ["vop-fb-phys"] + [f"diag-cpuif-{i}" for i in range(8)] + \
                [f"diag-vtimer-{i}" for i in range(8)]:
        v = qom_get(sk, prop)
        line += f" {prop.split('-')[1]}={v}"
    sk.close()
    print(line, flush=True)
print("exit", flush=True)
time.sleep(5)
p.kill()
