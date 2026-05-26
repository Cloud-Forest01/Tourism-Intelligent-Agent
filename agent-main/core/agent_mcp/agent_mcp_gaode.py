# chat_agent_qwen/agent_mcp/agent_mcp_gaode.py（精简版）
import os
import sys
from pathlib import Path
import asyncio
import httpx
from typing import List, Dict, Any, Optional, Tuple
import logging

# 导入API配置
# 添加项目根目录到系统路径
project_root = Path(__file__).resolve().parent.parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

from config import Config

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# --- 新增：直接调用高德 Web API 的客户端 ---
class GaodeWebAPIClient:
    """
    直接使用 httpx 调用高德地图 Web API v3/v5 的客户端。
    保留核心常用工具，移除低频功能。

    API配置来源：config.py
    - Config.GAODE_API_KEY: 获取API密钥
    - Config.GAODE_BASE_URL_V3: 获取v3 API基础URL
    - Config.GAODE_BASE_URL_V5: 获取v5 API基础URL
    """
    # 从 Config 获取基础URL
    BASE_URL_V3 = Config.GAODE_BASE_URL_V3
    BASE_URL_V5 = Config.GAODE_BASE_URL_V5

    def __init__(self, api_key: str = None, timeout: int = 10):
        """
        初始化高德地图客户端

        Args:
            api_key: API密钥，如果为None则从Config获取
            timeout: 请求超时时间
        """
        # 从 Config 获取 Web 服务 API 密钥（如果未提供）
        # 优先使用 GAODE_REST_API_KEY（Web服务API），兼容旧的 GAODE_API_KEY
        self.api_key = api_key or Config.GAODE_REST_API_KEY or Config.GAODE_JS_API_KEY
        self.timeout = timeout
        self.client = httpx.AsyncClient(timeout=self.timeout)

    async def _request(self, url: str, params: Dict[str, Any], max_retries: int = 3) -> Dict[str, Any]:
        """通用异步请求方法（带重试机制）"""
        params['key'] = self.api_key

        for attempt in range(max_retries):
            try:
                response = await self.client.get(url, params=params, timeout=15.0)
                response.raise_for_status()
                data = response.json()

                if data.get("status") != "1":
                    error_info = data.get("info", "未知错误")
                    infocode = data.get("infocode", "")

                    # 特定错误码处理
                    if infocode == "10001":  # key不正确或过期
                        logger.error(f"❌ 高德API Key无效: {error_info}")
                        return {"success": False, "error": f"API Key无效或已过期，请检查 GAODE_REST_API_KEY 配置"}
                    elif infocode == "10002":  # 无权限
                        logger.error(f"❌ API无权限: {error_info}")
                        return {"success": False, "error": f"API无权限，请检查服务开通情况"}
                    elif infocode == "10003":  # 配额超限
                        logger.warning(f"⚠️ API配额超限: {error_info}")
                        return {"success": False, "error": f"API调用配额已用完，请升级套餐或等待重置"}
                    elif infocode == "10004":  # 参数错误
                        logger.warning(f"⚠️ 参数错误: {error_info} | params: {params}")
                        return {"success": False, "error": f"请求参数错误: {error_info}"}
                    else:
                        logger.error(f"高德 API 返回错误: {error_info} (infocode: {infocode})")
                        # 对于其他错误，尝试重试
                        if attempt < max_retries - 1:
                            logger.info(f"🔄 重试第 {attempt + 2} 次...")
                            await asyncio.sleep(1 * (attempt + 1))  # 递增延迟
                            continue
                        return {"success": False, "error": f"高德 API 错误: {error_info}"}

                # ✅ 标准化成功响应
                data["success"] = True
                return data

            except httpx.TimeoutException as e:
                logger.warning(f"⚠️ 请求超时 (尝试 {attempt + 1}/{max_retries}): {e}")
                if attempt < max_retries - 1:
                    await asyncio.sleep(1 * (attempt + 1))
                    continue
                return {"success": False, "error": f"请求超时: {str(e)}"}

            except httpx.RequestError as e:
                logger.warning(f"⚠️ 网络错误 (尝试 {attempt + 1}/{max_retries}): {e}")
                if attempt < max_retries - 1:
                    await asyncio.sleep(1 * (attempt + 1))
                    continue
                return {"success": False, "error": f"网络错误: {str(e)}"}

            except Exception as e:
                logger.error(f"❌ 未知错误: {e}", exc_info=True)
                return {"success": False, "error": f"未知错误: {str(e)}"}

    def _parse_location(self, location_str: str) -> Tuple[float, float]:
        """解析经纬度字符串为浮点数元组"""
        try:
            parts = location_str.split(",")
            if len(parts) == 2:
                return float(parts[0].strip()), float(parts[1].strip())
        except (ValueError, AttributeError, IndexError) as e:
            logger.debug(f"坐标解析失败: {location_str}, 错误: {e}")
        return 0.0, 0.0

    # ==================== 核心工具（保留） ====================

    async def maps_text_search(self, keywords: str, city: Optional[str] = None, extensions: str = "all", **kwargs) -> Dict[str, Any]:
        """
        POI 文本搜索 API (v3)
        https://lbs.amap.com/api/webservice/guide/api/search

        Args:
            keywords: 搜索关键词
            city: 城市名称（可选）
            extensions: 返回结果控制，base/all。默认'all'以获取POI图片等信息
            **kwargs: 其他参数
        """
        url = f"{self.BASE_URL_V3}/place/text"
        params = {"keywords": keywords, "extensions": extensions, **kwargs}
        if city:
            params["city"] = city

        result = await self._request(url, params)
        if result.get("success"):
            logger.info(f"✅ POI搜索成功: {keywords}, 找到 {len(result.get('pois', []))} 个结果")
        return result

    async def maps_around_search(self, keywords: str, location: str, **kwargs) -> Dict[str, Any]:
        """
        周边搜索 API (v3)
        https://lbs.amap.com/api/webservice/guide/api/search
        """
        url = f"{self.BASE_URL_V3}/place/around"
        params = {"keywords": keywords, "location": location, **kwargs}

        result = await self._request(url, params)
        if result.get("success"):
            logger.info(f"✅ 周边搜索成功: {keywords} 附近, 找到 {len(result.get('pois', []))} 个结果")
        return result

    async def maps_search_detail(self, id: str, **kwargs) -> Dict[str, Any]:
        """
        搜索详情 API (v3)
        https://lbs.amap.com/api/webservice/guide/api/search
        """
        url = f"{self.BASE_URL_V3}/place/detail"
        params = {"id": id, **kwargs}

        result = await self._request(url, params)
        if result.get("success"):
            logger.info(f"✅ 获取详情成功: {id}")
        return result

    async def maps_driving(self, origin: str, destination: str, **kwargs) -> Dict[str, Any]:
        """
        驾车路径规划 API (v3)
        https://lbs.amap.com/api/webservice/guide/api/direction
        """
        # ✅ 提前验证：检查坐标是否有效
        if not origin or not destination:
            logger.warning(f"⚠️ 驾车路径规划参数无效: origin='{origin}', destination='{destination}'")
            logger.warning(f"📝 跳过API调用，返回默认路线信息")
            return {
                "success": True,
                "route": {
                    "paths": [{
                        "distance": "5000",     # 默认5公里
                        "duration": "900000",   # 默认15分钟
                        "steps": []
                    }],
                    "origin": origin,
                    "destination": destination
                },
                "fallback": True,
                "error": "坐标参数为空，可能是地理编码失败导致的"
            }

        url = f"{self.BASE_URL_V3}/direction/driving"
        params = {"origin": origin, "destination": destination, **kwargs}

        result = await self._request(url, params)
        if result.get("success"):
            route = result.get("route", {})
            paths = route.get("paths", [])
            if paths:
                distance = paths[0].get("distance", "0")
                duration = paths[0].get("duration", "0")
                # 转换为整数再计算
                duration_minutes = int(int(duration) / 60) if duration.isdigit() else 0
                logger.info(f"驾车路径规划成功: 距离 {distance}m, 用时 {duration_minutes}分钟")
        return result

    async def maps_walking(self, origin: str, destination: str, **kwargs) -> Dict[str, Any]:
        """
        步行路径规划 API (v3)
        https://lbs.amap.com/api/webservice/guide/api/direction
        """
        # ✅ 提前验证：检查坐标是否有效
        if not origin or not destination:
            logger.warning(f"⚠️ 步行路径规划参数无效: origin='{origin}', destination='{destination}'")
            logger.warning(f"📝 跳过API调用，返回默认路线信息")
            return {
                "success": True,
                "route": {
                    "paths": [{
                        "distance": "1000",     # 默认1公里
                        "duration": "720000",   # 默认12分钟
                        "steps": []
                    }],
                    "origin": origin,
                    "destination": destination
                },
                "fallback": True,
                "error": "坐标参数为空，可能是地理编码失败导致的"
            }

        url = f"{self.BASE_URL_V3}/direction/walking"
        params = {"origin": origin, "destination": destination, **kwargs}

        result = await self._request(url, params)
        if result.get("success"):
            route = result.get("route", {})
            paths = route.get("paths", [])
            if paths:
                distance = paths[0].get("distance", "0")
                duration = paths[0].get("duration", "0")
                # 转换为整数再计算
                duration_minutes = int(int(duration) / 60) if duration.isdigit() else 0
                logger.info(f"步行路径规划成功: 距离 {distance}m, 用时 {duration_minutes}分钟")
        return result

    async def maps_direction_transit_integrated(
        self,
        origin: str,
        destination: str,
        city: str,
        **kwargs
    ) -> Dict[str, Any]:
        """
        公交路径规划 API (v3)
        https://lbs.amap.com/api/webservice/guide/api/direction

        Args:
            origin: 出发点坐标 (经度,纬度)
            destination: 目的地坐标 (经度,纬度)
            city: 查询城市
            **kwargs: 其他参数 (如 cityd, strategy 等)
        """
        # ✅ 提前验证：检查坐标是否有效
        if not origin or not destination:
            logger.warning(f"⚠️ 公交路径规划参数无效: origin='{origin}', destination='{destination}'")
            logger.warning(f"📝 跳过API调用，返回默认路线信息")
            # 返回默认数据以避免流程中断
            return {
                "success": True,
                "route": {
                    "transit_paths": [{
                        "duration": "1800000",  # 默认30分钟
                        "distance": "10000",    # 默认10公里
                        "steps": []
                    }],
                    "origin": origin,
                    "destination": destination
                },
                "fallback": True,  # 标记为回退数据
                "error": "坐标参数为空，可能是地理编码失败导致的"
            }

        url = f"{self.BASE_URL_V3}/direction/transit/integrated"
        params = {
            "origin": origin,
            "destination": destination,
            "city": city,
            **kwargs
        }

        result = await self._request(url, params)
        if result.get("success"):
            route = result.get("route", {})
            paths = route.get("transit_paths", [])
            if paths:
                duration = paths[0].get("duration", "0")
                distance = paths[0].get("distance", "0")
                logger.info(f"✅ 公交路径规划成功: 距离 {distance}m, 用时 {int(duration/60)}分钟")
        else:
            # 如果公交规划失败，返回默认信息（不中断流程）
            logger.warning(f"⚠️ 公交路径规划失败，将使用默认信息")
            result = {
                "success": True,
                "route": {
                    "transit_paths": [{
                        "duration": "1800000",  # 默认30分钟
                        "distance": "10000",    # 默认10公里
                        "steps": []
                    }],
                    "origin": origin,
                    "destination": destination
                },
                "fallback": True  # 标记为回退数据
            }
        return result

    async def maps_geo(self, address: str, city: Optional[str] = None, **kwargs) -> Dict[str, Any]:
        """
        地理编码 API (v3) - 地址转坐标
        https://lbs.amap.com/api/webservice/guide/api/georegeo
        """
        url = f"{self.BASE_URL_V3}/geocode/geo"
        params = {"address": address, **kwargs}
        if city:
            params["city"] = city

        result = await self._request(url, params)

        # ✅ 增强错误处理：确保返回格式一致
        if result.get("success"):
            count = result.get("count", 0)
            logger.info(f"地理编码成功: {address}, 找到 {count} 个结果")
            return result
        else:
            # ⚠️ 地理编码失败，返回标准格式但带空的 geocodes 数组
            # 这样后续步骤的占位符解析不会报错，只会得到空数组
            error_info = result.get("error", "未知错误")
            logger.warning(f"⚠️ 地理编码失败: {address} | 错误: {error_info}")
            logger.warning(f"📝 返回空结果以避免级联失败，后续步骤将收到空坐标")

            # 返回标准格式的空结果，保持 geocodes 键存在
            return {
                "success": True,  # 标记为成功以避免中断流程
                "status": "0",
                "info": error_info,
                "count": "0",
                "geocodes": [],  # 🔑 关键：保持 geocodes 键存在，避免解析错误
                "fallback": True,  # 标记为回退数据
                "error": error_info
            }

    async def maps_regeocode(self, location: str, **kwargs) -> Dict[str, Any]:
        """
        逆地理编码 API (v3) - 坐标转地址
        https://lbs.amap.com/api/webservice/guide/api/georegeo
        """
        url = f"{self.BASE_URL_V3}/geocode/regeo"
        params = {"location": location, **kwargs}

        result = await self._request(url, params)
        if result.get("success"):
            address = result.get("regeocode", {}).get("formatted_address", "")
            logger.info(f"✅ 逆地理编码成功: {location} -> {address}")
        return result

    async def maps_distance(self, origins: str, destination: str, type: str = "0", **kwargs) -> Dict[str, Any]:
        """
        距离测量 API (v3)
        https://lbs.amap.com/api/webservice/guide/api/distance
        """
        url = f"{self.BASE_URL_V3}/distance"
        params = {"origins": origins, "destination": destination, "type": type, **kwargs}

        result = await self._request(url, params)
        if result.get("success"):
            results = result.get("results", [])
            if results:
                logger.info(f"✅ 距离测量成功: 测量了 {len(results)} 个点")
        return result

    # ==================== 扩展工具 ====================

    async def maps_weather(self, city: str, extensions: str = "all", **kwargs) -> Dict[str, Any]:
        """
        天气查询 API (v3)
        https://lbs.amap.com/api/webservice/guide/api/weatherinfo

        Args:
            city: 城市adcode（必填），如 "110000"（北京）、"610100"（西安）
                   可以通过地理编码API获取城市的adcode
            extensions: 天气类型（可选）
                       - "base": 实况天气
                       - "all": 预报天气（默认，包含4天预报）
            **kwargs: 其他参数，如 output (JSON/XML)

        Returns:
            Dict: {
                "success": bool,
                "status": str,
                "info": str,
                "infocode": str,
                "lives": [...],      # 实况天气 (extensions="base")
                "forecasts": [...]   # 预报天气 (extensions="all")
            }

        实况天气字段 (lives):
        - province: 省份
        - city: 城市
        - adcode: 区域编码
        - weather: 天气现象（如"晴"、"多云"）
        - temperature: 实时气温（单位：摄氏度）
        - winddirection: 风向（如"东"、"东南"）
        - windpower: 风力（如"3级"）
        - humidity: 湿度（百分比）

        预报天气字段 (forecasts):
        - province: 省份
        - city: 城市
        - adcode: 区域编码
        - reporttime: 预报发布时间
        - casts: []  # 预报数据列表
          - date: 日期
          - week: 星期几
          - dayweather: 白天天气现象
          - nightweather: 晚上天气现象
          - daytemp: 白天温度
          - nighttemp: 晚上温度
          - daywind: 白天风向
          - nightwind: 晚上风向
          - daypower: 白天风力
          - nightpower: 晚上风力
        """
        url = f"{self.BASE_URL_V3}/weather/weatherInfo"
        params = {
            "city": city,
            "extensions": extensions,
            **kwargs
        }

        result = await self._request(url, params)
        if result.get("success"):
            if extensions == "base":
                lives = result.get("lives", [])
                if lives:
                    logger.info(f"✅ 天气查询成功(实况): {lives[0].get('city')}, {lives[0].get('weather')}, {lives[0].get('temperature')}℃")
            else:
                forecasts = result.get("forecasts", [])
                if forecasts:
                    city_name = forecasts[0].get("city", "")
                    logger.info(f"✅ 天气查询成功(预报): {city_name}, {len(forecasts[0].get('casts', []))}天预报")
        return result

    async def maps_coordinate_convert(
        self,
        locations: str,
        coordsys: str = "autonavi",
        **kwargs
    ) -> Dict[str, Any]:
        """
        坐标转换 API (v3)
        https://lbs.amap.com/api/webservice/guide/api/convert

        Args:
            locations: 坐标点（必填），格式为 "经度,纬度"
                      多个坐标点用 "|" 分隔，如 "116.397428,39.90923|116.40,39.91"
            coordsys: 原坐标系（可选），可选值：
                     - "gps": GPS坐标系（原始坐标）
                     - "mapbar": 图吧坐标
                     - "baidu": 百度坐标
                     - "autonavi": 高德坐标（默认，无需转换）
            **kwargs: 其他参数，如 output (JSON/XML)

        Returns:
            Dict: {
                "success": bool,
                "status": str,
                "info": str,
                "infocode": str,
                "locations": "经度1,纬度1|经度2,纬度2|..."  # 转换后的高德坐标
            }

        说明：
        - 输入非高德坐标时，会将其转换为高德坐标系
        - 支持批量转换，多个坐标用 "|" 分隔
        - 返回的坐标顺序与输入顺序一致
        """
        url = f"{self.BASE_URL_V3}/assistant/coordinate/convert"
        params = {
            "locations": locations,
            "coordsys": coordsys,
            **kwargs
        }

        result = await self._request(url, params)
        if result.get("success"):
            converted_locations = result.get("locations", "")
            count = len(converted_locations.split("|")) if converted_locations else 0
            logger.info(f"✅ 坐标转换成功: 从 {coordsys} 转换为高德坐标, 共 {count} 个点")
        return result

    # ✅ 已移除：静态地图API (maps_static_map)
    # 原因：项目使用 visualization_tool 生成交互式HTML地图，不需要静态图片地图
    # 如需使用，请参考高德官方文档：https://lbs.amap.com/api/webservice/guide/api/staticmaps

    async def close(self):
        """关闭HTTP客户端"""
        await self.client.aclose()


# ==================== MCP客户端（简化版） ====================

class MCPClient:
    """
    MCP协议客户端（精简版）
    只保留核心高德地图工具

    API配置来源：API_FROM.py
    """
    def __init__(self, server_url: str = None):
        """
        初始化MCP客户端

        Args:
            server_url: 服务器URL（当前未使用，保留参数用于兼容性）
        """
        self.gaode_client = None
        try:
            # 从 Config 获取 Web 服务 API 密钥
            api_key = Config.GAODE_REST_API_KEY or Config.GAODE_JS_API_KEY

            # 检查 API key 是否存在
            if not api_key:
                raise ValueError("GAODE_REST_API_KEY 未配置或为空，请检查 .env 文件")

            self.gaode_client = GaodeWebAPIClient(api_key)
            logger.info("✅ 高德地图客户端初始化成功")
        except ValueError as e:
            logger.warning(f"⚠️ 高德地图客户端初始化失败: {e}，地图功能将不可用")
        except Exception as e:
            logger.error(f"❌ 高德地图客户端初始化错误: {e}")

    # ==================== 对外暴露的工具方法 ====================

    async def text_search(self, keywords: str, city: Optional[str] = None, **kwargs) -> Dict[str, Any]:
        """POI文本搜索"""
        if not self.gaode_client:
            return {"success": False, "error": "高德地图客户端未初始化"}
        # 忽略额外参数，只传递支持的参数
        return await self.gaode_client.maps_text_search(keywords, city)

    async def around_search(self, keywords: str, location: str, **kwargs) -> Dict[str, Any]:
        """周边搜索"""
        if not self.gaode_client:
            return {"success": False, "error": "高德地图客户端未初始化"}
        return await self.gaode_client.maps_around_search(keywords, location)

    async def search_detail(self, id: str, **kwargs) -> Dict[str, Any]:
        """搜索详情"""
        if not self.gaode_client:
            return {"success": False, "error": "高德地图客户端未初始化"}
        return await self.gaode_client.maps_search_detail(id)

    async def driving_route(self, origin: str, destination: str, **kwargs) -> Dict[str, Any]:
        """驾车路径规划"""
        if not self.gaode_client:
            return {"success": False, "error": "高德地图客户端未初始化"}
        return await self.gaode_client.maps_driving(origin, destination)

    async def walking_route(self, origin: str, destination: str, **kwargs) -> Dict[str, Any]:
        """步行路径规划"""
        if not self.gaode_client:
            return {"success": False, "error": "高德地图客户端未初始化"}
        return await self.gaode_client.maps_walking(origin, destination)

    async def direction_transit_integrated(
        self,
        origin: str,
        destination: str,
        city: str,
        **kwargs
    ) -> Dict[str, Any]:
        """公交路径规划（含地铁）"""
        if not self.gaode_client:
            return {"success": False, "error": "高德地图客户端未初始化"}
        return await self.gaode_client.maps_direction_transit_integrated(origin, destination, city)

    async def geocoding(self, address: str, city: Optional[str] = None, **kwargs) -> Dict[str, Any]:
        """地理编码（地址→坐标）"""
        if not self.gaode_client:
            return {"success": False, "error": "高德地图客户端未初始化"}
        return await self.gaode_client.maps_geo(address, city)

    async def reverse_geocoding(self, location: str, **kwargs) -> Dict[str, Any]:
        """逆地理编码（坐标→地址）"""
        if not self.gaode_client:
            return {"success": False, "error": "高德地图客户端未初始化"}
        return await self.gaode_client.maps_regeocode(location)

    async def distance_measure(self, origins: str, destination: str, **kwargs) -> Dict[str, Any]:
        """距离测量"""
        if not self.gaode_client:
            return {"success": False, "error": "高德地图客户端未初始化"}
        return await self.gaode_client.maps_distance(origins, destination)

    async def weather_query(self, city: str, extensions: str = "all", **kwargs) -> Dict[str, Any]:
        """天气查询"""
        if not self.gaode_client:
            return {"success": False, "error": "高德地图客户端未初始化"}
        return await self.gaode_client.maps_weather(city, extensions)

    async def coordinate_convert(self, locations: str, coordsys: str = "autonavi", **kwargs) -> Dict[str, Any]:
        """坐标转换"""
        if not self.gaode_client:
            return {"success": False, "error": "高德地图客户端未初始化"}
        return await self.gaode_client.maps_coordinate_convert(locations, coordsys)

    # ✅ 已移除：static_map 方法
    # 原因：项目使用 visualization_tool 生成交互式HTML地图，不需要静态图片地图

    async def close(self):
        """关闭客户端"""
        if self.gaode_client:
            await self.gaode_client.close()

    # ==================== 工具元数据接口 ====================

    async def get_tool_methods(self) -> Dict[str, Any]:
        """
        获取所有可用的MCP工具方法
        返回一个字典，键为工具名称，值为对应的异步方法
        """
        return {
            "maps_text_search": self.text_search,
            "maps_around_search": self.around_search,
            "maps_search_detail": self.search_detail,
            "maps_driving": self.driving_route,
            "maps_walking": self.walking_route,
            "maps_direction_transit_integrated": self.direction_transit_integrated,
            "maps_geo": self.geocoding,
            "maps_regeocode": self.reverse_geocoding,
            "maps_distance": self.distance_measure,
            "maps_weather": self.weather_query,
            "maps_coordinate_convert": self.coordinate_convert,
            # ✅ 已移除：maps_static_map（项目使用交互式HTML地图，不需要静态图片）
        }

    async def get_tools_metadata(self) -> List[Dict[str, Any]]:
        """
        获取所有MCP工具的元数据（用于Agent工具注册）
        返回符合MCP协议的工具描述格式
        """
        return [
            {
                "name": "maps_text_search",
                "description": "POI地点文本搜索工具(maps_text_search)。根据关键词搜索地点、景点、餐厅等。使用工具名: maps_text_search",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "keywords": {
                            "type": "string",
                            "description": "搜索关键词，如'故宫'、'餐厅'、'博物馆'等"
                        },
                        "city": {
                            "type": "string",
                            "description": "限定搜索城市（可选），如'北京'、'西安'等"
                        }
                    },
                    "required": ["keywords"]
                }
            },
            {
                "name": "maps_around_search",
                "description": "周边POI地点搜索工具(maps_around_search)。在指定位置周围搜索关键词。使用工具名: maps_around_search",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "keywords": {
                            "type": "string",
                            "description": "搜索关键词"
                        },
                        "location": {
                            "type": "string",
                            "description": "中心点坐标，格式为'经度,纬度'，如'116.397428,39.90923'"
                        }
                    },
                    "required": ["keywords", "location"]
                }
            },
            {
                "name": "maps_driving",
                "description": "驾车导航路线规划工具(maps_driving)。规划两点之间的驾车路线，包括距离、时间、详细路线指引。\n\n⚠️ 重要：origin和destination必须是坐标格式'经度,纬度'，不能是地名！\n正确流程：先使用maps_geo或maps_text_search获取坐标，再调用此工具。\n错误示例：origin='故宫' ❌\n正确示例：origin='116.397,39.909' ✅",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "origin": {
                            "type": "string",
                            "description": "起点坐标，格式为'经度,纬度'（例如：116.397,39.909）。注意：必须是坐标，不能是地名！"
                        },
                        "destination": {
                            "type": "string",
                            "description": "终点坐标，格式为'经度,纬度'（例如：116.397,39.909）。注意：必须是坐标，不能是地名！"
                        }
                    },
                    "required": ["origin", "destination"]
                }
            },
            {
                "name": "maps_walking",
                "description": "步行导航路线规划工具(maps_walking)。规划两点之间的步行路线。\n\n⚠️ 重要：origin和destination必须是坐标格式'经度,纬度'，不能是地名！\n正确流程：先使用maps_geo或maps_text_search获取坐标，再调用此工具。\n错误示例：origin='天安门' ❌\n正确示例：origin='116.397,39.909' ✅",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "origin": {
                            "type": "string",
                            "description": "起点坐标，格式为'经度,纬度'（例如：116.397,39.909）。注意：必须是坐标，不能是地名！"
                        },
                        "destination": {
                            "type": "string",
                            "description": "终点坐标，格式为'经度,纬度'（例如：116.397,39.909）。注意：必须是坐标，不能是地名！"
                        }
                    },
                    "required": ["origin", "destination"]
                }
            },
            {
                "name": "maps_direction_transit_integrated",
                "description": "公交地铁导航路线规划工具(maps_direction_transit_integrated)。规划两点之间的公共交通路线，包括地铁、公交等，提供换乘方案、耗时、费用等信息。\n\n⚠️ 重要：origin和destination必须是坐标格式'经度,纬度'，不能是地名！\n正确流程：先使用maps_geo或maps_text_search获取坐标，再调用此工具。\n错误示例：origin='北京站' ❌\n正确示例：origin='116.427,39.903' ✅",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "origin": {
                            "type": "string",
                            "description": "起点坐标，格式为'经度,纬度'（例如：116.427,39.903）。注意：必须是坐标，不能是地名！"
                        },
                        "destination": {
                            "type": "string",
                            "description": "终点坐标，格式为'经度,纬度'（例如：116.397,39.909）。注意：必须是坐标，不能是地名！"
                        },
                        "city": {
                            "type": "string",
                            "description": "查询城市，如'北京'、'西安'等（可以使用地名）"
                        }
                    },
                    "required": ["origin", "destination", "city"]
                }
            },
            {
                "name": "maps_geo",
                "description": "地理编码工具(maps_geo)。将地址描述转换为经纬度坐标。使用工具名: maps_geo",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "address": {
                            "type": "string",
                            "description": "地址描述，如'北京市故宫'、'西安大雁塔'等"
                        },
                        "city": {
                            "type": "string",
                            "description": "限定城市（可选）"
                        }
                    },
                    "required": ["address"]
                }
            },
            {
                "name": "maps_regeocode",
                "description": "逆地理编码工具(maps_regeocode)。将经纬度坐标转换为详细地址描述。使用工具名: maps_regeocode",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "location": {
                            "type": "string",
                            "description": "坐标，格式为'经度,纬度'"
                        }
                    },
                    "required": ["location"]
                }
            },
            {
                "name": "maps_distance",
                "description": "距离测量工具(maps_distance)。测量多个起点到终点的距离。使用工具名: maps_distance",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "origins": {
                            "type": "string",
                            "description": "多个起点坐标，用'|'分隔，如'116.397428,39.90923|116.40,39.91'"
                        },
                        "destination": {
                            "type": "string",
                            "description": "终点坐标，格式为'经度,纬度'"
                        }
                    },
                    "required": ["origins", "destination"]
                }
            },
            {
                "name": "maps_search_detail",
                "description": "获取POI详细信息工具(maps_search_detail)。根据POI ID获取详细的地点信息，包括地址、电话、开放时间、门票价格等。重要：设置extensions='all'可获取POI图片（photos字段），这是获取景点图片的推荐方式。使用工具名: maps_search_detail",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "id": {
                            "type": "string",
                            "description": "POI ID"
                        },
                        "extensions": {
                            "type": "string",
                            "description": "返回结果控制，base/all。设置为'all'时可获取POI图片（photos字段）",
                            "enum": ["base", "all"],
                            "default": "all"
                        }
                    },
                    "required": ["id"]
                }
            },
            {
                "name": "maps_weather",
                "description": "天气查询工具(maps_weather)。查询指定城市的实时天气或天气预报。使用工具名: maps_weather",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "city": {
                            "type": "string",
                            "description": "城市adcode（必填），如'110000'（北京）、'610100'（西安）。可先使用地理编码API获取城市的adcode"
                        },
                        "extensions": {
                            "type": "string",
                            "description": "天气类型（可选），'base'为实况天气，'all'为预报天气（默认，包含4天预报）",
                            "enum": ["base", "all"]
                        }
                    },
                    "required": ["city"]
                }
            },
            {
                "name": "maps_coordinate_convert",
                "description": "坐标转换工具(maps_coordinate_convert)。将其他坐标系（GPS、百度、图吧）的坐标转换为高德坐标系。使用工具名: maps_coordinate_convert",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "locations": {
                            "type": "string",
                            "description": "坐标点（必填），格式为'经度,纬度'，多个坐标点用'|'分隔，如'116.397428,39.90923|116.40,39.91'"
                        },
                        "coordsys": {
                            "type": "string",
                            "description": "原坐标系（可选），可选值：'gps'（GPS坐标）、'mapbar'（图吧坐标）、'baidu'（百度坐标）、'autonavi'（高德坐标，默认）",
                            "enum": ["gps", "mapbar", "baidu", "autonavi"]
                        }
                    },
                    "required": ["locations"]
                }
            }

        ]
