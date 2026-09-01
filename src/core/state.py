class AgentState:
    def __init__(self, user_input: str):
        self.user_input = user_input
        self.routes = []
        self.tool_results = []
        self.step = 0
        self.finished = False
        self.final_answer = None
