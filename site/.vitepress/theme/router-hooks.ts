import { useRouter } from 'vitepress'

// VitePress 的 router.onBeforeRouteChange / onAfterRouteChange 是单值属性而非
// 事件订阅：任意组件再赋值就会覆盖前一个。这里统一包一层订阅器：每个钩子只安装
// 一个 dispatcher，之后所有订阅者共享。新增路由切换逻辑一律走这里，别直接赋值。
type RouteHandler = (href: string) => void
type HookName = 'onBeforeRouteChange' | 'onAfterRouteChange'

const subscribers: Record<HookName, Set<RouteHandler>> = {
  onBeforeRouteChange: new Set(),
  onAfterRouteChange: new Set()
}
const installed: Record<HookName, boolean> = {
  onBeforeRouteChange: false,
  onAfterRouteChange: false
}

export function subscribeBeforeRouteChange(fn: RouteHandler): void {
  subscribe('onBeforeRouteChange', fn)
}

export function subscribeAfterRouteChange(fn: RouteHandler): void {
  subscribe('onAfterRouteChange', fn)
}

function subscribe(hook: HookName, fn: RouteHandler): void {
  subscribers[hook].add(fn)
  if (installed[hook]) return
  // useRouter 只能在 setup 上下文中调用，各订阅组件的 setup 均满足
  const router = useRouter()
  if (hook === 'onBeforeRouteChange') {
    router.onBeforeRouteChange = (href) => dispatch(hook, href)
  } else {
    router.onAfterRouteChange = (href) => dispatch(hook, href)
  }
  installed[hook] = true
}

function dispatch(hook: HookName, href: string): void {
  for (const fn of subscribers[hook]) {
    try {
      fn(href)
    } catch (e) {
      // 单个订阅者抛错不能连累其它订阅者
      console.error(`[router-hook] ${hook} 订阅者抛错`, e)
    }
  }
}
