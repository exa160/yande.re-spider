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

# 阶段二：后端依赖构建（编译 C 扩展）
FROM python:3.12-slim AS backend-builder

WORKDIR /build

# 安装编译必需的系统库和工具
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    python3-dev \
    libmariadb-dev \
    && rm -rf /var/lib/apt/lists/*

# 复制依赖文件
COPY pyproject.toml uv.lock ./

# 安装 uv 并同步依赖（会编译 mariadb C 扩展）
RUN pip install --no-cache-dir uv && \
    uv sync --no-dev --frozen

# 阶段三：最终运行镜像
FROM python:3.12-slim

WORKDIR /app

# 安装 mariadb 运行时库（C 扩展需要）
RUN apt-get update && apt-get install -y --no-install-recommends \
    libmariadb3 \
    && rm -rf /var/lib/apt/lists/*

# 从前端构建阶段复制静态文件
COPY --from=frontend-builder /frontend/dist ./frontend/dist/

# 从后端构建阶段复制已安装的虚拟环境
COPY --from=backend-builder /build/.venv ./.venv

# 复制后端代码和配置
COPY backend/ ./
COPY config/ ./config/

# 创建运行时需要的目录
RUN mkdir -p /app/logs /app/data /app/downloads

EXPOSE 8000

ENV PATH="/app/.venv/bin:$PATH"
CMD ["uvicorn", "service:app", "--host", "0.0.0.0", "--port", "8000"]