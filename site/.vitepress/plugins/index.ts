import type MarkdownIt from 'markdown-it'
import type { ProjectConfig } from '../config/schema'
import { cppTemplateEscapePlugin } from './escape-cpp-templates'
import { githubLinksPlugin } from './github-links'
import { kbdPlugin } from './kbd-plugin'
import { languageAliasPlugin } from './language-aliases'
import { codeFoldPlugin } from './code-fold-plugin'
import { codeLabelPlugin } from './code-label-plugin'

export function resolvePlugins(md: MarkdownIt, config: ProjectConfig): void {
  // codeLabel 必须先于 languageAlias:它的 core ruler 要在语言被改写(dts→c 等)之前
  // 读到作者原始围栏标签,否则设备树/Kconfig 角标无从谈起。
  md.use(codeLabelPlugin)
  md.use(languageAliasPlugin)
  // fence 覆写后 use 的在外层:codeFold 要把已换好角标的整段 HTML 包进 details。
  md.use(codeFoldPlugin)
  // 把指向 document/ srcDir 之外的仓库源文件/非页面资源的相对链接重写成 GitHub blob URL,
  // 让站点上点"看补丁/日志"能打开 GitHub(否则 404)。详见 github-links.ts。
  md.use(githubLinksPlugin, {
    owner: config.github.owner,
    repo: config.github.repo,
    branch: config.github.branch,
  })
  if (config.plugins.cppTemplateEscape) {
    cppTemplateEscapePlugin(md)
  }
  if (config.plugins.kbd) {
    md.use(kbdPlugin)
  }
}
