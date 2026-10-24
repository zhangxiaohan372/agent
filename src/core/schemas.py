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


class RouterDecision(BaseModel):
    """Router 顶层决策模型，对模型输出的路由清单进行整体校验与规范化。"""
    routes: List[RouteItem] = Field(default_factory=list, description="路由决策列表")

    @model_validator(mode="after")
    def apply_routing_rules(self) -> "RouterDecision":
        # 规则：如果存在任意非 CHAT 的能力路由，则自动过滤掉 CHAT，强制走能力链路
        has_non_chat = any(r.type != RouteType.CHAT for r in self.routes)
        if has_non_chat:
            self.routes = [r for r in self.routes if r.type != RouteType.CHAT]
        return self

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
