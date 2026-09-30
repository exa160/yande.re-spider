/**
 * useDownloadState —— 图片下载状态单例（image_id → 下载态）
 *
 * ## 为什么需要它
 *
 * 后端 `yande_data.down_flag` **只在下载完成时落库**
 * （`download_queue._update_image_database`），队列中的状态存在
 * `download_task.status` 里。因此前端有三个「点了没反应」的场景：
 *
 * 1. 单图下载：POST /download/task 成功后前端自己写 `down_flag = true`
 *    （乐观写），但这是**假的**——任务可能排队中甚至失败，瀑布流也会跟着
 *    错标成「已下载」；
 * 2. 批量下载：只创建任务，完全不改任何标识；
 * 3. 收藏自动下载：由后端 `MyFavoritesService.add` 触发，前端毫无感知。
 *
 * 本 composable 把这三处的「下载中」显式建模：
 *
 *   - 触发侧 `markQueued()`：本地立刻打上 `queued`，UI 无等待反馈；
 *   - 对账侧 `sync()`：轮询 `GET /download/tasks/states`，用后端队列状态
 *     覆盖本地值，把 `queued → downloading → downloaded` 串起来，
 *     失败/取消则复位成未下载。
 *
 * 收藏自动下载这类**前端未参与触发**的场景由对账侧兜住：后端任务一进队列
 * 就会被下一次轮询看到。
 *
 * ## 状态取值
 *
 * | 值            | 含义                                   | UI                    |
 * |---------------|----------------------------------------|-----------------------|
 * | `queued`      | 本地乐观标记（刚点了下载）             | 下载中（转圈）        |
 * | `pending`     | 后端队列等待中                         | 下载中（转圈）        |
 * | `downloading` | 后端下载中                             | 下载中（转圈）        |
 * | `paused`      | 后端任务已暂停                         | 已暂停（灰点）        |
 * | `downloaded`  | 下载完成（DB down_flag 也已为 true）   | 已下载（绿点/tag）    |
 * | `failed`      | 下载失败/取消，已复位为未下载          | 未下载（回到下载按钮）|
 *
 * ## 轮询节奏
 *
 * - 有进行中任务（含本地 queued）：2s
 * - 空闲：5s（只为发现「收藏自动下载」这类外部触发的任务）
 * - `document.hidden` 时不请求，页面重新可见立即补一次
 *
 * 采用模块级单例（与 `useFavoritesConfig` 一致）：Gallery 详情页与
 * WaterfallGallery 瀑布流共享同一份状态，任意一处触发、处处可见。
 */
import { reactive, readonly } from 'vue'
import api from '@/api'

/** 进行中（UI 显示「下载中」）的状态集合 */
const ACTIVE_STATES = new Set(['queued', 'pending', 'downloading'])
/** 需要跟随后端队列存活的状态（paused 也算，否则任务被删后会永久停在「已暂停」） */
const TRACKED_STATES = new Set([...ACTIVE_STATES, 'paused'])

/** image_id → 状态字符串。响应式对象，直接给模板用。 */
const states = reactive({})

let pollTimer = null
let polling = false
let refCount = 0
let started = false

const ACTIVE_INTERVAL = 2000
const IDLE_INTERVAL = 5000
// 终态回看窗口（秒）：要大于「两次轮询的间隔 + 页面可能的最长隐藏时间」，
// 否则任务刚结束就滑出窗口，前端会错过 completed 事件
const FINISHED_WINDOW = 300
// 兜底回收阈值（ms）：本地记着「下载中」但后端连续这么久没再上报，就认为任务
// 已经不在队列里，解除标记，避免「下载中」永久卡死
const STALE_MS = 120000

/** image_id → 最近一次「本地标记 / 后端确认在队列中」的时间戳 */
const lastSeenAt = {}

/** 下载完成订阅者（供收藏夹角标增量修正等旁路消费） */
const completedListeners = new Set()

/**
 * 订阅「本轮轮询中新变为已下载」的 image_id 列表。
 *
 * 只在**状态跃迁**时触发一次（queued/pending/downloading → downloaded）：
 * 终态回看窗口内后端会反复回放同一条 completed 记录，重复通知会导致
 * 调用方把收藏夹角标累加多次。
 *
 * @param {(ids: number[]) => void} fn
 * @returns {() => void} 取消订阅
 */
const onCompleted = (fn) => {
  completedListeners.add(fn)
  return () => completedListeners.delete(fn)
}

/** 是否处于「下载中」态（含本地乐观标记） */
const isActive = (imageId) => ACTIVE_STATES.has(states[imageId])

/** 是否已下载（本次会话内下载完成；持久态仍以 image.down_flag 为准） */
const isDownloaded = (imageId) => states[imageId] === 'downloaded'

/**
 * 图片的最终下载态：'downloading' | 'paused' | 'downloaded' | 'none'
 *
 * `downloaded` 需同时看 image.down_flag（DB 权威值，刷新后仍在）与本地
 * 状态（本次会话刚下载完、DB 快照还是 false）。
 *
 * @param {{id: number, down_flag?: boolean}} image
 * @returns {'downloading' | 'paused' | 'downloaded' | 'none'}
 */
const downStateOf = (image) => {
  if (!image) return 'none'
  const local = states[image.id]
  if (ACTIVE_STATES.has(local)) return 'downloading'
  if (local === 'paused') return 'paused'
  if (local === 'downloaded' || image.down_flag) return 'downloaded'
  return 'none'
}

/**
 * 本地乐观标记：任务已提交，UI 立刻转「下载中」，不等网络往返。
 *
 * 无条件覆盖既有状态（含 downloaded）——重新下载一张已下载的图片同样会
 * 走到这里，此时新任务确实在队列里，「下载中」才是正确展示。
 *
 * @param {number|number[]} imageIds
 */
const markQueued = (imageIds) => {
  const ids = Array.isArray(imageIds) ? imageIds : [imageIds]
  ids.forEach((id) => {
    if (id === null || id === undefined) return
    states[id] = 'queued'
    lastSeenAt[id] = Date.now()
  })
  scheduleNext()
}

/**
 * 清除本地状态，回到「未下载」。
 * @param {number|number[]} imageIds
 */
const reset = (imageIds) => {
  const ids = Array.isArray(imageIds) ? imageIds : [imageIds]
  ids.forEach((id) => {
    delete states[id]
    delete lastSeenAt[id]
  })
  scheduleNext()
}

/** 是否存在「进行中」状态（用于选择轮询节奏） */
const hasActiveStates = () => Object.values(states).some((s) => ACTIVE_STATES.has(s))

/**
 * 与后端队列对账。返回是否成功（失败时静默重试，不打断 UI）。
 * @returns {Promise<boolean>}
 */
const sync = async () => {
  if (polling) return false
  polling = true
  try {
    const resp = await api.get('/download/tasks/states', {
      params: { finished_window: FINISHED_WINDOW },
    })
    const payload = resp?.data?.data ?? resp?.data ?? resp ?? {}
    const active = Array.isArray(payload.active) ? payload.active : []
    const finished = Array.isArray(payload.finished) ? payload.finished : []
    const now = Date.now()

    // 1) 进行中任务：后端为准（覆盖本地乐观标记 queued），并刷新活跃时间戳
    const serverActive = new Set()
    active.forEach((item) => {
      if (item?.image_id === undefined) return
      serverActive.add(item.image_id)
      states[item.image_id] = item.status || 'pending'
      lastSeenAt[item.image_id] = now
    })

    // 2) 终态任务：completed → 已下载；failed / cancelled → 复位
    //    只把「本轮新变为 completed」的 id 收集起来通知订阅者（角标增量修正），
    //    窗口内重复回放的同一条记录不会二次通知。
    const newlyCompleted = []
    finished.forEach((item) => {
      if (item?.image_id === undefined) return
      if (item.status === 'completed') {
        if (states[item.image_id] !== 'downloaded') newlyCompleted.push(item.image_id)
        states[item.image_id] = 'downloaded'
      } else {
        delete states[item.image_id]
      }
      delete lastSeenAt[item.image_id]
    })

    // 3) 兜底回收：本地记着「下载中 / 已暂停」，但后端连续 STALE_MS 秒都没再上报它
    //    （例如页面长时间隐藏期间任务已结束，终态滑出了回看窗口；
    //      或该任务在下载页被直接删除）。不回收会让标识永久卡住。
    Object.keys(states).forEach((key) => {
      const id = Number(key)
      if (!TRACKED_STATES.has(states[key]) || serverActive.has(id)) return
      if (now - (lastSeenAt[id] ?? 0) > STALE_MS) {
        delete states[key]
        delete lastSeenAt[key]
      }
    })

    // 4) 通知订阅者（订阅者抛错不影响轮询本身）
    if (newlyCompleted.length && completedListeners.size) {
      const ids = [...newlyCompleted]
      completedListeners.forEach((fn) => {
        try {
          fn(ids)
        } catch (e) {
          if (typeof console !== 'undefined') {
            console.warn('[useDownloadState] onCompleted handler failed:', e?.message || e)
          }
        }
      })
    }

    scheduleNext()
    return true
  } catch (e) {
    // 网络抖动 / 后端未就绪：保持现状，下一轮重试
    return false
  } finally {
    polling = false
  }
}

/** 按当前活跃度重排轮询定时器（活跃 2s / 空闲 5s） */
const scheduleNext = () => {
  if (!started) return
  if (pollTimer !== null) clearTimeout(pollTimer)
  const delay = hasActiveStates() ? ACTIVE_INTERVAL : IDLE_INTERVAL
  pollTimer = setTimeout(runOnce, delay)
}

const runOnce = async () => {
  if (typeof document !== 'undefined' && document.hidden) {
    // 页面不可见时不请求，等下次定时器（用户切回时会立即补一次 sync）
    scheduleNext()
    return
  }
  await sync()
}

/** 启动轮询（引用计数，多组件共享单例定时器） */
const start = () => {
  refCount += 1
  if (started) return
  started = true
  sync() // 立即对账一次：刷新页面时正在下载的图片立刻能显示「下载中」
  scheduleNext()
}

/** 停止轮询（引用计数归零才真正清理定时器） */
const stop = () => {
  refCount = Math.max(0, refCount - 1)
  if (refCount > 0 || !started) return
  started = false
  if (pollTimer !== null) {
    clearTimeout(pollTimer)
    pollTimer = null
  }
}

/** 仅供测试：清空本地状态与定时器 */
const _resetForTest = () => {
  if (pollTimer !== null) clearTimeout(pollTimer)
  pollTimer = null
  refCount = 0
  started = false
  polling = false
  Object.keys(states).forEach((k) => delete states[k])
  Object.keys(lastSeenAt).forEach((k) => delete lastSeenAt[k])
  completedListeners.clear()
}

export const useDownloadState = () => ({
  states: readonly(states),
  downStateOf,
  isActive,
  isDownloaded,
  markQueued,
  reset,
  sync,
  start,
  stop,
  hasActiveStates,
  onCompleted,
  _resetForTest,
})

export default useDownloadState
