from enum import Enum


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

    def __init__(self):
        self.status = RegistrationStatus.IDLE
        self.fields = {}
        self.submitted = set()
        self.uncertain = set()

    @staticmethod
    def _normalize_reply(text):
        return "".join(text.strip().split()).strip("。！!，,？?")

    def reply_kind(self, text):
        reply = self._normalize_reply(text)
        if reply in self.CANCELLATIONS:
            return "cancel"
        if reply in self.CONFIRMATIONS:
            return "confirm"
        return None

    def cancel(self):
        self.fields = {}
        self.status = RegistrationStatus.CANCELLED

    def begin_revision(self):
        if self.status == RegistrationStatus.AWAITING_CONFIRMATION:
            self.status = RegistrationStatus.COLLECTING

    def propose(self, arguments):
        if not isinstance(arguments, dict):
            self.cancel()
            return "登记信息格式不正确，请重新提供。"

        if self.status not in {
            RegistrationStatus.COLLECTING,
            RegistrationStatus.AWAITING_CONFIRMATION,
        }:
            self.fields = {}

        for field in self.FIELD_LABELS:
            value = arguments.get(field)
            if isinstance(value, str) and value.strip():
                self.fields[field] = value.strip()

        if self.fields.get("pet_type") in {"猫", "猫咪"}:
            self.fields["pet_type"] = "cat"
        elif self.fields.get("pet_type") in {"狗", "狗狗"}:
            self.fields["pet_type"] = "dog"
        elif self.fields.get("pet_type"):
            self.fields["pet_type"] = self.fields["pet_type"].lower()

        if self.fields.get("pet_type") not in {None, "cat", "dog"}:
            self.fields.pop("pet_type")

        missing = [
            label
            for field, label in self.FIELD_LABELS.items()
            if not self.fields.get(field)
        ]
        if missing:
            self.status = RegistrationStatus.COLLECTING
            return f"登记还缺少：{'、'.join(missing)}。请补充这些信息，暂未提交。"

        fingerprint = tuple(self.fields[field] for field in self.FIELD_LABELS)
        if fingerprint in self.uncertain:
            self.cancel()
            return "这份登记的提交结果尚不确定，请先到业务系统核实，勿重复提交。"
        if fingerprint in self.submitted:
            self.cancel()
            return "相同的登记信息在本会话中已成功提交，请勿重复提交。"

        self.status = RegistrationStatus.AWAITING_CONFIRMATION
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
