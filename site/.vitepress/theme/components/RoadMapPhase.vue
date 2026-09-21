<script setup lang="ts">
import { computed } from 'vue'

const props = withDefaults(defineProps<{
  icon: string
  title: string
  subtitle?: string
  time: string
  difficulty: number
  num?: number
}>(), {
  num: undefined,
  subtitle: undefined
})

const maxDots = 5
const dots = computed(() =>
  Array.from({ length: maxDots }, (_, i) => i < props.difficulty)
)
</script>

<template>
  <div class="roadmap-phase">
    <div class="roadmap-phase-node">
      <span class="roadmap-phase-icon">{{ icon }}</span>
    </div>
    <div class="roadmap-phase-card">
      <div class="roadmap-phase-header">
        <div class="roadmap-phase-title-area">
          <span v-if="num" class="roadmap-phase-badge">Phase {{ num }}</span>
          <h3 class="roadmap-phase-title">{{ title }}</h3>
          <span v-if="subtitle" class="roadmap-phase-subtitle">{{ subtitle }}</span>
        </div>
        <div class="roadmap-phase-meta">
          <span class="roadmap-phase-time">{{ time }}</span>
          <span class="roadmap-phase-difficulty">
            <span
              v-for="(active, i) in dots"
              :key="i"
              class="difficulty-dot"
              :class="{ 'difficulty-dot--active': active }"
            />
          </span>
        </div>
      </div>
      <div class="roadmap-phase-chapters">
        <slot />
      </div>
    </div>
  </div>
</template>

<style scoped>
.roadmap-phase {
  position: relative;
  display: flex;
  gap: 16px;
  z-index: 1;
}

/* ── Timeline node ── */
.roadmap-phase-node {
  position: absolute;
  left: -32px;
  top: 22px;
  z-index: 2;
}

.roadmap-phase-icon {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 48px;
  height: 48px;
  border-radius: 8px;
  font-size: 19px;
  background: var(--vp-c-bg);
  border: 1px solid var(--vp-c-text-1);
  transition: border-color 0.18s ease;
}

.roadmap-phase:hover .roadmap-phase-icon {
  border-color: var(--vp-c-brand-1);
  transform: none;
}

/* ── Card ── */
.roadmap-phase-card {
  flex: 1;
  min-width: 0;
  padding: 20px 22px;
  border: 1px solid var(--vp-c-divider);
  border-radius: 8px;
  background-color: transparent;
  box-shadow: none;
  transition: border-color 0.18s ease, background-color 0.18s ease;
}

.roadmap-phase-card:hover {
  border-color: var(--vp-c-brand-1);
  background-color: var(--vp-c-bg-soft);
}

/* ── Header ── */
.roadmap-phase-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  flex-wrap: wrap;
}

.roadmap-phase-title-area {
  display: flex;
  align-items: baseline;
  gap: 8px;
  flex-wrap: wrap;
}

.roadmap-phase-badge {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  padding: 2px 10px;
  border-radius: 4px;
  border-bottom: 1px solid var(--vp-c-brand-1);
  background: transparent;
  color: var(--vp-c-brand-1);
  font-size: 11px;
  font-weight: 700;
  font-variant-numeric: tabular-nums;
  letter-spacing: 0.02em;
  white-space: nowrap;
}

.roadmap-phase-title {
  margin: 0;
  font-size: 16px;
  font-weight: 600;
  color: var(--vp-c-text-1);
  line-height: 1.4;
}

.roadmap-phase-subtitle {
  font-size: 12px;
  color: var(--vp-c-text-3);
  font-weight: 400;
}

.roadmap-phase-meta {
  display: flex;
  align-items: center;
  gap: 10px;
  flex-shrink: 0;
}

/* ── Time badge ── */
.roadmap-phase-time {
  font-size: 12px;
  font-weight: 600;
  color: var(--vp-c-brand-1);
  background: transparent;
  padding: 2px 10px;
  border-radius: 4px;
  white-space: nowrap;
}

/* ── Difficulty dots ── */
.roadmap-phase-difficulty {
  display: inline-flex;
  align-items: center;
  gap: 3px;
}

.difficulty-dot {
  width: 7px;
  height: 7px;
  border-radius: 50%;
  border: 1.5px solid var(--vp-c-divider);
  background: transparent;
  transition: background 0.35s ease, border-color 0.35s ease;
}

.difficulty-dot--active {
  background: var(--vp-c-brand-1);
  border-color: var(--vp-c-brand-1);
}

/* ── Chapter list slot ── */
.roadmap-phase-chapters {
  display: flex;
  flex-direction: column;
  gap: 6px;
  margin-top: 14px;
}

/* ── Dark mode ── */
.dark .roadmap-phase-icon {
  border-color: var(--vp-c-border);
  background: var(--vp-c-bg);
}

.dark .roadmap-phase:hover .roadmap-phase-icon {
  border-color: var(--vp-c-brand-1);
}

.dark .roadmap-phase-card {
  background-color: transparent;
  border-color: var(--vp-c-border);
  box-shadow: none;
}

.dark .roadmap-phase-card:hover {
  background-color: var(--vp-c-bg-soft);
  box-shadow: none;
}

/* ── Mobile ── */
@media (max-width: 639px) {
  .roadmap-phase {
    gap: 0;
  }

  .roadmap-phase-node {
    display: none;
  }

  .roadmap-phase-card {
    padding: 16px;
  }

  .roadmap-phase-title {
    font-size: 15px;
  }

  .roadmap-phase-header {
    gap: 8px;
  }

  .roadmap-phase-chapters {
    margin-top: 12px;
    gap: 4px;
  }
}
</style>
