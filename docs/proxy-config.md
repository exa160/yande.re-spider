# 代理配置说明

> 配置 UI 路径：API 配置 → 代理模式

后端通过 `ApiConfig.proxy_enable` 字段控制网络请求的代理行为，支持 **三态**：

| 模式 | `proxy_enable` 值 | 行为 |
|------|-------------------|------|
| **关闭** | `false` | 完全不走代理（强制 `trust_env=False`，不受环境变量影响） |
| **自定义** | `true` | 使用下方「代理地址」字段配置的 URL（强制 `trust_env=False`） |
| **系统代理** | `null` | 读取后端进程环境变量 `HTTP_PROXY` / `HTTPS_PROXY` / `NO_PROXY` |

> **重要：「系统代理」指后端进程环境变量，不是浏览器用户电脑的系统设置。**
> 详见下文 [Windows 注意事项](#windows-注意事项) 与 [Docker 部署](#docker-部署)。

---

## 三种模式详解

### 关闭（`proxy_enable: false`）

- 不使用任何代理
- 强制 `trust_env=False`，即使后端进程环境中有 `HTTP_PROXY` 也**不会被读取**
- 适用于：能直连 yande.re 的环境

### 自定义（`proxy_enable: true`）

- 使用 UI 中填写的代理 URL
- 支持 `http://` 与 `socks5://` 协议（依赖 `requests[socks]`）
- 强制 `trust_env=False`，避免用户配置与环境变量冲突
- 适用于：使用固定代理服务器的场景

### 系统代理（`proxy_enable: null`，YAML 中写 `null` 或省略）

- 强制 `trust_env=True`，由 requests 自动读取进程环境变量
- 读取的变量：`http_proxy` / `https_proxy` / `all_proxy` / `no_proxy`（requests 标准库 `urllib.request.getproxies()` 行为）
- 适用于：宿主机/容器已设置全局代理的环境（如 Clash、V2RayN 等工具注入）

> **行为细节**：切换模式时，UI 中已填的代理地址**不会被清空**——切回「自定义」时会恢复，便于临时切换调试。

---

## Windows 注意事项

Windows 下「系统代理」的语义有歧义，需要明确：

| 用户预期 | 代码行为 | 说明 |
|----------|----------|------|
| Windows 设置 → 网络 → 代理（IE/LAN 设置） | ❌ **不会读取** | 该设置走 WinINET，不是 `HTTP_PROXY` 环境变量 |
| 代理工具开启「系统代理」（Clash for Windows / V2RayN 等） | ✅ **会读取** | 这些工具会同时注入 `HTTP_PROXY` 到进程环境变量 |
| PowerShell 设 `$env:HTTP_PROXY` | ⚠️ 仅当前 session | 关闭终端即失效 |
| cmd 设 `set HTTP_PROXY=...` | ⚠️ 仅当前 session | uvicorn 子进程读不到（除非用系统环境变量） |

### Windows 推荐用法

| 场景 | 推荐配置 |
|------|----------|
| 使用 Clash / V2RayN / Clash Verge 等代理工具 | 工具开启「系统代理」→ UI 选 **系统代理** |
| 手动配置 Windows 网络设置代理 | UI 选 **自定义** → 填 `http://127.0.0.1:<工具本地端口>` |
| 想让 uvicorn 进程读到代理 | 在「系统属性 → 环境变量」设为**系统变量**而非用户变量，然后重启终端 |

### Windows 下手动启动 uvicorn 的环境变量示例

PowerShell（仅当前 session）：
```powershell
$env:HTTP_PROXY = "http://127.0.0.1:7890"
$env:HTTPS_PROXY = "http://127.0.0.1:7890"
cd backend
uvicorn service:main_app --reload --host 0.0.0.0 --port 8000
```

cmd（仅当前 session）：
```cmd
set HTTP_PROXY=http://127.0.0.1:7890
set HTTPS_PROXY=http://127.0.0.1:7890
cd backend
uvicorn service:main_app --reload --host 0.0.0.0 --port 8000
```

---

## Docker 部署

`docker-compose.yml` 已默认透传代理环境变量：

```yaml
environment:
  - HTTP_PROXY=${HTTP_PROXY:-}
  - HTTPS_PROXY=${HTTPS_PROXY:-}
  - ALL_PROXY=${ALL_PROXY:-}
  - NO_PROXY=${NO_PROXY:-}
```

> **注意**：`${HTTP_PROXY:-}` 表示"宿主有则透传，没有则设为空"。**宿主的 `HTTP_PROXY` 必须在 `docker compose up` 之前设置好**，否则容器内进程读到的就是空字符串。

### Docker on Windows 额外说明

- Docker Desktop on Windows 走 WSL2 backend，**宿主 Windows 环境变量不会自动进入容器**
- 需在 `docker compose up` 之前在 PowerShell/cmd 设置 `HTTP_PROXY`，或在 `docker-compose.yml` 中写死默认值：
  ```yaml
  - HTTP_PROXY=http://host.docker.internal:7890  # 仅 Linux 容器通用写法
  ```
  Windows 容器内访问宿主服务的地址因 WSL2 / Hyper-V backend 不同而异，按需调整。

### 仅「系统代理」模式生效

容器内只有 UI 选「系统代理」时才会使用这些环境变量；「关闭」和「自定义」模式会被后端强制忽略（`trust_env=False`），即使容器环境变量有值也不会生效。

---

## 隐藏 Bug 修复记录

之前 `proxy_enable=false` 时后端代码不会真正关闭代理——原因是 Python `requests` 默认 `trust_env=True`，进程环境变量里的 `HTTP_PROXY` 会被自动读取生效。新版本强制 `OFF`/`CUSTOM` 模式 `trust_env=False`，**真正关闭**。

集成测试 `unit_test/common/test_proxy_mode.py::test_off_mode_does_not_use_env_proxy` 已将此行为钉死。

---

## 相关源码

- 后端枚举与配置：`backend/src/common/constant.py` `ProxyMode` · `backend/src/common/settings.py` `ApiConfig.proxy_enable`
- 统一 Session 配置函数：`backend/src/common/utils.py` `configure_proxy_session`
- 前端 UI：`frontend/src/views/Config.vue`（三段滑块）
- 测试覆盖：`unit_test/common/test_proxy_mode.py`