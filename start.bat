@echo off
echo ========================================
echo Yande.re Spider - 启动脚本
echo ========================================
echo.

echo [1/3] 启动后端API服务...
start "API Server" cmd /k "python -m uvicorn api.main:app --reload --host 0.0.0.0 --port 8000"
timeout /t 3 /nobreak >nul

echo [2/3] 启动前端开发服务器...
cd frontend
start "Frontend Server" cmd /k "npm run dev"
cd ..
timeout /t 3 /nobreak >nul

echo [3/3] 打开浏览器...
start http://localhost:3000

echo.
echo ========================================
echo 启动完成！
echo ========================================
echo 后端API: http://localhost:8000
echo 前端界面: http://localhost:3000
echo API文档: http://localhost:8000/docs
echo ========================================
echo.
pause
