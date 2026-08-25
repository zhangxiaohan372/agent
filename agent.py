from dotenv import load_dotenv
load_dotenv()

from openai import OpenAI
import os
from message_manager import MessageManager
from prompt_manager import PromptManager
from tool_manager import ToolManager
from memory import MemoryManager, EmbeddingManager
from knowledge import KnowledgeManager
from router import Router
class Agent:
    def __init__(self):
        # 1. openai客户端
        self.client = OpenAI(
            base_url="https://api.deepseek.com/v1",
            api_key=os.getenv("OPENAI_API_KEY")
        )
        # 2. messages
        self.message_manager = MessageManager()
        self.prompt_manager = PromptManager()
        self.message_manager.add_system_message(
            self.prompt_manager.get_system_prompt()
        )
        self.router = Router(
            client=self.client,
            prompt=self.prompt_manager.get_router_prompt(),
        )
        # 3. tools
        self.tool_manager = ToolManager()
        # 4. Memory
        self.memory_manager = MemoryManager()
        self.embedding_manager = EmbeddingManager()
        # 加上记忆提取器放到大模型里
        self.memory_extraction_prompt = self.prompt_manager.get_memory_extraction_prompt()
        # 5. Knowledge
        self.knowledge_manager = KnowledgeManager("knowledge_document/rag-test-document.md")
        # 6. executor
        self.executor = AgentExecutor(
            memory_manager=self.memory_manager,
            knowledge_manager=self.knowledge_manager,
            tool_manager=self.tool_manager
        )
    # 封装调用大模型的过程
    def _call_llm(self):
        messages = self.message_manager.get_messages().copy()
        response = self.client.chat.completions.create(
            model="deepseek-v4-pro",
            messages=messages,
            tools=self.tool_manager.tools
        )
        return response.choices[0].message
    # 调用工具的过程需要循环调用大模型，直到没有工具调用为止，因此封装成一个函数
    def _handle_tool_call(self,message):
        while message.tool_calls:
            for tool_call in message.tool_calls:
                result = self.tool_manager.execute_tool_call(tool_call)
                self.message_manager.add_tool_message(result)
            message = self._call_llm()
            self.message_manager.add_assistant_message(message)
        return message
    # 判断用户输入是否值得存入记忆（存入memory）
    def _extract_memory(self, user_input):
        response = self.client.chat.completions.create(
            model="deepseek-v4-pro",
            messages=[
                {
                    "role":"system", 
                    "content":self.memory_extraction_prompt
                },
                {
                    "role":"user", 
                    "content":user_input
                }
            ]
        )
        response =  response.choices[0].message.content.strip()

        if response == "NONE":
            return None

        return response
    def run_one_turn(self, user_input):
        # fix 直接让router决定要做什么，然后executor执行
        # 1. router决定要做什么
        routes = self.router.route(user_input)
        # 2. executor执行
        context = self.executor.execute(routes)
        # 3. 先在用户信息里面加入参考信息
        self.message_manager.add_user_message(
            f"""
                参考信息:
                {context}
            """
        )
        # 4. 把执行结果交给LLM
        # todo 之后会可能改这里直接让llm接收参数
        answer = self._call_llm()
        return answer

    def chat(self):
        while True:
            user_input = input("用户：")
            if user_input.lower() == "exit":
                break
            reply = self.run_one_turn(user_input)
            print(reply)

agent = Agent()
agent.chat()
