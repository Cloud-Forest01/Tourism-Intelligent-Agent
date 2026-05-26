"""
智能规划数据模型设计
====================
基于参照图的地图中心化设计，创建结构化JSON数据模型
"""

from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field
from datetime import datetime


# ===================== 1. POI (兴趣点) 模型 =====================

class POI(BaseModel):
    """
    兴趣点 (Point of Interest)
    表示单个景点/地点
    """
    id: str = Field(..., description="POI唯一标识")
    name: str = Field(..., description="地点名称")

    # 坐标信息
    lng: float = Field(..., description="经度")
    lat: float = Field(..., description="纬度")
    address: Optional[str] = Field(None, description="详细地址")

    # 时间信息
    start_time: str = Field(..., description="开始时间 HH:MM")
    end_time: str = Field(..., description="结束时间 HH:MM")
    duration: Optional[int] = Field(None, description="建议游览时长（分钟）")

    # 显示信息
    order: int = Field(..., description="当天游览顺序 (1,2,3...)")
    image_url: Optional[str] = Field(None, description="地点图片URL")
    description: Optional[str] = Field(None, description="地点描述/简介")
    category: Optional[str] = Field(None, description="类别: 景点/美食/酒店/购物等")

    # 费用信息
    cost: Optional[float] = Field(None, description="预计花费（元）")
    ticket_price: Optional[float] = Field(None, description="门票价格（元）")

    # 额外信息
    notes: Optional[str] = Field(None, description="备注信息")
    rating: Optional[float] = Field(None, description="评分 (0-5)")
    tags: List[str] = Field(default_factory=list, description="标签: [经典打卡, 免费景点]")


# ===================== 2. Route (路线) 模型 =====================

class RouteSegment(BaseModel):
    """
    路线段
    两个POI之间的路径信息
    """
    from_poi_id: str = Field(..., description="起点POI ID")
    to_poi_id: str = Field(..., description="终点POI ID")
    distance: int = Field(..., description="距离（米）")
    duration: int = Field(..., description="预计耗时（秒）")
    path_coords: List[List[float]] = Field(default_factory=list, description="路径坐标 [[lng,lat],...]")
    transport_mode: str = Field(default="walking", description="交通方式: driving/walking/transit")


class DayRoute(BaseModel):
    """
    单日路线
    表示一天的完整行程安排
    """
    day: int = Field(..., description="第几天 (1-30)")
    date: Optional[str] = Field(None, description="日期 YYYY-MM-DD")

    # POI列表（按游览顺序）
    pois: List[POI] = Field(default_factory=list, description="当天游览的所有POI")

    # 路线信息
    route_segments: List[RouteSegment] = Field(default_factory=list, description="POI之间的路线段")
    total_distance: Optional[int] = Field(None, description="总距离（米）")
    total_duration: Optional[int] = Field(None, description="总时长（分钟）")

    # 路线显示样式
    route_color: str = Field(default="#10B981", description="路线颜色 (绿色参照图2)")
    route_width: int = Field(default=5, description="路线宽度")

    # 当日统计
    total_cost: Optional[float] = Field(None, description="当日总花费（元）")
    total_tickets: Optional[float] = Field(None, description="当日门票总计（元）")

    # 当日备注
    day_summary: Optional[str] = Field(None, description="当日行程总结")
    tips: List[str] = Field(default_factory=list, description="当日提示")


# ===================== 3. Itinerary (完整行程) 模型 =====================

class Itinerary(BaseModel):
    """
    完整行程计划
    表示整个旅行规划
    """
    # 基本信息
    id: str = Field(..., description="行程唯一ID")
    destination: str = Field(..., description="目的地")
    destination_city: Optional[str] = Field(None, description="目的地城市编码")

    # 日期信息
    start_date: str = Field(..., description="开始日期 YYYY-MM-DD")
    end_date: str = Field(..., description="结束日期 YYYY-MM-DD")
    total_days: int = Field(..., description="总天数")

    # 用户偏好
    travelers: int = Field(default=1, description="旅行人数")
    budget: Optional[float] = Field(None, description="总预算（元）")
    preferences: List[str] = Field(default_factory=list, description="用户偏好")

    # 完整行程数据
    days: List[DayRoute] = Field(default_factory=list, description="每日行程列表")

    # 统计信息
    estimated_total_cost: Optional[float] = Field(None, description="预计总花费（元）")
    estimated_total_distance: Optional[int] = Field(None, description="总距离（米）")

    # 创建时间
    created_at: datetime = Field(default_factory=datetime.now, description="创建时间")

    # 用户ID
    user_id: Optional[str] = Field(None, description="用户ID")

    # 额外说明
    overall_notes: Optional[str] = Field(None, description="整体备注")
    recommendations: List[str] = Field(default_factory=list, description="旅行建议")


# ===================== 4. 请求/响应模型 =====================

class TripPlanV2Request(BaseModel):
    """
    新版行程规划请求
    """
    destination: str = Field(..., description="目的地")
    start_date: str = Field(..., description="开始日期 YYYY-MM-DD")
    end_date: str = Field(..., description="结束日期 YYYY-MM-DD")
    travelers: int = Field(default=1, description="旅行人数")
    budget: Optional[float] = Field(None, description="预算（元）")
    preferences: List[str] = Field(default_factory=list, description="偏好列表")
    user_requirements: Optional[str] = Field(None, description="其他要求")
    user_id: Optional[str] = Field(None, description="用户ID")
    deep_thinking: bool = Field(default=False, description="是否深度思考")
    response_format: str = Field(default="json", description="响应格式: json/markdown")


class TripPlanV2Response(BaseModel):
    """
    新版行程规划响应
    """
    success: bool = Field(..., description="是否成功")
    message: Optional[str] = Field(None, description="提示信息")

    # 结构化数据
    itinerary: Optional[Itinerary] = Field(None, description="结构化行程数据")

    # 原始AI输出（备用）
    raw_plan: Optional[str] = Field(None, description="AI原始Markdown输出")

    # 错误信息
    error: Optional[str] = Field(None, description="错误详情")


# ===================== 5. 批量地理编码模型 =====================

class BatchGeocodeRequest(BaseModel):
    """
    批量地理编码请求
    """
    addresses: List[str] = Field(..., description="地址/地点名称列表")
    city: Optional[str] = Field(None, description="城市名称，用于提升准确度")


class GeocodedLocation(BaseModel):
    """
    地理编码结果
    """
    original_address: str = Field(..., description="原始输入地址")
    name: str = Field(..., description="解析出的地点名称")
    lng: float = Field(..., description="经度")
    lat: float = Field(..., description="纬度")
    formatted_address: Optional[str] = Field(None, description="格式化地址")
    level: Optional[str] = Field(None, description="地址级别")
    success: bool = Field(..., description="是否成功解析")
    error: Optional[str] = Field(None, description="错误信息")


class BatchGeocodeResponse(BaseModel):
    """
    批量地理编码响应
    """
    success: bool = Field(..., description="是否成功")
    city: Optional[str] = Field(None, description="查询城市")
    locations: List[GeocodedLocation] = Field(default_factory=list, description="编码结果列表")
    total: int = Field(..., description="总数")
    failed: int = Field(..., description="失败数量")


# ===================== 6. 前端展示模型 =====================

class MapMarker(BaseModel):
    """
    地图标记（用于前端展示）
    """
    id: str = Field(..., description="标记ID")
    position: List[float] = Field(..., description="位置 [lng, lat]")
    label: str = Field(..., description="标记文字（数字或名称）")
    title: str = Field(..., description="标记标题")
    icon_type: str = Field(default="numbered", description="图标类型: numbered/location/custom")
    color: str = Field(default="#10B981", description="标记颜色")


class MapPolyline(BaseModel):
    """
    地图路线（用于前端展示）
    """
    day: int = Field(..., description="天数")
    path: List[List[float]] = Field(..., description="路径坐标 [[lng,lat],...]")
    color: str = Field(default="#10B981", description="路线颜色（绿色）")
    width: int = Field(default=5, description="线条宽度")
    show: bool = Field(default=True, description="是否显示")


class MapDisplayData(BaseModel):
    """
    地图展示数据（前端调用）
    """
    destination: str = Field(..., description="目的地")
    center: List[float] = Field(..., description="地图中心 [lng, lat]")
    zoom: int = Field(default=12, description="缩放级别")

    markers: List[MapMarker] = Field(default_factory=list, description="所有POI标记")
    polylines: List[MapPolyline] = Field(default_factory=list, description="各天路线")

    current_day: int = Field(default=1, description="当前显示天数")
    total_days: int = Field(..., description="总天数")


# ===================== 使用示例 =====================

"""
示例JSON输出结构（AI应返回此格式）:
{
    "destination": "西安",
    "start_date": "2025-03-01",
    "end_date": "2025-03-03",
    "total_days": 3,
    "days": [
        {
            "day": 1,
            "date": "2025-03-01",
            "pois": [
                {
                    "id": "poi_1_1",
                    "name": "钟楼",
                    "lng": 108.940174,
                    "lat": 34.261938,
                    "address": "西安市莲湖区钟楼",
                    "start_time": "09:00",
                    "end_time": "11:00",
                    "duration": 120,
                    "order": 1,
                    "image_url": "https://example.com/zhonglou.jpg",
                    "description": "西安地标建筑，明代钟楼",
                    "category": "景点",
                    "cost": 50,
                    "ticket_price": 50,
                    "rating": 4.8,
                    "tags": ["经典打卡", "历史建筑"]
                },
                {
                    "id": "poi_1_2",
                    "name": "回民街",
                    "lng": 108.938967,
                    "lat": 34.263049,
                    "address": "西安市莲湖区回民街",
                    "start_time": "11:30",
                    "end_time": "13:30",
                    "duration": 120,
                    "order": 2,
                    "image_url": "https://example.com/huimin.jpg",
                    "description": "西安著名美食街",
                    "category": "美食",
                    "cost": 100,
                    "rating": 4.6,
                    "tags": ["平价美食"]
                }
            ],
            "route_color": "#10B981",
            "total_cost": 150,
            "day_summary": "上午游览钟楼，中午在回民街品尝美食"
        }
    ],
    "estimated_total_cost": 1500
}
"""
