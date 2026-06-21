# 06 — USB2PHY + DWC2 bring-up on RK3506 (Phase B)

Board-verified PASSED (boot-sdl-202606200858: both DWC2 controllers host-up,
USB hub + mass-storage stick → `/dev/sba`). Three non-obvious traps below; the
first two cost a board flash each. Full driver/DT detail in notes/28.

## P1 — kernel-trim.config silently kills ALL USB
**Symptom**: full build succeeds, but `.config` has **no USB at all** —
`CONFIG_USB_SUPPORT is not set`, and DWC2 / `PHY_ROCKCHIP_INNO_USB2` /
`USB_STORAGE` are all absent (not even `# ... is not set`, just gone).

**Root cause**: `board/rk3506-evb/kernel-trim.config` carried
`# CONFIG_USB_SUPPORT is not set` (USB listed under "subsystems not needed yet"),
and build-linux.sh merges fragments in order **multi_v7 → kernel.config →
kernel-trim → kernel-compress**. Trim runs AFTER kernel.config, so it OVERRIDES
your `CONFIG_PHY_ROCKCHIP_INNO_USB2=y` etc. `USB_SUPPORT` is the top-level
menuconfig gating every USB symbol → with it off, olddefconfig drops the lot.

**Fix**: delete the `# CONFIG_USB_SUPPORT is not set` line from kernel-trim when
a phase needs USB. Same pattern bit SOUND earlier (re-enabled in kernel.config
after trim stopped cutting it). **Always grep the built `.config`** for the flags
you added, not just the fragment — the merge order can hide an override.

## P2 — must enable the usb2phy PARENT node, not only the child ports
**Symptom**: `dmesg | grep dwc2` shows
`platform ff740000.usb: deferred probe pending: dwc2: error getting phy`,
and there is **no `rockchip-usb2phy ff2b0000` probe line at all**.

**Root cause**: `phy-rockchip-inno-usb2` binds to the `usb2phy` **parent** node
(the one with the `rk3506-usb2phy` compatible). The `otg-port` / `host-port`
children are the phys the driver PUBLISHES after it probes. The SoC dtsi ships
the parent `status = "disabled"`; enabling only `&u2phy_otg0/1` (the children)
leaves the provider unprobed → OF core never creates the parent platform device →
no phy provider → DWC2 defers forever.

**Fix**: also `&usb2phy { status = "okay"; };` in the board dts. Vendor
rk3506-evb2-v10.dtsi does exactly this (parent + child + dwc2, all three).
**Rule**: for any provider/consumer DT pair, the node the DRIVER matches (has the
compatible) must be enabled — enabling the sub-nodes it creates is not enough.

## P3 — RK3506 USB2PHY splits its registers across GRF + a dedicated PHY mmio
This is the key architecture fact that shapes the driver port (not a runtime bug,
but the thing that makes "just copy vendor's cfg" wrong).

**Fact**: line-by-lining the vendor 6.1 `phy-rockchip-inno-usb2.c`:
- Detection / power / charger regs (`phy_sus`, `bvalid/idfall/idrise/ls_det`,
  `utmi_*`, `chg_det`) → accessed via **`rphy->grf`** (the `rockchip,usbgrf=<&grf>`
  regmap, GRF@ff288000). Mainline's grf-regmap model handles these unchanged.
- PHY analog tuning + the 480M clkout gate → accessed via **`rphy->phy_base`**
  (ioremap of the PHY's own 0x8000 block @ 0xff2b0000). Mainline has no phy_base.

**Consequence**: RK3506 does NOT fit "PHY config lives in GRF" cleanly. The
faithful-lite port adds ONE optional `phy_base` (ioremap, IS_ERR→NULL so classic
GRF-only PHYs are unaffected) for the analog tuning; detection stays on grf. The
480M clkout is deliberately NOT modelled — RK3506 DWC2 consumes only CRU clocks,
not the PHY 480M, so the gate is irrelevant (DT carries no `#clock-cells`).

**How to apply** (any new Rockchip PHY port): first determine, from the vendor
driver, which register space EACH cfg field hits (grf regmap vs a dedicated
mmio). Don't assume the mainline single-regmap model — newer SoCs (rk3588,
rk3506) move PHY registers out of the GRF.
