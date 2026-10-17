import json
import logging
from sqlalchemy import text

from database.database import get_engine
from database.redis_client import redis_client

logger = logging.getLogger(__name__)


class _TrackedMessageList(list):
    """一个自动监听追加操作的列表，当有新消息加入时自动同步到 Redis 和 MySQL。"""

    def __init__(self, manager, *args):
        super().__init__(*args)
        self._manager = manager

    def append(self, item):
        super().append(item)
        if hasattr(self, "_manager") and not self._manager._is_loading:
            self._manager._on_message_added(item)

    def extend(self, items):
        super().extend(items)
        if hasattr(self, "_manager") and not self._manager._is_loading:
            for item in items:
                self._manager._on_message_added(item)


class MessageManager:
    """会话消息管理器。
    
    采用“Redis 活跃上下文 + MySQL 历史归档”架构：
    1. 活跃上下文（Redis）：存储最近 N 轮对话及系统提示词，设置 TTL 自动过期，保证极速访问与会话窗口控制。
    2. 历史归档（MySQL）：永久保存每轮用户和助手的对话历史，供复盘、审计及跨会话恢复。
    """

    def __init__(
        self,
        user_id: str = "local",
        session_id: str = "cli",
        max_context_turns: int = 20,
        ttl: int = 86400,
    ):
        self.user_id = str(user_id)
        self.session_id = str(session_id)
        self.max_context_turns = max_context_turns
        self.ttl = ttl
        self.redis_key = f"chat:context:{self.user_id}:{self.session_id}"

        self._is_loading = True
        self.messages = _TrackedMessageList(self)

        # 尝试恢复历史上下文
        self._hydrate_messages()
        self._is_loading = False

    def _hydrate_messages(self):
        """恢复会话消息：优先读 Redis，Redis 未命中则从 MySQL 回填。"""
        cached = self._load_from_redis()
        if cached is not None:
            self.messages.clear()
            self.messages.extend(cached)
            return

        # Redis 中无缓存，从 MySQL 恢复最近历史
        archived = self._load_from_mysql(limit=self.max_context_turns)
        if archived:
            self.messages.clear()
            self.messages.extend(archived)
            # 回填到 Redis
            self._sync_to_redis()

    def _load_from_redis(self) -> list[dict] | None:
        """从 Redis 读取活跃上下文。"""
        try:
            raw = redis_client.get(self.redis_key)
            if raw:
                data = json.loads(raw)
                if isinstance(data, list):
                    return data
        except Exception as e:
            logger.warning(f"[Redis] 读取活跃上下文失败: {e}")
        return None

    def _load_from_mysql(self, limit: int = 20) -> list[dict]:
        """从 MySQL 检索历史消息（按时间正序返回最近 limit 条）。"""
        try:
            with get_engine().connect() as connection:
                rows = connection.execute(
                    text(
                        """
                        SELECT role, content
                        FROM chat_history
                        WHERE user_id = :user_id AND session_id = :session_id
                        ORDER BY id DESC
                        LIMIT :limit
                        """
                    ),
                    {
                        "user_id": self.user_id,
                        "session_id": self.session_id,
                        "limit": limit,
                    },
                ).fetchall()
                # 倒序取出的列表需翻转为正序（按时间从先到后）
                history = [{"role": row[0], "content": row[1]} for row in reversed(rows)]
                return history
        except Exception as e:
            logger.warning(f"[MySQL] 读取历史归档失败: {e}")
            return []

    def _archive_to_mysql(self, role: str, content: str, metadata: dict = None):
        """将对话消息永久追加归档至 MySQL。"""
        try:
            meta_str = json.dumps(metadata, ensure_ascii=False) if metadata else None
            with get_engine().begin() as connection:
                connection.execute(
                    text(
                        """
                        INSERT INTO chat_history (user_id, session_id, role, content, metadata)
                        VALUES (:user_id, :session_id, :role, :content, :metadata)
                        """
                    ),
                    {
                        "user_id": self.user_id,
                        "session_id": self.session_id,
                        "role": role,
                        "content": content,
                        "metadata": meta_str,
                    },
                )
        except Exception as e:
            logger.warning(f"[MySQL] 归档消息失败: {e}")

    def _sync_to_redis(self):
        """将当前活跃上下文（保留 system prompt 及最近 max_context_turns 轮对话）同步刷新至 Redis。"""
        try:
            # 分离系统提示词与普通对话
            system_msgs = [m for m in self.messages if m.get("role") == "system"]
            dialogue_msgs = [m for m in self.messages if m.get("role") != "system"]

            # 滑动窗口：只保留最近 max_context_turns 轮对话消息
            trimmed_dialogue = dialogue_msgs[-self.max_context_turns:]
            active_context = system_msgs + trimmed_dialogue

            payload = json.dumps(active_context, ensure_ascii=False)
            redis_client.set(self.redis_key, payload, ex=self.ttl)
        except Exception as e:
            logger.warning(f"[Redis] 同步活跃上下文失败: {e}")

    def _on_message_added(self, message: dict):
        """新消息追加时的自动持久化回调。"""
        if not isinstance(message, dict):
            return

        role = message.get("role")
        content = str(message.get("content") or "")

        # 1. 归档到 MySQL（用户与助手对话属于核心历史）
        if role in {"user", "assistant"}:
            metadata = {}
            if "tool_calls" in message:
                metadata["tool_calls"] = message["tool_calls"]
            self._archive_to_mysql(role=role, content=content, metadata=metadata or None)

        # 2. 刷新活跃上下文到 Redis
        self._sync_to_redis()

    def add_system_message(self, content: str):
        """设置系统提示词。如果列表中已存在 system 角色则原地更新，否则插入至首位。"""
        for msg in self.messages:
            if msg.get("role") == "system":
                msg["content"] = content
                self._sync_to_redis()
                return

        # 不触发 _on_message_added 的 MySQL 归档，直接作为系统提示词放入首位
        old_loading = self._is_loading
        self._is_loading = True
        try:
            self.messages.insert(0, {"role": "system", "content": content})
            self._sync_to_redis()
        finally:
            self._is_loading = old_loading

    def add_user_message(self, content: str):
        """添加用户提问消息。"""
        self.messages.append({"role": "user", "content": content})

    def add_assistant_message(self, message):
        """添加模型回复消息（支持 OpenAI ChatCompletion 消息对象或字典）。"""
        if isinstance(message, dict):
            self.messages.append(message)
            return

        msg = {
            "role": "assistant",
            "content": getattr(message, "content", None) or "",
        }
        tool_calls = getattr(message, "tool_calls", None)
        if tool_calls:
            msg["tool_calls"] = [
                {
                    "id": tc.id,
                    "type": tc.type,
                    "function": {
                        "name": tc.function.name,
                        "arguments": tc.function.arguments,
                    },
                }
                for tc in tool_calls
            ]
        self.messages.append(msg)

    def add_tool_message(self, message):
        """添加工具执行响应消息。"""
        self.messages.append(message)

    def add_memory_message(self, memory_list):
        """添加检索到的长期记忆。"""
        if not memory_list:
            return
        lines = []
        for row in memory_list:
            content = row[1]
            category = row[2]
            importance = row[3]
            lines.append(f"- [{category}|重要度{importance}] {content}")
        self.messages.append(
            {
                "role": "system",
                "content": "以下是与当前问题相关的长期记忆，请结合这些信息回答用户：\n"
                + "\n".join(lines),
            }
        )

    def add_knowledge_message(self, knowledge_list):
        """添加检索到的知识库内容。"""
        if not knowledge_list:
            return
        lines = []
        for row in knowledge_list:
            content = row["content"]
            source = row["source"]
            score = row["score"]
            lines.append(f"- [{source}|相似度{score:.4f}] {content}")
        self.messages.append(
            {
                "role": "system",
                "content": "以下是与当前问题相关的知识库内容，请结合这些信息回答用户：\n"
                + "\n".join(lines),
            }
        )

    def add_context_message(self, context_list):
        """添加单轮参考上下文。"""
        if not context_list:
            return

        useful = [item for item in context_list if item.get("content")]
        if not useful:
            return

        lines = []
        for item in useful:
            lines.append(f"【{item['type']}】\n{item['content']}")

        self.messages.append(
            {
                "role": "system",
                "content": "参考上下文：\n\n" + "\n\n".join(lines),
            }
        )

    def get_messages(self) -> list[dict]:
        """获取当前供 LLM 推理的完整消息列表。"""
        return list(self.messages)

    def clear_context(self, clear_archive: bool = False):
        """清空当前会话的上下文。
        
        :param clear_archive: 是否同时清除 MySQL 永久历史归档。
        """
        # 清除 Redis 缓存
        try:
            redis_client.delete(self.redis_key)
        except Exception:
            pass

        # 若指定同时清除 MySQL
        if clear_archive:
            try:
                with get_engine().begin() as connection:
                    connection.execute(
                        text(
                            "DELETE FROM chat_history WHERE user_id = :user_id AND session_id = :session_id"
                        ),
                        {"user_id": self.user_id, "session_id": self.session_id},
                    )
            except Exception as e:
                logger.warning(f"[MySQL] 清除历史归档失败: {e}")

        # 保留 system prompt，清空其他对话
        system_msgs = [m for m in self.messages if m.get("role") == "system"]
        self._is_loading = True
        try:
            self.messages.clear()
            self.messages.extend(system_msgs)
        finally:
            self._is_loading = False

    @classmethod
    def get_archived_history(
        cls, user_id: str, session_id: str, limit: int = 50, offset: int = 0
    ) -> list[dict]:
        """查询 MySQL 中指定用户会话的历史归档（支持分页）。"""
        try:
            with get_engine().connect() as connection:
                rows = connection.execute(
                    text(
                        """
                        SELECT id, role, content, metadata, created_at
                        FROM chat_history
                        WHERE user_id = :user_id AND session_id = :session_id
                        ORDER BY id ASC
                        LIMIT :limit OFFSET :offset
                        """
                    ),
                    {
                        "user_id": str(user_id),
                        "session_id": str(session_id),
                        "limit": limit,
                        "offset": offset,
                    },
                ).fetchall()
                results = []
                for row in rows:
                    meta = json.loads(row[3]) if row[3] else None
                    results.append(
                        {
                            "id": row[0],
                            "role": row[1],
                            "content": row[2],
                            "metadata": meta,
                            "created_at": str(row[4]),
                        }
                    )
                return results
        except Exception as e:
            logger.warning(f"[MySQL] 查询历史归档失败: {e}")
            return []
