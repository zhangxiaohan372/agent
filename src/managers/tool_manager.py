from datetime import datetime
import json
from tools.pet_tool import register_pet, query_pets


class ToolManager:
    def __init__(self):
        # 当前可用工具字典
        self.available_functions = {}
        # 工具列表
        self.tools = []

        self.register(
            name="register_pet",
            description="向管理系统登记新增流浪动物（猫咪/狗狗）档案。名称、区域、品种、年龄、健康状态和健康描述必须由用户提供并逐项确认；缺失时先询问，不要猜测。",
            function=register_pet,
            parameters={
                "type": "object",
                "properties": {
                    "pet_type": {
                        "type": "string",
                        "enum": ["cat", "dog"],
                        "description": "动物类型：cat（猫咪）或 dog（狗狗）",
                    },
                    "name": {
                        "type": "string",
                        "description": "动物名字/昵称，如'小橘'、'大黄'",
                    },
                    "area": {
                        "type": "string",
                        "description": "发现或常出没区域，如'图书馆草坪'、'二教'、'一食堂附近'",
                    },
                    "breed": {
                        "type": "string",
                        "description": "用户提供的品种，如'橘猫'、'三花猫'、'田园犬'",
                    },
                    "age": {
                        "type": "string",
                        "description": "用户提供的估算年龄，如'约1岁'或'幼年'",
                    },
                    "health_status": {
                        "type": "string",
                        "description": "用户提供的健康状态，如'健康'、'需要关注'、'紧急'",
                    },
                    "health": {
                        "type": "string",
                        "description": "用户提供的健康描述，如'精神良好，毛发顺滑'",
                    },
                },
                "required": ["pet_type", "name", "area", "breed", "age", "health_status", "health"],
            },
        )

        self.register(
            name="query_pets",
            description="查询系统中已登记的流浪猫咪或狗狗列表与档案信息",
            function=query_pets,
            parameters={
                "type": "object",
                "properties": {
                    "pet_type": {
                        "type": "string",
                        "enum": ["cat", "dog"],
                        "description": "动物类型：cat（猫咪）或 dog（狗狗）",
                    },
                    "keyword": {
                        "type": "string",
                        "description": "关键词搜索，如名字或品种（可选）",
                    },
                    "area": {
                        "type": "string",
                        "description": "出没区域筛选（可选）",
                    },
                },
                "required": [],
            },
        )

        self.register(
            name="get_current_weather",
            description="获取天气",
            function=self.get_current_weather,
            parameters={
                "type": "object",
                "properties": {
                    "location": {
                        "type": "string",
                        "description": "城市名称",
                    }
                },
                "required": ["location"],
            },
        )

        self.register(
            name="get_current_time",
            description="获取时间",
            function=self.get_current_time,
            parameters={
                "type": "object",
                "properties": {},
                "required": [],
            },
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

    def describe_for_router(self):
        lines = []
        for tool in self.tools:
            fn = tool["function"]
            name = fn["name"]
            desc = fn["description"]
            params = fn.get("parameters", {})
            lines.append(f"- {name}: {desc}")
            lines.append(f"  args 参数: {json.dumps(params, ensure_ascii=False)}")
        return "\n".join(lines)
