import json
import re


class Router:
    VALID_ROUTES = {
        "MEMORY_WRITE",
        "MEMORY_SEARCH",
        "KNOWLEDGE_SEARCH",
        "KNOWLEDGE_INGEST",
        "TOOL",
        "CHAT",
    }

    MEMORY_RECALL_KEYWORDS = (
        "喜欢",
        "爱好",
        "记得",
        "还记得",
        "知道我",
        "我的",
        "我是谁",
        "我住",
        "常住",
        "职业",
        "专业",
        "偏好",
    )
    MEMORY_WRITE_KEYWORDS = ("喜欢", "爱好", "我是", "我住", "常住", "我在", "我的职业", "我的专业")
    WEATHER_KEYWORDS = ("天气", "气温", "下雨", "下雪", "温度")
    TIME_KEYWORDS = ("几点了", "现在时间", "什么时间", "当前时间", "今天几号", "什么日期", "几点")
    QUESTION_MARKERS = ("吗", "?", "？", "什么", "哪些", "谁", "多少", "怎么", "哪")

    def __init__(self, client, prompt, model="deepseek-v4-pro"):
        self.client = client
        self.prompt = prompt
        self.model = model

    def _is_question(self, text: str) -> bool:
        return any(marker in text for marker in self.QUESTION_MARKERS)

    def _has_context_type(self, messages, context_type: str) -> bool:
        marker = f"【{context_type}】"
        return any(
            message.get("role") == "system" and marker in message.get("content", "")
            for message in messages
        )

    def _has_tool_result(self, messages, tool_name: str) -> bool:
        marker = "【TOOL】"
        for message in messages:
            if message.get("role") != "system":
                continue
            content = message.get("content", "")
            if marker in content and tool_name in content:
                return True
        return False

    def _extract_city_from_memory_context(self, messages) -> str | None:
        for message in reversed(messages):
            if message.get("role") != "system":
                continue
            content = message.get("content", "")
            if "【MEMORY_SEARCH】" not in content:
                continue
            match = re.search(r"住在([^。\n\[]+)", content)
            if match:
                return match.group(1).strip()
            match = re.search(r"常住([^。\n\[]+)", content)
            if match:
                return match.group(1).strip()
        return None

    def _rule_based_route(self, user_input: str, messages):
        if not user_input:
            return None

        if any(keyword in user_input for keyword in self.MEMORY_RECALL_KEYWORDS):
            if self._is_question(user_input) and not self._has_context_type(
                messages, "MEMORY_SEARCH"
            ):
                return [
                    {
                        "type": "MEMORY_SEARCH",
                        "query": user_input,
                        "priority": 1,
                    }
                ]
            if (
                not self._is_question(user_input)
                and any(keyword in user_input for keyword in self.MEMORY_WRITE_KEYWORDS)
                and not self._has_context_type(messages, "MEMORY_WRITE")
            ):
                return [
                    {
                        "type": "MEMORY_WRITE",
                        "query": user_input,
                        "priority": 1,
                    }
                ]

        if any(keyword in user_input for keyword in self.WEATHER_KEYWORDS):
            if self._has_tool_result(messages, "get_current_weather"):
                return None
            if not self._has_context_type(messages, "MEMORY_SEARCH"):
                return [
                    {
                        "type": "MEMORY_SEARCH",
                        "query": "用户常住地或所在城市",
                        "priority": 1,
                    }
                ]
            city = self._extract_city_from_memory_context(messages)
            if city:
                return [
                    {
                        "type": "TOOL",
                        "name": "get_current_weather",
                        "args": {"location": city},
                        "priority": 1,
                    }
                ]

        if any(keyword in user_input for keyword in self.TIME_KEYWORDS):
            if not self._has_tool_result(messages, "get_current_time"):
                return [
                    {
                        "type": "TOOL",
                        "name": "get_current_time",
                        "args": {},
                        "priority": 1,
                    }
                ]

        return None

    def route(self, messages):
        user_input = ""
        for message in reversed(messages):
            if message.get("role") == "user":
                user_input = message.get("content", "")
                break

        rule_routes = self._rule_based_route(user_input, messages)
        if rule_routes is not None:
            return rule_routes

        response = self.client.chat.completions.create(
            model=self.model,
            messages=[
                {
                    "role": "system",
                    "content": self.prompt,
                },
                *messages,
            ],
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
