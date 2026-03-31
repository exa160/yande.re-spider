# Yande.re Spider Next

基于 Python 3.12 + FastAPI + Vue.js 3 的 yande.re 图片爬虫下载器

## 功能特性

### 后端功能
- ✅ FastAPI RESTful API 接口
- ✅ 高级查询功能（支持标签组合、分辨率、评分、文件大小等多维度过滤）
- ✅ 下载任务管理（支持暂停、恢复、取消）
- ✅ 多线程分段下载
- ✅ 断点续传
- ✅ MD5 校验
- ✅ 数据库持久化（MariaDB/SQLite）
- ✅ 自动去重检测

### 前端功能
- ✅ Vue.js 3 + Element Plus 界面
- ✅ 高级查询界面
- ✅ 瀑布流图库展示
- ✅ 无限滚动加载
- ✅ 图片预览和详情
- ✅ 下载任务管理界面
- ✅ 配置管理界面

## 技术栈

### 后端
- Python 3.12
- FastAPI
- SQLAlchemy
- MariaDB
- Loguru
- Pydantic

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
├── api/                    # FastAPI 后端
│   ├── main.py            # 主应用入口
│   └── routers/           # API 路由
│       ├── query.py       # 查询相关
│       ├── download.py    # 下载管理
│       ├── gallery.py     # 图库展示
│       └── config.py      # 配置管理
├── frontend/              # Vue.js 前端
│   ├── src/
│   │   ├── components/    # 组件
│   │   ├── views/         # 页面
│   │   ├── api/           # API 服务
│   │   └── router/        # 路由
│   └── package.json
├── utils/                 # 工具模块
│   ├── models.py         # 数据库模型
│   ├── database.py       # 数据库操作
│   └── constant.py       # 配置常量
├── spider/               # 爬虫模块
│   └── yande_api.py      # Yande API 客户端
├── test_api.py           # API 测试脚本
├── start.bat             # 启动脚本
└── requirements.txt      # Python 依赖
```

## 快速开始

### 1. 安装依赖

#### 后端依赖
```bash
python -m pip install -r requirements.txt
```

#### 前端依赖
```bash
cd frontend
npm install
```

### 2. 启动服务

#### 方式一：使用启动脚本（Windows）
```bash
start.bat
```

#### 方式二：手动启动
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
- ReDoc: http://localhost:8000/redoc

## API 接口文档

### 查询接口
- `POST /api/v1/query/search` - 高级查询
- `GET /api/v1/query/presets` - 获取查询预设
- `POST /api/v1/query/presets` - 保存查询预设

### 下载接口
- `POST /api/v1/download/task` - 创建下载任务
- `GET /api/v1/download/tasks` - 获取任务列表
- `POST /api/v1/download/task/{id}/start` - 启动任务
- `POST /api/v1/download/task/{id}/pause` - 暂停任务
- `POST /api/v1/download/task/{id}/resume` - 恢复任务
- `POST /api/v1/download/task/{id}/cancel` - 取消任务

### 图库接口
- `POST /api/v1/gallery/load` - 加载图库
- `GET /api/v1/gallery/image/{id}` - 获取图片详情

### 配置接口
- `GET /api/v1/config/` - 获取系统配置
- `PUT /api/v1/config/api` - 更新API配置
- `PUT /api/v1/config/downloader` - 更新下载器配置
- `PUT /api/v1/config/database` - 更新数据库配置

## 测试

### 运行API测试
```bash
python test_api.py
```

## 配置

### API配置
- `retry_times`: API重试次数（默认3）
- `timeout`: 超时时间（默认10秒）
- `proxy`: 代理地址

### 下载器配置
- `thread_num`: 下载线程数（默认4）
- `chunk_size`: 分块大小（默认10KB）
- `split_size`: 分段大小（默认200MB）

### 数据库配置
- `host`: 数据库主机
- `port`: 端口
- `user`: 用户名
- `password`: 密码
- `schema_name`: 数据库名

## 开发计划

- [ ] WebSocket 实时进度推送
- [ ] Electron 桌面客户端
- [ ] 查询条件预设管理
- [ ] 下载历史统计图表
- [ ] 移动端适配优化
- [ ] 多语言支持

## 许可证

MIT License

## 贡献

欢迎提交 Issue 和 Pull Request！
