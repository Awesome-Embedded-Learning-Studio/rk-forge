<script setup lang="ts">
const layers = [
  { code: '05', name: '用户空间', en: 'USER SPACE', detail: 'BusyBox shell / buildroot / 自定义程序' },
  { code: '04', name: '根文件系统', en: 'ROOT FILESYSTEM', detail: 'UBIFS · SPI-NAND / ext4 · SD' },
  { code: '03', name: 'Linux 内核', en: 'KERNEL · 7.1', detail: '主线驱动 / 调度 / 网络 / 板级 DTB' },
  { code: '02', name: 'U-Boot', en: 'BOOTLOADER · 2026.07-RC4', detail: 'DDR init → DTB → kernel' },
  { code: '01', name: 'Rockchip 硬件', en: 'HARDWARE', detail: 'RK3506B / RK3568 / RK3588' },
]
</script>

<template>
  <section class="system-plate">
    <header class="plate-heading">
      <div>
        <span class="plate-kicker">SYSTEM MAP / 01—05</span>
        <h2>从焊盘到用户空间</h2>
      </div>
      <p>不把“能编译”当“能运行”。每一层都对应真板日志、可复现命令和失败记录。</p>
    </header>

    <div class="stack">
      <div v-for="layer in layers" :key="layer.code" class="stack-row">
        <span class="stack-code">{{ layer.code }}</span>
        <span class="stack-name">{{ layer.name }}</span>
        <span class="stack-en">{{ layer.en }}</span>
        <span class="stack-detail">{{ layer.detail }}</span>
        <span class="stack-mark" aria-hidden="true">→</span>
      </div>
    </div>

    <footer class="plate-footer">
      <div><span>BOOT DIRECTION</span><i /></div>
      <a href="/rk-forge/tutorial/">打开完整教学路线 <b>↗</b></a>
    </footer>
  </section>
</template>

<style scoped>
.system-plate { max-width: 1104px; margin: 0 auto; padding: 76px 0 80px; }
.plate-heading { display: grid; grid-template-columns: 1fr minmax(280px, 420px); align-items: end; gap: 48px; margin-bottom: 38px; }
.plate-kicker { display: block; margin-bottom: 13px; color: var(--vp-c-brand-1); font-family: var(--vp-font-family-mono); font-size: 10px; font-weight: 800; letter-spacing: .14em; }
.plate-heading h2 { margin: 0; color: var(--vp-c-text-1); font-size: clamp(28px, 4vw, 48px); font-weight: 680; line-height: 1.08; letter-spacing: -.055em; }
.plate-heading p { margin: 0; color: var(--vp-c-text-2); font-size: 13px; line-height: 1.8; }
.stack { overflow: hidden; border: 1px solid var(--vp-c-text-1); border-radius: 8px; }
.stack-row { display: grid; grid-template-columns: 54px 120px 190px 1fr 24px; align-items: center; gap: 16px; min-height: 75px; padding: 0 18px; border-bottom: 1px solid var(--vp-c-divider); transition: background-color .18s ease; }
.stack-row:last-child { border-bottom: 0; }
.stack-row:hover { background: var(--vp-c-bg-soft); }
.stack-code { color: var(--vp-c-brand-1); font: 800 11px var(--vp-font-family-mono); }.stack-name { font-size: 16px; font-weight: 680; }.stack-en { color: var(--vp-c-text-3); font: 10px var(--vp-font-family-mono); letter-spacing: .08em; }.stack-detail { color: var(--vp-c-text-2); font-size: 12px; }.stack-mark { color: var(--vp-c-brand-1); font-size: 17px; opacity: 0; transform: translateX(-6px); transition: opacity .18s ease, transform .18s ease; }.stack-row:hover .stack-mark { opacity: 1; transform: translateX(0); }
.plate-footer { display: flex; justify-content: space-between; align-items: center; margin-top: 26px; }
.plate-footer > div { display: flex; align-items: center; gap: 12px; color: var(--vp-c-text-3); font: 9px var(--vp-font-family-mono); letter-spacing: .11em; }.plate-footer i { position: relative; width: 86px; height: 1px; background: var(--vp-c-text-3); }.plate-footer i::after { content: ''; position: absolute; right: 0; top: -3px; width: 7px; height: 7px; border-right: 1px solid var(--vp-c-text-3); border-bottom: 1px solid var(--vp-c-text-3); transform: rotate(-45deg); }
.plate-footer a { color: var(--vp-c-text-1); font-size: 13px; font-weight: 680; text-decoration: none; border-bottom: 2px solid var(--vp-c-brand-1); padding-bottom: 5px; }.plate-footer a b { margin-left: 9px; color: var(--vp-c-brand-1); }
@media (max-width: 1152px) { .system-plate { margin: 0 24px; } }
@media (max-width: 768px) { .plate-heading { grid-template-columns: 1fr; gap: 18px; }.stack-row { grid-template-columns: 38px 1fr auto; gap: 10px; padding: 15px 0; }.stack-name { font-size: 15px; }.stack-en { text-align: right; }.stack-detail { grid-column: 2 / -1; }.stack-mark { display: none; } }
@media (max-width: 639px) { .system-plate { margin: 0 16px; padding: 50px 0 58px; }.plate-heading h2 { font-size: 30px; }.plate-footer { align-items: flex-start; flex-direction: column; gap: 28px; } }
</style>
