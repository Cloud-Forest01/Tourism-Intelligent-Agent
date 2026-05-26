"""
统一LLM接口 - 支持多AI提供商切换
====================================
支持: 通义千问(Qwen)、OpenAI、DeepSeek、Anthropic Claude

使用方法:
    from core.agent_self.unified_llm import UnifiedLLM

    # 自动使用 .env 中 AI_PROVIDER 配置
    llm = UnifiedLLM(mode="fast")
    response = llm.generate(messages)

    # 指定AI提供商
    llm = UnifiedLLM(provider="openai", mode="deep")
    response = llm.generate(messages)
"""
from langchain_openai import ChatOpenAI
from langchain_core.callbacks import BaseCallbackHandler
from pydantic import SecretStr
from typing import AsyncIterator, Optional
import asyncio
import sys
from pathlib import Path
import logging

# 导入API配置
project_root = Path(__file__).resolve().parent.parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

from config import Config

logger = logging.getLogger(__name__)


# 定义自定义流式回调类
class PrintAndStoreHandler(BaseCallbackHandler):
    """在控制台实时打印token，并保存完整回复"""
    def __init__(self):
        self.current_text = ""

    def on_llm_new_token(self, token: str, **kwargs):
        print(token, end="", flush=True)
        self.current_text += token


class UnifiedLLM:
    """
    统一LLM接口类 - 支持多AI提供商

    支持的提供商:
    - qwen: 通义千问
    - openai: OpenAI GPT
    - deepseek: DeepSeek
    - anthropic: Anthropic Claude
    - zhipu: 智谱AI (GLM)
    """

    def __init__(self, provider: str = None, mode: str = "fast",
                 enable_thinking: bool = False, thinking_tokens: int = 2000):
        """
        初始化统一LLM接口

        Args:
            provider: AI提供商 (qwen, openai, deepseek, anthropic)
                     如果为None，则使用 Config.AI_PROVIDER 配置
            mode: 模型模式
                - "fast": 快速模式（成本低，响应快）
                - "deep": 深度思考模式（更智能，适合复杂任务）
            enable_thinking: 是否启用思考模式（仅通义千问支持）
                - True: 输出AI思考过程
                - False: 仅输出最终结果
            thinking_tokens: 思考过程最多使用的token数量（默认2000）
        """
        # 获取AI配置
        try:
            self.ai_config = Config.get_ai_config(provider)
        except ValueError as e:
            logger.error(f"AI配置错误: {e}")
            raise

        self.provider = self.ai_config["provider"]
        self.mode = mode
        self.model_name = self.ai_config["model_deep"] if mode == "deep" else self.ai_config["model_fast"]
        self.enable_thinking = enable_thinking
        self.thinking_tokens = thinking_tokens

        # 初始化流式回调
        self.handler = PrintAndStoreHandler()

        # 根据提供商创建对应的LLM实例
        self.llm = self._create_llm_instance()

        logger.info(f"✅ AI提供商初始化成功: {self.provider.upper()} | 模型: {self.model_name} | 模式: {mode}" +
                   (f" | 思考模式: 启用" if enable_thinking else ""))

    def _create_llm_instance(self):
        """根据提供商创建对应的LangChain LLM实例"""
        api_key = self.ai_config["api_key"]
        base_url = self.ai_config["base_url"]

        # Anthropic Claude 使用专用类（按需导入）
        if self.provider == "anthropic":
            try:
                from langchain_anthropic import ChatAnthropic
                return ChatAnthropic(
                    model=self.model_name,
                    api_key=SecretStr(api_key),
                    streaming=True,
                    callbacks=[self.handler],
                    temperature=0.7,
                    max_tokens=16000
                )
            except ImportError:
                logger.error("❌ langchain-anthropic 未安装")
                logger.error("💡 请运行: pip install langchain-anthropic")
                logger.error("📝 或在 requirements.txt 中添加: langchain-anthropic>=0.1.0")
                raise ImportError(
                    "使用 Claude 需要 langchain-anthropic 库。\n"
                    "请运行: pip install langchain-anthropic"
                )

        # 其他提供商使用 ChatOpenAI (支持OpenAI兼容接口)
        # 包括: Qwen、OpenAI、DeepSeek
        return ChatOpenAI(
            model=self.model_name,
            base_url=base_url,
            api_key=SecretStr(api_key),
            streaming=True,
            callbacks=[self.handler],
            temperature=0.7,
            max_tokens=16000
        )

    def generate(self, messages, **kwargs) -> str:
        """
        普通调用 - 返回完整文本(不实时打印)

        Args:
            messages: 消息列表
            **kwargs: 额外参数

        Returns:
            str: 完整回复文本
        """
        # 通义千问思考模式：在调用时传递额外参数
        if self.enable_thinking and self.provider == "qwen" and self.model_name != "qwen-max-thinking":
            # 将思考模式参数添加到调用中
            kwargs["extra_body"] = {
                "enable_thinking": True,
                "thinking_tokens": self.thinking_tokens
            }

        response = self.llm.invoke(messages, **kwargs)
        content = response.content

        # 如果启用思考模式，提取思考过程和最终答案
        if self.enable_thinking and self.provider == "qwen":
            return self._extract_thinking_process(content)

        return content

    def _extract_thinking_process(self, content: str) -> str:
        """
        从思考模式的输出中提取思考过程和最终答案

        Args:
            content: LLM返回的完整内容

        Returns:
            str: 格式化后的思考过程和答案
        """
        # 通义千问思考模式格式：<thinking>...</thinking>最终答案
        import re

        thinking_pattern = r'<thinking>(.*?)</thinking>'
        matches = re.findall(thinking_pattern, content, re.DOTALL)

        if matches:
            thinking_process = '\n\n'.join(matches).strip()
            # 移除思考标签后的剩余内容作为最终答案
            final_answer = re.sub(thinking_pattern, '', content, flags=re.DOTALL).strip()

            return f"""🧠 AI思考过程：
{'='*60}
{thinking_process}
{'='*60}

✅ 最终答案：
{final_answer}"""

        return content

    def stream_generate(self, messages) -> str:
        """
        流式输出 - 实时打印并返回完整回复

        Args:
            messages: 消息列表

        Returns:
            str: 完整回复文本
        """
        # 每次调用前重置handler缓存
        self.handler.current_text = ""
        self.llm.invoke(messages)
        return self.handler.current_text

    async def astream_generate(self, messages) -> AsyncIterator[str]:
        """
        异步流式生成 - 逐token返回

        Args:
            messages: 消息列表

        Yields:
            str: 单个token字符串
        """
        async for chunk in self.llm.astream(messages):
            # ✅ 只yield非空内容
            if hasattr(chunk, 'content') and chunk.content:
                content = str(chunk.content)  # 确保转换为字符串
                if content:  # 再次检查非空
                    yield content

    async def agenerate(self, messages, **kwargs) -> str:
        """
        异步生成 - 返回完整文本

        Args:
            messages: 消息列表
            **kwargs: 额外参数

        Returns:
            str: 完整回复文本
        """
        full_text = ""
        async for token in self.astream_generate(messages):
            full_text += token
        return full_text

    def get_model(self):
        """获取底层LangChain模型对象"""
        return self.llm

    def get_provider_info(self) -> dict:
        """获取当前AI提供商信息"""
        return {
            "provider": self.provider,
            "model": self.model_name,
            "mode": self.mode,
            "base_url": self.ai_config["base_url"]
        }


# ==================== 向后兼容 ====================
# 保留 QwenModel 类名，作为 UnifiedLLM 的别名
class QwenModel(UnifiedLLM):
    """
    向后兼容的 QwenModel 类

    注意: 此类现在是 UnifiedLLM 的别名
    如果未指定provider参数，默认使用 Config.AI_PROVIDER 配置
    """
    def __init__(self, model_mode: str = "fast"):
        """
        初始化Qwen模型（向后兼容）

        Args:
            model_mode: 模型模式 ("fast" 或 "deep")
        """
        # 为了向后兼容，如果未明确指定provider，则使用qwen
        provider = Config.AI_PROVIDER if Config.AI_PROVIDER == "qwen" else "qwen"
        super().__init__(provider=provider, mode=model_mode)


# ==================== 使用示例 ====================
if __name__ == "__main__":
    # 测试代码
    print("测试统一LLM接口...\n")

    # 示例1: 使用默认提供商 (从 .env 读取 AI_PROVIDER)
    llm = UnifiedLLM(mode="fast")
    print(f"当前提供商: {llm.get_provider_info()}")

    # 示例2: 指定提供商
    # llm_openai = UnifiedLLM(provider="openai", mode="deep")

    # 示例3: 向后兼容的 QwenModel
    # qwen = QwenModel(model_mode="fast")
