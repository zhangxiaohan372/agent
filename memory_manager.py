class MemoryManager:
    def __init__(self):
        self.memory_pool = []

    def save(self,memory):
        self.memory_pool.append(memory)
    
    def search(self,query):
        return self.memory_pool

    def get_all(self):
        return self.memory_pool