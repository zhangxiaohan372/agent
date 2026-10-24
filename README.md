# 🐾 Campus Pet Agent

> 一个为校园流浪动物救助场景构建的**生产级 AI Agent 系统**。  
> 不依赖 LangChain / LlamaIndex，从零实现了完整的 Agent 调度引擎。

[![Python](https://img.shields.io/badge/Python-3.11+-blue.svg)](https://python.org)
[![FastAPI](https://img.shields.io/badge/FastAPI-async-green.svg)](https://fastapi.tiangolo.com)
[![DeepSeek](https://img.shields.io/badge/LLM-DeepSeek--V4-purple.svg)](https://deepseek.com)
[![MCP](https://img.shields.io/badge/Protocol-MCP-orange.svg)](https://modelcontextprotocol.io)
[![License](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

---

## ✨ 项目简介

Campus Pet Agent 是一个面向**校园流浪动物救助**场景的智能对话系统。用户可以通过自然语言完成动物档案登记、查询校园内已登记动物信息、查询校园知识（喂养守则、救助流程等），系统同时维护用户的长期记忆，让每次对话都"记得你"。

**核心亮点：没有调用任何 Agent 框架**，路由引擎、执行器、记忆系统、工具协议均自主实现，具备高度可移植性，换一套 `system_prompt` + 工具即可迁移到任意业务场景。

---

## 🏗️ 整体架构

```
用户输入
   │
   ▼
┌─────────────────────────────────────────────────────────┐
│                      Agent (agent.py)                   │
│                                                         │
│  ┌──────────────┐    ┌──────────────┐                   │
│  │ MessageManager│    │ PromptManager│                   │
│  │  (上下文管理)  │    │  (提示词管理) │                   │
│  └──────┬───────┘    └──────────────┘                   │
│         │ messages                                      │
│         ▼                                               │
│  ┌──────────────┐  意图路由 JSON                         │
│  │    Router    │ ──────────────────────────────────┐   │
│  │  (意图分类)   │                                   │   │
│  └──────────────┘                                   │   │
│                                                     ▼   │
│  ┌─────────────────────────────────────────────────┐    │
│  │                  AgentExecutor                  │    │
│  │                                                 │    │
│  │   MEMORY_SEARCH  ──►  MemoryManager             │    │
│  │   KNOWLEDGE_SEARCH ►  KnowledgeManager          │    │
│  │   MEMORY_WRITE   ──►  MemoryManager.save()      │    │
│  │   TOOL (本地)    ──►  ToolManager               │    │
│  │   TOOL (远程)    ──►  MCPManager                │    │
│  │   PET_REGISTRATION►  PetRegistration (状态机)   │    │
│  └─────────────────────────────────────────────────┘    │
│         │ context 注入                                   │
│         ▼                                               │
│  ┌──────────────┐  流式 token                           │
│  │   LLM 调用   │ ──────────────────────────────────────┤
│  │ (DeepSeek)   │                                       │
│  └──────────────┘                                   SSE │
└─────────────────────────────────────────────────────────┘
   │ FastAPI + SSE
   ▼
前端 / CLI
```

---

## 🧩 核心模块详解

### 1. Router — 自研意图路由引擎

**文件：** `src/core/router.py`

Router 是整个系统的"大脑调度中枢"。它不是简单的关键词匹配，而是调用 LLM 对完整对话历史进行意图分析，输出结构化的路由决策 JSON：

```json
{
  "routes": [
    { "type": "KNOWLEDGE_SEARCH", "query": "图书馆草坪猫咪喂养规定", "priority": 1 },
    { "type": "MEMORY_SEARCH",    "query": "用户偏好的猫咪品种",       "priority": 2 }
  ]
}
```

支持的路由类型：

| 类型 | 触发场景 |
|------|---------|
| `CHAT` | 闲聊、创作、翻译等，无需外部信息 |
| `MEMORY_SEARCH` | 需要用户历史偏好、个人信息 |
| `MEMORY_WRITE` | 用户表达了需要长期记住的信息 |
| `KNOWLEDGE_SEARCH` | 查询业务文档（规章制度、救助流程等） |
| `TOOL` | 调用实时工具（天气、时间、查询宠物档案等） |
| `PET_REGISTRATION` | 登记新流浪动物档案（触发状态机流程） |

**设计亮点：**
- 路由只传入最近 6 轮对话 + 当前轮已获取的上下文，**隔离了业务 system prompt 和旧工具上下文**，避免路由器被历史噪声干扰
- 存在任意非 `CHAT` 路由时，自动过滤掉 `CHAT`，强制走能力链路
- 支持多路由并行（同一轮可同时触发 MEMORY_SEARCH + TOOL）

---

### 2. AgentExecutor — 多步执行器

**文件：** `src/core/executor.py`

执行器负责按路由调度各个能力模块，并将结果以 `context` 形式注入对话历史：

```
for step in range(max_steps):          # 最多 3 步
    routes = await router.route(...)   # 重新路由
    context = await executor.execute(routes)
    build_context(context)             # 注入上下文
    if is_ready_to_chat(routes):
        break                          # 上下文足够，直接生成回复
```

**防重复执行机制：** 对每条路由生成指纹 `(type, name, args_json)`，同一轮内相同路由只执行一次，防止 LLM 幻觉导致的重复工具调用。

---

### 3. PetRegistration — 状态机（业务核心）

**文件：** `src/core/pet_registration.py`

动物登记是一个需要**多轮收集 + 确认写入**的敏感操作，用状态机严格控制流程：

```
IDLE
  │ 用户提出登记
  ▼
COLLECTING          ← 字段不完整，继续追问
  │ 7个必填字段全部收集完毕
  ▼
AWAITING_CONFIRMATION  ← 向用户展示草稿，等待明确确认
  │ 用户点击"确认提交"
  ▼
SUBMITTING          ← 调用业务 API 写入
  │
  ├─ 成功 → SUBMITTED
  ├─ 失败 → CANCELLED
  └─ 不确定 → UNCERTAIN（防重复提交保护）
```

**工程亮点：**
- 状态通过 **Redis** 持久化（TTL 30分钟），支持跨请求的多轮收集
- **指纹去重**：同一会话内相同字段组合不允许重复提交
- **LLM 语义确认 + 确定性关键词兜底**：双重确认意图判断，防止误操作

---

### 4. MCPManager — MCP 协议工具扩展

**文件：** `src/managers/mcp_manager.py`

通过 [Model Context Protocol (MCP)](https://modelcontextprotocol.io) 实现工具热插拔：

```
mcp_servers.json
       │
       ▼ stdio_client（启动子进程）
       │
       ▼ ClientSession（JSON-RPC over pipe）
       │
       ▼ tool_to_session 路由表
       │
       ▼ session.call_tool() → 返回结果给 LLM
```

- 配置文件驱动，新增工具**无需修改任何 Python 代码**
- 单个 MCP 服务失败时**优雅降级**，不影响其他工具和主流程
- 每个服务独立 `AsyncExitStack`，确保生命周期正确隔离

---

### 5. 双轨记忆系统

#### MemoryManager — 向量长期记忆
**文件：** `src/memory/memory_manager.py`

- 记忆条目存入 **MySQL**（持久化）+ **向量 embedding**（语义检索）
- 检索时自动计算**余弦相似度**，返回 Top-K 最相关记忆
- 手写余弦相似度，不依赖向量数据库

#### KnowledgeManager — RAG 知识库
**文件：** `src/knowledge/knowledge_manager.py`

- 文档切片后写入 **ChromaDB**（HNSW 索引）
- 查询时将用户问题 embedding 后在 Chroma 中语义检索
- 支持按 `document_id` 过滤，实现多文档隔离检索

#### MessageManager — 会话上下文
**文件：** `src/managers/message_manager.py`

采用 **"Redis 活跃上下文 + MySQL 历史归档"** 双层架构：

```
新消息 → _TrackedMessageList.append()
              │
              ├─► Redis (key: chat:context:{user_id}:{session_id})
              │    └─ TTL 24h，保证极速访问与窗口控制
              │
              └─► MySQL messages 表（永久归档）
```

- `_TrackedMessageList` 重写 `list.append()`，实现消息零侵入自动同步
- Redis 未命中时自动从 MySQL 回填（容灾恢复）

---

### 6. FastAPI + SSE 流式输出

**文件：** `src/api/routes/chat.py`

```
POST /api/chat/stream    # 主聊天接口，SSE 流式返回
POST /api/chat/confirm   # 弹窗确认/取消动物登记
GET  /api/chat/history   # 翻页查询历史消息
```

每个 SSE 事件携带结构化 `type` 字段：

| type | 含义 |
|------|------|
| `step` | Agent 第 N 步路由决策 |
| `context` | 工具/知识库返回的上下文 |
| `token` | LLM 生成的文字 token |
| `confirm_dialog` | 触发前端确认弹窗 |
| `done` | 本轮结束 |

**安全设计：** 用户 ID 由后端 Token 解密提取，前端无法伪造；写入操作（登记动物）必须通过后端认证 Token 才能执行。

---

## 🗂️ 项目结构

```
agent/
├── src/
│   ├── agent.py                 # Agent 主类，整合所有模块
│   ├── core/
│   │   ├── router.py            # LLM 意图路由引擎
│   │   ├── executor.py          # 多步执行器
│   │   ├── pet_registration.py  # 登记状态机
│   │   └── state.py             # 单轮状态对象
│   ├── managers/
│   │   ├── message_manager.py   # 会话上下文（Redis+MySQL双层）
│   │   ├── prompt_manager.py    # 系统提示词管理
│   │   ├── tool_manager.py      # 本地工具注册与调用
│   │   └── mcp_manager.py       # MCP 协议工具管理
│   ├── memory/
│   │   ├── memory_manager.py    # 长期记忆（向量检索）
│   │   └── embedding_manager.py # 文本向量化
│   ├── knowledge/
│   │   ├── knowledge_manager.py # RAG 知识库检索
│   │   ├── init_knowledge.py    # 文档入库
│   │   └── chunker.py           # 文档切片
│   ├── database/
│   │   ├── database.py          # MySQL 连接池（SQLAlchemy）
│   │   ├── redis_client.py      # Redis（含内存降级）
│   │   └── vector_db.py         # ChromaDB 连接
│   ├── tools/
│   │   └── pet_tool.py          # 业务工具（登记/查询动物）
│   └── api/
│       ├── app.py               # FastAPI 应用入口
│       ├── schemas.py           # Pydantic 请求/响应模型
│       ├── session.py           # Agent 实例会话管理
│       └── routes/chat.py       # 聊天接口路由
├── knowledge_document/          # 知识库 Markdown 文档
├── data/chroma/                 # ChromaDB 持久化数据
├── mcp_servers.json             # MCP 服务配置
└── .env                         # 环境变量（不提交）
```

---

## 🚀 快速启动

### 环境要求

- Python 3.11+
- MySQL 8.0+
- Redis 7.0+（可选，无 Redis 自动降级为内存模式）

### 安装依赖

```bash
# 推荐使用 uv
uv sync

# 或使用 pip
pip install -r requirements.txt
```

### 配置环境变量

```bash
cp .env.example .env
# 编辑 .env，填写以下配置：
```

```env
# LLM
OPENAI_API_KEY=your_deepseek_api_key

# MySQL
MYSQL_HOST=127.0.0.1
MYSQL_PORT=3306
MYSQL_USER=root
MYSQL_PASSWORD=your_password
MYSQL_DATABASE=agent_db

# Redis（可选）
REDIS_HOST=127.0.0.1
REDIS_PORT=6379

# 业务后端（用于身份认证）
BUSINESS_API_BASE_URL=http://127.0.0.1:3001
```

### 初始化数据库

```bash
python src/database/init_db.py
```

### 启动服务

```bash
# API 服务（生产模式）
uvicorn src.api.app:app --host 0.0.0.0 --port 8000

# CLI 交互模式（快速测试）
python src/agent.py
```

---

## 🔧 扩展工具

### 添加本地工具

在 `ToolManager.__init__` 中调用 `self.register()` 即可：

```python
self.register(
    name="search_news",
    description="搜索最新新闻",
    function=search_news_func,
    parameters={
        "type": "object",
        "properties": {
            "keyword": {"type": "string", "description": "搜索关键词"}
        },
        "required": ["keyword"]
    }
)
```

### 添加 MCP 工具

编辑 `mcp_servers.json`，无需改动任何 Python 代码：

```json
{
  "mcpServers": {
    "my-tool-server": {
      "command": "uvx",
      "args": ["my-mcp-tool-package"]
    }
  }
}
```

---

## 🛠️ 技术栈

| 层级 | 技术 |
|------|------|
| LLM | DeepSeek-V4-Pro（OpenAI 兼容接口） |
| Web 框架 | FastAPI + Uvicorn |
| 流式输出 | Server-Sent Events (SSE) |
| 向量数据库 | ChromaDB (HNSW 索引) |
| 关系型数据库 | MySQL 8.0 + SQLAlchemy |
| 缓存 / 会话 | Redis（含内存降级兜底） |
| 工具协议 | Model Context Protocol (MCP) |
| Embedding | DashScope / OpenAI 兼容 embedding API |
| 包管理 | uv |

---

## 💡 设计亮点总结

1. **零框架依赖的 Agent 引擎** — Router + Executor + 状态机全部手写，深度理解 Agent 每一层设计权衡
2. **MCP 协议工具热插拔** — 新增外部工具只需改一行 JSON 配置
3. **指纹去重防幻觉** — 同一轮内相同工具调用只执行一次
4. **三阶段登记状态机** — 收集 → 确认 → 写入，Redis 持久化草稿，防止意外提交
5. **双层消息架构** — Redis 极速访问 + MySQL 永久归档，`_TrackedMessageList` 零侵入自动同步
6. **优雅降级设计** — Redis 不可用自动降级内存模式；MCP 服务失败跳过不影响主流程
