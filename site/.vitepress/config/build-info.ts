import { execFileSync } from 'node:child_process'
import { fileURLToPath } from 'node:url'
import projectConfig from '../../../project.config'

// config/ → .vitepress → site → 仓库根
const REPO_ROOT = fileURLToPath(new URL('../../../', import.meta.url))

function git(args: string[]): string {
  try {
    return execFileSync('git', args, {
      encoding: 'utf8',
      // vitepress 可能从任意 cwd 启动,锚定仓库根才能拿到 git 信号
      cwd: REPO_ROOT,
      stdio: ['ignore', 'pipe', 'ignore'],
    }).trim()
  } catch {
    return '' // git 不可用 / 源码包无 .git → 由调用方回退
  }
}

function composeVersion(described: string, sha: string): string {
  if (!described) return sha ? `dev-${sha}` : 'dev'
  const dirty = described.endsWith('-dirty')
  let base = dirty ? described.replace(/-dirty$/, '') : described
  if (/^[0-9a-f]{7,40}$/.test(base)) {
    // 无 tag 时 --always 退化为裸 SHA,补 dev- 前缀区分非发布构建
    base = `dev-${base}`
  } else if (sha && !base.endsWith(`-g${sha}`)) {
    // 恰好落在 tag 上时 describe 不含 SHA,补上以便定位到具体提交
    base = `${base}-${sha}`
  }
  return dirty ? `${base}-dirty` : base
}

export interface BuildInfo {
  /** 形如 v1.2.3-abc1234 / v1.2.3-3-gabc1234(-dirty);无 tag 为 dev-<sha>;git 不可用为 dev */
  version: string
  /** 7 位短 SHA;git 不可用时为空串 */
  sha: string
}

// config 在构建时求值一次,缓存避免同一进程内重复 exec git
let cached: BuildInfo | null = null

export function getBuildInfo(): BuildInfo {
  if (cached) return cached
  const sha = git(['rev-parse', '--short=7', 'HEAD'])
  const described = git(['describe', '--tags', '--always', '--dirty'])
  cached = { version: composeVersion(described, sha), sha }
  return cached
}

export function getFooterMessage(): string {
  return `由 ${projectConfig.name} ${getBuildInfo().version} 构建`
}
