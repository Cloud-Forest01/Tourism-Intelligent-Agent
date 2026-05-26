"""
高德地图API封装 - 智能规划专用
====================================
提供批量地理编码、路径规划、POI搜索等功能
为新的行程规划API提供底层支持
"""
import asyncio
import logging
from typing import List, Dict, Any, Optional, Tuple
from datetime import datetime
import httpx

# 导入配置
import sys
from pathlib import Path
project_root = Path(__file__).resolve().parent.parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

from config import Config
from data_models_design import POI, RouteSegment, DayRoute, Itinerary, GeocodedLocation, MapMarker, MapPolyline

logger = logging.getLogger(__name__)


class GaodeTripAPI:
    """
    高德地图API封装类 - 专为行程规划设计
    """

    def __init__(self, api_key: Optional[str] = None):
        """
        初始化API客户端

        Args:
            api_key: 高德 Web 服务 API 密钥，默认从 Config 获取
        """
        self.api_key = api_key or Config.GAODE_REST_API_KEY or Config.GAODE_JS_API_KEY
        self.base_url_v3 = Config.GAODE_BASE_URL_V3
        self.client = httpx.AsyncClient(timeout=30.0)

    async def close(self):
        """关闭HTTP客户端"""
        await self.client.aclose()

    # ==================== 1. 批量地理编码 ====================

    async def batch_geocode(
        self,
        addresses: List[str],
        city: Optional[str] = None
    ) -> List[GeocodedLocation]:
        """
        批量地理编码 - 将地址/地点名称转换为坐标

        Args:
            addresses: 地址/地点名称列表
            city: 城市名称（提升准确度）

        Returns:
            List[GeocodedLocation]: 地理编码结果列表
        """
        results = []

        # 并发请求所有地址（使用信号量限制并发数）
        semaphore = asyncio.Semaphore(5)  # 最多5个并发请求

        async def geocode_one(address: str) -> GeocodedLocation:
            async with semaphore:
                try:
                    url = f"{self.base_url_v3}/geocode/geo"
                    params = {
                        "key": self.api_key,
                        "address": address,
                        "city": city or ""
                    }

                    response = await self.client.get(url, params=params)
                    data = response.json()

                    if data.get("status") == "1" and data.get("count") != "0":
                        geocodes = data.get("geocodes", [])
                        if geocodes:
                            geo = geocodes[0]
                            location = geo.get("location", "")
                            lng, lat = self._parse_location(location)

                            return GeocodedLocation(
                                original_address=address,
                                name=geo.get("formatted_address", address),
                                lng=lng,
                                lat=lat,
                                formatted_address=geo.get("formatted_address"),
                                level=geo.get("level"),
                                success=True
                            )

                    # 失败：尝试POI搜索
                    logger.warning(f"地理编码失败，尝试POI搜索: {address}")
                    return await self._try_poi_search(address, city)

                except Exception as e:
                    logger.error(f"地理编码异常: {address}, 错误: {e}")
                    return GeocodedLocation(
                        original_address=address,
                        name=address,
                        lng=0,
                        lat=0,
                        success=False,
                        error=str(e)
                    )

        # 并发执行所有地理编码
        tasks = [geocode_one(addr) for addr in addresses]
        results = await asyncio.gather(*tasks)

        success_count = sum(1 for r in results if r.success)
        logger.info(f"✅ 批量地理编码完成: {success_count}/{len(addresses)} 成功")

        return results

    async def _try_poi_search(self, keyword: str, city: Optional[str]) -> GeocodedLocation:
        """
        当地理编码失败时，尝试POI搜索

        Args:
            keyword: 搜索关键词
            city: 城市

        Returns:
            GeocodedLocation: 搜索结果
        """
        try:
            url = f"{self.base_url_v3}/place/text"
            params = {
                "key": self.api_key,
                "keywords": keyword,
                "city": city or "",
                "citylimit": "true"  # 限制在指定城市
            }

            response = await self.client.get(url, params=params)
            data = response.json()

            if data.get("status") == "1":
                pois = data.get("pois", [])
                if pois:
                    poi = pois[0]
                    location = poi.get("location", "")
                    lng, lat = self._parse_location(location)

                    return GeocodedLocation(
                        original_address=keyword,
                        name=poi.get("name"),
                        lng=lng,
                        lat=lat,
                        formatted_address=poi.get("address") or poi.get("name"),
                        level="POI",
                        success=True
                    )

        except Exception as e:
            logger.debug(f"POI搜索失败: {keyword}, 错误: {e}")

        return GeocodedLocation(
            original_address=keyword,
            name=keyword,
            lng=0,
            lat=0,
            success=False,
            error="未找到该地点"
        )

    def _parse_location(self, location_str: str) -> Tuple[float, float]:
        """解析经纬度字符串"""
        try:
            parts = location_str.split(",")
            if len(parts) == 2:
                return float(parts[0]), float(parts[1])
        except (ValueError, AttributeError, IndexError):
            pass
        return 0.0, 0.0

    # ==================== 2. 路径规划 ====================

    async def plan_route(
        self,
        pois: List[POI],
        transport_mode: str = "walking"
    ) -> List[RouteSegment]:
        """
        路径规划 - 计算POI之间的路径

        Args:
            pois: POI列表（按游览顺序）
            transport_mode: 交通方式 (driving/walking/transit)

        Returns:
            List[RouteSegment]: 路径段列表
        """
        segments = []

        for i in range(len(pois) - 1):
            from_poi = pois[i]
            to_poi = pois[i + 1]

            origin = f"{from_poi.lng},{from_poi.lat}"
            destination = f"{to_poi.lng},{to_poi.lat}"

            try:
                if transport_mode == "driving":
                    result = await self._driving_route(origin, destination)
                elif transport_mode == "transit":
                    result = await self._transit_route(origin, destination, pois[0].name)
                else:  # walking (default)
                    result = await self._walking_route(origin, destination)

                segments.append(RouteSegment(
                    from_poi_id=from_poi.id,
                    to_poi_id=to_poi.id,
                    distance=result.get("distance", 0),
                    duration=result.get("duration", 0),
                    path_coords=result.get("path_coords", []),
                    transport_mode=transport_mode
                ))

            except Exception as e:
                logger.error(f"路径规划失败: {from_poi.name} -> {to_poi.name}, 错误: {e}")
                # 添加默认路径段
                segments.append(RouteSegment(
                    from_poi_id=from_poi.id,
                    to_poi_id=to_poi.id,
                    distance=0,
                    duration=0,
                    transport_mode=transport_mode
                ))

        logger.info(f"✅ 路径规划完成: {len(segments)} 个路段")
        return segments

    async def _walking_route(self, origin: str, destination: str) -> Dict[str, Any]:
        """步行路径规划"""
        url = f"{self.base_url_v3}/direction/walking"
        params = {"key": self.api_key, "origin": origin, "destination": destination}

        response = await self.client.get(url, params=params)
        data = response.json()

        if data.get("status") == "1":
            route = data.get("route", {})
            paths = route.get("paths", [])
            if paths:
                path = paths[0]
                # 提取路径坐标
                steps = path.get("steps", [])
                path_coords = self._extract_path_coords(steps)

                return {
                    "distance": int(path.get("distance", 0)),
                    "duration": int(path.get("duration", 0)) // 60,  # 转换为分钟
                    "path_coords": path_coords
                }

        return {"distance": 0, "duration": 0, "path_coords": []}

    async def _driving_route(self, origin: str, destination: str) -> Dict[str, Any]:
        """驾车路径规划"""
        url = f"{self.base_url_v3}/direction/driving"
        params = {"key": self.api_key, "origin": origin, "destination": destination}

        response = await self.client.get(url, params=params)
        data = response.json()

        if data.get("status") == "1":
            route = data.get("route", {})
            paths = route.get("paths", [])
            if paths:
                path = paths[0]
                steps = path.get("steps", [])
                path_coords = self._extract_path_coords(steps)

                return {
                    "distance": int(path.get("distance", 0)),
                    "duration": int(path.get("duration", 0)) // 60,
                    "path_coords": path_coords
                }

        return {"distance": 0, "duration": 0, "path_coords": []}

    async def _transit_route(self, origin: str, destination: str, city: str) -> Dict[str, Any]:
        """公交路径规划"""
        url = f"{self.base_url_v3}/direction/transit/integrated"
        params = {
            "key": self.api_key,
            "origin": origin,
            "destination": destination,
            "city": city
        }

        response = await self.client.get(url, params=params)
        data = response.json()

        if data.get("status") == "1":
            route = data.get("route", {})
            paths = route.get("transit_paths", [])
            if paths:
                path = paths[0]
                return {
                    "distance": int(path.get("distance", 0)),
                    "duration": int(path.get("duration", 0)) // 60,
                    "path_coords": []  # 公交路径通常不返回详细坐标
                }

        return {"distance": 0, "duration": 0, "path_coords": []}

    def _extract_path_coords(self, steps: List[Dict]) -> List[List[float]]:
        """从路径步骤中提取坐标点"""
        coords = []
        for step in steps:
            polyline = step.get("polyline", "")
            if polyline:
                points = polyline.split(";")
                for point in points:
                    lng, lat = self._parse_location(point)
                    if lng != 0 and lat != 0:
                        coords.append([lng, lat])
        return coords

    # ==================== 3. POI搜索和详情 ====================

    async def search_pois(
        self,
        keyword: str,
        city: Optional[str] = None,
        limit: int = 10
    ) -> List[Dict[str, Any]]:
        """
        POI文本搜索

        Args:
            keyword: 搜索关键词
            city: 城市
            limit: 返回数量限制

        Returns:
            List[Dict]: POI信息列表
        """
        try:
            url = f"{self.base_url_v3}/place/text"
            params = {
                "key": self.api_key,
                "keywords": keyword,
                "city": city or "",
                "offset": limit
            }

            response = await self.client.get(url, params=params)
            data = response.json()

            if data.get("status") == "1":
                return data.get("pois", [])

        except Exception as e:
            logger.error(f"POI搜索失败: {keyword}, 错误: {e}")

        return []

    async def get_poi_detail(self, poi_id: str) -> Optional[Dict[str, Any]]:
        """
        获取POI详情

        Args:
            poi_id: POI ID

        Returns:
            POI详情字典
        """
        try:
            url = f"{self.base_url_v3}/place/detail"
            params = {"key": self.api_key, "id": poi_id}

            response = await self.client.get(url, params=params)
            data = response.json()

            if data.get("status") == "1":
                return data.get("pois", [{}])[0]

        except Exception as e:
            logger.error(f"获取POI详情失败: {poi_id}, 错误: {e}")

        return None

    # ==================== 4. 辅助方法 ====================

    async def get_city_center(self, city: str) -> Tuple[float, float]:
        """
        获取城市中心坐标

        Args:
            city: 城市名称

        Returns:
            (经度, 纬度)
        """
        result = await self.batch_geocode([city])
        if result and result[0].success:
            return result[0].lng, result[0].lat

        # 默认返回北京坐标
        return 116.397428, 39.90923

    async def calculate_route_distance(
        self,
        pois: List[POI]
    ) -> Tuple[int, int]:
        """
        计算路线总距离和时长

        Args:
            pois: POI列表

        Returns:
            (总距离(米), 总时长(分钟))
        """
        total_distance = 0
        total_duration = 0

        segments = await self.plan_route(pois)
        for seg in segments:
            total_distance += seg.distance
            total_duration += seg.duration

        return total_distance, total_duration


# ==================== 单例模式 ====================

_gaode_api_instance: Optional[GaodeTripAPI] = None


def get_gaode_api() -> GaodeTripAPI:
    """获取高德API单例"""
    global _gaode_api_instance
    if _gaode_api_instance is None:
        _gaode_api_instance = GaodeTripAPI()
    return _gaode_api_instance


# ==================== 使用示例 ====================

"""
# 批量地理编码示例
api = GaodeTripAPI()
locations = await api.batch_geocode(
    addresses=["钟楼", "回民街", "大雁塔"],
    city="西安"
)

# 路径规划示例
pois = [
    POI(id="1", name="钟楼", lng=108.940174, lat=34.261938, ...),
    POI(id="2", name="回民街", lng=108.938967, lat=34.263049, ...),
]
segments = await api.plan_route(pois, transport_mode="walking")

# 获取城市中心
lng, lat = await api.get_city_center("西安")
"""
