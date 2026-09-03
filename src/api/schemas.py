from pydantic import BaseModel, Field

# 规定请求返回的格式
class ChatRequest(BaseModel):
    message: str = Field(..., description="用户输入的聊天内容")
    session_id: str = Field(default="default", description="会话ID")