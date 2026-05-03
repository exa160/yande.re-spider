# 阶段一：构建前端资源
FROM node:20-alpine AS frontend-builder

WORKDIR /frontend

# 只复制 package 文件用于依赖缓存
COPY frontend/package*.json ./

# 安装依赖（使用 lockfile 缓存）
RUN npm ci --prefer-offline

# 复制源代码并构建
COPY frontend/ ./
RUN npm run build

# 阶段二：运行后端服务
FROM python:3.12-slim

WORKDIR /app

# 安装 uv（用于快速 Python 包管理）
COPY --from=frontend-builder /frontend/dist ./frontend/dist/

# 复制依赖文件并安装
COPY pyproject.toml uv.lock ./
RUN pip install --no-cache-dir uv && \
    uv sync --no-dev --frozen

# 复制后端代码和配置
COPY backend/ ./backend/
COPY config/ ./config/

# 创建必要的目录
RUN mkdir -p /app/logs /app/data /app/downloads

EXPOSE 8000

CMD ["uvicorn", "service:app", "--host", "0.0.0.0", "--port", "8000"]