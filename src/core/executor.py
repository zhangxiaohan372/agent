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
    ):
        self.memory_manager = memory_manager
        self.knowledge_manager = knowledge_manager
        self.tool_manager = tool_manager
        self.mcp_manager = mcp_manager
        self.user_id = user_id
        self.session_id = session_id

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
                tool_args = route.get("args") or {}
                tool_args = tool_args.copy() if isinstance(tool_args, dict) else {}
                tool_args.pop("auth_token", None)

                if tool_name == "register_pet":
                    results.append({
                        "type": "TOOL",
                        "content": "register_pet: 尚未通过代码层确认，拒绝写入。",
                    })
                    continue

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

    async def execute_confirmed_pet(self, fields, auth_token):
        if not auth_token:
            return {
                "type": "TOOL",
                "content": "register_pet: 缺少当前请求的认证令牌，数据未写入。",
                "success": False,
                "uncertain": False,
            }
        register_pet = self.tool_manager.available_functions["register_pet"]
        try:
            result = await asyncio.to_thread(
                register_pet, **fields, auth_token=auth_token
            )
        except Exception:
            result = {
                "success": False,
                "channel": "unexpected_error",
                "message": "登记结果未知，请检查业务服务状态。",
            }
        success = isinstance(result, dict) and result.get("success") is True
        uncertain = not isinstance(result, dict) or result.get("channel") in {
            "connection_error", "api_error", "unexpected_error",
        }
        message = (
            result.get("message", "登记失败。")
            if isinstance(result, dict) else "登记结果未知。"
        )
        if uncertain:
            message += "提交结果可能未知，请先到业务系统核实，勿重复提交。"
        return {
            "type": "TOOL",
            "content": f"register_pet: {message}",
            "success": success,
            "uncertain": uncertain,
        }

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
