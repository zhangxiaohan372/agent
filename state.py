class AgentState:
    def __init__(self, user_input: str):
        # 用户输入
        self.user_input = user_input

        # Router 的决策结果
        self.routes = []

        # Executor 本轮执行结果（记忆 / 知识库 / 工具）
        self.tool_results = []

        # 当前 Agent 执行了多少步
        self.step = 0

        # 是否结束
        self.finished = False

        # 最终回答
        self.final_answer = None
 