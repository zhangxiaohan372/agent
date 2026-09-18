# [ mcp_servers.json ]
#         │
#         ▼ 1. 进程层 (stdio_client)
#  启动各个独立子进程，接管标准输入输出 (read/write 管道)
#         │
#         ▼ 2. 协议层 (ClientSession + AsyncExitStack)
#  把管道包装成可 await 的 RPC 客户端；ExitStack 保证子进程长驻不掉线
#         │
#         ▼ 3. 路由层 (self.tool_to_session & self.tools)
#  提取工具清单转成大模型能懂的格式，并在大模型呼叫时反查 Session
#         │
#         ▼ 4. 执行层 (session.call_tool)
#  接收 LLM 参数并调用子进程执行，把结果返回给大模型

import asyncio
import json
from contextlib import AsyncExitStack
from pathlib import Path
from typing import Any, Dict, List
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


class MCPManager:
    def __init__(self, config_path: str | Path | None = None):
        if config_path is None:
            self.config_path = (
                Path(__file__).parent.parent.parent / "mcp_servers.json"
            )
        else:
            self.config_path = Path(config_path)

        # 1. 管理所有子进程与会话生命周期（防止局部变量退出后连接中断）
        self.exit_stack = AsyncExitStack()

        # 2. 路由表：{ "tool_name": session_instance }
        self.tool_to_session: Dict[str, ClientSession] = {}

        # 3. 供大模型使用的标准工具格式列表
        self.tools: List[Dict[str, Any]] = []

    async def connect_all(self):
        """步骤 1 & 2 & 3: 启动子进程、初始化会话并抓取工具列表"""
        if not self.config_path.exists():
            print(f"[MCP] 配置文件不存在: {self.config_path}")
            return

        with open(self.config_path, "r", encoding="utf-8") as f:
            config = json.load(f)

        servers = config.get("mcpServers", {})

        for server_name, server_cfg in servers.items():
            stdio_params = StdioServerParameters(
                command=server_cfg.get("command"),
                args=server_cfg.get("args", []),
                env=server_cfg.get("env"),
            )

            # 为每个服务创建独立的局部 stack，避免单点失败导致 AnyIO 作用域泄露
            server_stack = AsyncExitStack()
            try:
                # 步骤 1: 启动子进程并接管 stdin/stdout
                read_stream, write_stream = (
                    await server_stack.enter_async_context(
                        stdio_client(stdio_params)
                    )
                )

                # 步骤 2: 将字节流包装为 JSON-RPC 客户端会话
                session = await server_stack.enter_async_context(
                    ClientSession(read_stream, write_stream)
                )
                # 设置 5 秒超时，防止外部子进程（如 uvx 下载包）卡死整个请求
                await asyncio.wait_for(session.initialize(), timeout=5.0)
                print(f"[MCP] 已建立连接: {server_name}")

                # 步骤 3: 获取元数据并注册到大模型格式
                tools_result = await session.list_tools()
                for tool in tools_result.tools:
                    self.tool_to_session[tool.name] = session
                    self.tools.append(
                        {
                            "type": "function",
                            "function": {
                                "name": tool.name,
                                "description": tool.description or "",
                                "parameters": tool.input_schema,
                            },
                        }
                    )
                    print(f"  └─ 注册工具: {tool.name}")

                # 连接成功，才把该服务的生命周期托管给全局 exit_stack
                self.exit_stack.push_async_callback(server_stack.aclose)

            except Exception as e:
                # 💥 核心降级：连接失败时，立刻关掉刚才进入的半截子进程，释放 AnyIO 作用域
                await server_stack.aclose()
                print(f"[MCP警告] 服务 {server_name} 启动失败，已优雅降级并跳过该工具: {e}")

    async def execute_tool(
        self, tool_name: str, arguments: dict | None = None
    ) -> Any:
        """步骤 4: 收到大模型 Tool Call 时执行对应工具"""
        session = self.tool_to_session.get(tool_name)
        if not session:
            raise ValueError(f"未找到工具 '{tool_name}' 对应的 MCP 服务")

        arguments = arguments or {}
        # 调用对应子进程的 ClientSession 执行并等待返回
        # 通过进程间管道（IPC），向提供该工具的子进程发送一个符合 JSON-RPC 2.0 标准的「调用请求」，并异步等待它执行完毕返回结果。
        #session.call_tool 返回的是一个带有各种元数据的 CallToolResult 对象。
        # 为了让 Executor 和大模型能直接看懂，建议把里面的文本内容提取拼接为纯字符串：
        result = await session.call_tool(tool_name, arguments)
        
        text_blocks = []
        
        for block in result.content:
            text = getattr(block, "text", None)
            if text is not None:
                text_blocks.append(text)
            else:
                text_blocks.append(str(block))
        return "\n".join(text_blocks)

    async def close(self):
        """应用关闭时安全杀死所有子进程管道"""
        await self.exit_stack.aclose()
        print("[MCP] 所有连接与子进程已释放")