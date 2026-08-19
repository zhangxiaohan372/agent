import json

class Router:
    VALID_ROUTES = {
        "DIRECT",
        "MEMORY",
        "KNOWLEDGE_QUERY",
        "KNOWLEDGE_INGEST",
        "TOOL",
    }
    
    def __init__(self,client,prompt,model="deepseek-v4-pro"):
        self.client = client
        self.prompt = prompt
        self.model = model
        
    def route(self,user_input):
        response = self.client.chat.completions.create(
            model=self.model,
            messages=[
                {
                    "role":"system",
                    "content":self.prompt
                },
                {
                    "role":"user",
                    "content":user_input
                }
            ]
        )
        content = response.choices[0].message.content.strip()

        try:
            data = json.loads(content)
            routes = data.get("routes",[])
        except:
            return ["DIRECT"]

        routes = [
            route for route in routes if route in self.VALID_ROUTES
        ]
        if not routes:
            return ["DIRECT"]

        if len(routes) > 1:
            routes = [route for route in routes if route != "DIRECT"]

        return routes or ["DIRECT"]