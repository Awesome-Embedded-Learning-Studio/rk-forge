<template>
  <figure class="bringup-sheet" aria-label="RK3588 板级启动验证记录">
    <figcaption class="sheet-head">
      <span>FIELD RECORD / 03</span>
      <span class="sheet-state"><i /> VERIFIED ON BOARD</span>
    </figcaption>

    <div class="sheet-body">
      <svg class="trace-map" viewBox="0 0 640 360" aria-hidden="true">
        <path d="M34 46h118l42 42h102" />
        <path d="M24 286h94l44-44h134" />
        <path d="M344 76h94l58 58h114" />
        <path d="M344 252h80l44-44h140" />
        <path d="M250 28v52M250 280v54M330 28v52M330 280v54" />
        <circle cx="34" cy="46" r="4" />
        <circle cx="24" cy="286" r="4" />
        <circle cx="610" cy="134" r="4" />
        <circle cx="608" cy="208" r="4" />
      </svg>

      <div class="sheet-index">RK / 3588</div>
      <div class="sheet-note sheet-note--a">UART · 115200</div>
      <div class="sheet-note sheet-note--b">VOP2 / DSI2</div>

      <div class="board">
        <span class="mount mount--tl" />
        <span class="mount mount--tr" />
        <span class="mount mount--bl" />
        <span class="mount mount--br" />

        <div class="board-mark">RK-FORGE<br><small>TOPEET / REV. A</small></div>
        <div class="soc">
          <span>ROCKCHIP</span>
          <strong>RK3588</strong>
          <small>8 CORE · ARM64</small>
        </div>
        <div class="ram ram--a">LPDDR</div>
        <div class="ram ram--b">LPDDR</div>
        <div class="connector connector--left" />
        <div class="connector connector--right" />
        <div class="connector connector--bottom" />
        <span class="led led--1" />
        <span class="led led--2" />
      </div>
    </div>

    <div class="sheet-log">
      <div><span>BOOT</span><b>U-Boot 2026.07-rc4</b><em>PASS</em></div>
      <div><span>KERNEL</span><b>Linux 7.1.0 / mainline</b><em>PASS</em></div>
      <div><span>OUTPUT</span><b>update.img / self-check</b><em>PASS</em></div>
    </div>
  </figure>
</template>

<style scoped>
.bringup-sheet {
  --sheet-ink: #20251f;
  --sheet-paper: #e8e3d8;
  --sheet-line: rgba(32, 37, 31, 0.24);
  width: min(100%, 610px);
  margin: 0;
  color: var(--sheet-ink);
  background: var(--sheet-paper);
  border: 1px solid var(--sheet-ink);
  border-radius: 8px;
  overflow: hidden;
  box-shadow: 9px 9px 0 rgba(32, 37, 31, 0.12);
}
.sheet-head {
  display: flex; justify-content: space-between; align-items: center; gap: 16px;
  min-height: 42px; padding: 0 15px; border-bottom: 1px solid var(--sheet-ink);
  font-family: var(--vp-font-family-mono); font-size: 10px; font-weight: 700; letter-spacing: .1em;
}
.sheet-state { display: inline-flex; align-items: center; gap: 7px; }
.sheet-state i { width: 7px; height: 7px; background: var(--vp-c-brand-1); }
.sheet-body {
  position: relative; min-height: 340px; overflow: hidden;
  background-image: linear-gradient(var(--sheet-line) 1px, transparent 1px), linear-gradient(90deg, var(--sheet-line) 1px, transparent 1px);
  background-size: 20px 20px;
}
.trace-map { position: absolute; inset: 0; width: 100%; height: 100%; fill: var(--sheet-paper); stroke: rgba(32, 37, 31, .52); stroke-width: 1.25; vector-effect: non-scaling-stroke; }
.sheet-index { position: absolute; right: 14px; top: 12px; font: 700 10px var(--vp-font-family-mono); letter-spacing: .13em; writing-mode: vertical-rl; }
.sheet-note { position: absolute; z-index: 2; padding: 3px 6px; background: var(--sheet-paper); border: 1px solid var(--sheet-ink); font: 9px var(--vp-font-family-mono); letter-spacing: .06em; }
.sheet-note--a { left: 20px; top: 39px; }.sheet-note--b { right: 18px; bottom: 40px; }
.board { position: absolute; left: 50%; top: 50%; width: 288px; height: 226px; transform: translate(-50%, -50%); background: #4f5d49; border: 2px solid var(--sheet-ink); border-radius: 5px; box-shadow: 5px 5px 0 rgba(32, 37, 31, .18); }
.mount { position: absolute; width: 14px; height: 14px; border: 2px solid #c4c7b4; border-radius: 50%; }
.mount--tl { left: 10px; top: 10px; }.mount--tr { right: 10px; top: 10px; }.mount--bl { left: 10px; bottom: 10px; }.mount--br { right: 10px; bottom: 10px; }
.board-mark { position: absolute; left: 36px; top: 18px; color: #e9e6d9; font: 700 11px/1.2 var(--vp-font-family-mono); letter-spacing: .08em; }
.board-mark small { font-size: 7px; font-weight: 500; opacity: .68; }
.soc { position: absolute; left: 91px; top: 67px; display: flex; flex-direction: column; justify-content: center; width: 106px; height: 92px; padding: 13px; color: #d9dbd0; background: #242b24; border: 1px solid #111510; box-shadow: inset 0 0 0 4px #303830; font-family: var(--vp-font-family-mono); }
.soc span, .soc small { font-size: 7px; letter-spacing: .11em; opacity: .7; }.soc strong { margin: 3px 0; font-size: 18px; line-height: 1; letter-spacing: -.04em; }
.ram { position: absolute; width: 56px; height: 30px; color: #aeb5a7; background: #2d352d; border: 1px solid #202620; font: 6px/30px var(--vp-font-family-mono); text-align: center; letter-spacing: .1em; }
.ram--a { left: 25px; top: 92px; }.ram--b { right: 25px; top: 92px; }
.connector { position: absolute; background: repeating-linear-gradient(90deg, #c9c1a5 0 3px, #282d27 3px 6px); border: 1px solid #1f241f; }
.connector--left { left: -7px; top: 58px; width: 15px; height: 106px; background: repeating-linear-gradient(0deg, #c9c1a5 0 3px, #282d27 3px 6px); }.connector--right { right: -7px; top: 58px; width: 15px; height: 106px; background: repeating-linear-gradient(0deg, #c9c1a5 0 3px, #282d27 3px 6px); }.connector--bottom { left: 94px; bottom: -7px; width: 100px; height: 15px; }
.led { position: absolute; bottom: 25px; width: 6px; height: 6px; background: #e0a239; box-shadow: 0 0 0 2px #394338; }.led--1 { left: 36px; }.led--2 { left: 49px; background: #d6d9bb; }
.sheet-log { border-top: 1px solid var(--sheet-ink); font-family: var(--vp-font-family-mono); }
.sheet-log > div { display: grid; grid-template-columns: 70px 1fr 46px; gap: 10px; align-items: center; min-height: 34px; padding: 0 14px; border-bottom: 1px solid var(--sheet-line); font-size: 9px; }
.sheet-log > div:last-child { border-bottom: 0; }.sheet-log span { color: rgba(32, 37, 31, .58); letter-spacing: .1em; }.sheet-log b { overflow: hidden; font-weight: 600; text-overflow: ellipsis; white-space: nowrap; }.sheet-log em { color: var(--vp-c-brand-1); font-style: normal; font-weight: 800; text-align: right; }
@media (max-width: 639px) {
  .bringup-sheet { width: calc(100vw - 48px); box-shadow: 6px 6px 0 rgba(32, 37, 31, .12); }.sheet-head { font-size: 8px; }.sheet-body { min-height: 285px; }.board { width: 230px; height: 184px; }.soc { left: 72px; top: 53px; width: 86px; height: 78px; }.ram { width: 43px; }.ram--a { left: 20px; top: 78px; }.ram--b { right: 20px; top: 78px; }.connector--left, .connector--right { top: 47px; height: 86px; }.connector--bottom { left: 74px; width: 82px; }.sheet-log > div { grid-template-columns: 56px 1fr 36px; gap: 6px; padding: 0 10px; font-size: 8px; }
}
</style>
