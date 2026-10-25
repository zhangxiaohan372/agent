from pathlib import Path
import sys
import os
import asyncio
from typing import AsyncGenerator, Dict, Any, Optional
from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parent.parent
SRC_DIR = PROJECT_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

load_dotenv()

from openai import AsyncOpenAI
from core.executor import AgentExecutor
from core.pet_registration import PetRegistration
from core.router import Router
from core.workflow import AgentWorkflow
from knowledge import KnowledgeManager
from managers.message_manager import MessageManager
from managers.prompt_manager import PromptManager
from managers.tool_manager import ToolManager
from managers.mcp_manager import MCPManager
from memory import MemoryManager
from utils.logger import get_logger


class Agent:
    """Agent 核心协调器。

    负责各基础模块的依赖注入（IoC）与生命周期管理，
    对外暴露统一的流式调用入口 run_one_turn_stream。
    """

    def __init__(self, user_id: str = "local", session_id: str = "cli"):
        self.user_id = str(user_id)
        self.session_id = str(session_id)
        self.logger = get_logger("agent")
        self._turn_lock = asyncio.Lock()

        # 1. 业务与模型基础设施
        self.client = AsyncOpenAI(
            base_url="https://api.deepseek.com/v1",
            api_key=os.getenv("OPENAI_API_KEY"),
        )
        self.pet_registration = PetRegistration(user_id=user_id, session_id=session_id)
        self.tool_manager = ToolManager()
        self.mcp_manager = MCPManager()
        self._mcp_initialized = False

        # 2. 会话上下文与提示词管理
        self.message_manager = MessageManager(user_id=user_id, session_id=session_id)
        self.prompt_manager = PromptManager()
        self.message_manager.add_system_message(self.prompt_manager.get_system_prompt())

        # 3. 意图路由器与执行器
        self.router = Router(
            client=self.client,
            prompt=self.prompt_manager.get_router_prompt(
                tool_list=self.tool_manager.describe_for_router()
            ),
        )
        self.memory_manager = MemoryManager()
        self.knowledge_manager = KnowledgeManager(
            PROJECT_ROOT / "knowledge_document" / "rag-test-document.md"
        )
        self.executor = AgentExecutor(
            memory_manager=self.memory_manager,
            knowledge_manager=self.knowledge_manager,
            tool_manager=self.tool_manager,
            mcp_manager=self.mcp_manager,
            user_id=user_id,
            session_id=session_id,
            pet_registration=self.pet_registration,
        )

        # 4. 编排工作流执行流水线
        self.workflow = AgentWorkflow(
            router=self.router,
            executor=self.executor,
            pet_registration=self.pet_registration,
            message_manager=self.message_manager,
            generate_fn=self.generate,
            user_id=user_id,
            session_id=session_id,
        )

    async def _call_llm(self) -> AsyncGenerator[str, None]:
        """调用大模型进行流式文本生成，并归档助手消息。"""
        messages = self.message_manager.get_messages().copy()
        response = await self.client.chat.completions.create(
            model="deepseek-v4-pro",
            messages=messages,
            stream=True,
        )
        full_content = []
        async for chunk in response:
            delta = chunk.choices[0].delta
            text = delta.content
            if text:
                yield text
                full_content.append(text)
        self.message_manager.messages.append(
            {
                "role": "assistant",
                "content": "".join(full_content),
            }
        )

    def build_context(self, context: list):
        self.message_manager.add_context_message(context)

    async def generate(self) -> AsyncGenerator[str, None]:
        async for text in self._call_llm():
            yield text

    async def init_mcp(self):
        """延迟加载并注册 MCP 扩展工具。"""
        if self._mcp_initialized:
            return
        await self.mcp_manager.connect_all()
        if self.mcp_manager.tools:
            self.tool_manager.tools.extend(self.mcp_manager.tools)
            self.router.prompt = self.prompt_manager.get_router_prompt(
                tool_list=self.tool_manager.describe_for_router()
            )
        self._mcp_initialized = True

    async def close(self):
        await self.mcp_manager.close()

    async def run_one_turn_stream(
        self, user_input: str, max_steps: int = 3, auth_token: Optional[str] = None
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """对外统一暴露的单轮流式执行接口。"""
        async with self._turn_lock:
            self.logger.info(f"[{self.user_id}:{self.session_id}] 收到用户请求: {user_input}")
            if not self._mcp_initialized:
                await self.init_mcp()

            async for event in self.workflow.execute_turn(
                user_input=user_input, max_steps=max_steps, auth_token=auth_token
            ):
                yield event

    async def run_one_turn(
        self, user_input: str, max_steps: int = 3, auth_token: Optional[str] = None
    ) -> str:
        """CLI 模式单轮辅助入口（委托给 cli 模块）。"""
        from cli import run_cli_turn
        return await run_cli_turn(self, user_input, max_steps=max_steps, auth_token=auth_token)

    def chat(self):
        """交互式终端聊天入口（委托给 cli 模块）。"""
        from cli import start_cli
        start_cli(self)


if __name__ == "__main__":
    Agent().chat()
