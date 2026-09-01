from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parent.parent
SRC_DIR = PROJECT_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from dotenv import load_dotenv

load_dotenv()

from openai import OpenAI
import os

from core.executor import AgentExecutor
from core.router import Router
from core.state import AgentState
from knowledge import KnowledgeManager
from managers.message_manager import MessageManager
from managers.prompt_manager import PromptManager
from managers.tool_manager import ToolManager
from memory import MemoryManager


class Agent:
    def __init__(self):
        self.client = OpenAI(
            base_url="https://api.deepseek.com/v1",
            api_key=os.getenv("OPENAI_API_KEY"),
        )
        self.tool_manager = ToolManager()

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
        )

    def _call_llm(self, stream=False):
        messages = self.message_manager.get_messages().copy()
        if not stream:
            response = self.client.chat.completions.create(
                model="deepseek-v4-pro",
                messages=messages,
                stream=False,
            )
            return response.choices[0].message

        response = self.client.chat.completions.create(
            model="deepseek-v4-pro",
            messages=messages,
            stream=True,
        )
        full_content = []
        for chunk in response:
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

    def generate(self):
        yield from self._call_llm(stream=True)

    def _is_ready_to_chat(self, routes):
        if not routes:
            return True
        return all(route.get("type") == "CHAT" for route in routes)

    def run_one_turn_stream(self, user_input, max_steps=3):
        state = AgentState(user_input)
        self.message_manager.add_user_message(user_input)

        for _ in range(max_steps):
            state.step += 1
            state.routes = self.router.route(self.message_manager.get_messages())

            yield {"type": "step", "step": state.step, "routes": state.routes}

            if self._is_ready_to_chat(state.routes):
                break

            context = self.executor.execute(state.routes)
            state.tool_results.extend(context)
            self.build_context(context)

            yield {"type": "context", "content": context}

        for text in self.generate():
            yield {"type": "token", "content": text}

        yield {"type": "done"}

    def run_one_turn(self, user_input, max_steps=3):
        print(f"[日志] 用户输入: {user_input}")
        chunks = []

        for event in self.run_one_turn_stream(user_input, max_steps):
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

    def chat(self):
        while True:
            user_input = input("用户：")
            if user_input.lower() == "exit":
                break
            self.run_one_turn(user_input)
