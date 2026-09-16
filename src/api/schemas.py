from pydantic import BaseModel, Field

# 规定请求返回的格式
class ChatRequest(BaseModel):
    message: str = Field(..., description="用户输入的聊天内容")
    user_id: str = Field(..., min_length=1, max_length=128, description="用户ID")
    session_id: str = Field(..., min_length=1, max_length=128, description="会话ID")
