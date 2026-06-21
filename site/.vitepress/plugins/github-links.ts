import type MarkdownIt from 'markdown-it'

/**
 * GitHub Links Rewriter
 *
 * rk-forge 的教程文档里大量使用相对链接指向 document/ srcDir **之外** 的仓库源文件:
 *   - 仓库根的补丁/脚本/板级文件:  ../../../patches/linux/0001-*.patch, ../../../scripts/forge.sh
 *   - 仓库根的说明:               ../../../BLOBS.md
 *   - 非页面的取证资源:            ../../logs/boot-sdl-*.txt
 *
 * VitePress 只把 document/ 下的 .md 渲染成页面,这些链接在站点上会 404。本插件把这类
 * "跳出 srcDir 或指向非页面资源" 的相对链接重写成 GitHub blob URL,让站点上点"看这个补丁
 * /日志"真能打开对应文件;同时保留源码里对本地读者友好的相对链接写法。
 *
 * 规则:
 *   - 仅处理相对链接(http/https/mailto/#/根绝对 跳过)。
 *   - 解析链接相对当前页(env.relativePath,srcDir 相对路径)的"仓库相对路径"。
 *   - 若链接"跳出 srcDir"(../ 在已到 srcDir 根时仍要上行)→ 重写为 blob/<仓库相对路径>。
 *   - 若落在 srcDir 内但是非页面资源(.txt/.patch/.sh/.its/.ini 等,非 .md/目录) →
 *     重写为 blob/document/<srcDir 相对路径>。
 *   - 否则(落在 srcDir 内的 .md 页面或目录链接)→ 保持站点内链接不动。
 */

export interface GithubLinksOptions {
  owner: string
  repo: string
  branch: string
}

interface Resolved {
  /** 解析后的路径(可能 srcDir 相对,也可能因逃逸而成为仓库根相对) */
  path: string
  /** 是否在解析过程中试图越过 srcDir 根(即链接指向 srcDir 之外) */
  escaped: boolean
}

/** VitePress 会把 srcDir 相对路径(如 "tutorial/boot/00_roadmap.md")放进 env.relativePath */
function resolve(relativePath: string | undefined, href: string): Resolved {
  const base = relativePath && relativePath.includes('/')
    ? relativePath.slice(0, relativePath.lastIndexOf('/'))
    : ''
  const stack = base ? base.split('/') : []
  let escaped = false

  for (const seg of href.split('/')) {
    if (seg === '' || seg === '.') continue
    if (seg === '..') {
      if (stack.length) stack.pop()
      else escaped = true // 已到 srcDir 根仍要上行 → 指向仓库根
      continue
    }
    stack.push(seg)
  }

  return { path: stack.join('/').replace(/[?#].*$/, ''), escaped }
}

// VitePress 会渲染成页面的扩展名(其余一律视为资源,需外链到 GitHub)
function isPageExtension(path: string): boolean {
  const ext = (path.match(/\.([^.\\/]+)$/)?.[1] || '').toLowerCase()
  return ext === '' || ext === 'md' // 目录链接 或 .md
}

export function githubLinksPlugin(md: MarkdownIt, opts: GithubLinksOptions): void {
  const blobBase = `https://github.com/${opts.owner}/${opts.repo}/blob/${opts.branch}/`

  md.core.ruler.push('github-links', (state) => {
    const relativePath = (state.env as { relativePath?: string } | undefined)?.relativePath

    const walk = (tokens: MarkdownIt.Token[]) => {
      for (const tok of tokens) {
        if (tok.type === 'inline' && tok.children) {
          walk(tok.children)
          continue
        }
        if (tok.type !== 'link_open' || !tok.attrs) continue

        const idx = tok.attrs.findIndex((a) => a[0] === 'href')
        if (idx < 0) continue
        const href = tok.attrs[idx][1]

        // 跳过绝对链接、锚点、根绝对路径(以 / 开头)
        if (/^(?:[a-z][a-z0-9+.-]*:|mailto:|#|\/)/i.test(href)) continue

        const { path, escaped } = resolve(relativePath, href)

        if (escaped) {
          // 指向 srcDir 之外 → 仓库根相对路径
          tok.attrs[idx][1] = blobBase + path
        } else if (!isPageExtension(path)) {
          // 落在 srcDir 内但是非页面资源(.txt 日志等) → document/<路径>
          tok.attrs[idx][1] = blobBase + 'document/' + path
        }
        // 否则:srcDir 内的 .md/目录 → 保持站点内链接
      }
    }

    walk(state.tokens)
    return true
  })
}
