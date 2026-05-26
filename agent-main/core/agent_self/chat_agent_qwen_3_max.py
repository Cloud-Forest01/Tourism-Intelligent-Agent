"""
统一LLM接口 - 支持多AI提供商切换
====================================
支持: 通义千问(Qwen)、OpenAI、DeepSeek、Anthropic Claude

⚠️ 注意: 此文件现在是 unified_llm.py 的别名，为了向后兼容保留
建议新代码直接使用: from core.agent_self.unified_llm import UnifiedLLM
"""

# 直接导入统一LLM接口
from core.agent_self.unified_llm import UnifiedLLM, PrintAndStoreHandler

# 导出 QwenModel 作为向后兼容的别名
QwenModel = UnifiedLLM

__all__ = ['QwenModel', 'UnifiedLLM', 'PrintAndStoreHandler']
