<script setup lang="ts">
import { ref, onMounted, onBeforeUnmount } from 'vue'
import { subscribeAfterRouteChange } from '../router-hooks'

// 顶部阅读进度条：滚动时按 scrollTop / (scrollHeight - clientHeight) 算百分比，
// 单色 brand 细线，固定在视口顶部。路由切换 rAF+300ms 双重重算（图片等异步
// 内容撑高后短页会归零失败，需补算一次）。scroll/resize 用 rAF 合并，一帧最多算一次。
const progress = ref(0)
let raf: number | null = null

function update() {
  raf = null
  const el = document.documentElement
  const scrollTop = el.scrollTop || document.body.scrollTop
  const scrollHeight = el.scrollHeight - el.clientHeight
  progress.value = scrollHeight > 0 ? Math.min(100, (scrollTop / scrollHeight) * 100) : 0
}

function scheduleUpdate() {
  if (raf !== null) return
  raf = requestAnimationFrame(update)
}

onMounted(() => {
  update()
  window.addEventListener('scroll', scheduleUpdate, { passive: true })
  window.addEventListener('resize', scheduleUpdate, { passive: true })
})

subscribeAfterRouteChange(() => {
  // 路由切换：新页 DOM 立即可测 + 300ms 后（图片等内容撑高）再补一次
  requestAnimationFrame(update)
  setTimeout(update, 300)
})

onBeforeUnmount(() => {
  if (raf !== null) cancelAnimationFrame(raf)
  window.removeEventListener('scroll', scheduleUpdate)
  window.removeEventListener('resize', scheduleUpdate)
})
</script>

<template>
  <div class="reading-progress" aria-hidden="true">
    <div class="reading-progress__bar" :style="{ width: progress + '%' }" />
  </div>
</template>

<style scoped>
.reading-progress {
  position: fixed;
  top: 0;
  left: 0;
  right: 0;
  height: 3px;
  z-index: 100;
  pointer-events: none;
  background: transparent;
}

.reading-progress__bar {
  height: 100%;
  background: var(--vp-c-brand-1);
  transition: width 0.12s ease-out;
}

@media print {
  .reading-progress { display: none; }
}
</style>
