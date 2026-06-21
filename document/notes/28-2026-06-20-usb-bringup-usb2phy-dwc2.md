# notes/28 — 2026-06-20 — B-USB bring-up (USB2PHY + DWC2)

**Status: code complete + built-in; board validation PENDING.** The only active
peripheral left. Goal = USB **enumeration** (dmesg device descriptor); WiFi
RTL8733BU dongle driver is follow-up.

## The three gaps (all wiring + one driver of_match, no architecture 原创)
1. **Driver**: mainline `drivers/phy/rockchip/phy-rockchip-inno-usb2.c` had no
   `rk3506-usb2phy` of_match → PHY never probed. Vendor 6.1 fork supports it but
   on a **diverged model** (extra `phy_base` mmio + extra cfg fields + macros).
2. **DT**: forge `rk3506.dtsi` (minimal) had no usb2phy/dwc2 nodes.
3. **config**: `PHY_ROCKCHIP_INNO_USB2` off; `USB_SUPPORT` cut by kernel-trim.

## Key architecture finding (the de-risk — read before touching this driver)
Line-by-lined the vendor 6.1 driver. RK3506's USB2PHY uses **two register spaces**:
- **Detection / power / charger** (`phy_sus`@0x0060, `bvalid/idfall/idrise/ls_det`@0x0150,
  `utmi_*`@0x0118, `chg_det`) → all via **`rphy->grf`** (vendor DT
  `rockchip,usbgrf = <&grf>`, GRF@ff288000). **Mainline's grf-regmap path covers
  these with zero driver change.**
- **Analog tuning + 480M clkout gate** (`clkout_ctl_phy`@0x041c, eye-height,
  pre-emphasis, diff-rx) → via **`rphy->phy_base`** (ioremap PHY block@ff2b0000).
  Mainline struct has **no phy_base / no ioremap**.
- **Why host enumeration doesn't need the hard parts**: `phy_sus` (the actual
  power switch) is in the GRF → mainline can power the PHY. The vendor DWC2 DT
  consumes **only CRU clocks** (HCLK_USBOTGx/_PMU/_ADP), **not the PHY 480M** →
  the clkout gate is irrelevant. Analog tuning is signal-quality, not enumeration.

## Approach: faithful-lite (not vendor-verbatim, not bare grf-only)
- struct `rockchip_usb2phy`: +1 field `void __iomem *phy_base`.
- probe: `devm_platform_ioremap_resource(pdev, 0)` → phy_base, **IS_ERR→NULL**
  (classic GRF-only PHYs unaffected; only RK3506's node has the MEM resource).
- `rk3506_usb2phy_tuning()`: ports vendor's 6 phy_base writes, open-codes
  `phy_clear_bits`/`phy_update_bits` as readl/writel RMW; no-op if phy_base NULL.
- `rk3506_phy_cfgs[]`: 2 ports, detection regs in grf (mapped `utmi_iddig`→`utmi_id`).
  **Dropped**: OTG iddig-force fields (`bvalid_grf_sel/con`, `iddig_output/en`,
  `vbus_det_en`, `port_ls_filter_con`) + `chg_det` (`chg_mode` has no mainline
  struct member; charger detect not needed for host) → **zero struct field additions**.
  **No `.clkout_ctl`** (DT carries no `#clock-cells` → `clk480m_register` never runs).
- of_match: +`rockchip,rk3506-usb2phy`.

## Deliverables (patches 0014 + 0015, committed in explore/linux)
- **0014** `phy: rockchip: inno-usb2: add RK3506 support` (539b4241d)
- **0015** `ARM: dts: rockchip: rk3506b-aes: add USB2PHY + DWC2` (75d13ceca)
  - rk3506.dtsi: `usb2phy@ff2b0000` (rk3506-usb2phy, usbgrf=<&grf>, no #clock-cells)
    + `u2phy_otg0`(otg-port,IRQ75/76/77) + `u2phy_otg1`(host-port,IRQ80/81/82);
    `usb@ff740000` + `usb@ff780000` (`rockchip,rk3066-usb`/`snps,dwc2` fallback —
    **no dwc2 driver patch**, dwc2 binds on the generic fallback).
  - rk3506b-aes.dts: both PHY ports + both controllers `dr_mode="host"`.
- config: `board/rk3506-evb/kernel.config` += `PHY_ROCKCHIP_INNO_USB2=y` +
  `USB_DWC2_HOST=y`; **`kernel-trim.config` dropped the `# CONFIG_USB_SUPPORT is
  not set` line** (it's applied AFTER kernel.config and was gating all USB off —
  the build first came up with DWC2/PHY absent until this was fixed).
- series: 0014/0015 appended.
- **Image**: `update-usb-bringup.img` (34341450 B, md5 `fd3e3912c26ec030e42274629f11cf76`)
  in `/mnt/d/DownloadFromInternet/`. PROVISION-UBIPROG variant (boot.img with the
  new kernel, padded to fill the 16 MiB boot partition).

## Build verification (local, all green)
- `--just-dtb`: USB nodes compile, all label/clock refs resolve.
- full build: exit 0. `.config` confirms `USB_SUPPORT=y / USB_DWC2=y /
  USB_DWC2_HOST=y / PHY_ROCKCHIP_INNO_USB2=y / USB_STORAGE=y`; `modules.builtin`
  lists `phy-rockchip-inno-usb2 / dwc2 / usb-storage / usb-common` (built-in).

## Board test #1 (boot-sdl-202606200858) — FAILED, root cause found + fixed
Boot itself fine (kernel 7.1.0, AES board, ubiprog provisioned rootfs, buildroot
login). But USB dead:
```
[   12.010085] platform ff740000.usb: deferred probe pending: dwc2: error getting phy
[   12.010816] platform ff780000.usb: deferred probe pending: dwc2: error getting phy
```
and `dmesg|grep` showed ONLY those two lines — **no `rockchip-usb2phy ff2b0000`
probe line at all**. So the PHY provider never came up; DWC2 correctly deferred.

**Root cause (DT bug, not driver)**: the SoC `usb2phy` **parent** node is
`status="disabled"` and I'd only enabled the child ports (`&u2phy_otg0/1`).
inno-usb2 binds to the parent (the node with the `rk3506-usb2phy` compatible);
the otg-port/host-port children are the phys it publishes AFTER it probes. With
the parent disabled, OF core never creates its platform device → driver never
probes → no phy provider → DWC2 defers forever. **Driver patch + DWC2 are fine.**

**Fix** (amended into 0015): enable the parent in aes.dts —
`&usb2phy { status = "okay"; };`. Mirrors vendor rk3506-evb2-v10.dtsi:779
(which enables `&usb2phy` alongside `&u2phy_otg0` + `&usb20_otg0`).
New image: **md5 `c633f11a894d7384f06ca941b7d8eb7d`** (was fd3e3912).

## Board test #2 (boot-sdl-202606200858, after the parent-enable fix) — PASSED ✅
Same image family, `&usb2phy { status="okay"; }` added. Full success — T1+T2+T3:
```
dwc2 ff740000.usb: DWC OTG Controller / new USB bus registered, bus number 1
dwc2 ff780000.usb: DWC OTG Controller / new USB bus registered, bus number 2
usb 2-1: new high-speed USB device number 2 using dwc2          ← enumeration
usb 2-1.3: new high-speed USB device number 3 using dwc2         ← behind a hub
usb-storage 2-1.1:1.0: USB Mass Storage device detected
sd 0:0:0:0: [sda] Attached SCSI removable disk                   ← /dev/sda, block device
```
Both DWC2 controllers registered as host (bus 1+2), got irqs 47/48, got their PHY
(no more "error getting phy"). A USB hub + mass-storage stick enumerated and the
stick attached as `/dev/sda`. `supply vusb_d/vusb_a not found → dummy regulator`
is the R2 vbus non-issue, confirmed harmless. **B-USB closed.** The WiFi dongle is
presumably one of the other enumerated devices — driver bring-up is the next phase.

## Board-test protocol (user: Windows RKDevTool烧 + UART抓log)
Boot args at the `=>` prompt: **`console=ttyS0,1500000` ONLY** (provision variant —
no root=, or /init won't run). Then `mtd read boot 0x04000000 0 0x1000000; bootm 0x04000000`.
- **T1 probe**: `dmesg | grep -iE "usb2phy|dwc2|u2phy|ff2b0000|ff740000|ff780000|rockchip-usb2phy"`
  → expect `rockchip-usb2phy ff2b0000.usb2-phy` probed + `dwc2 ff740000.usb`/`ff780000`
  host controller registered.
- **T2 enumerate**: plug USB dongle (or USB-stick) →
  `dmesg | grep -iE "usb [0-9]-[0-9]|new (high|full)-speed|device descriptor|Product:"`
  → device descriptor read = **B-USB achieved**.
- **T3** (if USB-stick): `ls /dev/sd*` / mount.

## Risks / follow-up
- **R1 PHY analog power-on**: vendor tuning touches no SIDDQ (analog block
  presumed powered by default), so enumeration should work on the first flash.
  If silent, add a phy_base power-on sequence (mirror whatever vendor's
  power_on does in phy_base).
- **R2 vbus**: no vbus regulator wired (board USB-A 5V assumed always-on). If a
  device doesn't enumerate, add a fixed always-on `vcc5v0_host` + `vbus-supply`.
- **F1 WiFi RTL8733BU dongle driver** (rtw88/rtl8xxxu, mainline, needs config) —
  the actual goal past enumeration.
- **F2 OTG/iddog + gadget**: needs the dropped iddig-force cfg fields + extcon.
- **F3 480M clkout**: only if a later EHCI/OHCI host controller consumes the PHY clock.
