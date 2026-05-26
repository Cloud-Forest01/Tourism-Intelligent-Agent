"""
预加载工具管理器 - 在AI决策前并行加载核心信息

功能：
1. 并行加载天气和POI等基础信息
2. 将预加载数据注入到Agent上下文
3. 减少AI规划负担，提高响应速度
"""
import asyncio
import logging
from typing import Dict, Any, Optional, List
from datetime import datetime

logger = logging.getLogger(__name__)


class PreloadManager:
    """预加载管理器 - 智能加载旅行规划所需的基础信息"""

    def __init__(self, agent_instance):
        """
        初始化预加载管理器

        Args:
            agent_instance: Agent实例，用于访问工具
        """
        self.agent = agent_instance

    async def preload_destination_info(
        self,
        destination: str,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        预加载目的地的基础信息

        并行加载：
        1. 天气预报（影响行程安排）
        2. POI搜索（获取景点列表）

        注意：图片不再预加载，改为在结果整合阶段使用web_search动态获取

        Args:
            destination: 目的地城市
            start_date: 开始日期（可选）
            end_date: 结束日期（可选）

        Returns:
            Dict: {
                "weather": 天气数据,
                "pois": POI列表,
                "preload_time": 预加载耗时
            }
        """
        preload_start = asyncio.get_event_loop().time()

        try:
            # 确保工具已注册
            if not self.agent.tools:
                await self.agent._register_tools()

            # 并行加载天气和POI
            tasks = []
            results = {}

            # 任务1: 查询天气
            async def fetch_weather():
                try:
                    weather_tool = self.agent.tools.get("maps_weather")
                    if weather_tool and hasattr(weather_tool, 'arun'):
                        result = await weather_tool.arun(city=destination)
                        logger.info(f"✅ 预加载天气完成: {destination}")
                        return result
                except Exception as e:
                    logger.warning(f"⚠️ 预加载天气失败: {e}")
                    return None

            # 任务2: 搜索POI（不获取详情，图片由web_search动态加载）
            async def fetch_pois():
                try:
                    poi_tool = self.agent.tools.get("maps_text_search")
                    if poi_tool and hasattr(poi_tool, 'arun'):
                        result = await poi_tool.arun(
                            keywords=f"{destination}旅游景点",
                            city=destination
                        )
                        logger.info(f"✅ 预加载POI完成: {destination}，找到 {len(result.get('pois', []))} 个结果")
                        return result
                except Exception as e:
                    logger.warning(f"⚠️ 预加载POI失败: {e}")
                    return None

            # 并行执行
            tasks = [fetch_weather(), fetch_pois()]
            weather_result, pois_result = await asyncio.gather(*tasks, return_exceptions=True)

            # 处理结果
            results["weather"] = weather_result if not isinstance(weather_result, Exception) else None
            results["pois"] = pois_result if not isinstance(pois_result, Exception) else None

            # 计算耗时
            preload_time = asyncio.get_event_loop().time() - preload_start
            results["preload_time"] = round(preload_time, 2)

            logger.info(f"✅ 预加载完成，耗时 {results['preload_time']}秒")

            return results

        except Exception as e:
            logger.error(f"❌ 预加载失败: {e}", exc_info=True)
            return {
                "weather": None,
                "pois": None,
                "preload_time": 0,
                "error": str(e)
            }

    def format_preloaded_context(
        self,
        preloaded_data: Dict[str, Any],
        destination: str,
        user_requirements: Optional[str] = None
    ) -> str:
        """
        将预加载数据格式化为上下文信息

        Args:
            preloaded_data: 预加载的数据
            destination: 目的地
            user_requirements: 用户其他要求

        Returns:
            str: 格式化的上下文字符串
        """
        context_parts = []

        # 天气信息
        weather = preloaded_data.get("weather")
        if weather and isinstance(weather, dict):
            forecasts = weather.get("forecasts", [])
            if forecasts:
                context_parts.append("## 🌤️ 天气预报（已预加载）")
                for i, cast in enumerate(forecasts[:4], 1):
                    context_parts.append(
                        f"第{i}天 ({cast.get('date', 'N/A')}): "
                        f"{cast.get('dayweather', 'N/A')}，{cast.get('daytemp', 'N/A')}°C/"
                        f"{cast.get('nighttemp', 'N/A')}°C"
                    )
                context_parts.append("")

        # POI信息摘要（不包含图片，图片由web_search动态获取）
        pois = preloaded_data.get("pois")
        if pois and isinstance(pois, dict):
            poi_list = pois.get("pois", [])
            if poi_list:
                context_parts.append(f"## 🏛️ 景点列表（已预加载 {len(poi_list)} 个）")
                # 只显示前5个
                for poi in poi_list[:5]:
                    name = poi.get("name", "未知")
                    address = poi.get("address", "")
                    type_poi = poi.get("type", "")
                    context_parts.append(f"- **{name}** ({type_poi}): {address}")

                if len(poi_list) > 5:
                    context_parts.append(f"... 还有 {len(poi_list) - 5} 个景点")
                context_parts.append("")

        # 预加载提示
        if context_parts:
            context_parts.insert(0, f"---\n**已预加载 {destination} 的基础信息：**\n")
            context_parts.append(
                "**重要提示**：\n"
                "1. 以上POI信息包含 **真实POI ID**，可直接用于调用 maps_search_detail\n"
                "2. 图片将在结果整合阶段使用 web_search 动态获取（景点名 + 高清图片 实景）\n"
                "3. 你可以基于这些信息进行详细规划，无需重复查询基础信息\n"
                "4. 建议使用真实的POI ID来获取更多详细信息\n---"
            )

        return "\n".join(context_parts)

    def should_skip_tool(self, tool_name: str, preloaded_data: Dict[str, Any]) -> bool:
        """
        判断某个工具是否可以跳过（因为已预加载）

        Args:
            tool_name: 工具名称
            preloaded_data: 预加载的数据

        Returns:
            bool: True表示可以跳过
        """
        # 如果天气已预加载，跳过再次查询
        if tool_name == "maps_weather" and preloaded_data.get("weather"):
            return True

        # 如果POI已预加载，跳过重复搜索（但允许详情查询）
        if tool_name == "maps_text_search" and preloaded_data.get("pois"):
            # 检查是否是通用搜索，如果是特定关键词搜索则不跳过
            # 这里简化处理：如果有POI数据就跳过第一次搜索
            return True

        return False
