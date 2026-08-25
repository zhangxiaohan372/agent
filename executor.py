class AgentExecutor:
    def __init__(
        self,
        memory_manager,
        knowledge_manager,
        tool_manager
    ):
        self.memory_manager = memory_manager
        self.knowledge_manager = knowledge_manager
        self.tool_manager = tool_manager

    def execute(self,routes):

        results = []

        for route in routes:

            route_type = route.get("type")

            if route_type == "MEMORY_SEARCH":
                result = self.memory_manager.search(
                    route["query"]
                )
                results.append(result)
            
            elif route_type == "KNOWLEDGE_SEARCH":
                result = self.knowledge_manager.search(
                    route["query"]
                )
                results.append(result)
            
            elif route_type == "MEMORY_WRITE":
                result = self.memory_manager.save(route["query"])
                results.append(result)
            
            return results