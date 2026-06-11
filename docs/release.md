# 版本升级流程

> **TL;DR** —— 改 `package.json` + `pyproject.toml` + `AppConfig.version` 三处 → commit → push → 打 tag → gh release create → gh issue create + gh pr create

本文档基于 v1.1.4 release 实战经验整理。如果用户说"提个 PR 走正常流程"或"升级版本"，**直接按本文档走**。

---

## 1. 三个 version 源（必须同步）

| 文件 | 字段 | 说明 |
|---|---|---|
| `frontend/package.json` | `"version"` | npm 语义版本，**Vite build 时通过 `define` 注入到 `__APP_VERSION__`**（见 [vite.config.js](../frontend/vite.config.js)）|
| `pyproject.toml` | `version` | PEP 621 规范，**uv/pip 用的 source of truth** |
| `backend/src/__init__.py` | `AppConfig.version` | FastAPI 应用版本，**自动同步到 OpenAPI `info.version`** + 启动 banner |

**坑**：v1.1.0 漏改 `pyproject.toml`（一直 1.0.0），v1.1.0-v1.1.3 期间 `AppConfig.version` 和 `package.json` 一直 1.1.0。**v1.1.4 才统一对齐**。**任何 release 必须三处都改**。

---

## 2. 后端启动 banner（v1.1.4+）

`init_app()` 末尾调用 `_print_startup_banner(app_config)`，打印：

```
==================================================================
  Yande.re Local Picture Manager v1.1.4 (git-2fd53c8)
  Python 3.12.3
------------------------------------------------------------------
  Data dir   : /path/to/data
  Download   : /path/to/downloads
  Log dir    : /path/to/logs
  Docs       : /docs  |  ReDoc: /redoc
==================================================================
```

- `git SHA` 来自 `git rev-parse --short HEAD`，**2 秒超时**，git 不可用 fallback `unknown`
- banner 放在 `init_app()` 末尾，**reload 模式会重复打印**（每次 reload 重新执行 `init_app`），但**单次进程启动只一次**
- 这意味着 docker 启动后**第一时间**就能看到 `v1.1.4`，跟 `/openapi.json` 的 `info.version` 一致

---

## 3. 前端 version 自动注入（v1.1.4+）

Config.vue 之前硬编码 `Version 1.1.4` —— 跟 npm 升级脱钩。修复：

**`frontend/vite.config.js`** 顶层：
```js
import { readFileSync } from 'fs'
const packageJson = JSON.parse(readFileSync(resolve(__dirname, 'package.json'), 'utf-8'))

export default defineConfig({
  // ...
  define: {
    __APP_VERSION__: JSON.stringify(packageJson.version)
  },
})
```

**`frontend/src/views/Config.vue`**：
```vue
<script setup>
const appVersion = __APP_VERSION__  // 编译时被替换成 "1.1.4"
</script>

<template>
  <div class="about-version">Version {{ appVersion }}</div>
</template>
```

**验证**：
```bash
cd frontend && npm run build
grep "__APP_VERSION__" dist/assets/*.js  # 期望 0 匹配（全部被替换）
grep '"1.1.4"' dist/assets/Config-*.js   # 期望 ≥1 匹配（字面量在 bundle）
```

**为什么不用 `import.meta.env.VITE_APP_VERSION`**：需要 shell 展开 `$npm_package_version`，**Windows CI 失效**。

---

## 4. GH Action 4-tier docker tag 设计

`.github/workflows/docker-build-push.yml` 在 v1.1.4 配齐了 4 套 tag：

| 触发 | 生成 tags | 用途 |
|---|---|---|
| `pull_request` (open/update) | `git-<sha>` | PR 临时验证 |
| `push` 到 `next` 分支（PR merge）| `dev-<sha>` + `dev` | 预发布（测试人员拉取）|
| `push` semver tag `v*.*.*` | `v<semver>` + `latest` | 正式发布 |

**关键配置**：
```yaml
on:
  pull_request:
    branches: [ "next" ]
  push:
    branches: [ "next" ]      # ← v1.1.4 补的（PR merge 触发必需）
    tags: [ 'v*.*.*' ]
```

**⚠️ RC 已知问题**：`v1.2.0-rc.1` tag 推送时 `latest` 仍会被绑定，污染 stable。**留作后续 PR 修**（用 semver `pattern=...rc-prerelease` 排除）。

---

## 5. 完整 release 流程

### 5.1 准备 commit

```bash
# 1. 三处 version 同步
vim frontend/package.json   # "version": "1.1.5"
vim pyproject.toml          # version = "1.1.5"
vim backend/src/__init__.py # version: str = "1.1.5"

# 2. 验证
cd frontend && npm run build
cd ../backend && /path/to/venv/bin/python -c "
import sys; sys.path.insert(0, '.')
from src import app_config
assert app_config.version == '1.1.5', app_config.version
print('PASS: version =', app_config.version)
"
# 后端启动 banner 应输出 v1.1.5

# 3. Commit
cd ..
git add frontend/package.json pyproject.toml backend/src/__init__.py
git commit -m "chore(release): bump version to 1.1.5"
git push origin next_dev
```

### 5.2 打 tag + push

```bash
# 写 release notes (跟之前 tag message 格式一致)
cat > /tmp/vX.Y.Z-tag-msg.txt << 'EOF'
vX.Y.Z - <一句话标题>

Highlights:
- ...

EOF

# 创建 annotated tag (指向刚 commit)
git tag -a vX.Y.Z -F /tmp/vX.Y.Z-tag-msg.txt <commit-sha>
git push origin vX.Y.Z
```

### 5.3 创建 GitHub Release

```bash
# 先建空 release (避开 gh release create + --target + --notes-file 的 500 错误)
gh release create vX.Y.Z --title "vX.Y.Z" 

# 再 edit 加完整 notes
gh release edit vX.Y.Z \
  --title "vX.Y.Z - <一句话标题>" \
  --notes-file /tmp/vX.Y.Z-tag-msg.txt
```

> **坑**：`gh release create --target <sha> --notes-file <file>` 组合在 GitHub API 上**有 500 错误 bug**，**先 create 后 edit** 模式 100% 可靠。

### 5.4 创建 Issue（"按正常流程"）

```bash
gh issue create \
  --title "[vX.Y.Z] <一句话标题>" \
  --label "release" \
  --body "$(cat <<'EOF'
## 背景
<v1.1.0/v1.1.1/v1.1.2/v1.1.3 没解决的痛点，或者 v1.1.X 这次引入的变更>

## 修复 / 改动
- 改动 1
- 改动 2

## 验证
| 场景 | 修复前 | 修复后 |
|---|---|---|
| ... | ... | ... |

## 关联 Commits
| Hash | 说明 |
|---|---|
| `xxxxxxx` | ... |
| `xxxxxxx` | ... |

## 文档
- Spec: docs/superpowers/specs/...
- Plan: docs/superpowers/plans/...

## Tag
`vX.Y.Z` (已 push)
EOF
)"
```

### 5.5 提 PR（next_dev → next）

```bash
# PR body 用 --body-file 避免 shell 转义
cat > /tmp/pr-body.md << 'EOF'
## 概述
<一句话>

## 关联
- Closes #N (issue 编号)

## 改动文件
| 文件 | 改动 |
|---|---|
| ... | ... |

## Commits
<commit 列表>

## 验证
<实证表格>

## 范围说明
- ✅ 改什么
- ❌ 不改什么
EOF

gh pr create \
  --base next \
  --head next_dev \
  --title "vX.Y.Z: <一句话标题>" \
  --body-file /tmp/pr-body.md
```

### 5.6 等合入后

PR merge 后 GH Action 自动构建 `vX.Y.Z` + `latest` docker 镜像。Issue 自动关闭（`Closes #N`）。

---

## 6. 历史参考

| Release | PR | Issues |
|---|---|---|
| v1.1.1 + v1.1.2 | [PR #4](https://github.com/exa160/yande.re-spider/pull/4) | #3, #5 |
| v1.1.3 | (未走流程) | (未走流程) |
| v1.1.4 | (未走流程) | (未走流程) |

v1.1.3/v1.1.4 当时是**跳过流程直接 tag + release**（用户说"后续流程待优化中"）。本文档建立后**任何未来 release 必须走完整流程**。

---

## 7. 已知坑清单

| 坑 | 触发场景 | 解决 |
|---|---|---|
| `gh release create --target + --notes-file` 报 500 | GH API bug | 先 create 空 release 再 edit |
| `gh pr view 4 --json body` 报 GraphQL 错（Projects deprecation）| gh CLI 2.45 + GH GraphQL 变动 | 用 `gh pr view 4 --json title,body` 加显式字段绕过 |
| uvicorn `--reload` 模式重复打印 banner | reload 重跑 init_app | 单次进程启动打印一次是预期行为（reload 时算新一次启动）|
| `BaseHTTPMiddleware` 跨 task ContextVar 失效 | v1.1.3 之前的代码 | Pure ASGI middleware + DAO session refetch（v1.1.3 修）|
| 3 个 version 源不一致 | v1.1.0-v1.1.3 期间 | v1.1.4 统一对齐 + 本文档约束未来必须三处都改 |
| RC tag 污染 latest | v1.2.0-rc.1 推送 | 未修（用 semver pattern 排除）|
