# chat_agent_qwen/agent_self/agent.py
import asyncio
from .chat_agent_qwen_3_max import QwenModel
from ..agent_tools.tools import (
    BaseTool,
    SecureCodeInterpreterTool,
    FileRunnerTool,
    TavilySearchTool,
    FileTool,
)
from ..agent_tools.rag_tool import RAGTool
from ..agent_tools.icl_tool import ICLTool
from ..ICL_agent.icl_agent import ICLAgent
from ..agent_mcp.agent_mcp_gaode import MCPClient
from ..agent_memory.memory import MemoryManager
from ..prompts.system_prompts import TASK_PLANNER_SYSTEM_PROMPT, TOOL_USAGE_GUIDELINES
from ..utils.json_parser import RobustJSONParser
from ..utils.message_validator import MessageValidator
from ..utils.step_context import StepContext, TaskStep, ExecutionStrategy
import logging
from enum import Enum
from pydantic import BaseModel, Field, create_model
import re
import os
import json
from typing import List, Dict, Any, Tuple, Callable, Coroutine, Optional

logger = logging.getLogger(__name__)


class Intent(Enum):
    """用户意图的枚举类型"""
    GENERAL_CHAT = "general_chat"
    TOOL_INFO_QUERY = "tool_info_query"
    KNOWLEDGE_QUERY_ICL = "knowledge_query_icl"
    KNOWLEDGE_QUERY_RAG = "knowledge_query_rag"
    COMPLEX_TASK = "complex_task"


class Agent:
    def __init__(self, model: QwenModel, memory: MemoryManager, use_conversation_system: bool = False):
        self.model = model
        self.memory = memory
        self.use_conversation_system = use_conversation_system
        self.file_runner = FileRunnerTool()
        self.mcp_client = MCPClient()
        self.file_tool = FileTool(llm_model=model, memory_manager=memory)
        self.icl_agent = ICLAgent(model)
        self.icl_tool = ICLTool(self.icl_agent)
        self.tools: Dict[str, BaseTool] = {}
        self.tool_methods: Dict[str, Coroutine] = {} # ✅ 新增：存储 MCP 工具方法

        # 如果启用会话系统，初始化会话管理器
        self._conversation_manager = None
        if use_conversation_system:
            self.memory.enable_conversation_system()

    def _save_assistant_message(self, user_id: str, content: str, conversation_id: Optional[str] = None):
        """
        保存助手回复到历史（支持会话系统）

        Args:
            user_id: 用户ID
            content: 回复内容
            conversation_id: 会话ID（可选）
        """
        if self.use_conversation_system and conversation_id:
            # 使用会话系统
            self.memory.add_message_to_conversation(user_id, conversation_id, "assistant", content)
        else:
            # 使用传统方式
            self.memory.update_history(user_id, {"role": "assistant", "content": content})
        
    async def _register_tools(self) -> None:
        """注册所有工具（包括MCP工具）"""
        # ✅ 步骤 1: 获取 MCP 工具的方法和元数据
        mcp_tool_methods = await self.mcp_client.get_tool_methods()
        mcp_tools_metadata = await self.mcp_client.get_tools_metadata()

        # ✅ 直接将MCP方法注册到tool_methods（用于执行）
        self.tool_methods.update(mcp_tool_methods)
        logger.info(f"✅ 加载了 {len(mcp_tool_methods)} 个 MCP 工具方法: {list(mcp_tool_methods.keys())}")

        # ✅ 步骤 2: 将 MCP 元数据转换为 BaseTool 兼容对象以便统一描述
        mcp_tools_as_basetools = {}
        for meta in mcp_tools_metadata:
            properties_dict = meta.get('parameters', {}).get('properties', {})

            # 动态创建 Pydantic 模型作为 args_schema
            args_fields = {}
            for field_name, field_definition in properties_dict.items():
                mcp_type = field_definition.get("type", "string")
                python_type = {
                    "string": str,
                    "integer": int,
                    "number": float,
                    "boolean": bool,
                }.get(mcp_type, str)

                description = field_definition.get("description", "")
                args_fields[field_name] = (python_type, Field(..., description=description))

            dynamic_args_model = create_model(
                f"{meta['name']}Args",
                **args_fields
            ) if args_fields else None

            # 创建 BaseTool 兼容的类
            tool_class = type(
                meta['name'],
                (BaseTool,),
                {
                    'name': meta['name'],
                    'description': meta['description'],
                    'args_schema': dynamic_args_model,
                }
            )
            mcp_tools_as_basetools[meta['name']] = tool_class(
                name=meta['name'],
                description=meta['description']
            )

        # ✅ 步骤 3: 合并所有工具描述对象（用于LLM查看）
        self.tools = {
            "web_search": TavilySearchTool(),
            "secure_python_interpreter": SecureCodeInterpreterTool(),
            "run_created_file": self.file_runner,
            "rag_query": RAGTool(),
            "in_context_learning_search": self.icl_tool,
            "file_tool": self.file_tool,
            **mcp_tools_as_basetools  # 合并 MCP 工具的描述对象
        }
        logger.info(f"✅ 工具描述已注册: {list(self.tools.keys())}")
        logger.info(f"✅ 工具执行方法已注册: {list(self.tool_methods.keys())}")


    def list_tools(self) -> str:
        """返回所有工具的描述字符串，供LLM使用。"""
        tool_strings = []
        for name, tool in self.tools.items():
            # 基础描述
            description = getattr(tool, 'description', 'No description available.')
            tool_str = f"- {name}: {description}"

            # 尝试获取并格式化参数
            if hasattr(tool, 'args_schema') and hasattr(tool.args_schema, 'model_fields'):
                params = tool.args_schema.model_fields
                if params:
                    param_details = []
                    for param_name, field_info in params.items():
                        param_desc = getattr(field_info, 'description', '')
                        param_details.append(f"  - {param_name}: {param_desc}")
                    if param_details:
                        tool_str += "\n  参数:\n" + "\n".join(param_details)
            tool_strings.append(tool_str)
        
        return "\n".join(tool_strings)

    async def _classify_intent(self, user_input: str, history: List[Dict]) -> Intent:
        """使用LLM对用户意图进行分类"""
        # 只使用最近1轮历史，避免token超限
        recent_history = history[-1:] if history else []

        # 限制历史内容长度，每条最多500字符
        truncated_history = []
        for msg in recent_history:
            content = msg.get("content", "")
            if len(content) > 500:
                content = content[:500] + "...[截断]"
            truncated_history.append({"role": msg.get("role"), "content": content})

        prompt = f"""
[任务]
根据用户的最新指令，将其分类到以下意图之一：

1.  **general_chat**: 普通闲聊、问候、推荐类问题、简单询问（AI基于对话历史和知识库回答）。
    (示例: "你好", "你叫什么名字?", "今天天气真好", "推荐住宿", "有什么好玩的", "美食推荐")
2.  **tool_info_query**: 询问关于Agent能力、可用工具的问题。
    (示例: "你能做什么?", "你有哪些工具?")
3.  **knowledge_query_icl**: （已弃用，转为general_chat）
4.  **knowledge_query_rag**: 需要从本地知识库中查找特定信息的问题。
    (示例: "深圳有哪些必去景点?", "介绍一下大鹏所城")
5.  **complex_task**: 需要执行多个步骤、调用一个或多个工具才能完成的复杂请求。
    (示例: "规划一个从深圳到北京的三日游", "帮我查一下从我家到公司怎么走，并把路线图画出来", "查天气并规划路线")

[历史对话]
{truncated_history if truncated_history else "无"}

[用户最新指令]
"{user_input[:1000]}"  # 限制用户输入长度

[输出]
请仅返回最匹配的意图类别名称（例如: "complex_task"）。
"""
        response = await self.model.agenerate(prompt)
        intent_str = response.strip().lower()

        try:
            return Intent(intent_str)
        except ValueError:
            logger.warning(f"未知的意图: '{intent_str}', 降级为 'complex_task'")
            return Intent.COMPLEX_TASK

    async def _need_tool_use(self, user_input: str, history: List[Dict]) -> bool:
        """(异步)判断是否需要使用工具。"""
        # 如果工具列表为空，先注册
        if not self.tools:
            await self._register_tools()

        # 只使用最近1轮历史，避免token超限
        recent_history = history[-1:] if history else []

        # 限制历史内容长度
        truncated_history = []
        for msg in recent_history:
            content = msg.get("content", "")
            if len(content) > 300:
                content = content[:300] + "...[截断]"
            truncated_history.append({"role": msg.get("role"), "content": content})

        prompt = f"""
[可用工具]
{self.list_tools()}

[历史对话]
{truncated_history if truncated_history else "无"}

[用户最新指令]
"{user_input[:500]}"

[判断任务]
根据用户的最新指令，判断是否必须使用上述一个或多个工具才能完成。
- 如果用户在进行常规聊天、打招呼、问候、表达观点，而没有提出具体的操作性需求，则回答 "否"。
- 如果用户的指令明确要求或暗示了需要进行搜索、计算、查询、画图、文件操作等，则回答 "是"。
- 如果用户的指令是关于代码或执行代码，则回答 "是"。
- 如果用户的指令是查询关于工具本身能做什么，则回答 "否"。

请只回答 "是" 或 "否"。
"""
        # 使用异步生成方法
        response = await self.model.agenerate(prompt)
        decision = response.strip()
        logger.info(f"工具使用决策: '{decision}' (原始输出: '{response}')")
        return "是" in decision

    async def plan_tasks(self, user_input: str, user_id: str, conversation_id: Optional[str] = None) -> List[TaskStep]:
        """异步任务规划（确保工具已加载）"""
        # ✅ 优先使用会话系统获取历史
        if self.use_conversation_system and conversation_id:
            history = self.memory.get_conversation_history(user_id, conversation_id, max_messages=20)
        else:
            # 回退到旧方式（兼容性）
            memory = self.memory.load_memory(user_id)
            history = memory["conversation_history"]

        if not self.tools:
            await self._register_tools()

        # ✅ 使用 list_tools() 生成更简洁、结构化的工具列表
        system_content = (
            f"{TASK_PLANNER_SYSTEM_PROMPT}\n\n"
            f"{TOOL_USAGE_GUIDELINES}\n\n"
            f"可用工具列表:\n{self.list_tools()}"
        )

        prompt = [
                        {"role": "system", "content": system_content},
                        {"role": "system", "content": """⚠️ 【最关键的约束 - 必须严格遵守】

你的职责是: 将用户请求拆解为 JSON 格式的任务步骤列表，由系统执行这些步骤后生成最终攻略。
你绝对不应该: 直接生成攻略文本、行程安排、Markdown格式的回答。

❌ 禁止输出格式示例（这些都是错误的，会导致系统失败）:
- # 北京两日游攻略
- ## 第一天行程
- 1. 早上9点出发...
- 任何包含时间、景点介绍的段落文本

✅ 唯一正确的输出格式: 纯 JSON 数组，包含 goal、tool_name、parameters 三个字段。

示例:
[
    {"goal": "搜索北京景点", "tool_name": "maps_text_search", "parameters": {"keywords": "故宫", "city": "北京"}},
    {"goal": "查询天气", "tool_name": "maps_weather", "parameters": {"city": "北京"}}
]

输出格式: 严格 JSON 数组,每个对象仅包含 goal、tool_name、parameters 三个字段。

绝对约束(必须遵守,否则执行会失败):
1) 工具名必须为具体的官方名称,例如: maps_geo, maps_driving, maps_walking, maps_direction_transit_integrated, maps_text_search, maps_around_search, maps_search_detail, maps_weather, maps_regeocode, maps_distance, file_tool, web_search, rag_query, in_context_learning_search。
     - 严禁使用任何中介别名(如 mcp_tool)。不要输出 {\"tool_name\": \"mcp_tool\"} 这样的结构。
     - 严禁在 parameters 内再次嵌套 {\"tool_name\": ..., \"parameters\": ...}。
2) 占位符仅允许字段/下标访问,格式: {step_N_result.field} 或 {step_N_result.array[0].field}。
     - 严禁任何方法/函数调用(例如 .split(), .get(), int(), float() 等)与任何算术/比较运算(+, -, *, /, %, >, < 等)。
     - 如果需要坐标,高德返回结果已提供独立字段: lng(经度,浮点数), lat(纬度,浮点数)。请直接引用:
             • {step_0_result.geocodes[0].lng} / {step_0_result.geocodes[0].lat}
             • {step_1_result.pois[0].lng} / {step_1_result.pois[0].lat}
         若工具需要完整坐标字符串(如 maps_direction_* 的 origin/destination),请引用已有的 location 字段:
             • {step_0_result.geocodes[0].location} 或 {step_1_result.pois[0].location}
3) 步骤索引从 0 开始,只能引用之前步骤的结果(不得引用当前或未来步骤)。

正确示例:
[
    {"goal": "获取深圳技术大学经纬度", "tool_name": "maps_geo", "parameters": {"address": "深圳技术大学"}},
    {"goal": "规划驾车路线", "tool_name": "maps_driving", "parameters": {"origin": "{step_0_result.geocodes[0].location}", "destination": "114.029963,22.609185"}}
]

错误示例(禁止):
[
    {"tool_name": "mcp_tool", "parameters": {"tool_name": "maps_geo", "parameters": {"address": "深圳"}}}
]
"""},
                ]

        # 减少历史对话轮数，从3改为1
        prompt = MessageValidator.safe_extend_history(prompt, history, max_count=1)
        prompt.append({"role": "user", "content": user_input[:1000]})  # 限制用户输入长度

        validated_prompt = MessageValidator.validate_messages(prompt)
        response = self.model.generate(validated_prompt).strip()

        logger.info(f"📋 任务规划原始输出长度: {len(response)} 字符")
        logger.debug(f"📋 任务规划完整输出（前500字符）: {response[:500]}...")

        steps_data = RobustJSONParser.parse(response)

        if not steps_data or not isinstance(steps_data, list):
            logger.warning(f"❌ 任务规划失败: 无法解析为列表")
            logger.warning(f"📋 解析失败时的输出片段（前1000字符）: {response[:1000]}...")
            logger.warning(f"📋 输出总长度: {len(response)} 字符")
            logger.warning("💡 提示: 如果输出被截断，可能是token限制，已自动尝试修复截断的JSON")
            return []

        logger.info(f"✅ 成功解析任务步骤: {len(steps_data)} 个步骤")
        try:
            return [TaskStep(**s) for s in steps_data]
        except Exception as e:
            logger.warning(f"⚠️ 任务步骤解析失败: {e} | 数据: {steps_data}")
            return []

    async def execute_step(self, step: TaskStep, user_id: str) -> Tuple[bool, Any]:
        """执行单个步骤，支持自定义 MCP 工具方法和标准工具"""
        
        # ✅ 调试日志：打印当前步骤和可用工具
        logger.info(f"🔍 准备执行步骤: {step.tool_name}")
        logger.debug(f"📋 可用MCP工具方法: {list(self.tool_methods.keys())}")
        logger.debug(f"📋 可用标准工具: {list(self.tools.keys())}")
        
        # ⚠️ 友好拦截: 若仍出现历史别名 mcp_tool, 直接给出明确错误与指导
        if step.tool_name == "mcp_tool":
            guidance = (
                "检测到无效工具名 'mcp_tool'。请直接使用具体的官方工具名, 例如: "
                f"{', '.join(sorted(list(self.tool_methods.keys()))[:8])} ...。"
                "不要在 parameters 内再次嵌套 tool_name/parameters; 按 {tool_name, parameters} 直接提供。"
            )
            logger.error(guidance)
            return False, {"error": guidance}
        
        # ✅ 优先检查是否为 MCP 工具方法
        if step.tool_name in self.tool_methods:
            target_callable = self.tool_methods[step.tool_name]
            logger.info(f"🛠️ 执行 MCP 工具方法: {step.goal} | 工具: {step.tool_name} | 参数: {step.parameters}")
            try:
                result = await target_callable(**step.parameters)
                logger.info(f"✅ MCP 工具 '{step.tool_name}' 执行成功")
                return True, result
            except Exception as e:
                error_msg = f"MCP 工具 '{step.tool_name}' 执行错误: {str(e)}"
                logger.error(error_msg, exc_info=True)
                return False, {"error": error_msg}

        # 检查标准工具
        tool = self.tools.get(step.tool_name)
        if not tool:
            all_available = list(self.tools.keys()) + list(self.tool_methods.keys())
            error_msg = f"❌ 工具 '{step.tool_name}' 不存在。可用工具: {all_available}"
            logger.error(error_msg)
            return False, error_msg

        try:
            logger.info(f"🛠️ 执行标准工具: {step.goal} | 工具: {step.tool_name} | 参数: {step.parameters}")
            
            # --- ✅ 修改开始：确保 params 是字典，并注入 user_id ---
            original_params = step.parameters
            # 确保 params 是一个字典，以便我们可以安全地添加 user_id 等键值对
            if isinstance(original_params, dict):
                # 使用 copy() 避免修改原始 step.parameters (虽然通常不是必需的，但更安全)
                params = original_params.copy() 
            else:
                # 如果 params 不是字典 (例如 None, str, list 等)
                # 1. 记录警告，因为这可能不是预期的行为
                logger.warning(
                    f"步骤 '{step.tool_name}' 的参数不是字典类型 (类型: {type(original_params)})。"
                    f"将尝试将其作为 'input' 参数传递给工具，并为需要的工具注入 user_id。"
                )
                # 2. 创建一个新的字典来存放参数
                #    - 将原始参数 (如果不是 None) 放入 'input' 键下。
                #    - 这是一种通用的处理方式，但具体工具可能需要不同的处理逻辑。
                #    - 对于 file_tool，它期望的是扁平的键值对参数，
                #      所以我们主要关心 user_id 的注入。如果原始参数很重要，
                #      工具内部需要能处理 'input' 键，或者这里需要更复杂的逻辑。
                params = {}
                if original_params is not None:
                    params["input"] = original_params # 可根据工具约定调整键名

            # 为特定工具注入 user_id（带兜底：CURRENT_USER_ID 或 anonymous）
            if step.tool_name == "file_tool":
                effective_uid = (user_id or os.environ.get("CURRENT_USER_ID") or "anonymous")
                if not params.get("user_id"):
                    params["user_id"] = effective_uid
                    logger.debug(f"已为工具 '{step.tool_name}' 注入 user_id: {effective_uid}")

            # 处理 ICL tool 的特殊情况 (如果适用)
            # 注意：如果 original_params 不是字典，这可能不适用或需要调整
            if step.tool_name == "in_context_learning_search" and "query" not in params:
                 # 注意：如果 step.goal 不是字符串或不适合做 query，这里可能需要调整
                params["query"] = getattr(step, 'goal', '') # 使用 getattr 避免 AttributeError
            # --- ✅ 修改结束 ---

            # --- ✅ 修改：调用工具 ---
            # 现在 params 肯定是字典了，可以安全地使用 **kwargs 解包
            if hasattr(tool, 'arun'):
                raw_result = await tool.arun(**params) # type: ignore
            else:
                # 注意：如果 params 不是工具 run 方法期望的类型（例如，它是一个字典，
                # 但工具 run 期望一个字符串或位置参数），这可能会失败。
                # 理想情况下，所有工具都应该统一使用 arun/run 并接受字典参数。
                # 这里我们保持原逻辑，但如果 params 结构复杂，可能需要更细致的处理。
                raw_result = tool.run(**params)
            # --- ✅ 修改结束 ---

            # --- ✅ 修改：结果处理 ---
            # 标准工具可能返回字符串，尝试解析为 JSON
            # 也有可能直接返回 Python 对象 (dict, list 等)
            if isinstance(raw_result, str):
                try:
                    # 尝试解析为 JSON 对象
                    parsed_result = json.loads(raw_result)
                except (json.JSONDecodeError, TypeError):
                    # 如果解析失败，保留原始字符串
                    logger.debug(f"工具 '{step.tool_name}' 返回的字符串无法解析为JSON，将作为原始字符串处理。")
                    parsed_result = raw_result
            else:
                # 如果不是字符串，直接使用返回值
                parsed_result = raw_result

            logger.info(f"✅ 标准工具 '{step.tool_name}' 执行成功")
            return True, parsed_result
            # --- ✅ 修改结束 ---
            
        except Exception as e:
            error_msg = f"标准工具 '{step.tool_name}' 执行错误: {str(e)}"
            logger.error(error_msg, exc_info=True)
            return False, {"error": error_msg}

    async def run(
        self,
        user_input: str,
        user_id: str = "default",
        conversation_id: Optional[str] = None,
        use_icl: bool = False,
        strategy: ExecutionStrategy = ExecutionStrategy.GRACEFUL_DEGRADE,
        stream_callback: Optional[Callable[[str], Coroutine]] = None,
        preloaded_data: Optional[Dict[str, Any]] = None
    ):
        """执行Agent主流程（异步生成器，支持流式输出）

        Args:
            user_input: 用户输入
            user_id: 用户ID
            conversation_id: 会话ID（可选，如果启用会话系统）
            use_icl: 是否使用ICL
            strategy: 执行策略 (失败处理方式)
            stream_callback: 用于流式输出的异步回调函数（已废弃，现在直接 yield）
            preloaded_data: 预加载数据（包含天气、POI等基础信息）

        Yields:
            str: 流式输出的文本片段
        """
        full_response = ""

        try:
            # ✅ 确保工具已异步注册（包括MCP）
            if not self.tools:
                await self._register_tools()
                logger.info(f"✅ 已注册 {len(self.tools)} 个工具")

            # 保存用户消息到历史
            if self.use_conversation_system and conversation_id:
                # 使用会话系统
                self.memory.add_message_to_conversation(user_id, conversation_id, "user", user_input)
            else:
                # 使用传统方式
                self.memory.update_history(user_id, {"role": "user", "content": user_input})

            # 1. 意图分类（静默执行，不显示给用户）
            # ✅ 优先使用会话系统获取历史
            if self.use_conversation_system and conversation_id:
                history_for_intent = self.memory.get_conversation_history(user_id, conversation_id, max_messages=20)
            else:
                memory = self.memory.load_memory(user_id)
                history_for_intent = memory["conversation_history"]
            intent = await self._classify_intent(user_input, history_for_intent)
            logger.info(f"🔍 意图分析: {intent.value}")  # 仅记录到日志，不输出给用户

            # 2. 根据意图执行不同逻辑
            if intent == Intent.GENERAL_CHAT:
                # 构建用于普通聊天的 Prompt
                # ✅ 优先使用会话系统获取历史
                if self.use_conversation_system and conversation_id:
                    history = self.memory.get_conversation_history(user_id, conversation_id, max_messages=20)
                else:
                    memory = self.memory.load_memory(user_id)
                    history = memory["conversation_history"]

                # 使用 ICL Agent 的示例（如果启用且有示例）
                icl_examples = ""
                if use_icl and self.icl_agent.examples:
                    icl_examples = "\n\n".join([f"示例 {i+1}:\n用户: {ex['query']}\n助手: {ex['response']}" for i, ex in enumerate(self.icl_agent.examples)])

                system_prompt = f"""你是一个旅行规划智能助手。请根据对话历史和你的知识库回答用户的问题。

**重要指导原则**：
1. **充分利用对话历史**：用户的问题可能承接上文（例如"推荐住宿"可能是指前面提到的旅行目的地）
2. **使用你的知识库**：基于你的训练数据提供推荐，不要编造具体价格（可以给大概范围）
3. **实用为主**：提供具体、可操作的建议（住宿类型、价格区间、注意事项）
4. **保持友好**：用自然的对话语气，避免过于机械化

{icl_examples}
"""
                # 构建 Messages
                messages = [{"role": "system", "content": system_prompt}]
                messages = MessageValidator.safe_extend_history(messages, history, max_count=2)  # 从5改为2
                messages.append({"role": "user", "content": user_input[:1000]})  # 限制用户输入长度
                validated_messages = MessageValidator.validate_messages(messages)

                # 调用模型流式生成
                response_generator = self.model.stream_generate(validated_messages) 
                
                # 流式输出
                if hasattr(response_generator, '__aiter__'):
                    async for chunk in response_generator:
                        full_response += chunk
                        yield chunk
                elif hasattr(response_generator, '__iter__'):
                    for chunk in response_generator:
                        full_response += chunk
                        yield chunk
                else:
                    # 如果不是生成器，直接输出
                    chunk = str(response_generator)
                    full_response += chunk
                    yield chunk

                self._save_assistant_message(user_id, full_response, conversation_id)
                return

            if intent == Intent.TOOL_INFO_QUERY:
                reply = "我具备以下能力：\n" + self.list_tools()
                full_response += reply
                yield reply
                self._save_assistant_message(user_id, reply, conversation_id)
                return

            # ✅ 修改：将 ICL 意图转为普通对话，让 AI 基于历史上下文回答
            if intent == Intent.KNOWLEDGE_QUERY_ICL:
                logger.info(f"🔄 ICL意图转为普通对话: {user_input[:50]}...")
                intent = Intent.GENERAL_CHAT  # 转为普通闲聊，利用对话历史和AI知识库

            if intent == Intent.KNOWLEDGE_QUERY_RAG:
                chunk = "正在查询本地知识库...\n\n"
                full_response += chunk
                yield chunk
                tool = self.tools["rag_query"]
                result = await tool.arun(query=user_input)
                result_str = str(result)
                full_response += result_str
                yield result_str
                self._save_assistant_message(user_id, full_response, conversation_id)
                return

            # --- 默认执行复杂任务逻辑 ---
            # 静默执行，不显示提示信息
            logger.info("🔧 开始规划任务步骤")
            steps = await self.plan_tasks(user_input, user_id, conversation_id)
            if not steps:
                reply = "抱歉，我无法为您的请求规划出有效的执行步骤。请尝试换一种方式提问，或者描述得更具体一些。"
                full_response += reply
                yield reply
                self._save_assistant_message(user_id, reply, conversation_id)
                return

            # 静默执行步骤，不显示详细信息（仅记录日志）
            logger.info(f"📋 已规划 {len(steps)} 个执行步骤")

            # ✅ 如果有预加载数据，检查哪些步骤可以跳过
            skipped_steps = []
            if preloaded_data:
                for i, step in enumerate(steps):
                    # 检查是否应该跳过这个工具
                    if step.tool_name == "maps_weather" and preloaded_data.get("weather"):
                        skipped_steps.append(i)
                        logger.info(f"⏭️ 步骤 {i+1} ({step.tool_name}) 已跳过（数据已预加载）")
                    elif step.tool_name == "maps_text_search" and preloaded_data.get("pois"):
                        skipped_steps.append(i)
                        logger.info(f"⏭️ 步骤 {i+1} ({step.tool_name}) 已跳过（POI已预加载）")

            step_context = StepContext()
            steps_results = []

            for i, step in enumerate(steps):
                # ✅ 跳过已预加载的步骤
                if i in skipped_steps:
                    # 使用预加载的数据作为结果
                    if step.tool_name == "maps_weather":
                        result = preloaded_data["weather"]
                        step_context.set_result(i, result)
                        steps_results.append((step, result))
                        logger.info(f"✅ 步骤 {i+1} 使用预加载的天气数据")
                    elif step.tool_name == "maps_text_search":
                        result = preloaded_data["pois"]
                        step_context.set_result(i, result)
                        steps_results.append((step, result))
                        logger.info(f"✅ 步骤 {i+1} 使用预加载的POI数据")
                    continue

                logger.info(f"🔧 执行步骤 {i+1}: {step.goal}")
                try:
                    resolved_params = step_context.replace_placeholders(step.parameters, i)
                    resolved_step = TaskStep(goal=step.goal, tool_name=step.tool_name, parameters=resolved_params)
                except ValueError as e:
                    logger.error(f"步骤 {i} 参数解析失败: {e}")
                    if strategy == ExecutionStrategy.FAIL_FAST:
                        final_reply = f"抱歉，任务在'{step.goal}'步骤中断，因为参数准备失败。"
                        full_response += final_reply
                        yield final_reply
                        self._save_assistant_message(user_id, full_response, conversation_id)
                        return
                    success, result = False, {"error": str(e)}
                    resolved_step = step
                else:
                    success, result = await self.execute_step(resolved_step, user_id)

                if not success:
                    error_msg = str(result)
                    logger.error(f"步骤 {i+1} 执行失败: {error_msg}")
                    if strategy == ExecutionStrategy.FAIL_FAST:
                        reply = f"抱歉，在执行'{step.goal}'时遇到问题：{error_msg}\n\n请尝试重新描述您的需求。"
                        full_response += reply
                        yield reply
                        self._save_assistant_message(user_id, full_response, conversation_id)
                        return
                    elif strategy == ExecutionStrategy.GRACEFUL_DEGRADE:
                        logger.info(f"步骤失败，降级为纯对话模式")
                        break

                try:
                    if isinstance(result, str):
                        result_dict = RobustJSONParser.parse(result)
                        step_context.set_result(i, result_dict if result_dict and isinstance(result_dict, dict) else {"raw": result, "success": success})
                    else:
                        step_context.set_result(i, result if isinstance(result, dict) else {"raw": str(result), "success": success})
                    logger.info(f"✅ 步骤 {i} 完成")
                except Exception as parse_error:
                    logger.warning(f"⚠️ 步骤 {i} 结果保存失败: {parse_error}")
                    step_context.set_result(i, {"raw": str(result), "success": success, "error": str(parse_error)})

                steps_results.append((resolved_step, result))
                # ❌ 已移除：不再将工具执行细节保存到对话历史
                # 原因：这些技术细节会导致对话历史膨胀，前端加载历史时崩溃
                # 工具结果已整合到最终的 assistant 回复中，无需额外保存
                # 如需调试，请查看日志文件中的完整执行记录

            # 调用结果整合方法（异步生成器）
            async for chunk in self.integrate_results_stream(user_input, steps_results, user_id, preloaded_data):
                full_response += chunk
                yield chunk

            self._save_assistant_message(user_id, full_response, conversation_id)

        except Exception as e:
            logger.error(f"Agent 主流程发生意外错误: {e}", exc_info=True)
            error_message = f"\n\n--- \n**系统错误** \n抱歉，我在处理您的请求时遇到了一个意外的问题: `{str(e)}` \n请稍后再试或联系技术支持。"
            full_response += error_message
            yield error_message
            # 确保即使在顶层异常中，最终的错误信息也被记录
            self._save_assistant_message(user_id, full_response, conversation_id)
    
    async def integrate_results_stream(
        self,
        user_input: str,
        steps_results: List[Tuple[TaskStep, Any]],
        user_id: str,
        preloaded_data: Optional[Dict[str, Any]] = None
    ):
        """整合所有步骤结果，生成最终回复（流式输出）

        Args:
            user_input: 用户原始输入
            steps_results: 所有步骤的执行结果列表 [(TaskStep, result), ...]
            user_id: 用户ID
            preloaded_data: 预加载数据（包含天气、POI、图片等）

        Yields:
            str: 生成的文本片段
        """
        try:
            # ✅ 步骤 1: 提取关键信息
            extracted_data = self._extract_key_information(steps_results)

            # ✅ 步骤 1.5: 动态加载真实POI的图片（基于AI实际调用的结果）
            # 从user_input中提取destination城市信息
            import re
            destination_match = re.search(r'计划去(\w+)旅行', user_input)
            destination = destination_match.group(1) if destination_match else None
            extracted_data = await self._load_poi_images_from_results(extracted_data, steps_results, destination)
            
            # ✅ 步骤 2: 构建整合提示词
            from ..prompts.system_prompts import RESULT_INTEGRATION_SYSTEM_PROMPT

            # 精简版：只生成工具调用摘要，不包含详细结果（减少token）
            tool_calls_summary = []
            poi_keywords = set()
            search_count = 0
            detail_count = 0
            web_search_count = 0

            for step, result in steps_results:
                tool_name = step.tool_name

                if tool_name == "maps_text_search":
                    search_count += 1
                    # 提取POI名称关键词
                    if isinstance(result, dict) and "pois" in result:
                        pois = result.get("pois", [])[:2]  # 只取前2个
                        for poi in pois:
                            name = poi.get("name", "")
                            if name:
                                poi_keywords.add(name)

                elif tool_name == "maps_search_detail":
                    detail_count += 1

                elif tool_name == "web_search":
                    web_search_count += 1

            # 生成摘要（只2-3行）
            if search_count > 0:
                poi_list = list(poi_keywords)[:4]  # 最多4个
                poi_str = "、".join(poi_list)
                tool_calls_summary.append(f"- 景点搜索: {poi_str}{' 等' if len(poi_keywords) > 4 else ''} ({search_count}次搜索)")
            if detail_count > 0:
                tool_calls_summary.append(f"- 详情获取: {detail_count}个POI")
            if web_search_count > 0:
                tool_calls_summary.append(f"- 信息搜索: 美食/住宿/交通 ({web_search_count}次搜索)")

            steps_text = f"已执行 {len(steps_results)} 个工具调用：\n" + "\n".join(tool_calls_summary) + "\n\n详细数据已提取，见下方结构化信息"
            
            # 获取历史对话
            memory = self.memory.load_memory(user_id)
            history = memory["conversation_history"]
            
            # ✅ 步骤 3: 构建增强的整合提示
            integration_prompt = self._build_integration_prompt(
                user_input,
                steps_text,
                extracted_data
            )

            # 构建消息
            messages = [
                {"role": "system", "content": RESULT_INTEGRATION_SYSTEM_PROMPT},
                {"role": "user", "content": integration_prompt}
            ]

            # 添加部分历史上下文（最多1轮，节省token）
            messages = MessageValidator.safe_extend_history(messages, history, max_count=1)

            # ✅ Token限制检查：估算总token数，如果超过25000则截断
            def estimate_tokens(text: str) -> int:
                """粗略估算token数：中文约1.5字=1token，英文约4字=1token"""
                chinese_chars = len([c for c in text if '\u4e00' <= c <= '\u9fff'])
                non_chinese = len(text) - chinese_chars
                return int(chinese_chars / 1.5 + non_chinese / 4)

            def truncate_prompt_if_needed(prompt: str, max_tokens: int = 28000) -> str:
                """截断prompt以避免token超限"""
                estimated = estimate_tokens(prompt)
                if estimated <= max_tokens:
                    return prompt

                # 智能截断策略：优先保留重要部分
                # 1. 保留开头（系统指令）
                # 2. 保留结尾的检查清单和强制限制
                # 3. 中间的数据部分可以适度压缩

                # 查找关键标记位置
                sections_to_keep = []

                # 保留开头到"**最后检查清单**"之前的内容
                checklist_pos = prompt.find("**最后检查清单**")
                if checklist_pos > 0:
                    # 保留前70%的内容 + 最后的检查清单
                    target_chars = int(len(prompt) * 0.7)
                    if target_chars > checklist_pos:
                        target_chars = checklist_pos - 100  # 留出余量

                    truncated = prompt[:target_chars]

                    # 追加最后的检查清单和强制限制部分
                    if "**🚨 输出格式强制限制" in prompt:
                        limit_pos = prompt.find("**🚨 输出格式强制限制")
                        if limit_pos > target_chars:
                            truncated += "\n\n" + prompt[limit_pos:]
                    elif checklist_pos > target_chars:
                        truncated += "\n\n" + prompt[checklist_pos:]
                else:
                    # 如果找不到检查清单，简单截断
                    target_chars = int(len(prompt) * (max_tokens / estimated) * 0.85)
                    truncated = prompt[:target_chars]

                # 在截断处添加提示
                if len(truncated) < len(prompt):
                    truncated += "\n\n...[内容因长度限制被截断，但关键数据和格式要求已包含]..."

                logger.warning(f"⚠️ Prompt过长({estimated} tokens)，已截断至约{max_tokens} tokens")
                return truncated

            # 截断system和user消息
            for msg in messages:
                if msg["role"] in ["system", "user"]:
                    msg["content"] = truncate_prompt_if_needed(msg["content"])

            # 验证消息
            validated_messages = MessageValidator.validate_messages(messages)

            # 流式生成最终回复（同时收集正文用于后续判断是否需要兜底追加）
            generated_chunks: List[str] = []
            async for chunk in self.model.astream_generate(validated_messages):
                generated_chunks.append(str(chunk))
                yield chunk
            
            # ✅ 步骤 4: 在流式输出后追加资源：文件、地图、图片（仅在正文未包含时兜底追加）
            body_text = "".join(generated_chunks)
            has_appended_header = False

            # 4.1 追加文件链接
            if extracted_data.get("file_paths"):
                yield "\n\n---\n\n"
                has_appended_header = True
                yield "📄 **生成的文件**:\n\n"
                for file_info in extracted_data["file_paths"]:
                    file_type = file_info.get("type", "文件")
                    file_path = file_info.get("path", "")
                    if file_path:
                        yield f"- [{file_type}]({file_path})\n"
                        logger.info(f"✅ 添加文件链接: {file_path}")

            # 4.2 图片预览已移除（图片已内联到正文中，不再追加）
            # if extracted_data.get("images"):
            #     if not has_appended_header:
            #         yield "\n\n---\n\n"
            #         has_appended_header = True
            #     # 若正文中已经包含图片（通过 Markdown ![]() 或包含已知 URL）则不再兜底
            #     body_has_inline_image = ("![" in body_text) or any(
            #         isinstance(u, str) and u in body_text for u in extracted_data["images"]
            #     )
            #     if not body_has_inline_image:
            #         yield "🖼️ **图片预览**:\n\n"
            #         # 支持每个景点多张图片（假定 images 为所有图片，分组逻辑可后续增强）
            #         for i, url in enumerate(extracted_data["images"][:10], start=1):
            #             if isinstance(url, str) and url.startswith("http"):
            #                 yield f"- 图片 {i}: {url}\n"
            #                 yield f"![图片 {i}]({url})\n"
            #                 logger.info(f"✅ 兜底追加图片URL: {url}")

        except Exception as e:
            logger.error(f"结果整合失败: {e}", exc_info=True)
            yield f"\n\n⚠️ 整合结果时遇到问题: {str(e)}\n\n"
            yield "不过，根据执行的步骤，我可以告诉您：\n"
            
            # 降级方案：简单列出结果
            for i, (step, result) in enumerate(steps_results):
                yield f"\n{i+1}. {step.goal}: "
                if isinstance(result, dict) and "error" not in result:
                    yield "✅ 成功"
                else:
                    yield "⚠️ 部分完成"
    
    def _extract_key_information(self, steps_results: List[Tuple[TaskStep, Any]]) -> Dict[str, Any]:
        """从步骤结果中提取关键信息
        
        Args:
            steps_results: 所有步骤的执行结果
            
        Returns:
            包含提取信息的字典
        """
        extracted = {
            "weather_data": [],
            "file_paths": [],
            "routes": [],
            "pois": [],
            "images": [],
            "web_search_images": [],  # [{query, image_urls}]
            "web_search_answers": [],  # [{query, answer}] - 新增：存储web_search的文本答案
            "poi_images": {}          # {poi_name: [urls]}
        }
        
        for step, result in steps_results:
            tool_name = step.tool_name
            
            # ✅ 提取天气数据
            if tool_name == "maps_weather" and isinstance(result, dict):
                if "forecasts" in result:
                    extracted["weather_data"].extend(result["forecasts"])
                    logger.info(f"✅ 提取天气数据: {len(result['forecasts'])} 条")
            
            # ✅ 提取文件路径
            elif tool_name == "file_tool" and isinstance(result, str):
                # file_tool 返回的是文件路径字符串
                if result and not result.startswith("错误"):
                    file_type = "行程文档"
                    if ".html" in result:
                        file_type = "HTML文档"
                    elif ".pdf" in result:
                        file_type = "PDF文档"
                    elif ".xlsx" in result or ".xls" in result:
                        file_type = "Excel表格"
                    
                    extracted["file_paths"].append({
                        "type": file_type,
                        "path": result
                    })
                    logger.info(f"✅ 提取文件路径: {result}")

            # ✅ 提取路线信息
            elif "direction" in tool_name and isinstance(result, dict):
                if "paths" in result or "route" in result:
                    extracted["routes"].append({
                        "tool": tool_name,
                        "data": result
                    })
                    logger.info(f"✅ 提取路线信息: {tool_name}")
            
            # ✅ 提取 POI 信息（支持多日旅行，增加数量限制）
            elif tool_name == "maps_text_search" and isinstance(result, dict):
                if "pois" in result:
                    # 对于旅行规划，需要提取更多POI以支持多日行程
                    # 如果已经有很多POI（>20个），就只取1个；否则取前3个
                    current_count = len(extracted["pois"])
                    take_count = 1 if current_count > 20 else 3
                    extracted["pois"].extend(result["pois"][:take_count])
                    logger.info(f"✅ 提取 POI 信息: {len(result['pois'])} 个，已限制为前{take_count}个（当前总计{current_count + take_count}个）")
            
            # ✅ 提取搜索结果中的图片 URL 和答案文本
            elif tool_name == "web_search":
                # 1) 优先从结构化字段提取（推荐路径）
                if isinstance(result, dict):
                    # 提取答案文本（餐厅、住宿等推荐）
                    answer_text = result.get("answer") or ""
                    try:
                        query_text = ""
                        if isinstance(step.parameters, dict):
                            query_text = step.parameters.get("query", "") or ""
                    except Exception:
                        query_text = ""

                    if answer_text and query_text:
                        extracted["web_search_answers"].append({
                            "query": query_text,
                            "answer": answer_text
                        })
                        logger.info(f"✅ 从 web_search 提取答案: query='{query_text[:30]}...', answer长度={len(answer_text)}")

                    # 提取图片URL
                    image_urls = result.get("image_urls") or []
                    if isinstance(image_urls, list) and image_urls:
                        # 最多保留 5 张
                        urls = [u for u in image_urls[:5] if isinstance(u, str)]
                        extracted["images"].extend(urls)
                        if query_text:
                            extracted["web_search_images"].append({
                                "query": query_text,
                                "image_urls": urls
                            })
                        logger.info(f"✅ 从 web_search.image_urls 提取图片: {len(urls)} 张 | query='{query_text[:40]}'")
                # 2) 兼容旧路径：从字符串结果中用正则提取
                elif isinstance(result, str):
                    import re
                    image_urls = re.findall(r'https?://[^\s<>"]+?\.(?:jpg|jpeg|png|gif|webp)', result)
                    if image_urls:
                        extracted["images"].extend(image_urls[:3])  # 最多3张
                        logger.info(f"✅ 从字符串结果提取图片 URL: {len(image_urls)} 个")

        # 基于 web_search 的 query 粗略将图片绑定到 POI（按名称包含关系）
        try:
            poi_names = []
            for poi in extracted.get("pois", []) or []:
                name = poi.get("name") or poi.get("title")
                if isinstance(name, str) and name:
                    poi_names.append(name)
            if poi_names and extracted.get("web_search_images"):
                for pair in extracted["web_search_images"]:
                    q = (pair.get("query") or "").lower()
                    urls = pair.get("image_urls") or []
                    if not q or not urls:
                        continue
                    # 找到名称与 query 互为包含的 POI
                    target = None
                    for pn in poi_names:
                        pn_l = pn.lower()
                        if pn_l in q or q in pn_l:
                            target = pn
                            break
                    if target:
                        bucket = extracted["poi_images"].setdefault(target, [])
                        for u in urls:
                            if isinstance(u, str) and u not in bucket:
                                bucket.append(u)
        except Exception as e:
            logger.warning(f"⚠️ 绑定图片到 POI 映射时发生问题: {e}")
        
        return extracted

    def _should_load_poi_image(self, poi: Dict[str, Any]) -> bool:
        """判断POI是否需要加载图片

        只加载景点、名胜古迹、博物馆等，过滤掉宾馆、饭店、商场等

        Args:
            poi: POI数据

        Returns:
            True表示需要加载图片，False表示跳过
        """
        # 获取POI名称和类型
        name = poi.get("name", "").lower()
        typecode = poi.get("typecode", "")
        poi_type = poi.get("type", "").lower()

        # 关键词黑名单：包含这些关键词的POI不加载图片
        blacklist_keywords = [
            "酒店", "宾馆", "旅馆", "青旅", "旅店", "招待所",
            "餐厅", "饭店", "美食", "小吃", "火锅", "烧烤",
            "商场", "购物", "超市", "便利店", "药店"
        ]

        # 检查名称是否包含黑名单关键词
        for keyword in blacklist_keywords:
            if keyword in name:
                return False

        # 根据高德typecode过滤
        # typecode格式：大类中类小类，如 "110101" 表示风景名胜
        if typecode:
            # 大类编码（前3位或前2位）
            major_type = typecode[:3] if len(typecode) >= 3 else typecode[:2]

            # 需要加载的类型
            # 11xxxx: 风景名胜
            # 14xxxx: 科教文化服务（博物馆、图书馆等）
            # 08xxxx: 体育休闲服务（部分，如公园）
            if major_type in ["110", "11", "140", "14", "080", "08"]:
                return True

            # 过滤掉住宿服务（10xxxx）、餐饮服务（05xxxx）、购物服务（06xxxx）
            if major_type in ["100", "10", "050", "05", "060", "06"]:
                return False

        # 根据type字段过滤
        if poi_type:
            # 需要的类型
            scenic_types = ["风景名胜", "景点", "博物馆", "古迹", "公园", "教堂", "寺庙", "文化"]
            if any(t in poi_type for t in scenic_types):
                return True

            # 过滤掉的类型
            filter_types = ["住宿", "餐饮", "购物", "服务"]
            if any(t in poi_type for t in filter_types):
                return False

        # 默认加载（如果没有明确的类型信息）
        return True

    async def _load_poi_images_from_results(
        self,
        extracted_data: Dict[str, Any],
        steps_results: List[Tuple[TaskStep, Any]],
        destination: Optional[str] = None
    ) -> Dict[str, Any]:
        """根据AI实际调用的POI结果，使用高德API的photos字段加载图片

        只使用高德地图API，不使用web_search兜底
        只加载景点类型的POI图片，过滤掉宾馆、饭店、商场等

        Args:
            extracted_data: 已提取的关键信息
            steps_results: 所有步骤的执行结果
            destination: 目的地城市（用于精确搜索）

        Returns:
            注入图片后的提取信息（包含有图片的景点和无图片景点列表）
        """
        try:
            # 1. 从步骤结果中找到所有 maps_text_search 的调用
            poi_list = []
            search_count = 0
            filtered_count = 0  # 记录被过滤的POI数量

            for step, result in steps_results:
                if step.tool_name == "maps_text_search" and isinstance(result, dict):
                    if result.get("success") and "pois" in result:
                        pois = result.get("pois", [])
                        if pois:
                            # 取前3个POI，但只保留需要加载图片的
                            for poi in pois[:3]:
                                if self._should_load_poi_image(poi):
                                    poi_list.append(poi)
                                else:
                                    filtered_count += 1
                                    logger.debug(f"  🔍 过滤POI: {poi.get('name', 'Unknown')} (type: {poi.get('typecode', 'N/A')})")

                            search_count += 1
                            logger.info(f"✅ 从 maps_text_search #{search_count} 提取到 {len([p for p in pois[:3] if self._should_load_poi_image(poi)])} 个景点POI (共{len(pois)}个, 过滤{filtered_count}个)")

            if not poi_list:
                logger.info("ℹ️ 未找到 maps_text_search 的POI结果，跳过图片加载")
                return extracted_data

            logger.info(f"🔄 为 {len(poi_list)} 个POI加载高德图片... (来自 {search_count} 次搜索, 城市: {destination})")

            # 2. 定义辅助函数：从高德photos字段提取图片
            def extract_images_from_gaode_photos(poi):
                """从高德API返回的photos字段中提取图片"""
                photos = poi.get("photos", [])
                if not photos:
                    return []

                # photos格式: [{"title": "图片介绍", "url": "具体链接"}, ...]
                image_list = []
                for photo in photos:
                    if isinstance(photo, dict):
                        url = photo.get("url", "")
                        title = photo.get("title", "")
                        if url and url.startswith("http"):
                            image_list.append({
                                "url": url,
                                "title": title
                            })
                return image_list

            # 3. 处理每个POI的图片（只使用高德API）
            pois_with_images = []  # 有图片的景点
            pois_without_images = []  # 无图片的景点

            for poi in poi_list:
                poi_name = poi.get("name", "")
                gaode_images = extract_images_from_gaode_photos(poi)

                if gaode_images:
                    # 有图片的景点
                    logger.info(f"  ✅ {poi_name}: 从高德API获取到 {len(gaode_images)} 张图片")
                    pois_with_images.append({"poi": poi, "images": gaode_images})
                else:
                    # 无图片的景点 - 记录下来用于后续提示
                    logger.info(f"  ℹ️ {poi_name}: 高德API无图片")
                    pois_without_images.append(poi)

            # 4. 将有图片的POI注入到 extracted_data
            total_images = 0
            for item in pois_with_images:
                poi = item.get("poi", {})
                images = item.get("images", [])
                poi_name = poi.get("name", "")

                if not images or not poi_name:
                    continue

                # 提取URL列表（兼容旧格式）
                urls = [img.get("url", "") for img in images if img.get("url")]

                # 添加到全局图片列表
                extracted_data.setdefault("images", [])
                for url in urls[:1]:  # 每个POI最多1张（减少token）
                    if url and url not in extracted_data["images"]:
                        extracted_data["images"].append(url)

                # 按POI名称分组（包含完整信息：url + title）
                extracted_data.setdefault("poi_images", {})
                extracted_data["poi_images"].setdefault(poi_name, [])
                for img in images[:1]:  # 每个POI最多1张（减少token）
                    url = img.get("url", "")
                    title = img.get("title", "")
                    if url:
                        # 检查是否已存在（处理字典和字符串两种格式）
                        already_exists = False
                        for existing in extracted_data["poi_images"][poi_name]:
                            if isinstance(existing, dict):
                                if existing.get("url") == url:
                                    already_exists = True
                                    break
                            elif isinstance(existing, str):
                                if existing == url:
                                    already_exists = True
                                    break

                        if not already_exists:
                            extracted_data["poi_images"][poi_name].append({
                                "url": url,
                                "title": title
                            })

                total_images += len(urls[:1])

            # 5. 记录无图片的景点列表（用于生成人性化提示）
            if pois_without_images:
                extracted_data["pois_without_images"] = [poi.get("name", "") for poi in pois_without_images]
                logger.info(f"📝 记录无图片景点: {', '.join(extracted_data['pois_without_images'])}")

            logger.info(f"✅ POI图片加载完成: 有图片 {len(extracted_data.get('poi_images', {}))} 个景点, 无图片 {len(pois_without_images)} 个景点, 总计 {total_images} 张图片")

            return extracted_data

        except Exception as e:
            logger.error(f"❌ POI图片加载时出错: {e}", exc_info=True)
            return extracted_data

    def _build_integration_prompt(
        self, 
        user_input: str, 
        steps_text: str, 
        extracted_data: Dict[str, Any]
    ) -> str:
        """构建增强的整合提示
        
        Args:
            user_input: 用户原始输入
            steps_text: 步骤执行结果文本
            extracted_data: 提取的关键信息
            
        Returns:
            整合提示词
        """
        prompt_parts = [
            f"[用户原始问题]",
            user_input,
            "",
            f"[执行步骤及结果]",
            steps_text,
            "",
            f"[任务]",
            "请基于以上步骤的执行结果，生成一个连贯、自然、信息完整且可直接渲染的 Markdown 回复。",
            "",
            f"**核心要求**:"
        ]
        
        # ✅ 添加天气数据要求（精简版）
        if extracted_data.get("weather_data"):
            forecast = extracted_data["weather_data"][0]
            casts = forecast.get("casts", [])

            if casts:
                weather_summary = "; ".join([
                    f"第{i+1}天({c.get('date','N/A')}):{c.get('dayweather','N/A')}/{c.get('nightweather','N/A')} {c.get('daytemp','N/A')}°C/{c.get('nighttemp','N/A')}°C"
                    for i, c in enumerate(casts[:4])
                ])
                prompt_parts.extend([
                    f"1. **天气** (必须引用): {weather_summary}",
                    ""
                ])
        
        # ✅ 添加 POI 信息要求（精简版，避免token超限）
        if extracted_data.get("pois"):
            pois_count = len(extracted_data["pois"])
            # 只列出前2个POI的名称，不展开详细信息
            poi_names = [poi.get('name', 'N/A') for poi in extracted_data['pois'][:2]]
            poi_list_str = "、".join(poi_names)

            prompt_parts.extend([
                f"2. **景点POI信息** (必须使用真实数据，共{pois_count}个):",
                f"   - 主要景点: {poi_list_str}{' 等' if pois_count > 2 else ''}",
                f"   - ⚠️ **强制要求**: 对每个重要景点生成独立小节（使用景点名称作为二级标题 ##）",
                f"   - 每个景点必须包含: 详细地址、类型、门票、开放时间",
                f"   - ❌ 不要向用户显示坐标信息(lng, lat)，但内部计算时仍需使用",
                f"   - ❌ 禁止纯编号列表堆砌，要有描述性段落",
                ""
            ])

        # ✅ 添加无图片景点的提示说明（移到前面，避免被截断）
        if extracted_data.get("pois_without_images"):
            pois_without = extracted_data["pois_without_images"]
            if pois_without:
                prompt_parts.extend([
                    f"3. **无图景点** (必须单独成section): {', '.join(pois_without)}",
                    f"   - ⚠️ **位置要求**: 在'## ⚠️ 避坑指南'之前单独开一个section，标题为'## 📷 部分景点无图片说明'",
                    f"   - ⚠️ **格式要求**:",
                    f"     ```",
                    f"     ## 📷 部分景点无图片说明",
                    f"     ",
                    f"     > 小You没有找到获取到这里的图片，那美丽的景色就留给你自己去探索吧~",
                    f"     ```",
                    f"   - ❌ **严禁**: 不要把这个section合并到'避坑指南'、'实用贴士'等其他section里",
                    f"   - ✅ **正确**: 单独成section，位置在'避坑指南'之前",
                    ""
                ])

        # ✅ 添加图片要求（内联插入）
        if extracted_data.get("poi_images"):
            # 限制：最多15个景点，每个景点最多1张图片（增加限制以覆盖更多景点）
            poi_items = list(extracted_data.get("poi_images", {}).items())[:15]
            # 直接提供完整的markdown语法示例
            image_examples = []
            for poi, urls in poi_items:
                if urls:
                    # 处理字典和字符串两种格式
                    first_img = urls[0]
                    if isinstance(first_img, dict):
                        url = first_img.get('url', '')
                    elif isinstance(first_img, str):
                        url = first_img
                    else:
                        continue

                    if url:
                        image_examples.append(f"   - {poi}: ![{poi}]({url})")

            image_list = "\n".join(image_examples)
            prompt_parts.extend([
                "4. **图片展示（必须内联）**:\n"
                "   - 以下图片URL已经格式化为markdown语法，直接复制粘贴到对应景点描述下方即可\n"
                "   - 为每个关键景点插入 1 张图片；图片紧贴在景点描述后，单独成行\n"
                f"   - 可用图片（共{len(image_examples)}个景点）：\n{image_list}\n"
                "   ❌ **绝对禁止**: 使用 example.com、placeholder.jpg 等示例链接\n"
                "   ✅ **正确做法**: 直接复制上面的markdown代码到对应景点下方\n"
                ""
            ])

        # ✅ 添加路线信息要求（精简版）
        if extracted_data.get("routes"):
            route_data = extracted_data["routes"][0].get("data", {})
            if "paths" in route_data and route_data["paths"]:
                path = route_data["paths"][0]
                distance = path.get('distance_km', 'N/A')
                duration = path.get('duration_min', 'N/A')

                prompt_parts.extend([
                    f"5. **路线** (精确数值): {distance}公里/{duration}分钟, 必须引用,禁止'大约/可能'"
                    ""
                ])

        # ✅ 添加web_search答案（餐厅、住宿推荐）
        if extracted_data.get("web_search_answers"):
            answers_count = len(extracted_data["web_search_answers"])
            prompt_parts.append(f"6. **搜索结果** (必须使用以下真实数据):")

            for item in extracted_data["web_search_answers"][:3]:  # 最多3个答案（减少token）
                query = item.get("query", "")
                answer = item.get("answer", "")
                # 限制答案长度到250字符（减少token）
                if len(answer) > 250:
                    answer = answer[:250] + "...[截断]"
                prompt_parts.extend([
                    f"   搜索: {query[:60]}",
                    f"   结果: {answer[:200]}..." if len(answer) > 200 else f"   结果: {answer}",
                    ""
                ])
            prompt_parts.extend([
                f"   ⚠️ 在美食/住宿/交通部分直接引用上述搜索结果",
                f"   - 有具体店名→列出;只区域推荐→如实转述",
                f"   - 禁止编造",
                ""
            ])

        # ✅ 添加通用要求（精简版）
        prompt_parts.extend([
            f"8. 整合信息(路线/距离/时间/天气/景点),内联图片和地图链接,Markdown格式",
            f"",
            f"**🚨 输出格式强制限制**:",  # ← 改为与截断逻辑匹配的标记
            f"❌ 住宿/美食无图;无每日小结;无天气预案;无图片汇总",
            f"❌ 禁止编造景点/餐厅/酒店!只用工具数据",
            f"✅ 图片内联景点中;结尾总结",
            f"",
            f"**📋 数据规则**:",
            f"✅ 景点: 从POI列表选,不够则说明'只找到X个,需更多请告诉我'",
            f"✅ 美食: 有店名→列出;无→'推荐去XX路附近,人均XX元'",
            f"✅ 住宿: 有名称→列出;无→'建议XX预算内选XX区域青旅'",
            f"",
            f"当前POI: {len(extracted_data.get('pois', []))}个",
            f"",
            f"**最后检查清单**: 真实数据,禁用'可能/大约',住宿美食无图,仅结尾总结,不编造",
            f"",
            f"**📋 Section结构检查**:",
            f"✅ 无图景点 → 单独section '## 📷 部分景点无图片说明' (在避坑指南前)",
            f"❌ 无图景点 → 不要放在避坑指南/实用贴士里"
        ])

        return "\n".join(prompt_parts)

