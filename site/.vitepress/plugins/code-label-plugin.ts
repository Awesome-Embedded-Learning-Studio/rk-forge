import type { PluginSimple } from 'markdown-it'
import type MarkdownIt from 'markdown-it'

/** 角标文案表:键是作者在围栏里写的语言,值是角标显示文案。表外语言不动。 */
const LABELS: Record<string, string> = {
  bash: '终端',
  sh: 'Shell',
  c: 'C',
  dts: '设备树',
  dtsi: '设备树',
  makefile: 'Makefile',
  kconfig: 'Kconfig',
  python: 'Python',
  // text 是"作者手写的文本块"(ASCII 拓扑图/转储/日志皆有),不是程序输出,
  // 标"输出"会误称;也不归一到 output 语法(绿卡是终端输出的视觉语言)。
  text: '文本',
  output: '输出',
}

/**
 * 语言角标中文化:把 VitePress preWrapper 输出的 <span class="lang"> 原文
 * (如 bash/dts)换成上表文案,不碰 copy/lang/pre 兄弟结构。
 *
 * 为什么在 core 期先记 token.meta.label:languageAliasPlugin 会在 core 期把
 * dts/dtsi 改写成 c、kconfig 改写成 ini,渲染期角标已分不清作者写的是哪种,
 * 必须在改写前按原始 info 取词。因此本插件必须在 languageAliasPlugin 之前 use。
 */
export const codeLabelPlugin: PluginSimple = (md: MarkdownIt) => {
  md.core.ruler.push('code_label_capture_lang', (state) => {
    for (const token of state.tokens) {
      if (token.type !== 'fence') continue
      // 本仓内容约定:无标签围栏 = 命令输出/UART 抓取。改写成 output 语法,
      // 走 article-code.css 的 language-output 扁平样式,避免空角标 pill。
      if (!token.info.trim()) token.info = 'output'
      const label = LABELS[token.info.trim().split(/\s+/)[0].toLowerCase()]
      if (label) {
        if (!token.meta) token.meta = {}
        token.meta.label = label
      }
    }
    return true
  })

  const fence = md.renderer.rules.fence
  if (!fence) return
  md.renderer.rules.fence = (...args) => {
    const [tokens, idx] = args
    const html = fence(...args)
    const label = tokens[idx].meta?.label
    if (!label) return html
    return html.replace(
      /(<span class="lang">)([^<]*)(<\/span>)/,
      (_, open, _lang, close) => open + label + close,
    )
  }
}
