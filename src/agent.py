from pathlib import Path
import sys
import asyncio
PROJECT_ROOT = Path(__file__).resolve().parent.parent
SRC_DIR = PROJECT_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from dotenv import load_dotenv

load_dotenv()

from openai import AsyncOpenAI
import os

from core.executor import AgentExecutor
from core.pet_registration import PetRegistration, RegistrationStatus
from core.router import Router
from core.state import AgentState
from knowledge import KnowledgeManager
from managers.message_manager import MessageManager
from managers.prompt_manager import PromptManager
from managers.tool_manager import ToolManager
from managers.mcp_manager import MCPManager
from memory import MemoryManager


class Agent:
    def __init__(self, user_id="local", session_id="cli"):
        self._turn_lock = asyncio.Lock()
        self.pet_registration = PetRegistration()
        self.client = AsyncOpenAI(
            base_url="https://api.deepseek.com/v1",
            api_key=os.getenv("OPENAI_API_KEY"),
        )
        self.tool_manager = ToolManager()
        self.mcp_manager = MCPManager()
        self._mcp_initialized = False

        self.message_manager = MessageManager()
        self.prompt_manager = PromptManager()
        self.message_manager.add_system_message(self.prompt_manager.get_system_prompt())
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
        )

    async def _call_llm(self):
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

    def build_context(self, context):
        self.message_manager.add_context_message(context)

    async def generate(self):
        async for text in self._call_llm():
            yield text

    def _is_ready_to_chat(self, routes):
        if not routes:
            return True
        return all(route.get("type") == "CHAT" for route in routes)

    async def init_mcp(self):
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

    async def run_one_turn_stream(self, user_input, max_steps=3, auth_token=None):
        async with self._turn_lock:
            if not self._mcp_initialized:
                await self.init_mcp()

            state = AgentState(user_input)
            self.message_manager.add_user_message(user_input)
            reply_kind = None
            if self.pet_registration.status in {
                RegistrationStatus.COLLECTING,
                RegistrationStatus.AWAITING_CONFIRMATION,
            }:
                try:
                    reply_kind = await self.router.classify_registration_reply(
                        user_input, self.pet_registration.status.value
                    )
                except Exception:
                    reply_kind = None
                if reply_kind == "none":
                    reply_kind = None
                if reply_kind is None:
                    reply_kind = self.pet_registration.reply_kind(user_input)

            if reply_kind == "cancel":
                self.pet_registration.cancel()
                message = "已取消登记，数据未写入。"
                self.message_manager.messages.append({"role": "assistant", "content": message})
                yield {"type": "token", "content": message}
                yield {"type": "done"}
                return

            if reply_kind == "confirm":
                confirmed_fields = self.pet_registration.confirm()
                if confirmed_fields is None:
                    message = "当前没有完整且待确认的登记信息，请先提供资料并核对草稿。"
                else:
                    try:
                        result = await self.executor.execute_confirmed_pet(
                            confirmed_fields, auth_token
                        )
                    except asyncio.CancelledError:
                        self.pet_registration.finish(False, uncertain=True)
                        raise
                    self.pet_registration.finish(result["success"], result["uncertain"])
                    message = result["content"]
                    yield {"type": "context", "content": [result]}
                self.message_manager.messages.append({"role": "assistant", "content": message})
                yield {"type": "token", "content": message}
                yield {"type": "done"}
                return

            self.pet_registration.begin_revision()

            executed_routes = set()
            for _ in range(max_steps):
                state.step += 1
                state.routes = await self.router.route(self.message_manager.get_messages())
                yield {"type": "step", "step": state.step, "routes": state.routes}

                proposals = [
                    route for route in state.routes
                    if route.get("type") == "PET_REGISTRATION"
                    or (route.get("type") == "TOOL" and route.get("name") == "register_pet")
                ]
                if proposals:
                    if len(proposals) != 1:
                        self.pet_registration.cancel()
                        message = "一次只能核对一份登记，请重新提供登记信息。"
                        self.message_manager.messages.append({"role": "assistant", "content": message})
                        yield {"type": "token", "content": message}
                        yield {"type": "done"}
                        return

                    propose_result = self.pet_registration.propose(proposals[0].get("args"))

                    # 字段不完整：继续文字对话收集缺失信息
                    if self.pet_registration.status != RegistrationStatus.AWAITING_CONFIRMATION:
                        self.message_manager.messages.append({"role": "assistant", "content": propose_result})
                        yield {"type": "token", "content": propose_result}
                        yield {"type": "done"}
                        return

                    # 字段完整、进入待确认：发弹窗事件，不发文字消息
                    # 前端收到 confirm_dialog 后展示弹窗，用户点击后调 POST /api/chat/confirm
                    self.message_manager.messages.append({"role": "assistant", "content": propose_result})
                    yield {
                        "type": "confirm_dialog",
                        "fields": self.pet_registration.fields.copy(),
                        "prompt": propose_result,   # 也附带原始文字，前端可选用
                    }
                    yield {"type": "done"}
                    return

                if self.pet_registration.fields:
                    self.pet_registration.cancel()
                if self._is_ready_to_chat(state.routes):
                    break

                # 过滤当前单轮循环中已经执行过的相同路由，防止 Step 1 失败/完成后在 Step 2 盲目重复执行
                unexecuted_routes = []
                for r in state.routes:
                    import json
                    r_fp = (
                        str(r.get("type")),
                        str(r.get("name")),
                        json.dumps(r.get("args") or {}, sort_keys=True, ensure_ascii=False)
                    )
                    if r_fp not in executed_routes:
                        executed_routes.add(r_fp)
                        unexecuted_routes.append(r)

                if not unexecuted_routes:
                    # 本轮计划调用的能力已经全部执行过，无需重复执行，直接进入生成最终回复
                    break

                context = await self.executor.execute(unexecuted_routes)
                state.tool_results.extend(context)
                self.build_context(context)
                yield {"type": "context", "content": context}

            async for text in self.generate():
                yield {"type": "token", "content": text}
            yield {"type": "done"}

    async def run_one_turn(self, user_input, max_steps=3, auth_token=None):
        print(f"[日志] 用户输入: {user_input}")
        chunks = []

        async for event in self.run_one_turn_stream(user_input, max_steps, auth_token=auth_token):
            if event["type"] == "step":
                print(f"[日志] Agent 第 {event['step']} 步")
                print(f"[日志] Router 路由: {event['routes']}")
                if self._is_ready_to_chat(event["routes"]):
                    print("[日志] 路由为 CHAT，结束多步执行")
            elif event["type"] == "context":
                print(f"[日志] Executor 上下文: {event['content']}")
                print("[日志] 已注入上下文")
            elif event["type"] == "token":
                print(event["content"], end="", flush=True)
                chunks.append(event["content"])

        print()
        print("[日志] LLM 调用完成")
        return "".join(chunks)

    async def _async_chat(self):
        try:
            await self.init_mcp()
            while True:
                user_input = await asyncio.to_thread(input, "用户：")
                if user_input.strip().lower() == "exit":
                    break
                if not user_input.strip():
                    continue
                await self.run_one_turn(user_input)
        finally:
            await self.close()

    def chat(self):
        asyncio.run(self._async_chat())
