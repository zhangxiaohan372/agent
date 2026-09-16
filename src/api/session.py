# role 处理并发
from agent import Agent
from threading import Lock
_agents: dict[tuple[str, str], Agent] = {}
_agents_lock = Lock()

def get_agent(user_id: str, session_id: str) -> Agent:
    agent_key = (user_id, session_id)
    with _agents_lock:
        agent = _agents.get(agent_key)

        if agent is None:
            agent = Agent(user_id=user_id, session_id=session_id)
            _agents[agent_key] = agent
        return agent


def remove_agent(user_id: str, session_id: str) -> bool:
    with _agents_lock:
        return _agents.pop((user_id, session_id), None) is not None
