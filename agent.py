from dotenv import load_dotenv
from openai import OpenAI
import os
from message_manager import MessageManager
from prompt_manager import PromptManager
from tool_manager import ToolManager
from memory_manager import MemoryManager
load_dotenv()

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
        # 加上记忆提取器放到大模型里
        self.memory_extraction_prompt = self.prompt_manager.get_memory_extraction_prompt()
    # 封装调用大模型的过程
    def _call_llm(self):
        messages = self.message_manager.get_messages().copy()
        memories = self.memory_manager.get_all()
        if memories:
            memory_prompt = "以下是用户的重要信息：\n"
            for memory in memories:
                memory_prompt += f"{memory}\n"
            messages.insert(
                1,
                {
                    "role":"system",
                    "content":memory_prompt
                }
            )
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
    def _extract_memory(self, user_input):
        response = self.client.chat.completions.create(
            model="deepseek-v4-pro",
            messages=[
                {"role":"system", "content":self.memory_extraction_prompt},
                {"role":"user", "content":user_input}
            ]
        )
        response =  response.choices[0].message.content

        if response == "NONE":
            return None

        return response
    def saveMemory(self, memory_text):
        if memory_text:
            memory_list = memory_text.splitlines()
            for memory in memory_list:
                memory = memory.strip()
                if memory:
                    self.memory_manager.save(memory)

    def run_one_turn(self, user_input):
        """处理一轮用户输入：记记忆 → 调模型 → 跑工具循环 → 返回回复文本。"""
        memory_text = self._extract_memory(user_input)
        if memory_text:
            memory_list = memory_text.splitlines()
            for memory in memory_list:
                memory = memory.strip()
                if memory:
                    self.memory_manager.save(memory)

        self.message_manager.add_user_message(user_input)
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
