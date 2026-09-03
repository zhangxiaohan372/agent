# role 处理并发
from agent import Agent
from threading import Lock
_agents: dict[str, Agent] = {}
_agents_lock = Lock()

def get_agent(session_id: str) -> Agent:
    with _agents_lock:
        agent = _agents.get(session_id)

        if agent is None:
            agent = Agent()
            _agents[session_id] = agent
        return agent
def remove_agent(seesion_id:str) -> bool:
    with _agents_lock:
        return _agents.pop(seesion_id, None) is not None