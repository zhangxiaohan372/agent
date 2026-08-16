class MessageManager:
    
    def __init__(self):
        self.messages = []

    def add_system_message(self, content):
        self.messages.append({
            "role": "system",
            "content": content
        })

    def add_user_message(self, content):
        self.messages.append({
            "role": "user",
            "content": content
        })
    
    def add_assistant_message(self, message):
        self.messages.append(message)
    
    def add_tool_message(self, message):
        self.messages.append(message)

    def add_memory_message(self, memory_list):
        if not memory_list:
            return
        lines = []
        for row in memory_list:
            # row: id, content, category, importance, embedding
            content = row[1]
            category = row[2]
            importance = row[3]
            lines.append(f"- [{category}|重要度{importance}] {content}")
        self.messages.append({
            "role": "system",
            "content": "以下是与当前问题相关的长期记忆，请结合这些信息回答用户：\n" + "\n".join(lines)
        })

    def add_knowledge_message(self, knowledge_list):
        if not knowledge_list:
            return
        lines = []
        for row in knowledge_list:
            content = row["content"]
            source = row["source"]
            score = row["score"]
            lines.append(f"- [{source}|相似度{score:.4f}] {content}")
        self.messages.append({
            "role": "system",
            "content": "以下是与当前问题相关的知识库内容，请结合这些信息回答用户：\n" + "\n".join(lines)
        })

    def get_messages(self):
        return self.messages
