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