# chat_agent_qwen/utils/image_service.py
"""
稳定的图片服务模块
整合多个图片源，提供可靠的景区图片获取

API配置来源：API_FROM.py
"""
import os
import sys
from pathlib import Path
import json
import hashlib
import logging
from typing import List, Dict, Any, Optional
import httpx

# 导入API配置
# 添加项目根目录到系统路径
project_root = Path(__file__).resolve().parent.parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

from config import Config

logger = logging.getLogger(__name__)


class ImageService:
    """
    稳定的图片服务类
    整合多个图片源，提供可靠的景区图片获取

    API配置来源：API_FROM.py
    """

    def __init__(self, cache_dir: Optional[str] = None):
        """初始化图片服务"""
        self.cache_dir = Path(cache_dir or "temp_visualizations/image_cache")
        self.cache_dir.mkdir(parents=True, exist_ok=True)

        # 🔧 备选功能：图片源配置
        # 注意：Unsplash 和 Pexels 需要 API Key 才能使用
        # LoremFlickr 是稳定的免费图库（无需 API Key），推荐使用
        self.image_sources = [
            "unsplash",      # 🔧 Unsplash（高质量免费图库，需要 UNSPLASH_ACCESS_KEY）
            "pexels",        # 🔧 Pexels（免费图库，需要 API Key）
            "loremflickr",   # ✅ LoremFlickr（随机图片，无需 API Key，推荐）
            "via.placeholder" # 占位图（最后回退选项）
        ]

        # 🔧 从 API_FROM 获取Unsplash API配置（可选，需要API Key）
        # 如需使用 Unsplash，请在 .env 文件中配置 UNSPLASH_ACCESS_KEY
        self.unsplash_access_key = Config.UNSPLASH_ACCESS_KEY
        self.unsplash_url = Config.UNSPLASH_BASE_URL

        # HTTP客户端
        self.client = httpx.AsyncClient(timeout=10.0)

    async def get_scenery_images(
        self,
        query: str,
        count: int = 3,
        fallback_keywords: Optional[List[str]] = None
    ) -> List[str]:
        """
        获取景区图片（带多源回退）

        Args:
            query: 搜索关键词（如"故宫"、"长城"）
            count: 需要的图片数量
            fallback_keywords: 备用关键词列表

        Returns:
            图片URL列表
        """
        # 尝试从缓存读取
        cache_key = self._get_cache_key(query, count)
        cached = self._load_from_cache(cache_key)
        if cached:
            logger.info(f"✅ 从缓存加载图片: {query}")
            return cached

        # 尝试多个图片源
        image_urls = []

        # 1. 尝试 Unsplash（如果有API Key）
        if self.unsplash_access_key:
            try:
                urls = await self._fetch_from_unsplash(query, count)
                if urls:
                    image_urls.extend(urls)
                    logger.info(f"✅ Unsplash获取到 {len(urls)} 张图片")
            except Exception as e:
                logger.warning(f"⚠️ Unsplash获取失败: {e}")

        # 2. 如果图片不够，使用 Pexels
        if len(image_urls) < count:
            needed = count - len(image_urls)
            try:
                urls = await self._fetch_from_pexels(query, needed)
                if urls:
                    image_urls.extend(urls)
                    logger.info(f"✅ Pexels获取到 {len(urls)} 张图片")
            except Exception as e:
                logger.warning(f"⚠️ Pexels获取失败: {e}")

        # 3. 如果还不够，使用 LoremFlickr（稳定的随机图片）
        if len(image_urls) < count:
            needed = count - len(image_urls)
            try:
                urls = await self._fetch_from_loremflickr(query, needed)
                if urls:
                    image_urls.extend(urls)
                    logger.info(f"✅ LoremFlickr获取到 {len(urls)} 张图片")
            except Exception as e:
                logger.warning(f"⚠️ LoremFlickr获取失败: {e}")

        # 4. 最后的回退：使用占位图
        if len(image_urls) < count:
            needed = count - len(image_urls)
            urls = self._generate_placeholder_urls(query, needed)
            image_urls.extend(urls)
            logger.info(f"✅ 生成 {len(urls)} 张占位图")

        # 保存到缓存
        if image_urls:
            self._save_to_cache(cache_key, image_urls)

        return image_urls[:count]

    async def _fetch_from_unsplash(self, query: str, count: int) -> List[str]:
        """从 Unsplash API 获取图片"""
        try:
            params = {
                "query": f"{query} landmark scenery travel",
                "per_page": min(count, 10),
                "orientation": "landscape"
            }

            headers = {"Authorization": f"Client-ID {self.unsplash_access_key}"}

            response = await self.client.get(
                self.unsplash_url,
                params=params,
                headers=headers,
                timeout=15.0
            )

            if response.status_code == 200:
                data = response.json()
                results = data.get("results", [])

                urls = []
                for photo in results[:count]:
                    # 使用中等尺寸的图片（balance between quality and speed）
                    url = photo.get("urls", {}).get("regular", "")
                    if url:
                        urls.append(url)

                return urls
            else:
                logger.warning(f"Unsplash API返回错误: {response.status_code}")
                return []

        except Exception as e:
            logger.warning(f"Unsplash请求失败: {e}")
            return []

    async def _fetch_from_pexels(self, query: str, count: int) -> List[str]:
        """
        🔧 备选功能：从 Pexels API 获取图片（需要 API Key）

        注意：此功能当前未完全实现，实际项目需要申请 Pexels API Key
        推荐使用 LoremFlickr 作为稳定的图片来源
        """
        try:
            # Pexels的图片搜索URL构建
            search_url = f"https://images.pexels.com/photos/{query}/"

            # 🔧 备选功能：Pexels API 调用
            # 使用Pexels的公开搜索（注意：实际需要API，这里提供占位实现）
            # 实际项目中建议申请 Pexels API Key
            logger.info("🔧 Pexels API 功能未完全实现，跳过此图片源")
            return []

        except Exception as e:
            logger.warning(f"Pexels请求失败: {e}")
            return []

    async def _fetch_from_loremflickr(self, query: str, count: int) -> List[str]:
        """
        从 LoremFlickr 获取随机图片
        稳定、免费、无需API Key
        """
        urls = []
        keywords = self._extract_keywords(query)

        for i in range(count):
            # 使用关键词组合
            keyword = keywords[i % len(keywords)]
            url = f"https://loremflickr.com/800/600/{keyword}?random={i + 1}"
            urls.append(url)

        return urls

    def _generate_placeholder_urls(self, query: str, count: int) -> List[str]:
        """生成占位图URL"""
        urls = []
        keywords = self._extract_keywords(query)

        for i in range(count):
            keyword = keywords[i % len(keywords)]
            # 使用 Via Placeholder 服务
            url = f"https://via.placeholder.com/800x600/4A90E2/ffffff?text={keyword}"
            urls.append(url)

        return urls

    def _extract_keywords(self, query: str) -> List[str]:
        """从查询中提取英文关键词"""
        # 中文到英文的映射
        keyword_map = {
            "故宫": "forbidden-city,palace",
            "长城": "great-wall",
            "天坛": "temple",
            "颐和园": "summer-palace",
            "兵马俑": "terracotta-warriors",
            "大雁塔": "pagoda",
            "回民街": "street-food,market",
            "钟楼": "bell-tower",
            "城墙": "city-wall",
            "博物馆": "museum",
            "公园": "park",
            "寺庙": "temple",
            "山": "mountain",
            "湖": "lake",
            "江": "river",
            "海": "sea,ocean",
            "美食": "food,street-food",
            "小吃": "snack,street-food",
            "餐厅": "restaurant",
            "景点": "landmark,scenery",
            "旅游": "travel,landscape"
        }

        # 提取关键词
        keywords = []
        query_lower = query.lower()

        for chinese, english in keyword_map.items():
            if chinese in query:
                keywords.extend(english.split(","))

        # 如果没有匹配，使用通用词
        if not keywords:
            keywords = ["landscape", "travel", "scenery", "landmark"]

        return keywords

    def _get_cache_key(self, query: str, count: int) -> str:
        """生成缓存键"""
        content = f"{query}_{count}"
        return hashlib.md5(content.encode()).hexdigest()

    def _load_from_cache(self, cache_key: str) -> Optional[List[str]]:
        """从缓存加载图片URL"""
        cache_file = self.cache_dir / f"{cache_key}.json"

        if cache_file.exists():
            try:
                with open(cache_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    # 检查缓存是否过期（7天）
                    import time
                    if time.time() - data.get("timestamp", 0) < 7 * 24 * 3600:
                        return data.get("urls", [])
            except Exception as e:
                logger.warning(f"缓存读取失败: {e}")

        return None

    def _save_to_cache(self, cache_key: str, urls: List[str]):
        """保存图片URL到缓存"""
        cache_file = self.cache_dir / f"{cache_key}.json"

        try:
            import time
            data = {
                "urls": urls,
                "timestamp": time.time()
            }

            with open(cache_file, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)

        except Exception as e:
            logger.warning(f"缓存保存失败: {e}")

    async def close(self):
        """关闭HTTP客户端"""
        await self.client.aclose()


# 全局单例
_image_service: Optional[ImageService] = None


def get_image_service() -> ImageService:
    """获取图片服务单例"""
    global _image_service
    if _image_service is None:
        _image_service = ImageService()
    return _image_service


# 便捷函数
async def get_scenery_images(query: str, count: int = 3) -> List[str]:
    """
    获取景区图片的便捷函数

    Args:
        query: 景区名称或关键词
        count: 需要的图片数量

    Returns:
        图片URL列表

    示例:
        >>> urls = await get_scenery_images("故宫", 3)
        >>> print(urls)
        ['https://...', 'https://...', 'https://...']
    """
    service = get_image_service()
    return await service.get_scenery_images(query, count)


if __name__ == "__main__":
    # 测试代码
    import asyncio

    async def test():
        service = ImageService()

        # 测试获取故宫图片
        urls = await service.get_scenery_images("故宫", 3)
        print("故宫图片:")
        for url in urls:
            print(f"  - {url}")

        # 测试获取美食图片
        urls = await service.get_scenery_images("回民街美食", 2)
        print("\n回民街美食图片:")
        for url in urls:
            print(f"  - {url}")

        await service.close()

    asyncio.run(test())
