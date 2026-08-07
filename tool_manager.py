from datetime import datetime
import json
class ToolManager:
    def __init__(self):
        # 当前可用工具字典
        self.available_functions = {}
        # 工具列表
        self.tools=[]
        self.register(
            name="get_current_weather",
            description="获取天气",
            function=self.get_current_weather,
            parameters={
                "type":"object",
                "properties":{
                    "location":{
                        "type":"string",
                        "description":"城市名称"
                    }
                },
                "required":["location"]
            }
        )

        self.register(
            name="get_current_time",
            description="获取时间",
            function=self.get_current_time,
            parameters={
                "type":"object",
                "properties":{},
                "required":[]
            }
        )
    def get_current_weather(self, location):

        if "北京" in location:
            return "北京天气晴天，30℃"

        return "暂时不知道该城市天气"


    def get_current_time(self):

        return datetime.now().strftime(
            "%Y-%m-%d %H:%M:%S"
        )

    def execute_tool_call(self,tool_call):
        # 工具名称
        tool_name = tool_call.function.name
        # 工具参数
        args = json.loads(tool_call.function.arguments)
        # 调用工具的结果
        result = self.available_functions[tool_name](**args)
        tool_message = {
            "role":"tool",
            "tool_call_id":tool_call.id,
            "content":result
        }
        return tool_message

    def register(
        self,
        name,
        description,
        function,
        parameters
    ):
        self.available_functions[name] = function

        self.tools.append({
            "type":"function",
            "function":{
                "name":name,
                "description":description,
                "parameters":parameters
            }
        })