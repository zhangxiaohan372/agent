import json
import logging
from pydantic import ValidationError
from core.schemas import RouterDecision, RegistrationIntentDecision, RouteItem, RouteType

logger = logging.getLogger(__name__)


class Router:
    VALID_ROUTES = {r.value for r in RouteType}

    def __init__(self, client, prompt, model="deepseek-v4-pro"):
        self.client = client
        self.prompt = prompt
        self.model = model

    async def classify_registration_reply(self, text, status):
        """Classify a registration reply with Pydantic validation."""
        response = await self.client.chat.completions.create(
            model=self.model,
            messages=[
                {
                    "role": "system",
                    "content": (
                        "你是登记确认意图分类器。只返回 JSON，格式为 "
                        '{"intent":"confirm|cancel|none"}。'
                        "confirm 仅表示用户明确同意提交当前已经展示的完整登记信息；"
                        "cancel 表示用户明确放弃、取消或暂不提交；"
                        "none 表示补充/修改字段、提问、犹豫、语义不明确或与登记无关。"
                        "不要把‘我不确定’、‘先看看’识别为 confirm。"
                    ),
                },
                {
                    "role": "user",
                    "content": f"当前登记状态：{status}\n用户回复：{text}",
                },
            ],
            response_format={"type": "json_object"},
            temperature=0,
        )
        content = (response.choices[0].message.content or "").strip()
        try:
            decision = RegistrationIntentDecision.model_validate_json(content)
            return decision.intent
        except (ValidationError, Exception) as e:
            logger.warning(f"[Router] 意图分类 Schema 校验未通过: {e}, 原文: {content}")
            return None

    # 路由器判断要聊天、查记忆还是查知识库时，只取最近 6 条用户或助手消息，并参考当前轮刚查到的内容。
    def _build_router_messages(self, messages, history_limit=6):
        """保留近期对话语义，同时隔离业务 system prompt 和旧工具上下文。"""
        last_user_index = next(
            (
                index
                for index in range(len(messages) - 1, -1, -1)
                if messages[index].get("role") == "user"
            ),
            None,
        )
        if last_user_index is None:
            return [{"role": "user", "content": "用户当前请求："}]

        user_input = messages[last_user_index].get("content", "")
        recent_dialogue = [
            {
                "role": message["role"],
                "content": message.get("content", ""),
            }
            for message in messages[:last_user_index]
            if message.get("role") in {"user", "assistant"}
            and message.get("content")
        ][-history_limit:]
        current_context = [
            message.get("content", "")
            for message in messages[last_user_index + 1:]
            if message.get("role") == "system" and message.get("content")
        ]

        content = f"用户当前请求：\n{user_input}"
        if current_context:
            content += "\n\n当前轮已获取的上下文：\n" + "\n\n".join(current_context)
        return [
            *recent_dialogue,
            {"role": "user", "content": content},
        ]

    # route主线路   
    async def route(self, messages):
        user_input = ""
        for message in reversed(messages):
            if message.get("role") == "user":
                user_input = message.get("content", "")
                break

        response = await self.client.chat.completions.create(
            model=self.model,
            messages=[
                {
                    "role": "system",
                    "content": self.prompt,
                },
                *self._build_router_messages(messages),
            ],
            response_format={"type": "json_object"},
            temperature=0,
        )
        content = (response.choices[0].message.content or "").strip()

        # 使用 Pydantic 进行强类型解析与模式校验
        try:
            decision = RouterDecision.model_validate_json(content)
            routes = decision.to_dict_list()
            if not routes:
                return [{"type": "CHAT", "priority": 1, "query": user_input, "name": None, "args": {}}]
            for r in routes:
                if not r.get("query"):
                    r["query"] = user_input
            return routes
        except ValidationError as e:
            logger.warning(f"[Router] 输出未通过 Pydantic 校验: {e}, 原文: {content}")
            # 容错自愈降级：尝试逐项解析可挽救的合法路由，若完全非法则回退 CHAT
            try:
                raw_data = json.loads(content)
                raw_routes = raw_data.get("routes", []) if isinstance(raw_data, dict) else []
                rescued = []
                for item in raw_routes:
                    try:
                        rescued.append(RouteItem.model_validate(item))
                    except ValidationError:
                        continue
                if rescued:
                    decision = RouterDecision(routes=rescued)
                    routes = decision.to_dict_list()
                    for r in routes:
                        if not r.get("query"):
                            r["query"] = user_input
                    return routes
            except Exception:
                pass
            return [{"type": "CHAT", "priority": 1, "query": user_input, "name": None, "args": {}}]
        except json.JSONDecodeError as e:
            logger.error(f"[Router] JSON 解析失败: {e}, 原文: {content}")
            return [{"type": "CHAT", "priority": 1, "query": user_input, "name": None, "args": {}}]
