import json
from enum import Enum
from pydantic import ValidationError
from core.schemas import PetRegistrationDraft
from database.redis_client import redis_client


class RegistrationStatus(Enum):
    IDLE = "idle"
    COLLECTING = "collecting"
    AWAITING_CONFIRMATION = "awaiting_confirmation"
    SUBMITTING = "submitting"
    SUBMITTED = "submitted"
    CANCELLED = "cancelled"
    UNCERTAIN = "uncertain"


class PetRegistration:
    FIELD_LABELS = {
        "pet_type": "种类",
        "name": "名称",
        "area": "所在区域",
        "breed": "品种",
        "age": "年龄",
        "health_status": "健康状态",
        "health": "健康描述",
    }
    CONFIRMATIONS = {
        "确认",
        "确认提交",
        "确定提交",
        "同意提交",
        "同意",
        "提交",
        "是的",
        "确定",
    }
    CANCELLATIONS = {
        "取消",
        "取消登记",
        "取消提交",
        "算了",
        "不登了",
        "不登记了",
        "不要提交",
    }

    def __init__(self, user_id: str = "default", session_id: str = "default"):
        self.user_id = user_id
        self.session_id = session_id
        self.redis_key = f"pet_reg:{user_id}:{session_id}"

        self.status = RegistrationStatus.IDLE
        self.fields = {}
        self.submitted = set()
        self.uncertain = set()

        self.load_from_redis()

    def save_to_redis(self, ttl: int = 1800):
        """将当前会话状态暂存到 Redis，并设置 TTL（默认30分钟/1800秒）"""
        if self.status in {
            RegistrationStatus.IDLE,
            RegistrationStatus.CANCELLED,
            RegistrationStatus.SUBMITTED,
        }:
            self.clear_redis()
            return
        payload = {
            "status": self.status.value,
            "fields": self.fields,
        }
        try:
            redis_client.set(self.redis_key, json.dumps(payload, ensure_ascii=False), ex=ttl)
        except Exception:
            pass

    def load_from_redis(self):
        """从 Redis 恢复可能还未过期的历史登记草稿"""
        try:
            raw = redis_client.get(self.redis_key)
            if raw:
                data = json.loads(raw)
                status_val = data.get("status")
                if status_val:
                    self.status = RegistrationStatus(status_val)
                self.fields = data.get("fields", {})
        except Exception:
            pass

    def clear_redis(self):
        """清除 Redis 中的当前会话草稿"""
        try:
            redis_client.delete(self.redis_key)
        except Exception:
            pass

    @staticmethod
    def _normalize_reply(text):
        return "".join(text.strip().split()).strip("。！!，,？?")

    def reply_kind(self, text):
        """Deterministic fallback used when semantic classification is unavailable."""
        reply = self._normalize_reply(text)
        if reply in self.CANCELLATIONS:
            return "cancel"
        if self.status != RegistrationStatus.AWAITING_CONFIRMATION:
            return None
        if reply in self.CONFIRMATIONS:
            return "confirm"
        return None

    def cancel(self):
        self.fields = {}
        self.status = RegistrationStatus.CANCELLED
        self.clear_redis()

    def begin_revision(self):
        if self.status == RegistrationStatus.AWAITING_CONFIRMATION:
            self.status = RegistrationStatus.COLLECTING
            self.save_to_redis(1800)

    def propose(self, arguments):
        if not isinstance(arguments, dict):
            self.cancel()
            return "登记信息格式不正确，请重新提供。"

        # 使用 Pydantic 进行输入清洗与强模式校验（包括品种类型规范化、去首尾空格等）
        try:
            draft = PetRegistrationDraft.model_validate(arguments)
        except ValidationError:
            self.cancel()
            return "登记信息格式不正确，请重新提供。"

        if self.status not in {
            RegistrationStatus.COLLECTING,
            RegistrationStatus.AWAITING_CONFIRMATION,
        }:
            self.fields = {}

        # 仅合并通过校验的有效非空字段
        for field, value in draft.model_dump(exclude_none=True).items():
            self.fields[field] = value

        missing = [
            label
            for field, label in self.FIELD_LABELS.items()
            if not self.fields.get(field)
        ]
        if missing:
            self.status = RegistrationStatus.COLLECTING
            self.save_to_redis(1800)
            return f"登记还缺少：{'、'.join(missing)}。请补充这些信息，暂未提交。"

        fingerprint = tuple(self.fields[field] for field in self.FIELD_LABELS)
        if fingerprint in self.uncertain:
            self.cancel()
            return "这份登记的提交结果尚不确定，请先到业务系统核实，勿重复提交。"
        if fingerprint in self.submitted:
            self.cancel()
            return "相同的登记信息在本会话中已成功提交，请勿重复提交。"

        self.status = RegistrationStatus.AWAITING_CONFIRMATION
        self.save_to_redis(1800)
        details = "\n".join(
            f"- {label}：{self.fields[field]}"
            for field, label in self.FIELD_LABELS.items()
        )
        return (
            f"请核对拟提交的登记信息：\n{details}\n"
            "确认无误请回复“确认提交”；修改或取消均不会写入。"
        )

    def confirm(self):
        if self.status != RegistrationStatus.AWAITING_CONFIRMATION:
            return None
        self.status = RegistrationStatus.SUBMITTING
        return self.fields.copy()

    def finish(self, success, uncertain=False):
        if self.status != RegistrationStatus.SUBMITTING:
            raise RuntimeError("登记状态不允许完成提交")
        if success:
            self.submitted.add(tuple(self.fields[field] for field in self.FIELD_LABELS))
        elif uncertain:
            self.uncertain.add(tuple(self.fields[field] for field in self.FIELD_LABELS))
        self.fields = {}
        if success:
            self.status = RegistrationStatus.SUBMITTED
        elif uncertain:
            self.status = RegistrationStatus.UNCERTAIN
        else:
            self.status = RegistrationStatus.CANCELLED
        self.clear_redis()
