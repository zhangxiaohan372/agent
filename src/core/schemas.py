import logging
from enum import Enum
from typing import Any, Dict, List, Literal, Optional
from pydantic import BaseModel, Field, field_validator, model_validator

logger = logging.getLogger(__name__)


class RouteType(str, Enum):
    MEMORY_WRITE = "MEMORY_WRITE"
    MEMORY_SEARCH = "MEMORY_SEARCH"
    KNOWLEDGE_SEARCH = "KNOWLEDGE_SEARCH"
    KNOWLEDGE_INGEST = "KNOWLEDGE_INGEST"
    PET_REGISTRATION = "PET_REGISTRATION"
    TOOL = "TOOL"
    CHAT = "CHAT"


class TaskStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class RouteItem(BaseModel):
    """单条路由决策项，严格校验能力类型、查询内容及入参结构。"""
    type: RouteType = Field(..., description="调用的能力类型")
    query: str = Field(default="", description="该能力真正需要处理的查询或动作")
    priority: int = Field(default=1, ge=1, le=10, description="优先级（1为最高）")
    name: Optional[str] = Field(default=None, description="工具名称（仅TOOL类型需要）")
    args: Dict[str, Any] = Field(default_factory=dict, description="工具入参或登记字段")

    @model_validator(mode="before")
    @classmethod
    def normalize_aliases_and_safety(cls, data: Any) -> Any:
        if not isinstance(data, dict):
            return data

        # 兼容 tool_name 和 tool_args 别名
        if "tool_name" in data and not data.get("name"):
            data["name"] = data["tool_name"]
        if "tool_args" in data and not data.get("args"):
            data["args"] = data["tool_args"]

        # 确保 args 一定是 dict
        args = data.get("args")
        if not isinstance(args, dict):
            args = {}

        # 强制剔除 auth_token，安全隔离
        data["args"] = {k: v for k, v in args.items() if k != "auth_token"}
        return data

    def to_dict(self) -> Dict[str, Any]:
        """向下兼容历史代码的 dict 格式访问"""
        return {
            "type": self.type.value,
            "query": self.query,
            "priority": self.priority,
            "name": self.name,
            "args": self.args,
        }


class PlanTask(BaseModel):
    """分层规划架构下的单个宏观子任务。"""
    id: int = Field(..., description="子任务编号")
    title: str = Field(..., description="面向用户的子任务标题（如'检索流浪猫止血急救指引'）")
    route: RouteItem = Field(..., description="对应的微观执行动作（Route）")
    status: TaskStatus = Field(default=TaskStatus.PENDING, description="任务执行状态")
    result: Optional[str] = Field(default=None, description="执行结果快照")

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "title": self.title,
            "type": self.route.type.value,
            "query": self.route.query,
            "status": self.status.value,
            "result": self.result,
        }


class ExecutionPlan(BaseModel):
    """顶层 Plan-and-Solve 生成的宏观任务规划蓝图。"""
    summary: str = Field(default="", description="整体计划摘要（面向前端展示看板）")
    tasks: List[PlanTask] = Field(default_factory=list, description="有序子任务序列")

    def to_dict(self) -> Dict[str, Any]:
        return {
            "summary": self.summary,
            "tasks": [t.to_dict() for t in self.tasks],
        }


class RouterDecision(BaseModel):
    """Router 顶层决策模型，支持单意图直出与复合任务 Plan-and-Solve 规划。"""
    plan_summary: Optional[str] = Field(default=None, description="复合任务的规划纲要")
    routes: List[RouteItem] = Field(default_factory=list, description="路由决策列表（按执行顺序编排）")

    @model_validator(mode="after")
    def apply_routing_rules(self) -> "RouterDecision":
        # 规则：如果存在任意非 CHAT 的能力路由，则自动过滤掉 CHAT，强制走能力链路
        has_non_chat = any(r.type != RouteType.CHAT for r in self.routes)
        if has_non_chat:
            self.routes = [r for r in self.routes if r.type != RouteType.CHAT]
        return self

    def to_execution_plan(self, default_summary: str = "已生成多步骤联合救助计划") -> Optional[ExecutionPlan]:
        """如果包含多个任务动作，自动升格为结构化 ExecutionPlan 任务清单"""
        if not self.routes or (len(self.routes) == 1 and self.routes[0].type == RouteType.CHAT):
            return None

        tasks = []
        for idx, route in enumerate(self.routes, start=1):
            title = self._generate_task_title(route)
            tasks.append(PlanTask(id=idx, title=title, route=route))

        summary = self.plan_summary or default_summary
        return ExecutionPlan(summary=summary, tasks=tasks)

    @staticmethod
    def _generate_task_title(route: RouteItem) -> str:
        if route.type == RouteType.KNOWLEDGE_SEARCH:
            return f"检索业务规程: {route.query or '救助指引'}"
        elif route.type == RouteType.MEMORY_SEARCH:
            return f"查找用户偏好记忆: {route.query or '历史偏好'}"
        elif route.type == RouteType.MEMORY_WRITE:
            return f"记录用户长期偏好: {route.query or '信息保存'}"
        elif route.type == RouteType.PET_REGISTRATION:
            return "核对流浪动物建档草稿与字段完整性"
        elif route.type == RouteType.TOOL:
            tool_name = route.name or "未知工具"
            if tool_name == "query_pets":
                kw = route.args.get("keyword")
                return f"在校内档案库检索匹配动物 ({kw or '按特征'})"
            elif tool_name == "get_current_weather":
                return f"查询 {route.args.get('location', '')} 实时天气"
            elif tool_name == "get_current_time":
                return "获取当前系统基准时间"
            return f"调用外部工具: {tool_name}"
        return f"执行步骤: {route.type.value}"

    def to_dict_list(self) -> List[Dict[str, Any]]:
        """转为字典列表，兼容 Executor 和 Agent 主循环"""
        return [r.to_dict() for r in self.routes]


class RegistrationIntentDecision(BaseModel):
    """登记确认意图分类结果模型。"""
    intent: Literal["confirm", "cancel", "none"] = Field(
        ...,
        description="用户意图分类：confirm=确认提交，cancel=放弃取消，none=补充/修改/犹豫/其他",
    )


class PetRegistrationDraft(BaseModel):
    """流浪动物登记草稿字段强校验模型。"""
    pet_type: Optional[Literal["cat", "dog"]] = Field(
        default=None,
        description="动物种类：cat（猫咪）或 dog（狗狗）",
    )
    name: Optional[str] = Field(default=None, description="动物名称/昵称")
    area: Optional[str] = Field(default=None, description="发现或出没区域")
    breed: Optional[str] = Field(default=None, description="品种")
    age: Optional[str] = Field(default=None, description="估算年龄")
    health_status: Optional[str] = Field(default=None, description="健康状态")
    health: Optional[str] = Field(default=None, description="健康描述")

    @field_validator("pet_type", mode="before")
    @classmethod
    def normalize_pet_type(cls, v: Any) -> Optional[str]:
        if not v or not isinstance(v, str):
            return None
        cleaned = v.strip().lower()
        if cleaned in {"cat", "猫", "猫咪"}:
            return "cat"
        if cleaned in {"dog", "狗", "狗狗"}:
            return "dog"
        return cleaned if cleaned in {"cat", "dog"} else None

    @field_validator("name", "area", "breed", "age", "health_status", "health", mode="before")
    @classmethod
    def clean_strings(cls, v: Any) -> Optional[str]:
        if isinstance(v, str):
            trimmed = v.strip()
            return trimmed if trimmed else None
        return None
