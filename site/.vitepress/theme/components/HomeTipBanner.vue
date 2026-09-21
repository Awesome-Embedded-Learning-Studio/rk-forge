<script setup lang="ts">
import { computed } from 'vue'
import { useData } from 'vitepress'
import type { ProjectConfig } from '../config/schema'

const { lang } = useData()
const props = defineProps<{ config?: ProjectConfig }>()
const bannerText = computed(() => {
  const cfg = props.config
  if (!cfg?.homeBanner) return ''
  return cfg.homeBanner[lang.value] || cfg.homeBanner[Object.keys(cfg.homeBanner)[0]] || ''
})
</script>

<template>
  <aside v-if="bannerText" class="field-note">
    <span class="field-note__index">READ / 01</span>
    <span class="field-note__text" v-html="bannerText" />
    <span class="field-note__arrow" aria-hidden="true">↗</span>
  </aside>
</template>

<style scoped>
.field-note { display: grid; grid-template-columns: 104px 1fr auto; align-items: center; gap: 20px; max-width: 1104px; margin: 0 auto 54px; padding: 20px 0; color: var(--vp-c-text-1); border-top: 1px solid var(--vp-c-text-1); border-bottom: 1px solid var(--vp-c-text-1); }
.field-note__index { color: var(--vp-c-brand-1); font-family: var(--vp-font-family-mono); font-size: 10px; font-weight: 800; letter-spacing: .12em; }.field-note__text { font-size: 14px; line-height: 1.7; }.field-note__text :deep(a) { color: inherit; font-weight: 700; text-decoration: underline; text-decoration-color: var(--vp-c-brand-1); text-decoration-thickness: 2px; text-underline-offset: 4px; }.field-note__arrow { color: var(--vp-c-brand-1); font-size: 22px; }
@media (max-width: 1152px) { .field-note { margin-right: 24px; margin-left: 24px; } }
@media (max-width: 639px) { .field-note { grid-template-columns: 1fr auto; gap: 8px 16px; margin: 0 16px 38px; }.field-note__index { grid-column: 1 / -1; }.field-note__text { font-size: 13px; } }
</style>
