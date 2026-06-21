import type MarkdownIt from 'markdown-it'
import type { ProjectConfig } from '../config/schema'
import { cppTemplateEscapePlugin } from './escape-cpp-templates'
import { githubLinksPlugin } from './github-links'
import { kbdPlugin } from './kbd-plugin'
import { languageAliasPlugin } from './language-aliases'

export function resolvePlugins(md: MarkdownIt, config: ProjectConfig): void {
  md.use(languageAliasPlugin)
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
