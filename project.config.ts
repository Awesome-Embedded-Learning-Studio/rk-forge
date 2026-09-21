import { defineProject } from './site/.vitepress/config/schema'

export default defineProject({
  name: 'rk-forge',
  title: { 'zh-CN': 'RK-Forge 的教程文档' },
  description: { 'zh-CN': 'RK-Forge，面向 Rockchip RK3506B / RK3568 / RK3588 的主线优先嵌入式 Linux 教程文档网站' },
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
      { text: '教学路线', link: '/planning/' },
      { text: '教程', link: '/tutorial/' },
      { text: '踩坑日记', link: '/pitfalls/' },
      { text: '工程笔记', link: '/notes/' },
      { text: '差距对照', link: '/sdk-diff' },
      {
        text: '项目',
        items: [
          { text: '蓝图与定位', link: '/blueprint' },
          { text: '架构与构建', link: '/architecture' },
        ],
      },
      { text: 'GitHub', link: 'https://github.com/Awesome-Embedded-Learning-Studio/rk-forge' },
    ],
  },

  sidebar: {
    volumes: [
      { name: 'planning', srcDir: 'planning', urlPrefix: '/planning' },
      { name: 'tutorial', srcDir: 'tutorial', urlPrefix: '/tutorial' },
      { name: 'pitfalls', srcDir: 'pitfalls', urlPrefix: '/pitfalls' },
      // 121 篇日更笔记平铺会撑爆侧栏:按编号每 20 篇收一段,当前段自动展开
      { name: 'notes', srcDir: 'notes', urlPrefix: '/notes', chunkFlatFiles: 20, chunkLabel: '笔记' },
    ],
    extra: {
      '/blueprint': [
        {
          text: '项目',
          items: [
            { text: '蓝图与定位', link: '/blueprint' },
            { text: '架构与构建', link: '/architecture' },
          ],
        },
      ],
      '/architecture': [
        {
          text: '项目',
          items: [
            { text: '蓝图与定位', link: '/blueprint' },
            { text: '架构与构建', link: '/architecture' },
          ],
        },
      ],
    },
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
    'zh-CN': '第一次来？从 <a href="/rk-forge/planning/">三板教学路线</a> 开始。它会告诉你 RK3506B、RK3568、RK3588 各自走到哪里，以及下一步该做什么。',
  },
})
