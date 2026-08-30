from dotenv import load_dotenv

load_dotenv()

from openai import OpenAI
import os
from message_manager import MessageManager
from prompt_manager import PromptManager
from tool_manager import ToolManager
from memory import MemoryManager
from knowledge import KnowledgeManager
from router import Router
from executor import AgentExecutor


class Agent:
    def __init__(self):
        # 1. openai客户端
        self.client = OpenAI(
            base_url="https://api.deepseek.com/v1", api_key=os.getenv("OPENAI_API_KEY")
        )
        # 2. messages && router
        self.message_manager = MessageManager()
        self.prompt_manager = PromptManager()
        # 将提示词加入到messages中
        self.message_manager.add_system_message(self.prompt_manager.get_system_prompt())
        self.router = Router(
            client=self.client,
            prompt=self.prompt_manager.get_router_prompt(),
        )
        # 3. tools
        self.tool_manager = ToolManager()
        # 4. Memory
        self.memory_manager = MemoryManager()
        # 5. Knowledge
        self.knowledge_manager = KnowledgeManager(
            "knowledge_document/rag-test-document.md"
        )
        # 6. executor
        self.executor = AgentExecutor(
            memory_manager=self.memory_manager,
            knowledge_manager=self.knowledge_manager,
        )

    # 封装调用大模型的过程
    def _call_llm(self):
        messages = self.message_manager.get_messages().copy()
        response = self.client.chat.completions.create(
            model="deepseek-v4-pro", messages=messages, tools=self.tool_manager.tools
        )
        return response.choices[0].message

    # LLM 返回 tool_calls 时 “循环”：执行工具 → 回传结果 → 再调 LLM，直到不再调用工具
    def _handle_tool_call(self, message, max_rounds=5):
        rounds = 0
        while message.tool_calls:
            rounds += 1
            if rounds > max_rounds:
                print("[日志] 工具调用次数已达上限，停止循环")
                break
            for tool_call in message.tool_calls:
                print(
                    f"[日志] 调用工具: {tool_call.function.name}({tool_call.function.arguments})"
                )
                tool_message = self.tool_manager.execute_tool_call(tool_call)
                self.message_manager.add_tool_message(tool_message)
            message = self._call_llm()
            self.message_manager.add_assistant_message(message)
        return message

    def build_context(self, context):
        self.message_manager.add_context_message(context)

    def generate(self):
        message = self._call_llm()
        self.message_manager.add_assistant_message(message)
        return self._handle_tool_call(message)
    def _is_ready_to_chat(self, routes):
        if not routes:
            return True
        return all(route.get("type") == "CHAT" for route in routes)
    # fix 加入agentloop
    def run_one_turn(self, user_input, max_steps=3):
        print(f"[日志] 用户输入: {user_input}")
        # 1. 先把用户消息加入历史
        self.message_manager.add_user_message(user_input)
        for step in range(max_steps):
            print(f"[日志] Agent 第 {step} 步")
            # 2. Router 基于完整 messages 决策
            routes = self.router.route(self.message_manager.get_messages())
            print(f"[日志] Router 路由: {routes}")
            if self._is_ready_to_chat(routes):
                print("[日志] 路由为 CHAT，结束多步执行")
                break
            context = self.executor.execute(routes)
            print(f"[日志] Executor 上下文: {context}")
            self.build_context(context)
            print("[日志] 已注入上下文")

        print("[日志] 开始调用 LLM")
        answer = self.generate()
        print("[日志] LLM 调用完成")
        return answer

    def chat(self):
        while True:
            user_input = input("用户：")
            if user_input.lower() == "exit":
                break
            reply = self.run_one_turn(user_input)
            print(reply.content)


agent = Agent()
agent.chat()
