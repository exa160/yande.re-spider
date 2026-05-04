# 目录结构规范

## 项目结构

```
yande.re-spider-next-dev/
├── backend/                    # 后端代码
│   ├── src/                   # 核心源码（重构后）
│   │   ├── __init__.py       # init_app() + AppConfig
│   │   ├── api/              # API 路由层
│   │   │   ├── __init__.py   # APILoader 自动路由注册
│   │   │   └── v1/           # API 版本控制
│   │   │       ├── config.py      # 配置管理
│   │   │       ├── download.py    # 下载管理
│   │   │       ├── favorites.py   # 收藏夹管理
│   │   │       ├── gallery.py     # 图库展示
│   │   │       ├── query.py       # 查询接口
│   │   │       └── tag_cache.py   # 标签缓存
│   │   ├── common/           # 公共常量/配置
│   │   │   ├── constant.py   # ErrMsg枚举、PathConstant、RouterMap
│   │   │   └── settings.py   # Pydantic 配置模型
│   │   ├── dao/              # 数据访问层
│   │   │   ├── database.py   # BaseDAO + Session 管理
│   │   │   ├── favorite_dao.py # 收藏夹数据访问
│   │   │   ├── yande_data_dao.py # 图片数据访问
│   │   │   ├── tag_dao.py     # 标签缓存访问
│   │   │   └── artist_dao.py  # 艺术家缓存访问
│   │   ├── infrastructure/    # 基础设施层
│   │   │   ├── advanced_search.py # 高级搜索
│   │   │   ├── download_queue.py  # 下载队列
│   │   │   ├── downloader.py      # MultiDown 分段下载器
│   │   │   ├── image_cache.py     # 图片缓存
│   │   │   └── yande_api.py       # Yande API 客户端
│   │   ├── middleware/       # 中间件层
│   │   │   ├── downloader.py     # 下载中间件
│   │   │   ├── errors.py         # APIException、ErrorHandleMiddleware
│   │   │   ├── frontend_static.py # 前端静态资源
│   │   │   ├── loggers.py        # LoggerMiddleware
│   │   │   └── session.py        # RequestSessionMiddleware
│   │   ├── models/           # 数据模型层
│   │   │   ├── database/     # 数据库模型
│   │   │   ├── request/      # 请求模型（Request DTO）
│   │   │   ├── response/     # 响应模型（Response DTO）
│   │   │   ├── download.py   # FileInfo, IterStatus
│   │   │   ├── favorite.py   # 收藏夹模型
│   │   │   └── yande.py      # YandePostData, Rating
│   │   └── services/         # 业务逻辑层
│   ├── service.py            # 应用入口
│   ├── config/               # 配置文件目录
│   └── data/                 # 数据目录
├── frontend/                   # Vue.js 前端
│   ├── src/
│   │   ├── components/       # 组件
│   │   ├── views/            # 页面
│   │   ├── api/              # API 服务
│   │   └── router/           # 路由
│   └── package.json
├── docker-compose.yml          # 生产环境 Compose
├── docker-compose.override.yml # 本地开发覆盖配置
├── Dockerfile                  # 多阶段构建
├── docs/                      # 文档
├── config/                    # 配置文件
├── pyproject.toml             # Python 项目配置
└── uv.lock                   # uv 依赖锁定文件
```

## 层级职责划分

| 层级 | 职责 | 注意事项 |
|------|------|----------|
| `api/v1/` | 路由定义、参数校验、调用Service | **禁止**直接操作DAO/数据库 |
| `models/request/` | 接收前端参数的DTO | 使用 Pydantic `Field()` 定义校验规则 |
| `models/response/` | 返回给前端的DTO | 必须继承 `BaseResponse` |
| `services/` | 业务逻辑编排 | 处理复杂业务逻辑 |
| `dao/` | 数据访问封装 | **禁止**在DAO层处理业务逻辑 |
| `middleware/` | 横切关注点 | 错误处理、日志、下载中间件 |
| `common/` | 常量定义、枚举、路径配置 | **禁止**业务逻辑 |