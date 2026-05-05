# Yande.re Spider Next

基于 Python 3.12 + FastAPI + Vue.js 3 的 yande.re **图片下载管理工具**

## 特点介绍

你是否经常在 yande.re 下载图片？
你是否苦恼于多个 tag 产生了大量重复文件？
你是否烦恼本地数以万计的库存不知如何归档查看？

现在你只需要交给这个平台即可：

- ✅ 支持文件下载并支持网页查询
- ✅ 支持高级搜索（标签、评分、格式、分辨率等多维度过滤）
- ✅ 支持 tag 收藏夹
- ✅ 完美解决 tag 重复图片反复下载问题
- 🚧 支持以搜索条件启动定时任务（规划中）
- 🚧 支持本地空间压缩，heif格式压缩占用空间是原来的1/10并且画质损失极低（规划中，目前存在偏色问题）

**使用注意**：
- 无法直连yande站时，需要自行准备梯子
- 未对文件名做uuid转换，请勿直接将该服务放至外网

## 功能特性

- ✅ 图片下载
- ✅ NSFW模糊
- ✅ 按tag分类浏览

### 后端功能
- ✅ FastAPI RESTful API 接口
- ✅ 高级查询功能（标签组合、分辨率、评分、文件大小等多维度过滤）
- ✅ 下载任务管理（支持暂停、恢复、取消）
- ✅ 多线程分段下载 + 进度实时同步
- ✅ 异步并发下载队列（可配置并发数）
- ✅ 断点续传 + MD5 校验（MD5失败只警告）
- ✅ 数据库持久化（MariaDB/SQLite）
- ✅ 代理配置热保存
- ✅ 瀑布流图库支持（本地/在线双模式）
- ✅ tag 收藏夹管理（支持在线/本地图片数量缓存）
- ✅ 本地标签搜索强制 AND 逻辑
- ✅ XML API 获取 yande 真实在线数量
- ✅ 预览图缓存接口安全性优化（移除 URL 参数注入风险）


## 技术栈

### 后端
- Python 3.12
- FastAPI
- SQLAlchemy
- MariaDB / SQLite
- Loguru
- Pydantic v2
- uv（依赖管理）

### 前端
- Vue.js 3
- Element Plus
- Pinia
- Vue Router
- Axios
- Vite

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

## API 接口

### 图库接口
- `POST /api/v1/gallery/load` - 加载图库（支持本地/在线模式）
- `GET /api/v1/gallery/image/{id}` - 获取图片详情
- `GET /api/v1/gallery/cache/preview/{filename}` - 获取预览图
- `GET /api/v1/gallery/cache/preview/generate/{image_id}` - 从原图生成缩略图
- `GET /api/v1/gallery/cache/preview/fetch/{image_id}` - 获取并缓存远程预览图

### 下载接口
- `POST /api/v1/download/task` - 创建下载任务
- `POST /api/v1/download/task/batch` - 批量创建下载任务
- `GET /api/v1/download/tasks` - 获取任务列表
- `GET /api/v1/download/task/{id}/progress` - 获取任务进度
- `POST /api/v1/download/task/{id}/start` - 启动任务
- `POST /api/v1/download/task/{id}/pause` - 暂停任务
- `POST /api/v1/download/task/{id}/resume` - 恢复任务
- `POST /api/v1/download/task/{id}/cancel` - 取消任务

### 配置接口
- `GET /api/v1/config/` - 获取系统配置
- `PUT /api/v1/config/api` - 更新API配置
- `PUT /api/v1/config/downloader` - 更新下载器配置
- `PUT /api/v1/config/database` - 更新数据库配置

### 收藏夹接口
- `GET /api/v1/favorites` - 获取所有收藏夹
- `GET /api/v1/favorites/with-count` - 获取收藏夹及图片数量
- `POST /api/v1/favorites` - 创建收藏夹
- `PUT /api/v1/favorites/{id}` - 更新收藏夹
- `DELETE /api/v1/favorites/{id}` - 删除收藏夹
- `POST /api/v1/favorites/{id}/online-count` - 更新在线数量
- `POST /api/v1/favorites/{id}/local-count` - 更新本地数量
- `POST /api/v1/favorites/{id}/refresh-online` - 从 yande XML API 刷新在线数量

## 高级搜索语法

支持 yande.re API 高级搜索语法：

### 标签语法
- `keyword` - 包含该标签
- `-keyword` - 排除该标签

### 字段比较
- `rating:e` - 评分为 Explicit
- `rating:q` - 评分为 Questionable
- `rating:s` - 评分为 Safe
- `width:>=1000` - 宽度大于等于 1000
- `height:>=1000` - 高度大于等于 1000
- `ext:png` - 文件格式为 PNG
- `score:>=100` - 评分大于等于 100
- `filesize:>=5000` - 文件大小大于等于 5000KB

### 组合示例
```
rating:e width:>=1000 height:>=1000 ext:png -explicit_tag +safe_tag
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

- [refactor-2026-04-28.md](docs/refactor-2026-04-28.md) - 导入路径和常量管理标准化
- [refactor-2026-05-02.md](docs/refactor-2026-05-02.md) - 批量下载、down_flag、YandeApi重试机制等修复

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

### 图片存储优化
- [ ] 本地图片空间压缩（HEIF/AVIF 格式自动转换）

### 远期计划
- [ ] Electron 桌面客户端
- [ ] 移动端适配优化

## 许可证

MIT License
