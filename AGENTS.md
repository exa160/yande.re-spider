# Yande.re Spider 接口编写规范

> 本规范基于 `next_dev` 分支的重构经验总结构建，对比了 `next`（AI原写）和 `next_dev`（可读性重构后）的代码差异。

**详细文档请参考 [docs/](docs/) 目录。**

---

## 核心原则

1. **分层职责**：`api/` → `services/` → `dao/` 严禁跨层调用
2. **类型安全**：所有函数必须声明返回类型注解
3. **统一响应**：`BaseResponse` + `APIException` + `ErrMsg`
4. **自动化**：路由注册、中间件加载全部自动化

---

## 快速参考

| 操作 | 规范 |
|------|------|
| 新增 API 路由 | 在 `api/v1/` 下创建文件，APILoader 自动发现 |
| 返回响应 | `BaseResponse(message=ErrMsg.OK.msg, data={...})` |
| 抛出错误 | `raise APIException(ErrMsg.XXX, e=e)` |
| 新增 DAO | 继承 `BaseDAO`，使用 `self.session` 操作数据库 |
| 配置常量 | 在 `common/constant.py` 中定义 `PathConstant`、`ErrMsg` 等 |
| **升级版本 / 发版** | **3 条核心流程线**：dev 合入（feature → next_dev）/ 正式 release（feature → next_dev + version bump → tag/GH Release → next）/ dev 多次合入后的 release，详见 [docs/release.md](docs/release.md) |

---

## 文档索引

| 文档 | 内容 |
|------|------|
| [docs/structure.md](docs/structure.md) | 项目目录结构、层级职责划分 |
| [docs/api-route.md](docs/api-route.md) | API 路由文件模板、关键规则 |
| [docs/response.md](docs/response.md) | BaseResponse、响应格式约定 |
| [docs/error-handling.md](docs/error-handling.md) | ErrMsg 枚举、APIException、错误中间件 |
| [docs/dao.md](docs/dao.md) | BaseDAO、Session 管理、编写规范 |
| [docs/middleware.md](docs/middleware.md) | 中间件注册顺序、模板、RequestSessionMiddleware |
| [docs/router-registry.md](docs/router-registry.md) | APILoader 自动路由发现、RouterMap |
| [docs/constants.md](docs/constants.md) | PathConstant、TaskStatus 等常量定义 |
| [docs/design.md](docs/design.md) | 架构设计详解 |
| [docs/tasks.md](docs/tasks.md) | 开发任务追踪 |
| [docs/release.md](docs/release.md) | **版本与发布流程**（3 条核心流程线 + 分支保护红线 + 主动 version bump 检查） |

---

## 代码风格要点

1. **类型注解**：所有函数必须声明返回类型
2. **Pydantic Field**：请求模型使用 `Field()` 定义校验规则
3. **docstring**：每个 API 路由添加 `"""描述"""` 文档字符串
4. **日志记录**：在 `middleware/loggers.py` 统一日志格式
5. **枚举优先**：状态码、错误码使用枚举而非硬编码字符串
6. **frozen 配置**：PathConstant 等配置类使用 `frozen=True` 防止意外修改

---

## 重构状态追踪

### 已完成的重构（next_dev 分支）

| 重构项 | 状态 | 提交记录 |
|--------|------|----------|
| 目录结构重组（backend/src/） | ✅ 完成 | 738beef, d4a01e4 |
| 自动路由注册（APILoader） | ✅ 完成 | b8afae8 |
| 统一响应格式（BaseResponse） | ✅ 完成 | 1489e01 |
| 统一错误处理（APIException + ErrMsg） | ✅ 完成 | 1489e01 |
| 中间件层拆分（middleware/） | ✅ 完成 | 6ef8596 |
| 常量管理统一（PathConstant） | ✅ 完成 | 8a05889 |
| 导入路径标准化（src.xxx） | ✅ 完成 | 8a05889 |
| DAO 层重构 | ✅ 完成 | bea5017 |
| API 路由系统重构 | ✅ 完成 | 3331539 |
| 数据库模型模块化 | ✅ 完成 | 8ce9224 |

### 代码规范检查清单

**API 路由文件检查**：
- [ ] 是否使用 `APIException(ErrMsg.XXX, e=e)` 模式
- [ ] 是否返回 `BaseResponse` 或继承类
- [ ] 是否声明返回类型注解
- [ ] 是否添加 docstring
- [ ] Request Model 是否使用 `Field()` 校验
- [ ] 本地 tag 匹配：默认精确 token；`*` 表通配（`pan*` 前缀，`p*n` 中间）；`-` 表排除；纯 `*` 忽略（详见 `docs/superpowers/specs/2026-07-18-local-tag-exact-match-design.md`）

**响应格式检查**：
- [ ] 成功响应：`BaseResponse(message=ErrMsg.OK.msg, data={...})`
- [ ] 错误响应：`raise APIException(ErrMsg.XXX, e=e)`
- [ ] 避免返回原始字典

---

## 🔐 密钥与敏感信息管理（强制红线）

> **运行时配置文件路径**（由 `PathConstant` 实例化时通过 `_resolve_user_config_dir()` 立即解析）：
> - POSIX 开发 / 裸机部署：`~/.config/yande-spider/config/config.yaml`
> - Windows 客户端：`%APPDATA%\yande-spider\config\config.yaml`
> - Docker：通过 `YANDE_USER_CONFIG_DIR=/app` 环境变量显式指定 → `config_file = /app/config/config.yaml`
>
> 仓库内 tracked 的 `backend/config/config.yaml` 和 `config/config.yaml` **均不被运行时读取**，仅作 PyInstaller frozen 资源兜底 placeholder。详见下方「📦 部署模式与配置路径」一节。

### 规则总览

| 位置 | 内容 | 是否进 git |
|------|------|-----------|
| **本地** `backend/config/config.yaml` | 真实密码（用于本地运行） | ❌ **不进**（已被 `.gitignore` 排除，但已 tracked 文件需 `git rm --cached`）|
| **本地** `backend/config/*.bak` | 真实密码（备份） | ❌ 强制不进（`.gitignore` 规则）|
| **远端** `backend/config/config.yaml` | 占位符 `password: ""` | ✅ 进 |

### 红线规则

- ❌ **绝不在 commit / push 中包含真实密码、token、API key、secret、内网 IP 等敏感字段**
- ✅ **远端仓库所有分支的** `backend/config/config.yaml` 中 `database.password` **必须是** `""` 或占位符
- ✅ **本地** `backend/config/config.yaml` 保留真实密码用于本地运行
- ❌ **`backend/config/*.bak`** 不应存在于任何分支（`.gitignore` 已覆盖）

### 推送前必查（强制执行）

推送任何 commit 前**必须**运行：

```bash
# 扫描即将推送的 diff 是否含真密钥（password / secret / token / api_key 等）
git diff origin/<base-branch>..HEAD \
  | grep -iE '(password|secret|token|api[_-]?key)\s*[:=]\s*["\047][^"\047]+["\047]' \
  | grep -vE '""|null|<YOUR_|<CHANGE_'
```

**判定规则**：
- ✅ **无输出** → 可以推送
- ❌ **有输出** → **立即停止推送**，把真密钥替换为占位符（如 `"<YOUR_DB_PASSWORD>"`），然后重新跑检查

### 错误示例与正确示例

```yaml
# ❌ 错误：含真实密码
database:
  password: "<真实密码>"

# ✅ 正确：占位符
database:
  password: ""
  # 或
  password: "<YOUR_DB_PASSWORD>"
```

### 历史密钥泄漏的紧急处理

如果发现历史 commit 误包含真密钥：

1. **立即 rotate 密钥**（数据库密码、API token 等）—— 这是**最关键**的一步
2. 用 [BFG Repo-Cleaner](https://rtyley.github.io/bfg-repo-cleaner/) 或 `git filter-branch` 清理历史（谨慎操作，会改 commit hash）
3. 通知所有协作者 pull 时注意
4. Force push 到所有相关分支（会改 commit hash，需重新打 tag）

### 远端仓库现状

```
✅ 所有远端分支的 backend/config/config.yaml 中 password = ""
✅ backend/config/*.bak 被 .gitignore 阻塞
```

**未来任何分支如有真密钥 → 视为事故，立即清理**。

---

## 📦 部署模式与配置路径

> 62f162d（v1.1.10）将 `PathConstant.config_file` 从 `install_dir/config/config.yaml` 拆到了 `user_config_dir/config/config.yaml`，以适配 PyInstaller Windows 客户端跨升级保留配置。但 **Docker / 裸机 server 部署的期望路径仍在 `install_dir`（容器内 `/app`，裸机仓库根）下**。
>
> `PathConstant` 在 `constant.py` 模块加载时通过 `_resolve_user_config_dir()` 立即读取 `YANDE_USER_CONFIG_DIR` 环境变量，**无须手动调用任何 resolver 函数**。Python 进程启动 → `constant.py` 加载 → `path_constant = PathConstant()` 实例化时环境变量已就绪 → `path_constant.config_file` 自动正确。

### 三种部署模式的路径解析

| 部署模式 | `install_dir` | `user_config_dir`（默认） | 覆盖方式 |
|---------|----------------|--------------------------|---------|
| **开发模式**（`uvicorn service:main_app --reload`） | 仓库根 | `~/.config/yande-spider`（POSIX）/ `%APPDATA%\yande-spider`（Windows） | 无需覆盖 |
| **PyInstaller 客户端**（Windows NSIS 安装器） | `sys._MEIPASS` 父目录 | `%APPDATA%\yande-spider` | 无需覆盖 |
| **Docker 服务**（`docker compose up`） | `/app` | **被 `YANDE_USER_CONFIG_DIR=/app` 覆盖** | 见下方 |

**关键区别**：

- 下载/数据/日志 路径跟随 `install_dir`（`downloads/`、`data/`、`logs/`），**始终在 install_dir 下**，Docker 与 dev 模式天然一致。
- `config.yaml`、`port`（PyInstaller launcher 用）跟随 `user_config_dir`，**必须显式覆盖才能与 Docker volume 挂载对齐**。

### Docker 部署的正确配置

`YANDE_USER_CONFIG_DIR` 的语义是「**用户配置根目录**」（其下还有 `config/` 子目录）。所以要让 `config_file = /app/config/config.yaml`，应设：

```yaml
# docker-compose.yml（关键片段）
services:
  picture-manager:
    volumes:
      - ./config:/app/config        # 宿主机 ./config/config.yaml 映射到容器 /app/config
    environment:
      - YANDE_USER_CONFIG_DIR=/app  # user_config_dir=/app → config_file=/app/config/config.yaml
```

**不设 `YANDE_USER_CONFIG_DIR` 的后果**：

- 容器内 `Path.home()` = `/root`，`_resolve_user_config_dir()` 返回 `/root/.config/yande-spider`
- `config_bootstrap` 会在 `/root/.config/yande-spider/config/config.yaml` 写一个 placeholder
- 宿主机 `./config/config.yaml` 永远不被读取 → UI 配置的密码/代理全部丢失，容器重启被覆盖
- 启动 banner 的 `Config:` 行会显示 `/root/.config/yande-spider/config/config.yaml`（一眼能看出来错配）

### 新增/修改路径相关的代码规范

| 操作 | 规范 |
|------|------|
| 读取运行时配置路径 | 通过 `path_constant.config_file`，**不要**直接写 `Path('config.yaml')` 或 `Path('~/.config/...')` |
| 跨部署兼容 | 让 path 在 `_resolve_user_config_dir()` 解析，不绕过 |
| 自定义部署路径 | 通过 `YANDE_USER_CONFIG_DIR` 环境变量注入，**不要**改代码硬编码 |
| 加新路径 | 在 `PathConstant` 加字段（跟随 `install_dir` 用类级 default，跟随 `user_config_dir` 用 `@property`） |
| 路径相关测试 | `backend/tests/test_path_constant.py` 加 case，必须包含 POSIX/Windows/环境变量覆盖三分支 |

### 启动 banner 中的 `Config:` 行

每次启动会在 logger banner 中打印 `Config: <config_file 绝对路径>`，便于第一时间确认路径解析正确：

```
==================================================================
  Yande.re Local Picture Manager v1.1.10 (git-ee71d04)
  Python 3.12.3
------------------------------------------------------------------
  Data dir   : /app/data
  Download   : /app/downloads
  Log dir    : /app/logs
  Config     : /app/config/config.yaml   ← Docker 应为这一行
  Docs       : /docs  |  ReDoc: /redoc
==================================================================
```

---

*最后更新：v1.1.7 release 后增加密钥管理章节；v1.1.9 dev 流程建立后增加 Dev 发布流程章节；v1.1.10 拆分 `config_file` 到 `user_config_dir` 后增加部署模式与配置路径章节；v1.1.10 release 复盘：Dev 发布流程迁入 docs/release.md，3 条核心流程线分明，禁止直接 push 到 next/next_dev，未经用户审核禁止 commit/push*