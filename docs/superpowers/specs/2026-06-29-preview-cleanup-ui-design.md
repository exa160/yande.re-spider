# 预览图清理前端 UI — 设计

**日期**：2026-06-29
**状态**：待批准
**作者**：Sisyphus
**范围**：前端（Config.vue + 新增 CleanupDialog.vue + API client）
**相关背景**：后端 `POST /api/v1/gallery/cache/preview/cleanup` 已实装并通过 spec/code review（参见 `2026-06-29-preview-cache-cleanup-design.md`）。本文档定义前端 UI 层。

---

## 1. 背景

后端已提供清理 preview 缩略图的能力（局部/全量、dry_run 评估、安全删除）。当前用户唯一手动入口是 curl 调用 API，缺乏可视化操作界面。

需求：在 Web UI 中提供一处安全、可视化的清理入口，让用户能：
- 一眼区分两种清理策略的语义
- 在删除前看到"将删多少 / 释放多少"
- 二次确认，避免误删

## 2. 目标

- **核心**：在 Config 页面增加"预览图清理"按钮 → 弹窗式交互 → 完成 dry_run 评估 → 二次确认 → 实际清理。
- **核心**：所有交互通过单端点 `POST /api/v1/gallery/cache/preview/cleanup` 完成，复用后端 dry_run 机制，前端无需自行实现"评估"逻辑。
- **次要**：dark mode 适配、移动端友好（按钮可点、布局不溢出）。
- **次要**：清理完成后展示完整结果（deleted / failed / total_bytes），便于用户感知副作用。

## 3. 非目标

- 不在 Gallery 顶部 toolbar 加入口（已在 brainstorm 阶段决定放 Config 页面，避免与浏览体验耦合）
- 不实现历史清理记录查询
- 不做定时清理（手动触发即可）
- 不写前端单元测试（项目无 Vitest 配置；后续可补）
- 不做按文件大小阈值 / 按日期范围的高级筛选（后端也未实现）

---

## 4. 用户流程（3 状态弹窗）

### 状态 ① 初始

- 用户点击 Config → 高级功能 → **预览图清理** 按钮
- 弹出 el-dialog
- 标题："预览图清理"
- 主体内容：
  - 说明文字：`删除 downloads/previews/ 下的缩略图缓存。先点击按钮评估，再二次确认执行。`
  - 两个并排按钮（等宽）：
    - **本地清理**（蓝色 / `#409eff`）— 副标题 "仅清有原图可再生的"
    - **全量清理**（橙色 / `#e6a23c`）— 副标题 "清空整个 previews/"
  - 警告条（黄底）：`⚠ 本地清理会清理约几百 MB~几 GB；全量清理会丢失所有未下载原图的预览`

### 状态 ② 评估完成（自动触发）

触发条件：用户在状态 ① 点击任一按钮 → 弹窗内自动调用 `POST /api/v1/gallery/cache/preview/cleanup { mode, dry_run: true }`。

- 标题：**清理信息**
- 加载状态：评估期间按钮显示 loading 转圈，不可重复点击
- 评估完成后展示 4 个指标卡片（2x2 grid）：
  - **命中文件** — `1,234`（API 响应 `matched` 字段，逗号千分位）
  - **预计释放** — `52 MB`（`total_bytes` 格式化，KB/MB/GB 自动单位）
  - **模式** — `本地清理` 或 `全量清理`（中文标签）
  - **耗时** — `142 ms`（`duration_ms` 字段）
- 警告条（红底）：`⚠ 清理后将无法恢复。再次点击"确认清理"才真正执行。`
- 底部按钮（居右）：
  - **取消**（默认色，点击关闭弹窗）
  - **确认清理**（红色 / `#f56c6c`，点击触发实际删除）

### 状态 ③ 清理完成

触发条件：用户在状态 ② 点击"确认清理" → 调用 `POST /api/v1/gallery/cache/preview/cleanup { mode, dry_run: false }`。

- 标题：`✓ 清理完成`（绿色 / `#67c23a`）
- 4 个指标卡片：
  - **实际删除** — `1,232`（`deleted` 字段，绿色背景强调成功）
  - **实际释放** — `52 MB`（实际删除字节数，与评估可能略有差异）
  - **失败** — `2 个文件（权限/占用）` 或 `无`（`failed` 字段，失败时红色背景）
  - **耗时** — `2.3 s`（秒级显示）
- 底部按钮：**关闭**（蓝色）

---

## 5. 视觉规范

| 元素 | 规范 |
|---|---|
| 弹窗宽度 | `width: 520px`（居中） |
| 圆角 | `border-radius: 6px` |
| 字体 | Element Plus 默认 + 项目 `styles/` 中已有样式覆盖 |
| 主色调 | 蓝色（本地清理 / 主操作）、橙色（全量清理 / 警告）、红色（确认清理 / 危险）、绿色（成功） |
| 暗色模式 | 跟随系统 `dark` 模式，与项目其他 `el-dialog` 一致（参考 Gallery.vue） |
| 移动端 | 弹窗宽度 `90vw`；按钮仍 2 列等宽；指标卡 2 列不变 |
| 警告条 | `el-alert` 或自定义 div，类型对应颜色（warning / error） |

### Mockup

完整视觉稿见 brainstorm session：
- `.superpowers/brainstorm/2923924-1782732306/content/layout-v2.html`

3 个状态的 wireframe 已画在该 HTML 中，包含准确的中文文案、按钮颜色、指标卡片布局。

---

## 6. 架构

### 组件结构

```
frontend/src/
├── views/
│   └── Config.vue                    ← 修改：在"高级功能"section 加按钮
├── components/
│   └── PreviewCleanupDialog.vue      ← 新建：弹窗组件（含 3 状态逻辑）
└── api/
    └── index.js                      ← 修改：新增 cleanupPreviews() 方法
```

### 组件职责

**`PreviewCleanupDialog.vue`**（新增）
- Props:
  - `modelValue: boolean` — el-dialog v-model 绑定
  - 默认从父组件接收，无外部 state
- Emits:
  - `update:modelValue` — 关闭弹窗
- 内部 state:
  - `currentState: 'idle' | 'evaluating' | 'evaluated' | 'cleaning' | 'done'`
  - `selectedMode: CleanupMode | null`
  - `evalResult: { matched, total_bytes, duration_ms } | null`
  - `cleanResult: { deleted, failed, total_bytes, duration_ms } | null`
  - `error: string | null`
- 模板分支：
  - `currentState === 'idle'` → 状态 ①
  - `currentState === 'evaluating'` → 状态 ① + loading（按钮 disabled）
  - `currentState === 'evaluated'` → 状态 ②
  - `currentState === 'cleaning'` → 状态 ② + 确认按钮 loading
  - `currentState === 'done'` → 状态 ③

**`Config.vue`**（修改）
- 在"高级功能"section 末尾追加：
  ```vue
  <el-form-item label="预览图清理">
    <el-button type="warning" @click="showCleanupDialog = true">
      <el-icon><Delete /></el-icon>
      预览图清理
    </el-button>
  </el-form-item>
  ```
- 新增 `showCleanupDialog: boolean = false` 局部 state
- 在 template 末尾挂载 `<PreviewCleanupDialog v-model="showCleanupDialog" />`

**`api/index.js`**（修改）
- 新增方法：
  ```js
  export async function cleanupPreviews(mode, dryRun) {
    return request({
      url: '/gallery/cache/preview/cleanup',
      method: 'post',
      data: { mode, dry_run: dryRun },
    });
  }
  ```

---

## 7. API 调用契约

### 评估调用

```js
const resp = await cleanupPreviews('clean_local_previews', true);
// resp.data = {
//   code: "0000",
//   message: "OK.",
//   data: {
//     mode: "clean_local_previews",
//     dry_run: true,
//     matched: 1234,
//     deleted: 0,
//     failed: 0,
//     total_bytes: 52428800,
//     duration_ms: 142,
//   },
// }
```

### 实际清理调用

```js
const resp = await cleanupPreviews('clean_local_previews', false);
// resp.data.data = { matched, deleted, failed, total_bytes, duration_ms }
```

### 错误响应

- HTTP 422（mode 非法）：由后端 Pydantic 校验自动返回，前端无需特殊处理（mode 来自按钮点击，不可能非法）
- HTTP 500（数据库/IO 错误）：`code: "0013"`，前端在弹窗内显示错误条
- 网络断开：`axios` 抛异常，前端捕获后显示 `ElMessage.error`

---

## 8. 错误处理

| 场景 | 前端行为 |
|---|---|
| 评估 API 失败（500、网络） | 弹窗内显示红色错误条 + 提示文字，按钮恢复可点击（用户可重试） |
| 评估 matched=0 | 状态 ② 显示空数据 + 警告"没有可清理的文件"，确认按钮 disabled |
| 清理 API 失败（500） | 状态 ② 保持（按钮恢复可点击），红色错误条提示 |
| 清理部分失败（deleted < matched） | 状态 ③ 正常显示，"失败"卡片显示具体数字和原因 |
| 用户在评估/清理执行中关闭弹窗 | 弹窗 disabled mask，请求继续执行但结果丢弃（前端不展示）；下次打开弹窗重置回状态 ① |
| 弹窗在 done 状态关闭后再次打开 | 重置回状态 ①（避免显示旧结果） |

---

## 9. 状态机

```
idle ──[click 本地/全量]──> evaluating ──[API success]──> evaluated
  │                            │                              │
  │                            └──[API error]──> idle + error  │
  │                                                           │
  │                              evaluated ──[click 确认清理]──> cleaning ──[API success]──> done
  │                                │                              │                          │
  │                                └──[click 取消]──> (close)      └──[API error]──> evaluated + error
  │
  └──[click X / 取消]──> (close, reset to idle on next open)
```

---

## 10. 文件改动清单

| 文件 | 改动 | 行数估算 |
|---|---|---|
| `frontend/src/components/PreviewCleanupDialog.vue` | 新建 | +180 |
| `frontend/src/views/Config.vue` | 在"高级功能"section 加按钮 + dialog mount | +15 |
| `frontend/src/api/index.js` | 新增 `cleanupPreviews()` | +8 |
| **总计** | | **+203** |

---

## 11. 实施顺序

按依赖关系：

1. `frontend/src/api/index.js` — 加 `cleanupPreviews()` 方法
2. `frontend/src/components/PreviewCleanupDialog.vue` — 新建组件
3. `frontend/src/views/Config.vue` — 接入入口

每步独立 commit。

---

## 12. 验收标准

- [ ] Config 页面 → 高级功能 → 看到"预览图清理"按钮
- [ ] 点击按钮弹出 el-dialog，标题"预览图清理"
- [ ] 弹窗内显示两个按钮（本地清理蓝、全量清理橙）
- [ ] 点击"本地清理"自动触发评估，加载状态可见
- [ ] 评估完成显示 4 个指标卡片 + "清理信息"标题
- [ ] matched=0 时确认按钮 disabled
- [ ] 点击"确认清理"触发实际删除，加载状态可见
- [ ] 清理完成显示"✓ 清理完成"标题 + 4 个指标（实际删除 / 实际释放 / 失败 / 耗时）
- [ ] failed > 0 时"失败"卡片显示具体数字
- [ ] API 错误时弹窗内显示红色错误条
- [ ] 弹窗右上角 X 在评估/清理执行中 disabled
- [ ] dark mode 视觉与项目其他 el-dialog 一致
- [ ] 移动端（≤768px）弹窗宽度 90vw，按钮仍可点
- [ ] 弹窗关闭后再次打开重置回状态 ①

---

## 13. 未来扩展（本次不实现）

- [ ] 历史清理记录（后端需新增 `cleanup_history` 表）
- [ ] 定时自动清理（cron 表达式）
- [ ] 按文件大小阈值 / 按日期范围清理（需后端先支持）
- [ ] 前端 Vitest 单测
- [ ] PreviewCleanupDialog 抽成独立 npm 包供其他项目复用

---

**参考文档**：
- `docs/superpowers/specs/2026-06-29-preview-cache-cleanup-design.md` — 后端 API 设计
- `AGENTS.md` — 项目代码规范
- `docs/release.md` — 版本升级流程（前端独立版本）
- `.superpowers/brainstorm/2923924-1782732306/content/layout-v2.html` — 视觉 mockup
- `frontend/src/views/Gallery.vue` — 现有 el-dialog / el-button 使用参考
- `frontend/src/views/Config.vue` — 修改目标文件
- `frontend/src/api/index.js` — axios 封装参考