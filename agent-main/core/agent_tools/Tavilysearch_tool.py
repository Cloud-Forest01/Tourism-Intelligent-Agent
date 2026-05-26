# tavily_search_tools.py
"""
Tavily Search 工具集 - 用于执行 Web 搜索和内容提取

此模块提供 TavilySearchTool 和 TavilyExtractTool，它们封装了 Tavily API 的功能。
通过 TavilySearchToolManager 进行统一管理和初始化。

API配置来源：config.py
"""

import os
import sys
from pathlib import Path
import logging
from typing import List, Any, Optional, Dict, Literal
import re
from langchain_core.tools import BaseTool
from tavily import AsyncTavilyClient
from pydantic import Field, BaseModel

# 导入API配置
# 添加项目根目录到系统路径
project_root = Path(__file__).resolve().parent.parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

from config import Config

# 设置日志记录器
logger = logging.getLogger(__name__)

# --- 新增：定义 TavilySearchTool 和 TavilyExtractTool 的参数模型 ---
# 这有助于更好地定义工具的输入参数结构和进行类型检查


class TavilyExtractParams(BaseModel):
    """Tavily Extract 工具的参数模型"""
    urls: List[str] = Field(..., description="要提取内容的 URL 列表")


class TavilySearchParams(BaseModel):
    """Tavily Search 工具的参数模型"""
    query: str = Field(..., description="搜索关键词")
    search_depth: Literal["basic", "advanced"] = Field(default="advanced", description="搜索深度")
    max_results: int = Field(default=5, description="返回的最大结果数")
    days: Optional[int] = Field(default=None, description="限制搜索结果的天数")
    include_answer: bool = Field(default=True, description="是否包含 AI 生成的答案")
    include_images: bool = Field(default=False, description="是否包含图片链接（默认禁用，避免外部图片）")


# 注意: TavilySearchTool 的实现在 tools.py 中被使用
# 此处的重复定义已被移除


class TavilyExtractTool(BaseTool):
    """Tavily 内容提取工具"""
    
    name: str = Field(default="tavily_extract", description="工具名称")
    description: str = Field(
        default="Extract clean, structured content from one or more URLs.",
        description="工具描述"
    )
    # --- ✅ 移除错误的 client 字段定义 ---
    # client: AsyncTavilyClient = Field(..., description="Tavily 异步客户端实例") # ❌ 不当的定义

    # --- ✅ 新增/修改：显式定义 __init__ 方法 ---
    def __init__(self, client: AsyncTavilyClient):
        """
        初始化 TavilyExtractTool。
        
        Args:
            client (AsyncTavilyClient): 已初始化的 Tavily 异步客户端实例。
        """
        # --- ✅ 关键修改 1: 设置 args_schema ---
        self.args_schema = TavilyExtractParams # ✅ 正确方式
        # --- ✅ 关键修改 2: 存储 client 实例 ---
        self.client = client # ✅ 正确方式
        # --- ✅ 关键修改 3: 调用父类 __init__ ---
        super().__init__( # type: ignore
            name="tavily_extract",
            description="Extract clean, structured content from one or more URLs.",
            args_schema=TavilyExtractParams, # 传入 args_schema 类
            client=client # 传入 client 实例
        )
        # --- ✅ 修改结束 ---

    # --- ✅ 保留 _arun 方法 ---
    async def _arun(self, **kwargs) -> Dict[str, Any]:
        """
        异步执行 Tavily 内容提取。

        Args:
            **kwargs: 提取参数，应符合 TavilyExtractParams 模型。
                      例如: urls=["http://example.com/page1", "http://example.com/page2"]

        Returns:
            Dict[str, Any]: Tavily API 返回的提取结果字典。
            
        Raises:
            ValueError: 如果参数验证失败或 URL 列表为空。
            RuntimeError: 如果 Tavily API 调用失败。
        """
        # --- ✅ 使用 Pydantic 模型验证和解析参数 ---
        try:
            params = TavilyExtractParams(**kwargs)
        except Exception as e:
            logger.error(f"TavilyExtractTool 参数验证失败: {e}")
            raise ValueError(f"参数验证失败: {e}")

        if not params.urls:
            logger.warning("TavilyExtractTool 接收到空的 URL 列表")
            raise ValueError("URL list cannot be empty.")
        try:
            logger.debug(f"调用 Tavily API extract: {params.urls}")
            response = await self.client.extract(urls=params.urls) # type: ignore
            logger.debug(f"Tavily API extract 响应: {response}")
            return response
        except Exception as e:
            logger.error(f"Tavily extract failed: {e}")
            raise RuntimeError(f"Tavily extract failed: {e}")

    def _run(self, *args, **kwargs):
        """同步执行方法未实现，强制使用异步版本"""
        raise NotImplementedError("Use async version only.")


class TavilySearchToolManager:
    """
    Tavily Search 工具管理器

    API配置来源：config.py
    """

    def __init__(self, api_key: Optional[str] = None):
        """
        初始化 TavilySearchToolManager。

        Args:
            api_key (Optional[str]): Tavily API 密钥。
                                   如果未提供，将从 Config 获取。
        """
        # 从 Config 获取API密钥（如果未提供）
        self.api_key = api_key or Config.TAVILY_API_KEY
        if not self.api_key:
            logger.warning("未提供 Tavily API 密钥，部分功能可能受限。")
        self.client = AsyncTavilyClient(api_key=self.api_key)
        self.tools: List[BaseTool] = []
        self._initialized = False

    async def initialize(self) -> List[BaseTool]:
        """
        异步初始化 Tavily 工具（创建 SDK 客户端并加载工具）。

        Returns:
            List[BaseTool]: 初始化后的工具列表。
        """
        if self._initialized:
            logger.info("Tavily 工具已初始化，返回缓存的工具列表。")
            return self.tools

        logger.info("🔄 正在初始化 TavilySearchToolManager...")
        try:
            # --- ✅ 正确实例化工具 ---
            # 直接将 self.client 作为关键字参数传递给工具的构造函数
            self.tools = [
                TavilySearchTool(client=self.client), # type: ignore # Pydantic 会处理
                TavilyExtractTool(client=self.client), # type: ignore # Pydantic 会处理
            ]
            self._initialized = True
            logger.info(f"✅ Tavily Search 工具加载成功，共 {len(self.tools)} 个")
            return self.tools
        except Exception as e:
            logger.error(f"❌ Tavily 工具初始化失败: {e}")
            # 优雅降级：返回空列表
            self.tools = []
            self._initialized = True # 标记为已尝试初始化
            return self.tools

    def get_tool_by_name(self, name: str) -> Optional[BaseTool]:
        """
        根据工具名称获取工具实例。

        Args:
            name (str): 工具名称。

        Returns:
            Optional[BaseTool]: 找到的工具实例，如果未找到则返回 None。
        """
        for tool in self.tools:
            if tool.name == name:
                return tool
        return None

    # --- 以下为便捷方法，供内部或外部直接调用 ---

    async def search_and_summarize(self, query: str, days: int = 30) -> str:
        """
        便捷方法：执行搜索并返回 AI 摘要。

        Args:
            query (str): 搜索查询。
            days (int, optional): 限制搜索结果的天数。 Defaults to 30.

        Returns:
            str: AI 生成的摘要。
        """
        if not self._initialized:
            await self.initialize()
            
        search_tool = self.get_tool_by_name("tavily_search")
        if not search_tool:
            raise ValueError("tavily_search 工具未加载")

        try:
            result = await search_tool._arun(query=query, days=days, include_answer=True)
            answer = result.get("answer", "").strip()
            if not answer:
                answer = "未能生成摘要，但可参考以下搜索结果。"
            return answer
        except Exception as e:
            logger.error(f"search_and_summarize 失败: {e}")
            return f"搜索摘要失败: {e}"

    async def search_and_extract(self, query: str, max_urls: int = 3) -> List[Dict[str, str]]:
        """
        便捷方法：先搜索，再提取前 N 个结果的内容。

        Args:
            query (str): 搜索查询。
            max_urls (int, optional): 要提取内容的最大 URL 数量。 Defaults to 3.

        Returns:
            List[Dict[str, str]]: 提取的内容列表，每个元素包含 url, title, raw_content。
        """
        if not self._initialized:
            await self.initialize()
            
        search_tool = self.get_tool_by_name("tavily_search")
        extract_tool = self.get_tool_by_name("tavily_extract")
        if not search_tool or not extract_tool:
            raise ValueError("所需工具未加载")

        try:
            search_result = await search_tool._arun(
                query=query, max_results=max_urls, include_answer=False
            )
            urls = [r["url"] for r in search_result.get("results", [])[:max_urls] if r.get("url")]
            if not urls:
                return []

            extract_result = await extract_tool._arun(urls=urls)
            extracted = []
            for item in extract_result.get("results", []):
                extracted.append({
                    "url": item.get("url", ""),
                    "title": item.get("title", ""),
                    "raw_content": (item.get("raw_content", "")[:500] + "...") if item.get("raw_content") else ""
                })
            return extracted
        except Exception as e:
            logger.error(f"search_and_extract 失败: {e}")
            return []


# --- 全局单例（可选）---
_tavily_manager: Optional[TavilySearchToolManager] = None

async def get_tavily_tools(api_key: Optional[str] = None) -> List[BaseTool]:
    """
    获取全局 Tavily 工具列表的便捷函数。

    Args:
        api_key (Optional[str]): Tavily API 密钥。

    Returns:
        List[BaseTool]: 初始化后的 Tavily 工具列表。
    """
    global _tavily_manager
    if _tavily_manager is None:
        _tavily_manager = TavilySearchToolManager(api_key=api_key)
        await _tavily_manager.initialize()
    return _tavily_manager.tools


async def tavily_search_and_summarize(query: str, days: int = 30) -> str:
    """
    全局便捷函数：执行 Tavily 搜索并返回 AI 摘要。

    Args:
        query (str): 搜索查询。
        days (int, optional): 限制搜索结果的天数。 Defaults to 30.

    Returns:
        str: AI 生成的摘要。
    """
    global _tavily_manager
    if _tavily_manager is None:
        await get_tavily_tools()
    assert _tavily_manager is not None
    return await _tavily_manager.search_and_summarize(query, days=days)
