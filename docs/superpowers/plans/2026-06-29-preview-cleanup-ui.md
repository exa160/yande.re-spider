# 预览图清理前端 UI 实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在 Config 页面加入"预览图清理"按钮，弹窗式交互完成 dry_run 评估 → 二次确认 → 实际删除。

**Architecture:** 单一新 SFC 组件 `PreviewCleanupDialog.vue` + 在 `Config.vue` 入口挂载 + `api/index.js` 新增方法。复用现有 Element Plus + axios 封装，无新依赖。

**Tech Stack:** Vue 3 (Composition API)、Element Plus (el-dialog/el-button/el-alert)、axios、SCSS。

**前置条件**：
- Spec: `docs/superpowers/specs/2026-06-29-preview-cleanup-ui-design.md` ✅ 已批准
- 后端 API `POST /api/v1/gallery/cache/preview/cleanup` ✅ 已实装并测试通过

---

## 文件结构

| 文件 | 改动 | 职责 |
|---|---|---|
| `frontend/src/api/index.js` | 修改（+8 行） | 新增 `cleanupPreviews()` 方法 |
| `frontend/src/components/PreviewCleanupDialog.vue` | 新建（~180 行） | 弹窗组件，含 3 状态机 |
| `frontend/src/views/Config.vue` | 修改（+15 行） | 高级功能 section 末尾加按钮 + 挂载 dialog |

**测试约定**：项目无 Vitest 配置，本 plan 不写单元测试。验证用：
- API client：`curl` 实际后端确认可调用
- Vue 组件：`npm run build` 必须 exit 0（vite/vite-plugin-vue 编译 SFC 失败立即报红）

---

## Task 1: API client `cleanupPreviews()`

**Files:**
- Modify: `frontend/src/api/index.js:50`

- [ ] **Step 1: 在 `frontend/src/api/index.js` 末尾新增 `cleanupPreviews` 方法**

编辑 `frontend/src/api/index.js`，将第 50 行的 `export default api` 改为：

```javascript
/**
 * 预览图清理
 * @param {'clean_local_previews' | 'clean_all_previews'} mode - 清理模式
 * @param {boolean} dryRun - true 仅评估不删除，false 真实清理
 * @returns {Promise<{code: string, message: string, data: CleanupResult}>}
 */
export async function cleanupPreviews(mode, dryRun) {
  return api({
    url: '/gallery/cache/preview/cleanup',
    method: 'post',
    data: { mode, dry_run: dryRun },
    timeout: 60000,  // 清理操作可能涉及较多文件 IO，延长超时
  })
}

export default api
```

- [ ] **Step 2: 验证语法**

Run:
```bash
cd /home/exa160/opencode/yande.re-spider-next-dev/frontend && node -e "
const m = require('./src/api/index.js');
console.log('loaded:', Object.keys(m));
" 2>&1 | head -20
```

Expected: 出现 `SyntaxError: Unexpected token` 时立即修复；正常打印 `loaded: [ 'cleanupPreviews', 'default' ]` 或类似（CommonJS 兼容性问题可忽略，关键是 **不报 syntax error**）。

- [ ] **Step 3: 启动前端 + curl 真实后端验证调用**

启动后端（如未运行）：

```bash
cd /home/exa160/opencode/yande.re-spider-next-dev/backend && \
  (uvicorn service:main_app --host 127.0.0.1 --port 8000 > /tmp/opencode/backend-verify.log 2>&1 &) && \
  sleep 4 && \
  curl -s -o /dev/null -w '%{http_code}\n' http://127.0.0.1:8000/api/v1/gallery/cache/preview/cleanup \
    -X POST -H 'Content-Type: application/json' \
    -d '{"mode":"clean_local_previews","dry_run":true}'
```

Expected: HTTP `200`，响应体形如：
```json
{"code":"0000","message":"OK.","data":{"matched":0,"deleted":0,"failed":0,"total_bytes":0,"duration_ms":3}}
```

验证完后停掉后端（用户可能本就在运行后端，按情况决定 kill 或保留）：

```bash
pkill -f "uvicorn service:main_app --host 127.0.0.1 --port 8000" || true
```

- [ ] **Step 4: Commit**

```bash
cd /home/exa160/opencode/yande.re-spider-next-dev && \
  git add frontend/src/api/index.js && \
  git commit -m "feat(frontend): add cleanupPreviews() API client

POST /api/v1/gallery/cache/preview/cleanup wrapper with 60s timeout.
Used by PreviewCleanupDialog for dry_run evaluation + actual cleanup."
```

---

## Task 2: 新建 `PreviewCleanupDialog.vue` 组件

**Files:**
- Create: `frontend/src/components/PreviewCleanupDialog.vue`

- [ ] **Step 1: 创建组件文件骨架**

创建文件 `frontend/src/components/PreviewCleanupDialog.vue`，内容：

```vue
<template>
  <el-dialog
    :model-value="modelValue"
    :title="dialogTitle"
    width="520px"
    :close-on-click-modal="false"
    :close-on-press-escape="currentState === 'idle' || currentState === 'done'"
    :show-close="canClose"
    @update:model-value="handleClose"
  >
    <!-- 状态 ① 初始 -->
    <div v-if="currentState === 'idle'" class="state-content">
      <p class="state-desc">
        删除 <code>downloads/previews/</code> 下的缩略图缓存。先点击按钮评估，再二次确认执行。
      </p>
      <el-alert type="warning" :closable="false" show-icon class="state-alert">
        本地清理会释放几百 MB ~ 几 GB；全量清理会丢失所有未下载原图的预览。
      </el-alert>
      <div class="button-row">
        <el-button
          type="primary"
          size="large"
          :loading="evaluating"
          class="action-btn"
          @click="handleEvaluate('clean_local_previews')"
        >
          <div class="btn-title">本地清理</div>
          <div class="btn-subtitle">仅清有原图可再生的</div>
        </el-button>
        <el-button
          type="warning"
          size="large"
          :loading="evaluating"
          class="action-btn"
          @click="handleEvaluate('clean_all_previews')"
        >
          <div class="btn-title">全量清理</div>
          <div class="btn-subtitle">清空整个 previews/</div>
        </el-button>
      </div>
    </div>

    <!-- 状态 ② 评估完成 / 清理中 -->
    <div v-else-if="currentState === 'evaluated' || currentState === 'cleaning'" class="state-content">
      <h4 class="state-h4">清理信息</h4>
      <div class="stat-grid">
        <div class="stat-card">
          <div class="stat-card-label">命中文件</div>
          <div class="stat-card-value">{{ formatNumber(evalResult?.matched) }}</div>
        </div>
        <div class="stat-card">
          <div class="stat-card-label">预计释放</div>
          <div class="stat-card-value">{{ formatBytes(evalResult?.total_bytes) }}</div>
        </div>
        <div class="stat-card">
          <div class="stat-card-label">模式</div>
          <div class="stat-card-value mode-label">{{ modeLabel }}</div>
        </div>
        <div class="stat-card">
          <div class="stat-card-label">耗时</div>
          <div class="stat-card-value">{{ evalResult?.duration_ms ?? 0 }} ms</div>
        </div>
      </div>
      <el-alert type="error" :closable="false" show-icon class="state-alert">
        清理后将无法恢复。再次点击"确认清理"才真正执行。
      </el-alert>
    </div>

    <!-- 状态 ③ 清理完成 -->
    <div v-else-if="currentState === 'done'" class="state-content">
      <h4 class="state-h4 done-title">✓ 清理完成</h4>
      <div class="stat-grid">
        <div class="stat-card success">
          <div class="stat-card-label">实际删除</div>
          <div class="stat-card-value">{{ formatNumber(cleanResult?.deleted) }}</div>
        </div>
        <div class="stat-card success">
          <div class="stat-card-label">实际释放</div>
          <div class="stat-card-value">{{ formatBytes(cleanResult?.total_bytes) }}</div>
        </div>
        <div class="stat-card" :class="{ failed: (cleanResult?.failed ?? 0) > 0 }">
          <div class="stat-card-label">失败</div>
          <div class="stat-card-value">{{ cleanResult?.failed ?? 0 }} 个文件</div>
        </div>
        <div class="stat-card">
          <div class="stat-card-label">耗时</div>
          <div class="stat-card-value">{{ formatDuration(cleanResult?.duration_ms) }}</div>
        </div>
      </div>
    </div>

    <!-- 错误条 -->
    <el-alert
      v-if="error"
      type="error"
      :closable="false"
      show-icon
      class="state-alert"
    >
      {{ error }}
    </el-alert>

    <template #footer>
      <!-- 状态 ① / ② 错误恢复: 取消 -->
      <el-button
        v-if="currentState === 'idle'"
        @click="handleClose(false)"
      >
        取消
      </el-button>

      <!-- 状态 ②: 取消 + 确认清理 -->
      <template v-else-if="currentState === 'evaluated' || currentState === 'cleaning'">
        <el-button :disabled="cleaning" @click="handleClose(false)">取消</el-button>
        <el-button
          type="danger"
          :loading="cleaning"
          :disabled="(evalResult?.matched ?? 0) === 0"
          @click="handleConfirmClean"
        >
          确认清理
        </el-button>
      </template>

      <!-- 状态 ③: 关闭 -->
      <el-button v-else type="primary" @click="handleClose(false)">关闭</el-button>
    </template>
  </el-dialog>
</template>

<script setup>
import { ref, computed, watch } from 'vue'
import { cleanupPreviews } from '@/api'

const props = defineProps({
  modelValue: { type: Boolean, required: true },
})

const emit = defineEmits(['update:modelValue'])

// 状态机
const currentState = ref('idle')  // 'idle' | 'evaluated' | 'cleaning' | 'done'
const evaluating = ref(false)
const cleaning = ref(false)
const error = ref(null)
const selectedMode = ref(null)
const evalResult = ref(null)
const cleanResult = ref(null)

// 计算属性
const dialogTitle = computed(() => {
  if (currentState.value === 'done') return '预览图清理'
  return '预览图清理'
})

const canClose = computed(() => {
  // 评估中 / 清理中禁止关闭弹窗
  return !evaluating.value && !cleaning.value
})

const modeLabel = computed(() => {
  return selectedMode.value === 'clean_local_previews' ? '本地清理' : '全量清理'
})

// 监听 modelValue：关闭时重置状态
watch(() => props.modelValue, (visible) => {
  if (!visible) {
    // 延迟重置，避免动画期间闪烁
    setTimeout(() => {
      if (!props.modelValue) {
        resetState()
      }
    }, 300)
  }
})

function resetState() {
  currentState.value = 'idle'
  evaluating.value = false
  cleaning.value = false
  error.value = null
  selectedMode.value = null
  evalResult.value = null
  cleanResult.value = null
}

function handleClose(visible) {
  if (!canClose.value && visible === false) {
    return  // 拒绝关闭
  }
  emit('update:modelValue', visible)
}

async function handleEvaluate(mode) {
  selectedMode.value = mode
  evaluating.value = true
  error.value = null
  try {
    const resp = await cleanupPreviews(mode, true)
    evalResult.value = resp.data
    currentState.value = 'evaluated'
  } catch (e) {
    error.value = `评估失败：${e.message || '未知错误'}`
  } finally {
    evaluating.value = false
  }
}

async function handleConfirmClean() {
  if (!selectedMode.value) return
  cleaning.value = true
  error.value = null
  try {
    const resp = await cleanupPreviews(selectedMode.value, false)
    cleanResult.value = resp.data
    currentState.value = 'done'
  } catch (e) {
    error.value = `清理失败：${e.message || '未知错误'}`
  } finally {
    cleaning.value = false
  }
}

// 工具函数
function formatNumber(n) {
  if (n == null) return '0'
  return Number(n).toLocaleString('en-US')
}

function formatBytes(bytes) {
  if (!bytes || bytes <= 0) return '0 B'
  const units = ['B', 'KB', 'MB', 'GB', 'TB']
  const k = 1024
  const i = Math.floor(Math.log(bytes) / Math.log(k))
  const value = bytes / Math.pow(k, i)
  return `${value.toFixed(value >= 100 ? 0 : value >= 10 ? 1 : 2)} ${units[i]}`
}

function formatDuration(ms) {
  if (!ms || ms <= 0) return '0 ms'
  if (ms < 1000) return `${ms} ms`
  return `${(ms / 1000).toFixed(2)} s`
}
</script>

<style scoped>
.state-content {
  padding: 4px 0;
}

.state-desc {
  font-size: 13px;
  color: var(--text-secondary, #606266);
  line-height: 1.6;
  margin: 0 0 12px 0;
}

.state-desc code {
  background: var(--bg-primary, #f5f7fa);
  padding: 2px 6px;
  border-radius: 3px;
  font-size: 12px;
}

.state-h4 {
  font-size: 15px;
  font-weight: 600;
  color: var(--text-primary, #303133);
  margin: 0 0 16px 0;
}

.state-h4.done-title {
  color: #67c23a;
}

.state-alert {
  margin: 12px 0;
}

.button-row {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 12px;
  margin-top: 16px;
}

.action-btn {
  height: auto !important;
  padding: 16px 12px !important;
  white-space: normal;
  line-height: 1.4;
}

.btn-title {
  font-size: 15px;
  font-weight: 600;
  margin-bottom: 4px;
}

.btn-subtitle {
  font-size: 11px;
  opacity: 0.85;
}

.stat-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 12px;
  margin-bottom: 4px;
}

.stat-card {
  padding: 12px 14px;
  background: var(--bg-primary, #f5f7fa);
  border-radius: 6px;
  border-left: 3px solid #dcdfe6;
}

.stat-card.success {
  border-left-color: #67c23a;
  background: #f0f9eb;
}

.stat-card.failed {
  border-left-color: #f56c6c;
  background: #fef0f0;
}

.stat-card-label {
  font-size: 12px;
  color: var(--text-muted, #909399);
  margin-bottom: 4px;
}

.stat-card-value {
  font-size: 18px;
  font-weight: 600;
  color: var(--text-primary, #303133);
}

.mode-label {
  font-size: 15px;
}

/* 暗色模式适配 */
:deep(.dark) .stat-card {
  background: #1a1a2e;
}

:deep(.dark) .stat-card.success {
  background: #1a2e1a;
}

:deep(.dark) .stat-card.failed {
  background: #2e1a1a;
}

:deep(.dark) .state-desc {
  color: #c0c4cc;
}

/* 移动端 */
@media screen and (max-width: 768px) {
  :deep(.el-dialog) {
    width: 90vw !important;
  }

  .stat-grid {
    gap: 8px;
  }

  .stat-card {
    padding: 10px;
  }

  .stat-card-value {
    font-size: 16px;
  }
}
</style>
```

- [ ] **Step 2: 验证组件能被 vite 编译**

Run:
```bash
cd /home/exa160/opencode/yande.re-spider-next-dev/frontend && \
  npx vite build 2>&1 | tail -25
```

Expected: 出现 `✓ built in <X>s` 行（即使整个 build 因其他原因失败，关键是 **无 SFC 语法错误**）。如有 `ERROR: Failed to parse ... PreviewCleanupDialog.vue` 立即修复。

注：完整 build 可能因其他文件失败，但不报错 SFC 语法即通过本 step。

- [ ] **Step 3: Commit**

```bash
cd /home/exa160/opencode/yande.re-spider-next-dev && \
  git add frontend/src/components/PreviewCleanupDialog.vue && \
  git commit -m "feat(frontend): add PreviewCleanupDialog component

3-state dialog for preview cache cleanup:
- idle:    two buttons (本地清理 / 全量清理) trigger auto-evaluation
- evaluated: 4 stat cards (命中/预计释放/模式/耗时) + 确认清理 button
- done:    4 stat cards (实际删除/实际释放/失败/耗时) + 关闭 button

State machine with guard against close during evaluating/cleaning.
dark mode + mobile (≤768px) responsive styles included."
```

---

## Task 3: 在 `Config.vue` 接入入口

**Files:**
- Modify: `frontend/src/views/Config.vue` (template line ~213 + script line ~225 + state line ~262)

- [ ] **Step 1: 在高级功能 section 末尾添加按钮**

编辑 `frontend/src/views/Config.vue`，在 line 213 的 `<el-button \` 标签之前（即 `refreshArtistsParams` 那个 refresh-item 关闭 `</div>` 后、`</div></div>` 关闭 refresh-controls 前），**实际位置**：找到 `<div class="refresh-controls">` 内最后一个 `<div class="refresh-item">` 的关闭 `</div>` 之后，再加一个 `<div class="refresh-item">`。

精确插入位置 — 在 line 212 的 `</el-button>\n            </div>` 之后，line 213 的 `</div>` (refresh-controls 关闭) 之前，插入：

```vue
            <div class="refresh-item">
              <div class="refresh-info">
                <div class="refresh-name">预览图清理</div>
                <div class="refresh-params">
                  <span class="param-tip">删除 downloads/previews/ 下的缩略图缓存</span>
                </div>
              </div>
              <el-button
                type="warning"
                size="small"
                @click="showCleanupDialog = true"
              >
                打开清理
              </el-button>
            </div>
```

- [ ] **Step 2: 在 template 末尾（`</div></div>\n  </div>\n</template>` 之前）挂载 dialog**

找到 `</template>` 标签正上方（即 `</div>` 关闭 `config-content` 的下方、`</div>` 关闭 `config-page` 的下方），在 line 217 的 `</div>\n  </div>\n</template>` 中的第一个 `</div>` 之前插入：

```vue

    <PreviewCleanupDialog v-model="showCleanupDialog" />
```

最终这块结构应为：

```vue
      </div>  <!-- 关闭 advanced section -->
    </div>  <!-- 关闭 config-content -->

    <PreviewCleanupDialog v-model="showCleanupDialog" />
  </div>  <!-- 关闭 config-page -->
</template>
```

- [ ] **Step 3: 在 `<script setup>` 中加 import 和 state**

在 line 224（`import { tagCacheApi } from '@/api/tagCache'`）之后插入：

```javascript
import PreviewCleanupDialog from '@/components/PreviewCleanupDialog.vue'
```

在 line 262（`const refreshArtistsParams = ref({ page: 1, limit: 100, max_pages: 10 })`）之后插入：

```javascript

// 预览图清理弹窗
const showCleanupDialog = ref(false)
```

- [ ] **Step 4: 验证完整 build**

Run:
```bash
cd /home/exa160/opencode/yande.re-spider-next-dev/frontend && \
  npx vite build 2>&1 | tail -30
```

Expected: `✓ built in <X>s` 且无 `ERROR` 行。如果报 `Failed to resolve import "@/components/PreviewCleanupDialog.vue"` 或 `PreviewCleanupDialog is not a registered component`，立即修复 import 路径或 component registration。

- [ ] **Step 5: 手动 smoke test（如后端可启动）**

启动后端 + 前端，浏览器打开 `http://localhost:3000/#/config` → 高级功能 → 看到 "预览图清理" 行 + "打开清理" 按钮 → 点击 → 弹窗 → 点击 "本地清理" → 等待评估 → 看到 4 个指标卡 + "清理信息" 标题 → 点击 "确认清理" → 看到 "✓ 清理完成" 状态。

```bash
cd /home/exa160/opencode/yande.re-spider-next-dev/backend && \
  (uvicorn service:main_app --host 127.0.0.1 --port 8000 > /tmp/opencode/smoke.log 2>&1 &) && \
  sleep 4 && \
  cd ../frontend && \
  (npx vite --host 127.0.0.1 --port 3000 > /tmp/opencode/vite.log 2>&1 &) && \
  sleep 5 && \
  echo "frontend: http://127.0.0.1:3000" && \
  echo "backend: http://127.0.0.1:8000" && \
  echo "test api:" && \
  curl -s http://127.0.0.1:8000/api/v1/gallery/cache/preview/cleanup \
    -X POST -H 'Content-Type: application/json' \
    -d '{"mode":"clean_local_previews","dry_run":true}' | head -c 200 && echo
```

清理：

```bash
pkill -f "uvicorn service:main_app --host 127.0.0.1 --port 8000" || true
pkill -f "vite --host 127.0.0.1 --port 3000" || true
```

- [ ] **Step 6: Commit**

```bash
cd /home/exa160/opencode/yande.re-spider-next-dev && \
  git add frontend/src/views/Config.vue && \
  git commit -m "feat(frontend): wire preview cleanup entry into Config page

Adds '预览图清理' row to 高级功能 section with '打开清理' button.
Mounts PreviewCleanupDialog with v-model for v-dialog controlled flow."
```

---

## Self-Review

✅ **Spec coverage**：
- 位置（Config → 高级功能）：Task 3 ✅
- 3 状态弹窗：Task 2 (`idle` / `evaluated` / `cleaning` / `done`) ✅
- 两个按钮自动评估：Task 2 `handleEvaluate()` ✅
- 二次确认：Task 2 状态 ② "确认清理" 按钮 ✅
- 状态 ② 标题 "清理信息"：Task 2 template ✅
- matched=0 禁用确认：Task 2 `:disabled="(evalResult?.matched ?? 0) === 0"` ✅
- 4 个指标卡：Task 2 状态 ② 和 ③ ✅
- 实际删除/释放/失败/耗时：Task 2 状态 ③ ✅
- 失败时红色卡片：Task 2 `.stat-card.failed` ✅
- API 错误条：Task 2 `<el-alert v-if="error">` ✅
- 评估/清理中禁关闭：Task 2 `:show-close="canClose"` + `handleClose` guard ✅
- dark mode 适配：Task 2 `:deep(.dark)` 样式 ✅
- 移动端 ≤768px 弹窗宽度 90vw：Task 2 `@media (max-width: 768px)` ✅
- 关闭后再次打开重置回 ①：Task 2 `watch(() => props.modelValue)` + `resetState()` ✅

✅ **Placeholder scan**：无 TBD/TODO；所有按钮、样式、状态值都是实际字符串。

✅ **Type consistency**：
- `cleanupPreviews(mode, dryRun)` 函数签名在 Task 1 定义，Task 2 一致使用。
- `selectedMode.value` 类型 `'clean_local_previews' | 'clean_all_previews'`，Task 2 状态流转一致。
- `evalResult.value` / `cleanResult.value` 字段 (`matched`/`total_bytes`/`duration_ms`/`deleted`/`failed`) 与后端 API 响应一致（参见 spec §7）。

✅ **Dependency ordering**：Task 1 (API) → Task 2 (component 依赖 API) → Task 3 (Config.vue 依赖 component)。

---

**Plan complete. Files modified: 1 (api/index.js) + 1 (Config.vue) + 1 created (PreviewCleanupDialog.vue).**

---

## Execution Handoff

Two execution options:

1. **Subagent-Driven (recommended)** — 每个 task 独立 subagent 实施 + spec/code 双 review，上下文隔离，回滚成本低
2. **Inline Execution** — 同一 session 顺序执行所有 task

请选择执行方式。