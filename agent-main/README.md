# 下一站Youth — 智慧旅行 AI Agent 系统

> **Tourism Intelligent Agent** — 面向大学生群体的智能旅行规划助手，基于 LLM Agent 架构实现多工具编排、多轮对话与个性化行程生成。

---

## 目录

- [项目简介](#项目简介)
- [核心亮点](#核心亮点)
- [系统架构](#系统架构)
- [技术栈](#技术栈)
- [功能模块](#功能模块)
- [项目结构](#项目结构)
- [快速开始](#快速开始)
- [API 文档](#api-文档)

---

## 项目简介

**下一站Youth** 是一款面向大学生群体的 AI 旅行规划系统。用户通过自然语言描述旅行需求（目的地、预算、天数、偏好等），系统利用 LLM Agent 自动调用高德地图 POI 搜索、路线规划、天气查询等工具，结合互联网实时搜索，生成结构化的个性化行程方案。系统同时支持用户注册/登录、会话管理、对话历史持久化，并提供完整的前后台 Web 界面。

### 解决的痛点

- **大学生预算有限**：系统根据预算约束自动筛选景点、餐饮和住宿建议
- **规划效率低**：AI 自动编排多工具调用，数秒内生成完整行程
- **信息碎片化**：整合地图 POI、实时天气、网络搜索，一站式输出

---

## 核心亮点

### 1. 自研 LLM Agent 框架

自己实现的 Agent 架构（非 LangChain），核心流程如下：

```
用户输入 → 意图识别 → 任务规划 → 工具编排 → 多步执行 → 结果整合 → 流式输出
```

- **意图识别**：区分闲聊、知识问答、工具查询、复杂任务四种意图类型
- **任务规划器**：将复杂用户请求拆解为多个子任务步骤
- **工具编排**：根据步骤自动选择合适的工具（地图/搜索/文件/代码等）
- **多步执行**：支持串行/并行执行策略，处理工具间的依赖关系
- **流式输出**：SSE 实时推送生成内容，提升用户体验

### 2. 多模型支持

通过统一 LLM 接口层，支持热切换多种大语言模型提供商：

| 提供商 | 模型 | 说明 |
|--------|------|------|
| Qwen (通义千问) | 主用 | 通过 DashScope API，支持快速/深度双模式 |
| OpenAI | 可选 | GPT 系列兼容 |
| DeepSeek | 可选 | 高性价比推理 |
| Anthropic Claude | 可选 | 长上下文理解 |
| Zhipu (智谱AI) | 可选 | 国产替代方案 |

### 3. 高德地图 MCP 集成

基于 MCP (Model Context Protocol) 协议封装高德地图 API 为 Agent 可调用的工具集：

- **POI 搜索**：按关键词/区域搜索景点、餐饮、酒店
- **地理编码**：地址与经纬度互转
- **路线规划**：驾车/公交/步行/骑行多种方式
- **天气查询**：实时天气与未来预报
- **周边搜索**：以某点为中心的周边设施搜索

### 4. RAG + ICL 双通道知识增强

- **RAG (检索增强生成)**：基于 FAISS 向量数据库，将旅行知识库嵌入后，在对话中检索相关内容增强回答质量
- **ICL (上下文学习)**：根据用户问题动态检索相似案例，构造 Few-shot 示例注入 Prompt

### 5. 安全设计

- **JWT 认证**：用户登录后生成 JWT Token，Bearer 方式验证
- **bcrypt 密码哈希**：用户密码使用 bcrypt 加密存储
- **代码执行沙箱**：SecureCodeInterpreter 对 LLM 生成的代码进行安全检查
- **路径安全校验**：防止路径遍历攻击的文件操作
- **输入验证**：消息内容安全校验与净化

---

## 系统架构

```
┌─────────────────────────────────────────────────────────┐
│                    前端页面 (Static)                      │
│   index.html / planner.html / dashboard.html / ...       │
│   HTML5 + CSS3 + Vanilla JavaScript                      │
├──────────────────────────────────────────────────────────┤
│                    FastAPI 统一服务层                      │
│   unified_server.py                                       │
│   ├── /api/chat          聊天接口 (SSE 流式)              │
│   ├── /api/trip/plan     行程规划接口                      │
│   ├── /api/auth/*        用户认证接口                      │
│   ├── /api/admin/*       管理后台接口                      │
│   └── /api/conversations 会话管理接口                      │
├──────────────────────────────────────────────────────────┤
│                     Agent 核心层                           │
│   ┌─────────────┐  ┌──────────┐  ┌──────────────────┐   │
│   │ Agent       │  │ Memory   │  │ UnifiedLLM       │   │
│   │ (任务编排)   │  │ (记忆管理)│  │ (多模型适配)      │   │
│   └──────┬──────┘  └──────────┘  └──────────────────┘   │
│          │                                                 │
│   ┌──────┴────────────────────────────────────────┐      │
│   │                 工具层 (Tools)                  │      │
│   │  TavilySearch │ FileTool │ CodeInterpreter     │      │
│   │  RAGTool      │ ICLTool  │ GaodeMCPClient     │      │
│   └─────────────────────────────────────────────────┘     │
├──────────────────────────────────────────────────────────┤
│                     数据持久层                            │
│   SQLAlchemy ORM + SQLite / RAG: FAISS 向量索引           │
└──────────────────────────────────────────────────────────┘
```

---

## 技术栈

| 层级 | 技术选型 | 说明 |
|------|---------|------|
| **Web 框架** | FastAPI + Uvicorn | 异步高性能 Python Web 框架 |
| **前端** | HTML5 + CSS3 + Vanilla JS | 零依赖纯原生前端 |
| **LLM** | Qwen (通义千问) | 通过 DashScope API 调用 |
| **Agent 框架** | 自研 (非 LangChain) | 意图识别 → 任务规划 → 工具编排 |
| **地图服务** | 高德地图 API (MCP 封装) | POI/路线/天气/地理编码 |
| **实时搜索** | Tavily Search API | 互联网实时信息检索 |
| **向量数据库** | FAISS | RAG 检索增强 |
| **数据库** | SQLite + SQLAlchemy ORM | 用户/会话/资源存储 |
| **认证** | JWT + bcrypt | 用户认证与密码安全 |
| **流式响应** | SSE (Server-Sent Events) | 实时推送生成内容 |
| **迁移工具** | Alembic | 数据库版本管理 |

---

## 功能模块

### 用户系统
- 注册/登录/注销
- JWT Token 验证与自动刷新
- 个人信息管理、头像上传
- 密码重置

### 旅行规划
- 自然语言输入旅行需求
- 行程结构化输出（JSON + 可视化）
- 目的地智能推荐
- 交互式地图展示
- 行程方案导出（PDF/Excel）

### AI 对话
- 多轮对话上下文记忆
- 流式 SSE 实时输出
- 对话历史管理与回放
- 多会话切换

### 管理后台
- 用户管理与统计
- 会话监控
- 系统配置管理
- 操作审计日志
- 系统告警

### 安全机制
- JWT 认证
- bcrypt 密码加密
- 代码执行沙箱
- 路径安全校验
- 输入内容净化

---

## 项目结构

```
agent-main/
├── unified_server.py          # 主服务入口（FastAPI）
├── trip_api_v2.py             # V2 行程规划 API
├── config.py                  # 全局配置管理
├── data_models_design.py      # Pydantic 数据模型
│
├── core/                      # 核心模块
│   ├── agent_self/            # Agent 核心（意图识别/任务规划/工具编排）
│   │   ├── agent.py           # 主 Agent 类
│   │   └── unified_llm.py     # 统一 LLM 接口
│   ├── agent_mcp/             # 高德地图 MCP 客户端
│   │   ├── agent_mcp_gaode.py # 高德 API 封装
│   │   └── gaode_trip_wrapper.py
│   ├── agent_memory/          # 记忆与对话历史管理
│   ├── agent_tools/           # 工具实现
│   │   ├── tools.py           # 主工具集
│   │   ├── rag_tool.py        # RAG 检索工具
│   │   └── icl_tool.py        # ICL 学习工具
│   ├── RAG_agent/             # RAG 检索引擎
│   ├── ICL_agent/             # 上下文学习代理
│   ├── auth/                  # 认证服务
│   ├── database/              # 数据库层 (SQLAlchemy ORM)
│   ├── user_system/           # 用户与会话系统
│   ├── prompts/               # 系统提示词模板
│   └── utils/                 # 工具函数
│
├── api/                       # API 路由
│   ├── auth_routes.py         # 认证相关路由
│   ├── admin_routes.py        # 管理后台路由
│   └── profile_routes.py      # 用户资料路由
│
├── static/                    # 前端页面
│   ├── *.html                 # 页面模板
│   ├── css/                   # 样式文件
│   ├── js/                    # 前端逻辑
│   └── images/                # 图片资源
│
├── admin/                     # 管理后台前端
├── gradio/                    # Gradio 开发调试界面
├── local_models/              # 本地模型配置 (不含权重文件)
└── create_admin.py            # 管理员创建脚本
```

---

## 快速开始

### 环境要求

- Python 3.10+
- 高德地图 API Key（[高德开放平台](https://lbs.amap.com/)）
- DashScope API Key（[阿里云百炼](https://bailian.console.aliyun.com/)）
- Tavily Search API Key（[Tavily](https://tavily.com/)）

### 安装步骤

```bash
# 1. 克隆项目
git clone https://github.com/Cloud-Forest01/Tourism-Intelligent-Agent.git
cd Tourism-Intelligent-Agent/agent-main

# 2. 创建虚拟环境
python -m venv .venv
source .venv/bin/activate  # Linux/Mac
# .venv\Scripts\activate   # Windows

# 3. 安装依赖
pip install -r requirements.txt

# 4. 配置环境变量
cp .env.example .env
# 编辑 .env 文件，填入你的 API Key

# 5. 初始化数据库
python -c "from core.database.models import Base; from core.database.repository import engine; Base.metadata.create_all(bind=engine)"

# 6. 创建管理员（可选）
python create_admin.py

# 7. 启动服务
python unified_server.py

# 访问 http://localhost:8000
```

### 环境变量说明

需在 `.env` 文件中配置以下变量：

```env
# AI 提供商
AI_PROVIDER=qwen
DASHSCOPE_API_KEY=你的通义千问API密钥

# 高德地图
GAODE_REST_API_KEY=你的高德Web服务密钥
GAODE_API_KEY=你的高德JS API密钥

# 搜索服务
TAVILY_API_KEY=你的Tavily搜索密钥

# JWT 安全
JWT_SECRET_KEY=你的JWT密钥

# 可选：其他模型提供商
# OPENAI_API_KEY=
# DEEPSEEK_API_KEY=
# ANTHROPIC_API_KEY=
# ZHIPU_API_KEY=
```

---

## API 文档

启动服务后访问：`http://localhost:8000/docs` (Swagger UI)

### 主要接口

| 端点 | 方法 | 说明 |
|------|------|------|
| `/api/chat` | POST | AI 聊天 |
| `/api/chat/stream` | POST | 流式 AI 聊天 (SSE) |
| `/api/trip/plan` | POST | 行程规划 |
| `/api/trip/plan/stream` | POST | 流式行程规划 |
| `/api/conversations` | GET/POST/DELETE | 会话管理 |
| `/api/auth/register` | POST | 用户注册 |
| `/api/auth/login` | POST | 用户登录 |
| `/api/auth/me` | GET | 获取当前用户信息 |
| `/api/admin/dashboard` | GET | 管理后台概览 |

---

## 许可证

本项目仅用于学习使用。

---

## 联系方式

GitHub: [Cloud-Forest01](https://github.com/Cloud-Forest01)

---

*Built with FastAPI + Qwen + Gaode Maps + Tavily Search*
