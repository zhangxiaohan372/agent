import asyncio
import sys
from typing import Any


async def run_cli_turn(agent: Any, user_input: str, max_steps: int = 3, auth_token: str = None) -> str:
    """在终端格式化展示 Agent 单轮任务看板、子任务跃迁与流式文本输出。"""
    agent.logger.info(f"[{agent.user_id}:{agent.session_id}] CLI 模式请求: {user_input}")
    chunks = []

    async for event in agent.run_one_turn_stream(user_input, max_steps=max_steps, auth_token=auth_token):
        etype = event.get("type")

        if etype == "plan_created":
            plan = event["plan"]
            print(f"\n [任务规划看板] {plan.get('summary', '执行方案')}")
            for t in plan.get("tasks", []):
                print(f"  [ ] 任务 #{t['id']}: {t['title']}")
            print()

        elif etype == "task_updated":
            task = event["task"]
            if task["status"] == "running":
                print(f"   [执行中] 任务 #{task['id']}: {task['title']}...")
            elif task["status"] == "completed":
                print(f"   [已完成] 任务 #{task['id']}: {task['title']}")

        elif etype == "confirm_dialog":
            print(f"\n [待确认提交] {event.get('prompt', '')}")
            fields = event.get("fields", {})
            for k, v in fields.items():
                print(f"   - {k}: {v}")

        elif etype == "token":
            print(event["content"], end="", flush=True)
            chunks.append(event["content"])

    print()
    full_reply = "".join(chunks)
    agent.logger.info(f"[{agent.user_id}:{agent.session_id}] LLM 调用完成 (生成 {len(full_reply)} 字)")
    return full_reply


async def _async_cli_loop(agent: Any):
    try:
        await agent.init_mcp()
        print("🤖 Agent 助手已就绪，请输入您的问题（输入 'exit' 退出）：")
        while True:
            try:
                user_input = await asyncio.to_thread(input, "\n用户：")
            except (EOFError, KeyboardInterrupt):
                break
            if user_input.strip().lower() in {"exit", "quit"}:
                break
            if not user_input.strip():
                continue
            await run_cli_turn(agent, user_input)
    finally:
        await agent.close()


def start_cli(agent: Any = None):
    """启动交互式终端控制台。"""
    if agent is None:
        from agent import Agent
        agent = Agent()
    asyncio.run(_async_cli_loop(agent))


if __name__ == "__main__":
    from agent import Agent
    start_cli(Agent())
