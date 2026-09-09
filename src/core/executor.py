import asyncio


class AgentExecutor:
    def __init__(self, memory_manager, knowledge_manager, tool_manager):
        self.memory_manager = memory_manager
        self.knowledge_manager = knowledge_manager
        self.tool_manager = tool_manager

    async def execute(self, routes):
        results = []
        for route in routes:
            route_type = route.get("type")
            query = route.get("query", "")
            if route_type == "MEMORY_SEARCH":
                raw = await asyncio.to_thread(self.memory_manager.search, query)
                results.append(self._format_memory_search(raw))

            elif route_type == "KNOWLEDGE_SEARCH":
                raw = await asyncio.to_thread(self.knowledge_manager.search, query)
                results.append(self._format_knowledge_search(raw))

            elif route_type == "MEMORY_WRITE":
                category = "preference"
                importance = 7
                embedding = await asyncio.to_thread(
                    self.memory_manager.embedding_manager.embed, query
                )
                await asyncio.to_thread(
                    self.memory_manager.save, query, category, importance, embedding
                )
                results.append(
                    {
                        "type": "MEMORY_WRITE",
                        "content": f"已保存 [{category}|重要度{importance}] {query}",
                    }
                )
            elif route_type == "TOOL":
                tool_name = route.get("name")
                tool_args = route.get("args") or {}
                fn = self.tool_manager.available_functions.get(tool_name)
                if fn is None:
                    content = f"未知工具: {tool_name}"
                else:
                    content = str(await asyncio.to_thread(fn, **tool_args))
                results.append({"type": "TOOL", "content": f"{tool_name}: {content}"})
            elif route_type == "CHAT":
                results.append({"type": "CHAT", "content": ""})

        return results

    def _format_memory_search(self, rows):
        if not rows:
            return {"type": "MEMORY_SEARCH", "content": "未找到相关记忆。"}
        lines = []

        for row in rows:
            content = row[1]
            category = row[2]
            importance = row[3]
            lines.append(f"- [{category}|重要度{importance}] {content}")

        return {"type": "MEMORY_SEARCH", "content": "\n".join(lines)}

    def _format_knowledge_search(self, chunks):
        if not chunks:
            return {"type": "KNOWLEDGE_SEARCH", "content": "未找到相关知识。"}

        lines = []

        for chunk in chunks:
            lines.append(
                f"- [{chunk['source']}|相似度{chunk['score']:.4f}] {chunk['content']}"
            )

        return {"type": "KNOWLEDGE_SEARCH", "content": "\n".join(lines)}
