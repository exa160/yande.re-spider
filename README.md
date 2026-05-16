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
- ✅ NSFW 友好模式，省流模式
- ✅ 数据库缓存，根据tag下载时相同ID不会重复下载
- ✅ 标签收藏夹管理（支持在线/本地数量缓存）
- ✅ 瀑布流图库 + 高级查询（标签组合、分辨率、评分、文件大小过滤）

**使用注意**：
- 无法直连yande站时，需要自行准备梯子
- 未对文件名做uuid转换，请勿直接将该服务放至外网


## 快速开始

### 1. 安装依赖

#### 后端依赖
```bash
# 使用 uv 管理依赖（推荐）
uv sync

# 或使用 pip
pip install -e .
```

#### 前端依赖
```bash
cd frontend
npm install
```

### 2. 启动服务

```bash
# 启动后端API服务（在 backend 目录下）
cd backend
uvicorn service:main_app --reload --host 0.0.0.0 --port 8000

# 正式环境部署（去除 --reload）
uvicorn service:main_app --host 0.0.0.0 --port 8000

# 启动前端开发服务器
cd frontend
npm run dev
```

### 3. 访问应用
- 前端界面: http://localhost:3000
- 后端API: http://localhost:8000
- API文档: http://localhost:8000/docs

### 4. Docker 部署

```bash
# 本地开发（自动构建）
docker compose up

# 生产环境（使用预构建镜像）
docker compose -f docker-compose.yml up

# 镜像通过 GitHub Actions 自动构建推送：
# - PR 到 next 分支 → 构建 git-<SHA> 标签
# - 推送 v*.*.* tag → 构建语义化版本标签 + latest
```

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
- [_] 本地模式 tag 分组展示
- [ ] 点击详情页中的 tag 快速跳转查询
- [ ] 下载历史在数据库中记录

### 架构优化
- [x] 改为 uv 管理项目依赖
- [x] Docker 多阶段构建优化
- [x] Docker Compose 分离生产/开发配置
- [ ] 增加异步定时任务功能（根据 tag 定时启动下载器）
- [ ] 多机部署优化：OBS模式存储，Celery托管下载器/定时任务
- [ ] moebooru like 平台兼容
- [ ] danbooru like 平台兼容

### 图片存储优化
- [ ] 本地图片空间压缩（HEIF/AVIF 格式自动转换）

### 远期计划
- [ ] Electron 桌面客户端
- [ ] 移动端适配优化

### 已知问题
- [ ] 省流模式本地失效
- [ ] 本地tag数量刷新慢

## 许可证

MIT License
