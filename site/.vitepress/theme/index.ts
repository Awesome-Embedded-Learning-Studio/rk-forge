import DefaultTheme from 'vitepress/theme'
import { h } from 'vue'
import type { Theme } from 'vitepress'
import HomeTipBanner from './components/HomeTipBanner.vue'
import HomeArchDiagram from './components/HomeArchDiagram.vue'
import ChapterNav from './components/ChapterNav.vue'
import ChapterLink from './components/ChapterLink.vue'
import PageHeader from './components/PageHeader.vue'
import StatusTag from './components/StatusTag.vue'
import StepFlow from './components/StepFlow.vue'
import StepItem from './components/StepItem.vue'
import InfoCard from './components/InfoCard.vue'
import RoadMap from './components/RoadMap.vue'
import RoadMapPhase from './components/RoadMapPhase.vue'
import NavSpinner from './components/NavSpinner.vue'
import ReadingProgress from './components/ReadingProgress.vue'
import ResizableSidebar from './components/ResizableSidebar.vue'
import FontSizeSwitcher from './components/FontSizeSwitcher.vue'
import HomeHeroVisual from './components/HomeHeroVisual.vue'
import projectConfig from '../../../project.config.ts'
// 导入顺序即层叠顺序:article-code/article-quote 需要覆盖 custom.css 里的基础规则
import './custom.css'
import './interactive.css'
import './article-code.css'
import './article-quote.css'

export default {
  extends: DefaultTheme,
  Layout() {
    return h(DefaultTheme.Layout, null, {
      'layout-top': () => [h(NavSpinner), h(ReadingProgress), h(ResizableSidebar)],
      'nav-bar-content-after': () => h(FontSizeSwitcher),
      'nav-screen-content-after': () => h(FontSizeSwitcher),
      'home-hero-image': () => h(HomeHeroVisual),
      'home-features-before': () => h(HomeTipBanner, { config: projectConfig }),
      'home-features-after': () => h(HomeArchDiagram)
    })
  },
  enhanceApp({ app }) {
    app.component('ChapterNav', ChapterNav)
    app.component('ChapterLink', ChapterLink)
    app.component('PageHeader', PageHeader)
    app.component('StatusTag', StatusTag)
    app.component('StepFlow', StepFlow)
    app.component('StepItem', StepItem)
    app.component('InfoCard', InfoCard)
    app.component('RoadMap', RoadMap)
    app.component('RoadMapPhase', RoadMapPhase)
  }
} satisfies Theme
