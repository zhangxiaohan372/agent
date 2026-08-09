from database.database import get_connection

class MemoryManager:
    def __init__(self):
        self.connection = get_connection()
        self.cursor = self.connection.cursor()

    def save(self,memory):
        self.cursor.execute("INSERT INTO memories (content) VALUES (?)", (memory,))
        self.connection.commit()
    def search(self,query):
        self.cursor.execute("SELECT * FROM memories WHERE content LIKE ?", (f"%{query}%",))
        return self.cursor.fetchall()   

    def get_all(self):
        self.cursor.execute("SELECT * FROM memories")
        return self.cursor.fetchall()

    def close(self):
        self.cursor.close()
        self.connection.close()