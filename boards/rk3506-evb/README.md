# boards/rk3506-evb

Placeholder board entry. The real board is TBD — likely whatever the
正点原子/ALIENTEK SDK targets (confirm it's actually RK3506), or
Firefly Core-3506BY / ArmSoM / LuckFox.

## Why this directory is the heart of rk-forge

Upstream already has RK3506 **SoC** support (pinctrl + clk since Linux 6.19→now 7.0.x;
U-Boot SoC support via Jonas Karlman's merged v2 series). What upstream does **NOT**
have is a **board** device tree. That board `.dts` is rk-forge's main contribution —
the upstream-bound artifact this project exists to produce.

## Files

| file | status | purpose |
|---|---|---|
| `board.dts` | TODO (Week 5-6) | board-level DT: UART/clk/pinctr/other nodes the real board needs |
| `kernel.config` | stub | defconfig fragment, merged via kernel's `merge_config.sh` |
| `README.md` | this | |

## Next step

Once the real board is known, extract its pin/clock/peripheral truth from the
vendor SDK (`third_party/vendor-sdk/`) via `scripts/sdk-diff.sh`, and author
`board.dts` on top of mainline's `arch/arm/boot/dts/rockchip/rk3506*.dtsi`.
