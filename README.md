# Yande.re Spider Next

基于 Python 3.12 + FastAPI + Vue.js 3 的 yande.re 图片画廊系统

## 功能特性

### 后端功能
- ✅ FastAPI RESTful API 接口
- ✅ 高级查询功能（标签组合、分辨率、评分、文件大小等多维度过滤）
- ✅ 下载任务管理（支持暂停、恢复、取消）
- ✅ 多线程分段下载 + 进度实时同步
- ✅ 断点续传 + MD5 校验
- ✅ 数据库持久化（MariaDB/SQLite）
- ✅ 代理配置热保存
- ✅ 瀑布流图库支持（本地/在线双模式）

### 前端功能
- ✅ Vue.js 3 + Element Plus 响应式界面
- ✅ 瀑布流图库展示（从左到右排序）
- ✅ 无限滚动加载
- ✅ 图片预览和详情（显示 tags）
- ✅ 下载任务管理界面（实时进度同步）
- ✅ 配置管理界面（代理开关热保存）
- ✅ 省流模式（不加载远程缩略图）
- ✅ 重试按钮（点击失败图标可重试）

## 技术栈

### 后端
- Python 3.12
- FastAPI
- SQLAlchemy
- MariaDB / SQLite
- Loguru
- Pydantic v2

### 前端
- Vue.js 3
- Element Plus
- Pinia
- Vue Router
- Axios
- Vite

## 项目结构

```
yande.re-spider-next/
├── backend/                    # 后端代码
│   ├── api/
│   │   └── routers/           # API 路由
│   │       ├── config.py      # 配置管理
│   │       ├── download.py   # 下载管理
│   │       ├── gallery.py     # 图库展示
│   │       └── query.py       # 查询接口
│   ├── config/
│   │   └── settings.py       # Pydantic 配置模型
│   ├── dao/                   # 数据访问层
│   │   ├── database.py        # MariaDBClient ORM
│   │   └── yande_data.py     # YandeDataRepository
│   ├── infrastructure/       # 基础设施层
│   │   ├── downloader.py    # MultiDown 分段下载器
│   │   ├── image_cache.py    # 图片缓存
│   │   └── yande_api.py      # Yande API 客户端
│   └── models/               # 数据模型
│       ├── yande.py           # YandePostData, Rating
│       └── download.py        # FileInfo, IterStatus
├── frontend/                   # Vue.js 前端
│   ├── src/
│   │   ├── components/       # 组件
│   │   ├── views/            # 页面
│   │   ├── api/              # API 服务
│   │   └── router/           # 路由
│   └── package.json
├── api/
│   └── main.py               # FastAPI 入口
├── spider/                    # 爬虫模块（CLI）
├── utils/                     # 工具模块
├── docs/                      # 文档
├── config/                    # 配置文件
├── gui/                       # GUI 模块
└── requirements.txt           # Python 依赖
```

## 快速开始

### 1. 安装依赖

#### 后端依赖
```bash
pip install -r requirements.txt
```

#### 前端依赖
```bash
cd frontend
npm install
```

### 2. 启动服务

```bash
# 启动后端API服务
python -m uvicorn api.main:app --reload --host 0.0.0.0 --port 8000

# 启动前端开发服务器
cd frontend
npm run dev
```

### 3. 访问应用
- 前端界面: http://localhost:3000
- 后端API: http://localhost:8000
- API文档: http://localhost:8000/docs

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

## 开发计划

- [ ] WebSocket 实时进度推送
- [ ] Electron 桌面客户端
- [ ] 查询条件预设管理
- [ ] 下载历史统计图表
- [ ] 移动端适配优化

## 许可证

MIT License
