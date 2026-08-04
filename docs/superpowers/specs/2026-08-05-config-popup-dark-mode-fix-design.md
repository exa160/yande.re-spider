# 配置弹框夜间模式与代理提示修复设计

**日期**: 2026-08-05
**分支**: next（领先 origin/next 10 commits）
**范围**: `frontend/src/App.vue`、`frontend/src/views/Config.vue`
**前置 commit**: `56932df feat(proxy): 三态代理模式`、`76faa53 feat(ui): 全局 Element Plus 暗色模式适配`

---

## 背景

用户在「配置」路由页（由 `Gallery.vue` 的 `showConfigDialog` 触发）发现以下问题：

1. 高级功能区除「全量清理」外，其余按钮（刷新×2、本地清理，type=primary）在夜间模式下与主题不协调；
2. 代理模式三段式开关（`el-segmented`）整体未适配夜间模式；
3. 「系统代理」四个字因 `block` 三等分后宽度不足，渲染时被截断；
4. 选中「系统代理」后弹出的提示文案偏冗长。

## 根因

- `App.vue` 已有的 `.dark-mode .el-button` 规则仅覆盖 default/success/warning/info 四种 type，**遗漏了 `primary` 和 `danger`**；这导致 primary 类按钮（蓝底白字）在 dark mode 下沿用 light 主题的描边色，与暗色卡片背景对比突兀；
- `el-segmented` 在整个项目里没有专属 dark CSS；Element Plus 2.5.x 默认深色适配在该组件上覆盖不完整；
- `<el-segmented block>` 在 `.config-section { max-width: 400px }` + `label-width=100px` 下，每段 ≈90px，无法稳妥容纳「系统代理」四字 + 默认 padding；
- 提示文案原为两段技术性文字（含 Docker 部署细节），不符合「提示应当简明」的设计原则。

## 设计

### 修改 1：App.vue 追加 primary/danger 暗色规则

在现有 `.dark-mode .el-button.el-button--default` 等规则块（同 L175-200 范围）后追加：

```css
.dark-mode .el-button.el-button--primary,
.dark-mode .el-button.el-button--danger {
  --el-button-hover-text-color: #fff;
  --el-button-hover-border-color: var(--el-color-primary);
  --el-button-active-border-color: var(--el-color-primary);
}
.dark-mode .el-button.el-button--primary:hover,
.dark-mode .el-button.el-button--danger:hover {
  border-color: var(--el-color-primary) !important;
  filter: brightness(1.1);
}
```

**取舍**：保留主题色（蓝/红）做按钮语义标识，仅微调 hover 态（`brightness(1.1)` 与 primary 描边色），避免重写为深灰底破坏视觉语义。

### 修改 2：App.vue 新增 el-segmented 暗色规则

在 `.dark-mode .el-button--text` 之前插入：

```css
/* el-segmented 暗色适配 */
.dark-mode .el-segmented {
  --el-segmented-bg-color: var(--bg-tertiary);
  --el-segmented-item-color: var(--text-primary);
  --el-segmented-item-hover-color: var(--hover-bg);
  --el-segmented-item-active-color: #fff;
  --el-segmented-item-active-bg-color: var(--el-color-primary);
  background-color: var(--bg-tertiary);
}
.dark-mode .el-segmented .el-segmented__item {
  color: var(--text-primary);
}
.dark-mode .el-segmented .el-segmented__item:hover {
  background-color: var(--hover-bg);
}
.dark-mode .el-segmented .el-segmented__item.is-selected {
  background-color: var(--el-color-primary);
  color: #fff;
  border-color: var(--el-color-primary);
}
.dark-mode .el-segmented .el-segmented__group {
  background-color: var(--bg-tertiary);
}
```

### 修改 3：Config.vue segmented 模板与提示文案

```vue
<!-- 修改前 -->
<el-segmented
  v-model="apiConfig.proxy_enable"
  :options="proxyModeOptions"
  block
/>
```

```vue
<!-- 修改后 -->
<el-segmented
  v-model="apiConfig.proxy_enable"
  :options="proxyModeOptions"
  class="proxy-mode-segmented"
/>
```

```vue
<!-- 修改前 -->
<el-alert type="info" :closable="false" show-icon>
  使用后端进程环境变量 HTTP_PROXY / HTTPS_PROXY / NO_PROXY；
  Docker 部署需在 docker-compose.yml 中显式透传。
</el-alert>
```

```vue
<!-- 修改后 -->
<el-alert type="info" :closable="false" show-icon>
  使用系统环境变量中的代理配置
</el-alert>
```

### 修改 4：Config.vue 样式区追加 segmented 容器规则

在已有 `.config-section` 块附近追加：

```css
.proxy-mode-segmented {
  min-width: 320px;
  max-width: 100%;
}
.proxy-mode-segmented :deep(.el-segmented__item) {
  white-space: nowrap;
  padding: 0 16px;
}
```

**取舍**：移除 `block` 让 segmented 自然宽度，叠加 `min-width: 320px` 保证三段视觉均衡；保留 `max-width: 100%` 在窄屏自适应收缩；`white-space: nowrap` 防止「系统代理」被换行截断。

## 不做

- 不重构 `PreviewCleanupDialog.vue` 的 danger 按钮——本次仅修「配置页」按钮，不扩散范围；
- 不修改 `max-width: 400px` 的 form 宽度（避免连锁布局影响）；
- 不引入新依赖或工具函数；
- 不改变代理模式数据模型（仍为 `false / true / null` 三态，与后端 `test_proxy_mode.py` 测试对齐）。

## 验证

1. `npx eslint frontend/src/App.vue frontend/src/views/Config.vue`（若项目启用 lint）；
2. `cd frontend && npm run build` 必须 exit 0；
3. 在 `localhost:3000` 开发服下：
   - 切到夜间模式，配置页高级功能区 primary 按钮 hover 应有描边 + 提亮；
   - 代理三段式开关在 light/dark 下均可见，三段文字（含「系统代理」）完整不被截断；
   - 选中「系统代理」后提示文案为「使用系统环境变量中的代理配置」单行。

## 提交策略

**不自动提交**。修改落在工作区后由用户审核后人工 commit。