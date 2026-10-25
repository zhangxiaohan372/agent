import asyncio
import json
import logging
from typing import Any, AsyncGenerator, Callable, Dict, Optional, Set

from core.pet_registration import PetRegistration, RegistrationStatus
from core.router import Router
from core.schemas import ExecutionPlan, RouteItem, RouterDecision, TaskStatus
from core.state import AgentState

logger = logging.getLogger("workflow")


class AgentWorkflow:
    """复合任务工作流执行引擎。

    负责驱动单轮对话的完整生命周期：
    1. 意图分类与多轮登记确认拦截
    2. 顶层 Plan-and-Solve 任务蓝图生成与事件派发
    3. 微观 ReAct 动作循环与子任务状态跃迁 (pending -> running -> completed)
    4. 执行指纹去重与任务完结即时跳出
    5. 汇总多任务上下文驱动 LLM 综合回复生成
    """

    def __init__(
        self,
        router: Router,
        executor: Any,
        pet_registration: PetRegistration,
        message_manager: Any,
        generate_fn: Callable[[], AsyncGenerator[str, None]],
        user_id: str = "local",
        session_id: str = "cli",
    ):
        self.router = router
        self.executor = executor
        self.pet_registration = pet_registration
        self.message_manager = message_manager
        self.generate_fn = generate_fn
        self.user_id = str(user_id)
        self.session_id = str(session_id)

    def _is_ready_to_chat(self, routes: list) -> bool:
        if not routes:
            return True
        return all(route.get("type") == "CHAT" for route in routes)

    async def _handle_pre_turn_registration_reply(
        self, user_input: str, auth_token: Optional[str]
    ) -> Optional[AsyncGenerator[Dict[str, Any], None]]:
        """检测并处理用户对未决草稿的确认/取消意图。"""
        if self.pet_registration.status not in {
            RegistrationStatus.COLLECTING,
            RegistrationStatus.AWAITING_CONFIRMATION,
        }:
            return None

        reply_kind = None
        try:
            reply_kind = await self.router.classify_registration_reply(
                user_input, self.pet_registration.status.value
            )
        except Exception:
            reply_kind = None

        if reply_kind in {"none", None}:
            reply_kind = self.pet_registration.reply_kind(user_input)

        if reply_kind == "cancel":
            self.pet_registration.cancel()
            message = "已取消登记，数据未写入。"
            self.message_manager.messages.append({"role": "assistant", "content": message})

            async def _cancel_gen():
                yield {"type": "token", "content": message}
                yield {"type": "done"}

            return _cancel_gen()

        if reply_kind == "confirm":
            confirmed_fields = self.pet_registration.confirm()
            if confirmed_fields is None:
                message = "当前没有完整且待确认的登记信息，请先提供资料并核对草稿。"

                async def _err_gen():
                    self.message_manager.messages.append({"role": "assistant", "content": message})
                    yield {"type": "token", "content": message}
                    yield {"type": "done"}

                return _err_gen()

            try:
                result = await self.executor.execute_confirmed_pet(confirmed_fields, auth_token)
            except asyncio.CancelledError:
                self.pet_registration.finish(False, uncertain=True)
                raise

            self.pet_registration.finish(result["success"], result["uncertain"])
            message = result["content"]

            async def _confirm_gen():
                yield {"type": "context", "content": [result]}
                self.message_manager.messages.append({"role": "assistant", "content": message})
                yield {"type": "token", "content": message}
                yield {"type": "done"}

            return _confirm_gen()

        return None

    async def execute_turn(
        self, user_input: str, max_steps: int = 3, auth_token: Optional[str] = None
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """执行单轮对话的主工作流生成器。"""
        state = AgentState(user_input)
        self.message_manager.add_user_message(user_input)

        # 1. 检查是否为上一轮草稿的直接确认/取消回复
        shortcut = await self._handle_pre_turn_registration_reply(user_input, auth_token)
        if shortcut is not None:
            async for ev in shortcut:
                yield ev
            return

        self.pet_registration.begin_revision()

        executed_routes: Set[tuple] = set()

        for _ in range(max_steps):
            state.step += 1
            state.routes = await self.router.route(self.message_manager.get_messages())
            yield {"type": "step", "step": state.step, "routes": state.routes}

            # 2. 顶层 Plan-and-Solve: 多步骤复合意图生成可视化执行看板
            if state.step == 1 and len(state.routes) > 1 and not state.plan:
                try:
                    decision = RouterDecision(routes=[RouteItem(**r) for r in state.routes])
                    plan = decision.to_execution_plan(default_summary="已规划多步骤联合处理方案")
                    if plan:
                        state.plan = plan
                        logger.info(
                            f"[{self.user_id}:{self.session_id}] 顶层 Plan-and-Solve 生成计划清单 "
                            f"({len(plan.tasks)} 步): {plan.summary}"
                        )
                        yield {"type": "plan_created", "plan": plan.to_dict()}
                except Exception as e:
                    logger.warning(f"生成任务规划清单异常: {e}")

            # 3. 登记草稿合法性初筛
            proposals = [
                r for r in state.routes
                if r.get("type") == "PET_REGISTRATION"
                or (r.get("type") == "TOOL" and r.get("name") == "register_pet")
            ]
            if proposals:
                if len(proposals) != 1:
                    self.pet_registration.cancel()
                    message = "一次只能核对一份登记，请重新提供登记信息。"
                    self.message_manager.messages.append({"role": "assistant", "content": message})
                    yield {"type": "token", "content": message}
                    yield {"type": "done"}
                    return

                # 单意图快速通道：没有其它任务时直接响应缺项追问或弹窗
                if not state.plan and len(state.routes) == 1:
                    propose_result = self.pet_registration.propose(proposals[0].get("args"))
                    self.message_manager.messages.append({"role": "assistant", "content": propose_result})

                    if self.pet_registration.status != RegistrationStatus.AWAITING_CONFIRMATION:
                        yield {"type": "token", "content": propose_result}
                        yield {"type": "done"}
                        return

                    yield {
                        "type": "confirm_dialog",
                        "fields": self.pet_registration.fields.copy(),
                        "prompt": propose_result,
                    }
                    yield {"type": "done"}
                    return

            # 4. 转向新话题时主动清理上一轮遗留的未确认草稿
            has_reg_intent = any(
                r.get("type") == "PET_REGISTRATION"
                or (r.get("type") == "TOOL" and r.get("name") == "register_pet")
                for r in state.routes
            )
            if state.step == 1 and not has_reg_intent and self.pet_registration.fields:
                self.pet_registration.cancel()

            if self._is_ready_to_chat(state.routes):
                break

            # 5. 指纹去重，过滤本轮已执行过的动作
            unexecuted_routes = []
            for r in state.routes:
                r_fp = (
                    str(r.get("type")),
                    str(r.get("name")),
                    json.dumps(r.get("args") or {}, sort_keys=True, ensure_ascii=False),
                )
                if r_fp not in executed_routes:
                    executed_routes.add(r_fp)
                    unexecuted_routes.append(r)

            if not unexecuted_routes:
                break

            # 6. 微观 ReAct 执行层与计划状态更新
            if state.plan:
                context = []
                for r in unexecuted_routes:
                    matched_task = next(
                        (
                            t for t in state.plan.tasks
                            if t.route.type.value == r.get("type")
                            and (not t.route.name or t.route.name == r.get("name"))
                            and t.status == TaskStatus.PENDING
                        ),
                        None,
                    )
                    if matched_task:
                        matched_task.status = TaskStatus.RUNNING
                        logger.debug(
                            f"[{self.user_id}:{self.session_id}] 启动子任务 #{matched_task.id}: {matched_task.title}"
                        )
                        yield {"type": "task_updated", "task": matched_task.to_dict()}

                    single_res = await self.executor.execute_single_route(r)
                    context.append(single_res)

                    if matched_task:
                        matched_task.status = TaskStatus.COMPLETED
                        matched_task.result = str(single_res.get("content", ""))[:120]
                        logger.debug(
                            f"[{self.user_id}:{self.session_id}] 完成子任务 #{matched_task.id}: {matched_task.title}"
                        )
                        yield {"type": "task_updated", "task": matched_task.to_dict()}
            else:
                context = await self.executor.execute(unexecuted_routes)

            state.tool_results.extend(context)
            self.message_manager.add_context_message(context)
            yield {"type": "context", "content": context}

            # 7. 顶层规划全部执行完毕，零延迟跳出，直接进入回复生成流
            if state.plan and all(t.status == TaskStatus.COMPLETED for t in state.plan.tasks):
                logger.debug(
                    f"[{self.user_id}:{self.session_id}] 规划的 {len(state.plan.tasks)} 项子任务已全部执行完毕，直接进入生成答复"
                )
                break

        # 8. 大模型综合答复生成（流式输出）
        async for text in self.generate_fn():
            yield {"type": "token", "content": text}

        # 9. 复合任务完成后，若登记字段已齐全，推送弹窗事件
        if self.pet_registration.status == RegistrationStatus.AWAITING_CONFIRMATION:
            yield {
                "type": "confirm_dialog",
                "fields": self.pet_registration.fields.copy(),
                "prompt": "请核对拟提交的登记信息",
            }

        yield {"type": "done"}
