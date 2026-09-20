from pydantic import BaseModel, Field
from typing import Optional

# 规定请求返回的格式
class ChatRequest(BaseModel):
    message: str = Field(..., description="用户输入的聊天内容")
    session_id: str = Field(..., min_length=1, max_length=128, description="会话ID")
    user_id: Optional[str] = Field(None, description="兼容历史字段，服务端将严格基于Token鉴权结果取真实user_id")
