from agent import Agent

_agents: dict[str, Agent] = {}


def get_agent(session_id: str) -> Agent:
    if session_id not in _agents:
        _agents[session_id] = Agent()
    return _agents[session_id]
