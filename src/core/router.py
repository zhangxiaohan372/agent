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
