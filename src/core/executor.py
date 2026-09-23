import asyncio


class AgentExecutor:
    def __init__(
        self,
        memory_manager,
        knowledge_manager,
        tool_manager,
        mcp_manager=None,
        user_id="local",
        session_id="cli",
        auth_token=None,
    ):
        self.memory_manager = memory_manager
        self.knowledge_manager = knowledge_manager
        self.tool_manager = tool_manager
        self.mcp_manager = mcp_manager
        self.user_id = user_id
        self.session_id = session_id
        self.auth_token = auth_token

    async def execute(self, routes):
        results = []
        for route in routes:
            route_type = route.get("type")
            query = route.get("query", "")
            if route_type == "MEMORY_SEARCH":
                raw = await asyncio.to_thread(
                    self.memory_manager.search,
                    query,
                    self.user_id,
                    self.session_id,
                )
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
                    self.memory_manager.save,
                    query,
                    category,
                    importance,
                    embedding,
                    self.user_id,
                    self.session_id,
                )
                results.append(
                    {
                        "type": "MEMORY_WRITE",
                        "content": f"已保存 [{category}|重要度{importance}] {query}",
                    }
                )
            elif route_type == "TOOL":
                tool_name = route.get("name")
                tool_args = (route.get("args") or {}).copy()
                if self.auth_token and "auth_token" not in tool_args:
                    tool_args["auth_token"] = self.auth_token

                # 优先判断是否是 MCP 注册的工具
                if self.mcp_manager and tool_name in self.mcp_manager.tool_to_session:
                    try:
                        content = await self.mcp_manager.execute_tool(tool_name, tool_args)
                    except Exception as e:
                        content = f"MCP 工具执行失败: {e}"
                else:
                    fn = self.tool_manager.available_functions.get(tool_name)
                    if fn is None:
                        content = f"未知工具: {tool_name}"
                    else:
                        try:
                            res = await asyncio.to_thread(fn, **tool_args)
                            if isinstance(res, dict) and "message" in res:
                                content = res["message"]
                            else:
                                content = str(res)
                        except Exception as e:
                            content = f"工具执行异常: {e}"
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
