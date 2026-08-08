# 版本与发布流程 (Release Process)

> **TL;DR —— 核心发布包含 3 条流程线**：
> 1. **dev 合入流程**（日常开发）：`feature` → `next_dev`。
> 2. **正式 release 流程**（单次功能直接发版）：`feature` → `next_dev` + `version bump` → `tag/GH Release` → `next`。
> 3. **dev 多次合入后的 release 流程**（累积发版）：`next_dev` 已累积多次更新，直接 `version bump` → `tag/GH Release` → `next`。

本文档基于实战经验与最新的 GitHub Action 自动化构建策略整理。

---

## 0. 🔒 分支保护与操作红线

❌ **非用户明确同意的情况下，禁止任何人（包含 LLM Agent）直接 push 代码到 `next_dev` 和 `next` 分支**。

❌ **未经用户审核，不能直接 commit push 代码**（避免无效 commit 导致 commit 反复修改）。

所有对受保护分支的更改，默认必须通过新建开发分支并提交 PR/MR 的方式进行。如需使用 `--admin` 绕过保护直接合并，必须事先得到用户的明确授权，且授权仅对当前单次操作有效。

LLM 工作流约束：
- 改代码前：先口头描述改动方案，等用户确认
- 改代码后：先展示 `git diff` 给用户审核，等用户明确说"OK commit" 再 commit
- commit 后：等用户明确说"OK push" 再 push

---

## 1. 流程线一：dev 合入流程

**适用场景**：日常功能开发、Bug 修复，仅合入开发环境 (`next_dev`) 供测试，不打 tag，不发版。

### 1.1 准备分支

- **规范**：由最新的 `next_dev` 分支分叉，新建分支（如 `feature-<name>` 或 `feat/<name>`）作为开发分支。注意：现有 `feature` 分支会冲突，必须用连字符命名（如 `feature-release-docs-refactor`）。
- **第三方/脱节分支的特殊处理 (Cherry Up)**：
  若前部分的开发并非基于最新的 `next_dev` 分支（例如来自其他第三方开发分支），则必须：
  1. `git fetch origin next_dev`
  2. 从最新 `next_dev` 创建新分支：`git checkout -b <new-branch> origin/next_dev`
  3. 将第三方分支上的最新 commit 提取过来：`git cherry-pick <commit-sha>`
  4. 解决冲突（如有）后 push 新分支。

### 1.2 主动检查 Version Bump

走完功能开发、准备合入前，**主动检查** version 是否有变更：

```bash
# 对比上次 release 与当前 dev diff
git log <last-release-tag>..origin/next_dev --oneline

# 检查 3 处 version 与上次 release tag 是否一致
grep -n '"version"' frontend/package.json
grep -n '^version' pyproject.toml
grep -n 'version:' backend/src/__init__.py
```

判断规则：
- 如果 3 处 version **与上次 release tag 一致**（说明上次 release 后尚未 bump），且本次改动包含用户可见功能/行为变化 → **必须先 bump version**（见 §4 三处版本源）
- 如果 3 处 version **已与上次 release tag 不一致**（说明上次 release 后已 bump），无需再 bump

### 1.3 提 PR 与合入

开发与测试完成后，提交并创建 PR 合入 `next_dev`：

```bash
git push origin <branch>
gh pr create --base next_dev --head <branch> --title "<title>" --body "Closes #N ..."
```

*注：经用户授权后，可使用 `gh pr merge <N> --admin --squash` 合入。*

---

## 2. 流程线二：正式 release 流程

**适用场景**：最新代码改动后需要正式发布（流程线一完成后立即发版）。

### 2.1 走完 dev 合入流程

首先按「流程线一」§1.1-§1.3，将本次的代码改动合入到 `next_dev`。

### 2.2 版本号同步 (Version Bump)

按 §1.2 的判断规则再次确认：
- 如果 3 处 version **已与上次 release tag 不一致**（说明 §1.2 已 bump），跳过本节
- 如果 3 处 version **仍然一致**，在 `next_dev` 上补做 version bump

修改 3 处 version 源（参考 §4 表格）：

```bash
# 1. 改 3 处 version
# frontend/package.json: "version": "X.Y.Z"
# pyproject.toml: version = "X.Y.Z"
# backend/src/__init__.py: AppConfig.version = "X.Y.Z"

# 2. 本地验证
cd frontend && npm run build
cd ../backend && /path/to/venv/bin/python -c "from src import app_config; assert app_config.version == 'X.Y.Z'; print('PASS')"

# 3. 提交 bump commit
git checkout next_dev
git pull origin next_dev
git add frontend/package.json pyproject.toml backend/src/__init__.py
git commit -m "chore(release): bump version to X.Y.Z"
git push origin next_dev
```

### 2.3 打 Tag 并推送

```bash
cat > /tmp/vX.Y.Z-tag-msg.txt << 'EOF'
vX.Y.Z - <一句话标题>

Highlights:
- ...
EOF

git tag -a vX.Y.Z -F /tmp/vX.Y.Z-tag-msg.txt origin/next_dev
git push origin vX.Y.Z
```

### 2.4 创建 GitHub Release & Issue

> **坑**：`gh release create --target + --notes-file` 组合在 GH API 上有 500 错误 bug。必须**先 create 后 edit**。

```bash
# 1. 发 Release（notes 简化，引用 issue 编号）
gh release create vX.Y.Z --title "vX.Y.Z"
gh release edit vX.Y.Z \
  --title "vX.Y.Z - <一句话标题>" \
  --notes-file /tmp/vX.Y.Z-release-notes.md

# 2. 记 Issue（详细背景，release notes 引用 issue 编号）
gh issue create \
  --title "[vX.Y.Z] <一句话标题>" \
  --label "release" \
  --body-file /tmp/vX.Y.Z-issue-body.md
```

**Issue body 详细模板**（背景/修复/验证/Commits/Tag）：

```markdown
## 背景
<v1.1.X 没解决的痛点，或本次引入的变更>

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

## Tag
`vX.Y.Z` (已 push)
```

**Release notes 简化模板**（引用 issue 编号）：

```markdown
# vX.Y.Z - <一句话标题>

完整背景、修复、验证见 Issue #[N]。

## Highlights
- ...
```

### 2.5 提 PR (next_dev → next)

```bash
gh pr create \
  --base next \
  --head next_dev \
  --title "[Release] vX.Y.Z: <一句话标题>" \
  --body "Release vX.Y.Z. Closes #N"
```

合入（仅当用户授权用 `--admin`）：

```bash
gh pr merge <N> --admin --squash --delete-branch=false
```

PR merge 后，GitHub Actions 将自动构建并推送 `latest` 镜像。

---

## 3. 流程线三：dev 多次合入后的 release 流程

**适用场景**：用户要求正式 release 时，**检查到无新代码需要 push**（`next_dev` 已累积多次 dev 合入，但用户没新增功能要合入），但用户要求基于当前的 `next_dev` 积累内容直接发版。此时 `next` 分支滞后于 `next_dev`。

**操作步骤**：跳过 §2.1（流程线一），直接从 **§2.2 版本号同步** 开始，但 version bump 判断规则**与上次 release tag 比对**：

1. 在最新 `next_dev` 上检查 3 处 version 与上一个 release tag 的差异：

   ```bash
   git log <last-release-tag>..origin/next_dev --oneline
   grep -n '"version"' frontend/package.json
   ```

2. **判断**：
   - 如果 3 处 version **与上次 release tag 一致**（说明累积的 dev 合入中无人主动 bump）→ 按 §2.2 提交 bump commit
   - 如果 3 处 version **已与上次 release tag 不一致**（说明累积的 dev 合入中已有人主动 bump）→ 跳过 bump，直接进入 §2.3 打 tag

3. 按 **§2.3-§2.5** 完成 tag + GH Release + Issue + PR (next_dev → next)。

---

## 4. 版本号与环境同步机制（原理参考）

系统内强制要求 3 个 Version 源必须同步，以实现全栈版本号的统一展示：

| 文件 | 字段 | 作用机制 |
| --- | --- | --- |
| `frontend/package.json` | `"version"` | 编译时 Vite 会读取，并通过 `define: { __APP_VERSION__: ... }` 硬编码注入到前端 `Config.vue` 界面中。 |
| `pyproject.toml` | `version` | Python 依赖打包规范 (PEP 621)，`uv/pip` 安装与环境的 source of truth。 |
| `backend/src/__init__.py` | `AppConfig.version` | FastAPI 运行时版本，自动同步至 OpenAPI `/openapi.json` 的 `info.version`，并在后端终端打印**启动 Banner**。 |

---

## 5. GitHub Action 镜像构建策略

Docker 镜像的构建与 Tag 分发由 `.github/workflows/docker-build-push.yml` 自动接管，设计了针对不同环境的 3 套分发策略：

| 触发条件 | 分发 Tags | 环境与用途 |
| --- | --- | --- |
| **Push / Merge 至 `next_dev`** | `dev-<sha>`<br>`dev` | **开发/预发布环境**。`dev-<sha>` 便于追溯和回滚；`dev` 为浮动指针，始终指向最新开发代码。 |
| **Push / Merge 至 `next`** | `rc-<sha>` | **发布验证环境**。无浮动指针，强制测试与运维显式拉取 SHA，避免自动化工具误将 RC 拉入生产。 |
| **Push Semver Tag (`vX.Y.Z`)** | `vX.Y.Z`<br>`latest` | **正式生产环境**。仅监听严格格式 (`v[0-9]+.[0-9]+.[0-9]+`)。 |

✅ **修复了历史上的 RC 污染问题**：原有的工作流在推送形如 `vX.Y.Z-rc.1` 的标签时会错误绑定 `latest`。当前 Action 配置通过 `tags: ["v[0-9]+.[0-9]+.[0-9]+"]` 实现了严格正则过滤，彻底杜绝了非正式 Release 污染 `latest` 的现象。

---

## 6. 历史参考与已知坑清单

### 6.1 历史参考

| Release | PR | Issues |
|---|---|---|
| v1.1.1 + v1.1.2 | [PR #4](https://github.com/exa160/yande.re-spider/pull/4) | #3, #5 |
| v1.1.3 | (未走流程) | (未走流程) |
| v1.1.4 | (未走流程) | (未走流程) |
| v1.1.10 | (本文档建立后首次正式 release) | (累积 dev 合入后) |

### 6.2 已知坑清单

| 坑 / 问题 | 触发场景 | 解决方案 / 现状 |
| --- | --- | --- |
| `gh release create` 报 500 | 携带 `--target` 与 `--notes-file` 一并创建时 | 改为"先 create 空 release，再 edit 补充信息"。 |
| `gh pr view` 报 GraphQL 错 | 旧版 GitHub CLI 与 Projects API 弃用冲突 | 使用 `--json title,body` 显式指定字段绕过，或升级 gh cli。 |
| Reload 模式重复打印 banner | uvicorn `--reload` 模式下 | 预期行为。单次进程启动仅打印一次，reload 被视作新建进程。 |
| 版本号不统一遗留问题 | 早期 v1.1.0~v1.1.3 未严格同步版本文件 | 已在 v1.1.4 修复对齐，后续发版强制检查 3 处 version 源。 |
| RC tag 污染 latest | 旧 workflow 推送 `vX.Y.Z-rc.1` 时 | 已用 semver regex `v[0-9]+.[0-9]+.[0-9]+` 过滤，详见 §5。 |