"""
API接口测试脚本
"""
import sys
import os
import io

# 设置标准输出编码为UTF-8
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

# 添加项目根目录到路径
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from fastapi.testclient import TestClient
from api.main import app

client = TestClient(app)


def test_health_check():
    """测试健康检查接口"""
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"
    print("[PASS] 健康检查接口测试通过")


def test_root():
    """测试根路径"""
    response = client.get("/")
    assert response.status_code == 200
    assert "name" in response.json()
    print("[PASS] 根路径测试通过")


def test_query_search():
    """测试查询接口"""
    response = client.post(
        "/api/v1/query/search",
        json={
            "tags": "wallpaper",
            "min_width": 1920,
            "max_width": 3840,
            "rating": "Safe",
            "sort_by": "created_at",
            "sort_order": "desc",
            "page": 1,
            "page_size": 20
        }
    )
    assert response.status_code == 200
    assert "total" in response.json()
    print("[PASS] 查询接口测试通过")


def test_get_config():
    """测试获取配置接口"""
    response = client.get("/api/v1/config/")
    assert response.status_code == 200
    assert "api" in response.json()
    assert "downloader" in response.json()
    print("[PASS] 获取配置接口测试通过")


def test_gallery_load():
    """测试图库加载接口"""
    response = client.post(
        "/api/v1/gallery/load",
        json={
            "page": 1,
            "page_size": 20
        }
    )
    assert response.status_code == 200
    assert "total" in response.json()
    print("[PASS] 图库加载接口测试通过")


def test_download_task():
    """测试下载任务接口"""
    response = client.post(
        "/api/v1/download/task",
        json={
            "image_id": 12345,
            "file_url": "https://example.com/image.jpg",
            "save_path": "/tmp",
            "file_name": "test.jpg",
            "thread_num": 4
        }
    )
    assert response.status_code == 200
    assert "task_id" in response.json()
    print("[PASS] 创建下载任务接口测试通过")


if __name__ == "__main__":
    print("\n[INFO] 开始测试API接口...\n")

    try:
        test_health_check()
        test_root()
        test_query_search()
        test_get_config()
        test_gallery_load()
        test_download_task()

        print("\n[SUCCESS] 所有API接口测试通过！\n")
        print("[INFO] API文档地址：")
        print("  - Swagger UI: http://localhost:8000/docs")
        print("  - ReDoc: http://localhost:8000/redoc")
        print("\n[INFO] 启动API服务：")
        print("  python -m uvicorn api.main:app --reload --host 0.0.0.0 --port 8000")

    except AssertionError as e:
        print(f"\n[ERROR] 测试失败: {e}\n")
        sys.exit(1)
    except Exception as e:
        print(f"\n[ERROR] 测试出错: {e}\n")
        sys.exit(1)
