# Yande.re Spider Next

基于 FastAPI + Vue3 的 yande.re **图片下载管理工具**，支持图片批量下载、标签管理、本地浏览等功能。

## 功能预览

<details>
<summary>点击展开查看截图</summary>

| 首页瀑布流 | NSFW模式 | 暗黑模式 |
|:---:|:---:|:---:|
| ![首页](docs/pic/homepage.png) | ![NSFW](docs/pic/nsfwmode.png) | ![暗黑模式](docs/pic/darkmode.png) |

| 详情页 | 标签分类 | 标签缓存 |
|:---:|:---:|:---:|
| ![详情页](docs/pic/detail_view.png) | ![标签功能](docs/pic/tag_cache.png) | ![标签缓存](docs/pic/tag_update.png) |

| 标签搜索订阅 | 批量下载 | 配置页面 |
|:---:|:---:|:---:|
| ![标签搜索订阅](docs/pic/tag_search_subscribe.png) | ![批量下载](docs/pic/download_select.png) | ![配置](docs/pic/config.png) |

| NSFW模式 | 下载管理 | 移动端适配 | 移动端适配 |
|:---:|:---:|:---:|:---:|
| ![NSFW](docs/pic/nsfwmode.png) | ![下载](docs/pic/download.png) | ![移动端](docs/pic/download_select_mobile.png) | ![移动端](docs/pic/download_mobile.png) |

</details>

## 主要功能

- ✅ yande.re 图片批量下载（多线程 + 断点续传）
- ✅ 瀑布流图库 + 高级查询（本地 tag 默认精确匹配，`pan*` 前缀通配、`p*n` 中间通配，与 yande.re DSL 一致）
- ✅ 使用docker部署，支持MeriaDB/SQLite
- ✅ NSFW 友好模式，省流模式
- ✅ 数据库缓存，根据tag下载时相同ID不会重复下载
- ✅ 标签收藏夹管理（支持在线/本地数量缓存）
- ✅ 收藏夹定时调度（按 cron 表达式自动拉取新图入下载队列，增量/最大两种模式）

**使用注意**：
- 无法直连yande站时，需要自行准备梯子（见 [代理配置说明](docs/proxy-config.md)）
- 未对文件名做uuid转换，请勿直接将该服务放至外网

## 代理配置

UI 提供 **三态代理模式**：

- **关闭** — 不使用任何代理（强制不受环境变量影响）
- **自定义** — 使用下方填写的代理 URL（支持 `http://` / `socks5://`）
- **系统代理** — 读取后端进程环境变量 `HTTP_PROXY` / `HTTPS_PROXY`

> ⚠️ **「系统代理」指后端进程环境变量**，不是浏览器用户电脑的系统设置。
> Windows 用户请先阅读 [docs/proxy-config.md](docs/proxy-config.md#windows-注意事项)，否则可能误以为选了「系统代理」就走 Windows 网络设置里的代理（不会）。

Docker 部署时 `docker-compose.yml` 已默认透传 `HTTP_PROXY` 等环境变量（仅在 UI 选「系统代理」时生效）。

详见 [docs/proxy-config.md](docs/proxy-config.md)。


## 快速开始

### 开发环境（本地热重载）

适合修改代码、需要前后端热重载的开发场景。前端独立运行在 3000 端口，通过 Vite proxy 转发 `/api` 到后端 8000。

```bash
# 1. 安装依赖
uv sync                                  # 后端（推荐使用 uv）
# 或：cd backend && pip install -e .

cd frontend && npm install && cd ..      # 前端

# 2. 启动后端（监听 8000，--reload 自动重载）
cd backend
uvicorn service:main_app --port 8000 --reload --reload-dir ./src

# 3. 启动前端开发服务器（新终端）
cd frontend
npm run dev
```

访问：
- 前端（带热重载）：http://localhost:3000
- 后端 API：http://localhost:8000
- API 文档：http://localhost:8000/docs

### 生产环境

适合对外提供服务。前端构建后由后端 `frontend_static` 中间件直接托管，**单端口同时服务前端与 API**。

#### 方式 A：Docker（推荐）

```bash
# 拉取预构建的 latest 镜像并启动
docker compose -f docker-compose.yml up -d
```

镜像版本与构建策略详见下方 [分支与发布策略](#分支与发布策略) 章节。

#### 方式 B：手动部署

```bash
# 1. 构建前端（产物在 frontend/dist）
cd frontend
npm install
npm run build
cd ..

# 2. 安装后端依赖
uv sync

# 3. 启动后端（去掉 --reload，单进程服务前端 + API）
cd backend
uvicorn service:main_app --host 0.0.0.0 --port 8000 --workers 2
```

访问：
- 全部入口（前端 + API）：http://localhost:8000
- API 文档：http://localhost:8000/docs

## 分支与发布策略

> 代码从开发到上线的完整路径，对应 `.github/workflows/docker-build-push.yml` 的触发器。

### 分支层级

| 分支 | 角色 | 触发 Docker 镜像 |
|------|------|------------------|
| `feature/<name>` | 主开发分支，新功能在此实现 | （本地构建） |
| `next_feature` | 新特性验证专用分支（与 `feature` 区分） | （本地构建） |
| `next_dev` | 多功能集成验证 | `dev-<sha>` + 浮动 `dev` |
| `next` | RC 验证 | `rc-<sha>`（**无浮动指针**） |
| `vX.Y.Z` tag | 正式发布 | `X.Y.Z` + 浮动 `latest` |

### 完整流程

```
feature/<name>  ──┐
feature/<name2> ──┼─→  next_dev  ──→  next  ──→  vX.Y.Z tag  ──→  latest
feature/<name3> ──┘
```

1. 从 `feature` 拉新分支开发，完成后 MR 合入 `next_dev` 集成验证
2. 多个功能在 `next_dev` 验证通过后，`next_dev` 合入 `next` 作为 RC
3. RC 验证通过后，打 `vX.Y.Z` tag 发布为 latest

> **RC 无浮动指针的设计原因**：强制显式选择 SHA，避免自动化脚本误把 RC 镜像拉进生产。`rc-<sha>` 是给测试人员人肉验证用的，不是给自动化用的。

## 数据流程

### 在线模式
1. 用户浏览时，数据自动保存到数据库（down_flag=False）
2. 下载完成后，down_flag 更新为 True
3. 支持按评分、分辨率、格式等条件过滤

### 本地模式
1. 仅显示数据库中 down_flag=True 的记录
2. 从本地文件加载预览图和原图
3. 支持省流模式（不加载预览图）

## 架构设计

详见 [docs/design.md](docs/design.md)

## 重构记录

- [refactor-2026-05-17.md](docs/refactor-2026-05-17.md) - 图片预览优化、后端架构重组、前端交互改进
- [refactor-2026-05-02.md](docs/refactor-2026-05-02.md) - 批量下载、down_flag、YandeApi重试机制等修复
- [refactor-2026-04-28.md](docs/refactor-2026-04-28.md) - 导入路径和常量管理标准化

## 开发计划

### 近期功能
- [x] 本地模式 tag 收藏夹管理
- [x] 本地模式标签搜索强制 AND 逻辑
- [x] 收藏夹在线数量 XML API 获取
- [x] 下载器 MD5 失败只警告
- [x] 下载器断点续传优化
- [x] 本地 tag 默认精确匹配 + 通配兼容（`pan*` 前缀、`p*n` 中间，与 yande.re DSL 一致，详见 [spec](docs/superpowers/specs/2026-07-18-local-tag-exact-match-design.md)）
- [x] 收藏夹定时调度 UI 增强（立即执行 + 搜索）
- [x] 请求头可视化编辑（配置页 Dialog，详见 [spec](docs/superpowers/specs/2026-07-28-headers-editor-design.md)）
- [x] 全局 Element Plus 暗色模式适配
- [x] 代理三态模式（关闭 / 自定义 / 系统代理，详见 [代理配置说明](docs/proxy-config.md)）
- [_] 本地模式 tag 分组展示
- [ ] 点击详情页中的 tag 快速跳转查询
- [ ] 下载历史在数据库中记录

### 架构优化
- [x] 改为 uv 管理项目依赖
- [x] Docker 多阶段构建优化
- [x] Docker Compose 分离生产/开发配置
- [x] 增加异步定时任务功能（根据 tag 定时启动下载器）
- [x] DAO 异步化与配置简化（v1.1.7）
- [x] helper 函数返回类型注解完整化
- [ ] 多机部署优化：OBS 模式存储，Celery 托管下载器/定时任务
- [ ] moebooru like 平台兼容
- [ ] danbooru like 平台兼容

### 图片存储优化
- [ ] 本地图片空间压缩（HEIF/AVIF 格式自动转换）

### 远期计划
- [ ] Electron 桌面客户端
- [ ] 移动端适配优化

### 已知问题
- [ ] 省流模式本地失效
- [ ] 本地 tag 数量刷新慢

## 许可证

MIT License
