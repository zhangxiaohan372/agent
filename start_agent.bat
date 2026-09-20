@echo off
chcp 65001 >nul
echo ========================================================
echo 正在启动 AI Agent 智能问答服务 (FastAPI on Port 8000)...
echo ========================================================
if exist ".venv\Scripts\activate.bat" (
    call .venv\Scripts\activate.bat
)
uvicorn src.api.app:app --host 0.0.0.0 --port 8000 --reload
pause
