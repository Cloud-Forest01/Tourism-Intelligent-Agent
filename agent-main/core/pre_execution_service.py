"""
预执行服务 - 实现 <3秒 首token延迟
====================================
核心思路：在用户填写表单时，后台预先执行工具调用
用户提交时直接使用预加载数据，立即开始流式生成

工作流程：
-----------
1. 用户打开表单页面
2. 用户输入目的地/日期 → 触发预执行
3. 后台并行调用：天气API、POI搜索
4. 用户提交表单
5. 立即使用预加载数据生成攻略（跳过工具调用）
"""
import asyncio
import logging
from typing import Dict, Any, Optional
from datetime import datetime
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


class PreExecuteRequest(BaseModel):
    """预执行请求"""
    destination: str = Field(..., description="目的地")
    start_date: str = Field(..., description="开始日期 YYYY-MM-DD")
    end_date: str = Field(..., description="结束日期 YYYY-MM-DD")
    preferences: list = Field(default_factory=list, description="旅游偏好")
    travelers: int = Field(1, description="旅行人数")


class PreExecutedData(BaseModel):
    """预执行结果数据"""
    request_hash: str = Field(..., description="请求唯一标识")
    destination: str
    start_date: str
    end_date: str
    weather_data: Optional[Dict] = None
    poi_data: Optional[Dict] = None
    search_results: Optional[Dict] = None
    created_at: str = Field(default_factory=lambda: datetime.now().isoformat())
    expires_at: str  # 过期时间

    class Config:
        json_schema_extra = {
            "example": {
                "request_hash": "beijing_2024-07-01_2024-07-03",
                "destination": "北京",
                "weather_data": {"forecasts": [...]},
                "poi_data": {"pois": [...]}
            }
        }


class PreExecutionService:
    """预执行服务 - 单例模式"""

    _instance = None
    _lock = asyncio.Lock()

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if self._initialized:
            return

        self._initialized = True
        self._cache: Dict[str, PreExecutedData] = {}
        self._gaode_client = None
        self._tavily_client = None
        self._execution_locks: Dict[str, asyncio.Lock] = {}

        logger.info("✅ 预执行服务初始化完成")

    async def initialize_clients(self, gaode_client=None, tavily_client=None):
        """初始化客户端连接"""
        self._gaode_client = gaode_client
        self._tavily_client = tavily_client
        logger.info("✅ 预执行服务客户端已初始化")

    def _generate_request_hash(self, request: PreExecuteRequest) -> str:
        """生成请求唯一标识"""
        # 使用目的地+日期生成唯一hash
        # 相同的目的地和日期会返回相同的hash
        key = f"{request.destination}_{request.start_date}_{request.end_date}"
        return key.lower().replace(" ", "_")

    def _is_cache_valid(self, data: PreExecutedData) -> bool:
        """检查缓存是否有效"""
        try:
            expires_at = datetime.fromisoformat(data.expires_at)
            now = datetime.now()
            return now < expires_at
        except:
            return False

    async def execute_preload(
        self,
        request: PreExecuteRequest,
        force_refresh: bool = False
    ) -> PreExecutedData:
        """
        执行预加载（核心方法）

        Args:
            request: 预执行请求
            force_refresh: 是否强制刷新缓存

        Returns:
            PreExecutedData: 预执行结果
        """
        request_hash = self._generate_request_hash(request)

        # 检查缓存
        if not force_refresh and request_hash in self._cache:
            cached_data = self._cache[request_hash]
            if self._is_cache_valid(cached_data):
                logger.info(f"✅ 使用缓存数据: {request_hash}")
                return cached_data
            else:
                logger.info(f"⚠️ 缓存已过期: {request_hash}")
                del self._cache[request_hash]

        # 获取或创建该请求的锁（防止并发重复执行）
        if request_hash not in self._execution_locks:
            self._execution_locks[request_hash] = asyncio.Lock()

        async with self._execution_locks[request_hash]:
            # 双重检查：可能在等待锁的过程中，其他任务已经完成了预加载
            if not force_refresh and request_hash in self._cache:
                cached_data = self._cache[request_hash]
                if self._is_cache_valid(cached_data):
                    return cached_data

            logger.info(f"🚀 开始预执行: {request_hash}")
            start_time = datetime.now()

            try:
                # 并行执行所有预加载任务
                weather_task = self._preload_weather(request.destination)
                poi_task = self._preload_pois(request.destination)
                search_task = self._preload_search_results(request)

                # 等待所有任务完成
                weather_data, poi_data, search_results = await asyncio.gather(
                    weather_task,
                    poi_task,
                    search_task,
                    return_exceptions=True
                )

                # 处理异常结果
                if isinstance(weather_data, Exception):
                    logger.warning(f"⚠️ 天气预加载失败: {weather_data}")
                    weather_data = None

                if isinstance(poi_data, Exception):
                    logger.warning(f"⚠️ POI预加载失败: {poi_data}")
                    poi_data = None

                if isinstance(search_results, Exception):
                    logger.warning(f"⚠️ 搜索结果预加载失败: {search_results}")
                    search_results = None

                # 创建预执行结果
                from datetime import timedelta

                pre_executed = PreExecutedData(
                    request_hash=request_hash,
                    destination=request.destination,
                    start_date=request.start_date,
                    end_date=request.end_date,
                    weather_data=weather_data,
                    poi_data=poi_data,
                    search_results=search_results,
                    # 缓存有效期：30分钟
                    expires_at=(datetime.now() + timedelta(minutes=30)).isoformat()
                )

                # 保存到缓存
                self._cache[request_hash] = pre_executed

                elapsed = (datetime.now() - start_time).total_seconds()
                logger.info(f"✅ 预执行完成: {request_hash} (耗时: {elapsed:.2f}秒)")

                return pre_executed

            except Exception as e:
                logger.error(f"❌ 预执行失败: {e}", exc_info=True)
                # 返回空数据，让系统降级处理
                return PreExecutedData(
                    request_hash=request_hash,
                    destination=request.destination,
                    start_date=request.start_date,
                    end_date=request.end_date,
                    expires_at=(datetime.now()).isoformat()
                )

    async def _preload_weather(self, city: str) -> Optional[Dict]:
        """预加载天气数据"""
        try:
            if not self._gaode_client:
                return None

            logger.info(f"🌤️ 预加载天气: {city}")
            result = await self._gaode_client.weather(city=city)

            if result.get("success"):
                logger.info(f"✅ 天气预加载成功: {city}")
                return result
            else:
                logger.warning(f"⚠️ 天气预加载失败: {result.get('error')}")
                return None

        except Exception as e:
            logger.error(f"❌ 天气预加载异常: {e}")
            return None

    async def _preload_pois(self, city: str) -> Optional[Dict]:
        """预加载POI数据"""
        try:
            if not self._gaode_client:
                return None

            logger.info(f"🏛️ 预加载POI: {city}")

            # 搜索热门景点
            keywords = ["景点", "名胜古迹", "博物馆", "公园"]
            all_pois = []

            for keyword in keywords:
                result = await self._gaode_client.text_search(
                    keywords=keyword,
                    city=city,
                    city_limit=True
                )

                if result.get("success") and "pois" in result:
                    all_pois.extend(result["pois"][:5])  # 每个关键词取5个

            if all_pois:
                logger.info(f"✅ POI预加载成功: {city} ({len(all_pois)}个)")
                return {"pois": all_pois}
            else:
                logger.warning(f"⚠️ POI预加载失败: 未找到结果")
                return None

        except Exception as e:
            logger.error(f"❌ POI预加载异常: {e}")
            return None

    async def _preload_search_results(self, request: PreExecuteRequest) -> Optional[Dict]:
        """预加载搜索结果（美食/住宿）"""
        try:
            if not self._tavily_client:
                return None

            logger.info(f"🔍 预加载搜索结果: {request.destination}")

            # 构建搜索查询
            city = request.destination
            queries = [
                f"{city}平价美食推荐 学生穷游",
                f"{city}青年旅舍推荐 经济型住宿"
            ]

            results = {}
            for query in queries:
                result = await self._tavily_client.search(query, max_results=3)
                results[query] = result

            logger.info(f"✅ 搜索结果预加载成功: {city}")
            return results

        except Exception as e:
            logger.error(f"❌ 搜索结果预加载异常: {e}")
            return None

    def get_cached_data(self, request: PreExecuteRequest) -> Optional[PreExecutedData]:
        """获取缓存数据（同步方法，用于快速查询）"""
        request_hash = self._generate_request_hash(request)

        if request_hash in self._cache:
            cached_data = self._cache[request_hash]
            if self._is_cache_valid(cached_data):
                return cached_data

        return None

    async def clear_cache(self, pattern: Optional[str] = None):
        """清除缓存"""
        if pattern:
            # 按模式清除
            keys_to_delete = [
                k for k in self._cache.keys()
                if pattern in k
            ]
            for key in keys_to_delete:
                del self._cache[key]
            logger.info(f"🗑️ 已清除匹配 '{pattern}' 的缓存 (共{len(keys_to_delete)}项)")
        else:
            # 清除全部
            count = len(self._cache)
            self._cache.clear()
            logger.info(f"🗑️ 已清除全部缓存 (共{count}项)")

    def get_cache_stats(self) -> Dict:
        """获取缓存统计信息"""
        valid_count = sum(
            1 for data in self._cache.values()
            if self._is_cache_valid(data)
        )
        expired_count = len(self._cache) - valid_count

        return {
            "total_entries": len(self._cache),
            "valid_entries": valid_count,
            "expired_entries": expired_count,
            "cache_keys": list(self._cache.keys())
        }


# ==================== 全局单例 ====================
_pre_execution_service: Optional[PreExecutionService] = None


def get_pre_execution_service() -> PreExecutionService:
    """获取预执行服务单例"""
    global _pre_execution_service
    if _pre_execution_service is None:
        _pre_execution_service = PreExecutionService()
    return _pre_execution_service
