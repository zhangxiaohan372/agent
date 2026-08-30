import json


class Router:
    VALID_ROUTES = {
        "MEMORY_WRITE",
        "MEMORY_SEARCH",
        "KNOWLEDGE_SEARCH",
        "KNOWLEDGE_INGEST",
        "CHAT",
    }
    
    def __init__(self,client,prompt,model="deepseek-v4-pro"):
        self.client = client
        self.prompt = prompt
        self.model = model
        
    def route(self,messages):
        response = self.client.chat.completions.create(
            model=self.model,
            messages=[
                {
                    "role":"system",
                    "content":self.prompt
                },
                *messages
            ]
        )
        content = response.choices[0].message.content.strip()
        try:
            data = json.loads(content)
            routes = data.get("routes",[])
        except:
            return [
                {
                    "type":"CHAT",
                    "priority":1,
                    "query":messages
                }
            ]

        # 过滤非法route
        valid_routes = []

        for route in routes:
            # 先判断是不是字典
            if not isinstance(route, dict):
                continue
            route_type = route.get("type")
            if route_type not in self.VALID_ROUTES:
                continue
            valid_routes.append(
                {
                    "type": route_type,
                    "query": route.get("query", messages),
                    "priority": route.get("priority", 1),
                }
            )
        # 没有合法的route
        if not valid_routes:
            return [{"type": "CHAT", "priority": 1, "query": messages}]

        # 如果存在其他能力，则删除CHAT
        has_non_chat = any(route["type"] != "CHAT" for route in valid_routes)

        if has_non_chat:
            valid_routes = [route for route in valid_routes if route["type"] != "CHAT"]

        return valid_routes