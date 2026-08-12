from dotenv import load_dotenv
load_dotenv()

from openai import OpenAI
import os
from message_manager import MessageManager
from prompt_manager import PromptManager
from tool_manager import ToolManager
from memory import MemoryManager, EmbeddingManager

class Agent:
    def __init__(self):
        #1.openai客户端
        self.client = OpenAI(
            base_url="https://api.deepseek.com/v1",
            api_key=os.getenv("OPENAI_API_KEY")
        )
        #2.messages
        self.message_manager = MessageManager()
        self.prompt_manager = PromptManager()
        self.message_manager.add_system_message(
            self.prompt_manager.get_system_prompt()
        )
        #3.tools
        self.tool_manager = ToolManager()
        #让大模型拥有长期记忆
        self.memory_manager = MemoryManager()
        self.embedding_manager = EmbeddingManager()
        # 加上记忆提取器放到大模型里
        self.memory_extraction_prompt = self.prompt_manager.get_memory_extraction_prompt()
        self.memory_search_prompt = self.prompt_manager.get_memory_search_prompt()
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
    # 判断用户输入是否值得存入数据库
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
    # 判断用户输入是否需要调用数据库中的数据回答
    def _need_memory_search(self, user_input):
        response = self.client.chat.completions.create(
            model="deepseek-v4-pro",
            messages=[
                {
                    "role":"system",
                    "content":self.memory_search_prompt
                },
                {
                    "role":"user",
                    "content":user_input
                }
            ]
        )
        response = response.choices[0].message.content.strip()
        if response == "YES":
            return True
        else:
            return False
    def run_one_turn(self, user_input):
        """处理一轮用户输入：记记忆 → 调模型 → 跑工具循环 → 返回回复文本。"""
        memory_text = self._extract_memory(user_input)
        if memory_text:
            memory_list = memory_text.splitlines()
            for line in memory_list:
                line = line.strip()
                if not line or line == "NONE":
                    continue
                parts = [part.strip() for part in line.split("|")]
                if len(parts) != 3:
                    continue
                memory, category, importance = parts
                try:
                    importance = int(importance)
                except ValueError:
                    continue
                embedding = self.embedding_manager.embed(memory)
                self.memory_manager.save(memory, category, importance, embedding)
        self.message_manager.add_user_message(user_input)
        if self._need_memory_search(user_input):
            memory_list = self.memory_manager.search(user_input)
            # 加入messgae当中，再次请求模型回答问题
            self.message_manager.add_memory_message(memory_list)
        assistant_message = self._call_llm()
        self.message_manager.add_assistant_message(assistant_message)
        assistant_message = self._handle_tool_call(assistant_message)
        return assistant_message.content

    def chat(self):
        while True:
            user_input = input("用户：")
            if user_input.lower() == "exit":
                break
            reply = self.run_one_turn(user_input)
            print(reply)

agent = Agent()
agent.chat()
