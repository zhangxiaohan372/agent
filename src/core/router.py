import json


class Router:
    VALID_ROUTES = {
        "MEMORY_WRITE",
        "MEMORY_SEARCH",
        "KNOWLEDGE_SEARCH",
        "KNOWLEDGE_INGEST",
        "PET_REGISTRATION",
        "TOOL",
        "CHAT",
    }

    def __init__(self, client, prompt, model="deepseek-v4-pro"):
        self.client = client
        self.prompt = prompt
        self.model = model

    async def classify_registration_reply(self, text, status):
        """Classify a registration reply without allowing the model to write data."""
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
        try:
            intent = json.loads(response.choices[0].message.content).get("intent")
        except (AttributeError, TypeError, json.JSONDecodeError):
            return None
        return intent if intent in {"confirm", "cancel", "none"} else None

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
        content = response.choices[0].message.content.strip()
        try:
            data = json.loads(content)
            routes = data.get("routes", [])
        except json.JSONDecodeError:
            return [
                {
                    "type": "CHAT",
                    "priority": 1,
                    "query": user_input,
                }
            ]

        valid_routes = []

        for route in routes:
            if not isinstance(route, dict):
                continue
            route_type = route.get("type")
            if route_type not in self.VALID_ROUTES:
                continue
            arguments = route.get("args") or route.get("tool_args") or {}
            if not isinstance(arguments, dict):
                arguments = {}
            valid_routes.append(
                {
                    "type": route_type,
                    "query": route.get("query", user_input),
                    "priority": route.get("priority", 1),
                    "name": route.get("name") or route.get("tool_name"),
                    "args": {key: value for key, value in arguments.items() if key != "auth_token"},
                }
            )

        if not valid_routes:
            return [{"type": "CHAT", "priority": 1, "query": user_input}]

        has_non_chat = any(route["type"] != "CHAT" for route in valid_routes)

        if has_non_chat:
            valid_routes = [route for route in valid_routes if route["type"] != "CHAT"]

        return valid_routes
