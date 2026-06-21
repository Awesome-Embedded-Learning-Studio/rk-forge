import { defineProject } from './site/.vitepress/config/schema'

export default defineProject({
  name: 'rk-forge',
  title: { 'zh-CN': 'RK-Forge 的教程文档' },
  description: { 'zh-CN': 'RK-Forge，专注于 Rockchip RK3506 主线优先的嵌入式 Linux 教程文档网站' },
  base: '/rk-forge/',
  copyright: 'Copyright © 2026 Charliechen - 保留所有权利',

  documentsDir: 'document',
  siteDir: 'site',

  locales: [
    { code: 'zh-CN', label: '中文', default: true },
  ],

  nav: {
    'zh-CN': [
      { text: '首页', link: '/' },
      { text: '教程', link: '/tutorial/' },
      { text: '踩坑日记', link: '/pitfalls/' },
      { text: '工程笔记', link: '/notes/' },
      { text: '差距对照', link: '/sdk-diff' },
      { text: 'GitHub', link: 'https://github.com/Awesome-Embedded-Learning-Studio/rk-forge' },
    ],
  },

  sidebar: {
    volumes: [
      { name: 'tutorial', srcDir: 'tutorial', urlPrefix: '/tutorial' },
      { name: 'pitfalls', srcDir: 'pitfalls', urlPrefix: '/pitfalls' },
      { name: 'notes', srcDir: 'notes', urlPrefix: '/notes' },
    ],
  },

  github: {
    owner: 'Awesome-Embedded-Learning-Studio',
    repo: 'rk-forge',
    branch: 'main',
    documentsPath: 'document',
  },

  build: {
    concurrency: 4,
    rootPages: ['index.md'],
    rootAssets: [],
  },

  plugins: {
    cppTemplateEscape: true,
    kbd: true,
    math: false,
  },

  favicon: '/rk-forge/Awesome-Embedded.ico',

  homeBanner: {
    'zh-CN': '🚀 新手必读：不知道从哪里开始？请先查看 <a href="/rk-forge/tutorial/boot/">引导启动路线图</a>，了解 RK3506 主线启动的完整学习路径。',
  },
})
