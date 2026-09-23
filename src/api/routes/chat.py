import json
import os
import httpx
from fastapi import APIRouter, Header, HTTPException, Depends
from fastapi.responses import StreamingResponse

from api.schemas import ChatRequest
from api.session import get_agent

from pathlib import Path
from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parents[3]
load_dotenv(PROJECT_ROOT / ".env")

router = APIRouter()

BUSINESS_API_BASE_URL = os.getenv("BUSINESS_API_BASE_URL", "http://127.0.0.1:3001").rstrip("/")


async def authenticate_user(authorization: str | None = Header(default=None)) -> dict:
    """
    通过调用业务后端 (/api/auth/verify) 验证 Token 并提取真实身份信息
    """
    if not authorization:
        raise HTTPException(
            status_code=401,
            detail={"success": False, "data": None, "msg": "未登录，缺少认证令牌"}
        )

    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.get(
                f"{BUSINESS_API_BASE_URL}/api/auth/verify",
                headers={"Authorization": authorization}
            )
    except Exception as err:
        raise HTTPException(
            status_code=503,
            detail={"success": False, "data": None, "msg": f"业务身份认证服务连接失败: {str(err)}"}
        )

    if resp.status_code == 401:
        raise HTTPException(
            status_code=401,
            detail={"success": False, "data": None, "msg": "登录令牌已过期或无效，请重新登录"}
        )

    if not resp.is_success:
        raise HTTPException(
            status_code=resp.status_code,
            detail={"success": False, "data": None, "msg": f"身份认证异常: {resp.text}"}
        )

    body = resp.json()
    if not body.get("success"):
        raise HTTPException(
            status_code=401,
            detail={"success": False, "data": None, "msg": body.get("msg", "身份认证未通过")}
        )

    user_info = body.get("data") or {}
    role = user_info.get("role", "")
    permissions = user_info.get("permissions") or []

    # 校验 AI 使用权限
    if role != "admin" and "ai:use" not in permissions:
        raise HTTPException(
            status_code=403,
            detail={"success": False, "data": None, "msg": "抱歉，您暂无 AI 助手的使用权限"}
        )

    return user_info


@router.post("/chat/stream")
async def chat_stream(
    req: ChatRequest,
    authorization: str | None = Header(default=None),
    current_user: dict = Depends(authenticate_user),
):
    # 严格使用由业务端 Token 解密出的真实用户 ID，杜绝客户端伪造
    real_user_id = str(current_user["user_id"])
    agent = get_agent(real_user_id, req.session_id)

    async def event_stream():
        try:
            async for event in agent.run_one_turn_stream(req.message, auth_token=authorization):
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
