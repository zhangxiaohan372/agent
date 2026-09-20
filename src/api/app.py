from pathlib import Path
import sys

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parents[2]
load_dotenv(PROJECT_ROOT / ".env")

SRC_DIR = Path(__file__).resolve().parent.parent
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from api.routes.chat import router as chat_router

app = FastAPI(title="Agent API")
app.add_middleware(
    CORSMiddleware,
    # 跨域三要素:请求头，请求方法，域名
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(chat_router, prefix="/api")
