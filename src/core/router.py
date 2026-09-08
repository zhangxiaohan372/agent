import json


class Router:
    VALID_ROUTES = {
        "MEMORY_WRITE",
        "MEMORY_SEARCH",
        "KNOWLEDGE_SEARCH",
        "KNOWLEDGE_INGEST",
        "TOOL",
        "CHAT",
    }

    def __init__(self, client, prompt, model="deepseek-v4-pro"):
        self.client = client
        self.prompt = prompt
        self.model = model

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

    def route(self, messages):
        user_input = ""
        for message in reversed(messages):
            if message.get("role") == "user":
                user_input = message.get("content", "")
                break

        response = self.client.chat.completions.create(
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
            valid_routes.append(
                {
                    "type": route_type,
                    "query": route.get("query", user_input),
                    "priority": route.get("priority", 1),
                    "name": route.get("name") or route.get("tool_name"),
                    "args": route.get("args") or route.get("tool_args") or {},
                }
            )

        if not valid_routes:
            return [{"type": "CHAT", "priority": 1, "query": user_input}]

        has_non_chat = any(route["type"] != "CHAT" for route in valid_routes)

        if has_non_chat:
            valid_routes = [route for route in valid_routes if route["type"] != "CHAT"]

        return valid_routes
