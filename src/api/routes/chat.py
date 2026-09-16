import json

from fastapi import APIRouter
from fastapi.responses import StreamingResponse

from api.schemas import ChatRequest
from api.session import get_agent

# 创建一个子路由实例
router = APIRouter()


@router.post("/chat/stream")
# req: ChatRequest 是 FastAPI 中用来接收并校验客户端传参（请求体）的语法。
async def chat_stream(req: ChatRequest):
    agent = get_agent(req.user_id, req.session_id)

    async def event_stream():
        try:
            async for event in agent.run_one_turn_stream(req.message):
                yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"
        except Exception as e:
            payload = {"type": "error", "message": str(e)}
            yield f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
