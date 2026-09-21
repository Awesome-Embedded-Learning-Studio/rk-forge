import type { DefaultTheme } from 'vitepress'
import { readdirSync, statSync, readFileSync, existsSync } from 'fs'
import { join } from 'path'
import type { ProjectConfig, VolumeConfig } from './schema'

type SidebarItem = DefaultTheme.SidebarItem

function extractTitle(filePath: string): string | null {
  try {
    const content = readFileSync(filePath, 'utf-8')
    const fmMatch = content.match(/^---[\s\S]*?^title:\s*['"]?(.+?)['"]?\s*$/m)
    if (fmMatch) return fmMatch[1]
    const h1 = content.match(/^#\s+(.+)$/m)
    if (h1) {
      return h1[1]
        .replace(/\{.*?\}/g, '')
        // rk-forge 章节用 "ChN — 标题" 格式,侧边栏里去掉前缀更干净
        .replace(/^Ch\d+\s*[—\-:：]\s*/i, '')
        .trim()
    }
  } catch { /* ignore */ }
  return null
}

function humanize(name: string): string {
  return name
    .replace(/^\d+[-]?/, '')
    .replace(/[-_]/g, ' ')
    .replace(/\b\w/g, c => c.toUpperCase())
}

// 阅读顺序（rk-forge 的 bring-up 弧线）：引导启动 → 根文件系统 → 外设 → SD 卡启动 → forge 编排器
// 仅对"无数字前缀的目录"生效（如 document/tutorial/ 下的子卷）；
// 目录内部、章节文件一律按文件名数字前缀(00_/01_/02_...)排序——例如 boot 卷里 02_uboot 在 03_kernel 之前。
const LEARNING_ORDER = [
  'boot',
  'rootfs',
  'peripherals',
  'sd-boot',
  'forge',
]

function sortEntries(a: string, b: string): number {
  const na = a.match(/^(\d+)/)?.[1]
  const nb = b.match(/^(\d+)/)?.[1]
  if (na && nb) return parseInt(na) - parseInt(nb)
  if (na) return -1
  if (nb) return 1

  // 对于没有数字前缀的目录，按学习顺序排序
  const ia = LEARNING_ORDER.indexOf(a)
  const ib = LEARNING_ORDER.indexOf(b)
  if (ia !== -1 && ib !== -1) return ia - ib
  if (ia !== -1) return -1
  if (ib !== -1) return 1

  return a.localeCompare(b, 'en')
}

function scanDir(dir: string, urlPrefix: string, depth = 0): SidebarItem[] {
  if (depth > 5) return []

  let entries: string[]
  try {
    entries = readdirSync(dir).filter(e =>
      !e.startsWith('.') &&
      e !== 'hooks' &&
      e !== 'stylesheets' &&
      e !== 'javascripts' &&
      e !== 'images' &&
      e !== 'logo'
    )
  } catch { return [] }

  entries.sort(sortEntries)
  const items: SidebarItem[] = []

  for (const name of entries) {
    const fullPath = join(dir, name)
    if (!statSync(fullPath).isDirectory() && !name.endsWith('.md')) continue

    if (statSync(fullPath).isDirectory()) {
      const subItems = scanDir(fullPath, `${urlPrefix}/${name}`, depth + 1)
      const indexPath = join(fullPath, 'index.md')
      const title = extractTitle(indexPath) || humanize(name)

      if (subItems.length > 0) {
        items.push({
          text: title,
          link: existsSync(indexPath) ? `${urlPrefix}/${name}/` : undefined,
          items: subItems,
          // 默认收起;含当前页的组由 VitePress 自动展开,防止多卷全展开的长蛇侧栏
          collapsed: true,
        })
      } else if (existsSync(indexPath)) {
        items.push({ text: title, link: `${urlPrefix}/${name}/` })
      }
    } else if (name !== 'index.md' && name !== 'tags.md' && name !== 'README.md') {
      const title = extractTitle(fullPath) || humanize(name.replace(/\.md$/, ''))
      items.push({ text: title, link: `${urlPrefix}/${name.replace(/\.md$/, '')}` })
    }
  }

  return items
}

export function volumeSidebar(
  docsRoot: string,
  vol: VolumeConfig
): DefaultTheme.SidebarItem[] {
  const dir = join(docsRoot, vol.srcDir)
  const indexPath = join(dir, 'index.md')
  let items = scanDir(dir, vol.urlPrefix)

  // 平铺文件过多的卷(如 notes 121 篇日更笔记)按文件名数字前缀分段收组:
  // 组间按序、组内原序,prev/next 扁平序不变;当前页所在段自动展开,
  // 其余段收起 —— 任何页面侧栏最多露出一段。
  if (vol.chunkFlatFiles) {
    const dirs = items.filter(i => i.items)
    const files = items.filter(i => !i.items && i.link)
    if (files.length >= vol.chunkFlatFiles) {
      const num = (it: SidebarItem) =>
        parseInt(it.link!.split('/').pop()!.match(/^(\d+)/)?.[1] ?? '', 10)
      const pad = (n: number) => String(n).padStart(3, '0')
      const chunks: SidebarItem[] = []
      const unnumbered: SidebarItem[] = []
      let cur: SidebarItem[] = []
      let start = NaN
      const flush = () => {
        if (!cur.length) return
        chunks.push({
          text: vol.chunkLabel
            ? `${vol.chunkLabel} ${pad(start)}–${pad(num(cur[cur.length - 1]))}`
            : `${pad(start)}–${pad(num(cur[cur.length - 1]))}`,
          items: cur,
          collapsed: true,
        })
        cur = []
        start = NaN
      }
      for (const f of files) {
        const n = num(f)
        if (isNaN(n)) { unnumbered.push(f); continue }
        if (isNaN(start)) start = n
        cur.push(f)
        if (cur.length >= vol.chunkFlatFiles) flush()
      }
      flush()
      if (unnumbered.length) {
        chunks.push({ text: vol.chunkLabel ? `${vol.chunkLabel}·其他` : '其他', items: unnumbered, collapsed: true })
      }
      items = [...dirs, ...chunks]
    }
  }

  const overviewTitle = extractTitle(indexPath) || humanize(vol.srcDir)
  return [
    { text: overviewTitle, link: `${vol.urlPrefix}/` },
    ...items,
  ]
}

export function buildSidebar(
  docsRoot: string,
  config: ProjectConfig
): DefaultTheme.Sidebar {
  const sidebar: DefaultTheme.Sidebar = {}

  for (const vol of config.sidebar.volumes) {
    sidebar[`${vol.urlPrefix}/`] = volumeSidebar(docsRoot, vol)
  }

  if (config.sidebar.extra) {
    Object.assign(sidebar, config.sidebar.extra)
  }

  // Build sidebar for non-default locales
  for (const locale of config.locales) {
    if (locale.default || !locale.dir) continue
    const localeDir = join(docsRoot, locale.dir)
    if (!existsSync(localeDir)) continue

    const localeItems = scanDir(localeDir, locale.prefix || `/${locale.dir}`)
    if (localeItems.length > 0) {
      const prefix = locale.prefix || `/${locale.dir}/`
      sidebar[prefix] = [{ text: locale.label, items: localeItems }]
    }
  }

  return sidebar
}
