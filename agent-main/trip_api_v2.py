"""
新版行程规划API - 智能规划V2
================================
实现结构化JSON输出的行程规划接口
需要添加到 unified_server.py 中
"""
import logging
import asyncio
from typing import Optional, List
from datetime import datetime
from fastapi import HTTPException
from pydantic import BaseModel, Field

# 导入数据模型
import sys
from pathlib import Path
project_root = Path(__file__).parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

from data_models_design import (
    TripPlanV2Request, TripPlanV2Response, Itinerary,
    BatchGeocodeRequest, BatchGeocodeResponse, GeocodedLocation,
    MapDisplayData, MapMarker, MapPolyline
)
from core.prompts.trip_planning_prompts import (
    get_structured_trip_prompt,
    parse_json_from_ai_response
)
from core.agent_mcp.gaode_trip_wrapper import GaodeTripAPI

logger = logging.getLogger(__name__)


# ===================== 全局变量 =====================

# 全局高德API实例（在unified_server.py中初始化）
gaode_api: Optional[GaodeTripAPI] = None

# 全局agent实例（在unified_server.py中初始化）
agent_instance = None


# ===================== API实现函数 =====================

async def plan_trip_v2(
    request: TripPlanV2Request,
    _agent_instance=None,
    _gaode_api=None
) -> TripPlanV2Response:
    """
    行程规划V2 - 返回结构化JSON数据

    Args:
        request: 行程规划请求
        _agent_instance: Agent实例（从外部传入）
        _gaode_api: 高德API实例（从外部传入）

    Returns:
        TripPlanV2Response: 结构化行程数据
    """
    global agent_instance, gaode_api

    # 使用传入的实例或全局实例
    agent = _agent_instance or agent_instance
    api = _gaode_api or gaode_api

    if agent is None:
        return TripPlanV2Response(
            success=False,
            message="Agent系统未初始化",
            error="服务不可用"
        )

    try:
        # 1. 计算天数
        from datetime import datetime as dt
        try:
            start = dt.strptime(request.start_date, "%Y-%m-%d")
            end = dt.strptime(request.end_date, "%Y-%m-%d")
            days_count = (end - start).days + 1
        except:
            days_count = 3

        # 2. 生成结构化提示词
        prompt = get_structured_trip_prompt(
            destination=request.destination,
            start_date=request.start_date,
            end_date=request.end_date,
            days_count=days_count,
            preferences=request.preferences,
            budget=request.budget,
            travelers=request.travelers,
            user_requirements=request.user_requirements
        )

        logger.info(f"📋 开始V2行程规划: {request.destination}, {days_count}天")

        # 3. 调用AI获取JSON响应（直接调用模型，跳过任务规划）
        user_id = request.user_id or "anonymous"

        # ✅ 根据请求参数选择模型（深度思考 vs 快速模式）
        from config import Config
        import time

        original_model = agent.model.llm.model_name


        # 根据 deep_thinking 参数选择模型
        if request.deep_thinking:
            agent.model.llm.model_name = Config.QWEN_MODEL_DEEP
            logger.info(f"🧠 深度思考模式启用，使用 {Config.QWEN_MODEL_DEEP}")
        else:
            agent.model.llm.model_name = Config.QWEN_MODEL_FAST
            logger.info(f"⚡ 快速模式启用，使用 {Config.QWEN_MODEL_FAST}")

        # ✅ 修复：直接调用 LLM 模型，不通过 agent.run() 的任务规划流程
        # 旅行规划 API 需要直接获取旅行规划数据，而不是任务步骤
        messages = [{"role": "user", "content": prompt}]

        # ⏱️ 开始计时 - AI调用
        llm_start = time.time()
        logger.info(f"⏱️ [计时] 开始AI调用，Prompt长度: {len(prompt)} 字符")
        full_response = await agent.model.agenerate(messages)
        llm_time = time.time() - llm_start
        logger.info(f"⏱️ [计时] AI调用完成，耗时: {llm_time:.1f}秒，响应长度: {len(full_response)} 字符")

        # 4. 解析JSON响应
        parse_start = time.time()
        parsed_data = parse_json_from_ai_response(full_response)
        parse_time = time.time() - parse_start
        logger.info(f"⏱️ [计时] JSON解析耗时: {parse_time:.2f}秒")

        if parsed_data is None:
            # JSON解析失败
            logger.warning("⚠️ JSON解析失败，返回原始响应")
            return TripPlanV2Response(
                success=False,
                message="AI返回的数据格式不正确，无法解析为结构化数据",
                raw_plan=full_response,
                error="JSON解析失败"
            )

        # 5. 添加元数据
        parsed_data["id"] = f"trip_{user_id}_{int(datetime.now().timestamp())}"
        parsed_data["user_id"] = user_id
        parsed_data["travelers"] = request.travelers
        parsed_data["preferences"] = request.preferences

        # 6. 验证并创建Itinerary对象
        try:
            itinerary = Itinerary(**parsed_data)
        except Exception as e:
            logger.error(f"⚠️ Itinerary验证失败: {e}")
            return TripPlanV2Response(
                success=False,
                message=f"数据验证失败: {str(e)}",
                raw_plan=full_response,
                error=str(e)
            )

        # 7. 如果有高德API，进行地理编码增强
        if api and itinerary.days:
            geo_start = time.time()
            logger.info("🗺️ 开始地理编码增强...")
            await enhance_itinerary_with_geocoding(itinerary, api)
            geo_time = time.time() - geo_start
            logger.info(f"⏱️ [计时] 地理编码增强耗时: {geo_time:.1f}秒")

        total_time = time.time() - llm_start
        logger.info(f"✅ V2行程规划完成: {len(itinerary.days)} 天行程，总耗时: {total_time:.1f}秒")

        return TripPlanV2Response(
            success=True,
            message="行程规划成功",
            itinerary=itinerary,
            raw_plan=full_response
        )

    except Exception as e:
        logger.error(f"❌ V2行程规划失败: {e}", exc_info=True)
        return TripPlanV2Response(
            success=False,
            message=f"行程规划失败: {str(e)}",
            error=str(e)
        )


async def enhance_itinerary_with_geocoding(
    itinerary: Itinerary,
    gaode_api: GaodeTripAPI
) -> None:
    """
    使用高德地理编码增强行程数据

    修正AI生成的坐标，规划路径，计算距离

    Args:
        itinerary: 行程对象（会被原地修改）
        gaode_api: 高德API实例
    """
    # 步骤1：收集需要地理编码的POI（坐标无效的）
    all_places = []
    for day in itinerary.days:
        for poi in day.pois:
            # 如果坐标无效(0,0)或需要验证，则重新地理编码
            if poi.lng == 0 or poi.lat == 0 or abs(poi.lng) < 1:
                all_places.append(poi)

    # 步骤2：对需要地理编码的POI进行批量处理
    if all_places:
        place_names = [poi.name for poi in all_places]
        results = await gaode_api.batch_geocode(
            addresses=place_names,
            city=itinerary.destination
        )

        # 更新POI坐标
        success_count = 0
        for poi, result in zip(all_places, results):
            if result.success:
                poi.lng = result.lng
                poi.lat = result.lat
                if result.formatted_address:
                    poi.address = result.formatted_address
                success_count += 1

        logger.info(f"✅ 地理编码完成: {success_count}/{len(all_places)} 成功")
    else:
        logger.info("✅ 所有POI已有有效坐标，跳过地理编码")

    # 步骤3：为每天规划路径（无论是否执行了地理编码）
    for day in itinerary.days:
        if len(day.pois) >= 2:
            segments = await gaode_api.plan_route(
                pois=day.pois,
                transport_mode="walking"
            )
            day.route_segments = segments

            # 计算总距离和时长
            total_distance = sum(s.distance for s in segments)
            total_duration = sum(s.duration for s in segments)
            day.total_distance = total_distance
            day.total_duration = total_duration


async def batch_geocode_api(
    request: BatchGeocodeRequest,
    _gaode_api=None
) -> BatchGeocodeResponse:
    """
    批量地理编码API

    Args:
        request: 地理编码请求
        _gaode_api: 高德API实例（从外部传入）

    Returns:
        BatchGeocodeResponse: 地理编码结果
    """
    global gaode_api
    api = _gaode_api or gaode_api

    if api is None:
        return BatchGeocodeResponse(
            success=False,
            city=request.city,
            locations=[],
            total=len(request.addresses),
            failed=len(request.addresses)
        )

    try:
        results = await api.batch_geocode(
            addresses=request.addresses,
            city=request.city
        )

        return BatchGeocodeResponse(
            success=True,
            city=request.city,
            locations=results,
            total=len(results),
            failed=sum(1 for r in results if not r.success)
        )

    except Exception as e:
        logger.error(f"批量地理编码失败: {e}", exc_info=True)
        return BatchGeocodeResponse(
            success=False,
            city=request.city,
            locations=[],
            total=len(request.addresses),
            failed=len(request.addresses)
        )


def get_map_display_data(
    itinerary: Itinerary,
    current_day: int = 1
) -> MapDisplayData:
    """
    从行程数据生成地图展示数据

    Args:
        itinerary: 行程对象
        current_day: 当前显示的天数

    Returns:
        MapDisplayData: 地图展示数据
    """
    # 收集所有标记
    markers = []
    polylines = []

    for day in itinerary.days:
        # 创建当天的POI标记
        for poi in day.pois:
            marker = MapMarker(
                id=poi.id,
                position=[poi.lng, poi.lat],
                label=str(poi.order) if day.day == current_day else "",
                title=poi.name,
                icon_type="numbered",
                color="#10B981" if day.day == current_day else "#9CA3AF"
            )
            markers.append(marker)

        # 创建当天的路线
        if day.route_segments and day.day <= current_day:
            # 提取路径坐标
            path_coords = []
            for seg in day.route_segments:
                if seg.path_coords:
                    path_coords.extend(seg.path_coords)
                else:
                    # 如果没有详细路径，使用起点终点
                    from_poi = next((p for p in day.pois if p.id == seg.from_poi_id), None)
                    to_poi = next((p for p in day.pois if p.id == seg.to_poi_id), None)
                    if from_poi and to_poi:
                        path_coords.append([from_poi.lng, from_poi.lat])
                        path_coords.append([to_poi.lng, to_poi.lat])

            if path_coords:
                polyline = MapPolyline(
                    day=day.day,
                    path=path_coords,
                    color="#10B981" if day.day == current_day else "#D1D5DB",
                    width=5 if day.day == current_day else 3,
                    show=day.day <= current_day
                )
                polylines.append(polyline)

    # 计算地图中心（使用第一个POI或城市中心）
    center = [116.397428, 39.90923]  # 默认北京
    if itinerary.days and itinerary.days[0].pois:
        first_poi = itinerary.days[0].pois[0]
        if first_poi.lng != 0 and first_poi.lat != 0:
            center = [first_poi.lng, first_poi.lat]

    return MapDisplayData(
        destination=itinerary.destination,
        center=center,
        zoom=13,
        markers=markers,
        polylines=polylines,
        current_day=current_day,
        total_days=itinerary.total_days
    )


# ===================== 添加到unified_server.py的路由 =====================

"""
在 unified_server.py 中添加以下路由：

@app.post("/api/trip/plan-v2", response_model=TripPlanV2Response)
async def plan_trip_v2_endpoint(request: TripPlanV2Request):
    '''行程规划V2 - 返回结构化JSON数据'''
    global agent_instance, gaode_api_instance
    return await plan_trip_v2(request, agent_instance, gaode_api_instance)


@app.post("/api/map/batch-geocode", response_model=BatchGeocodeResponse)
async def batch_geocode_endpoint(request: BatchGeocodeRequest):
    '''批量地理编码API'''
    global gaode_api_instance
    return await batch_geocode_api(request, gaode_api_instance)


@app.get("/api/trip/{trip_id}/map", response_model=MapDisplayData)
async def get_trip_map_data(trip_id: str, day: int = Query(1, ge=1)):
    '''获取行程的地图展示数据'''
    # 从数据库或内存中获取行程数据
    # 这里需要根据实际存储方式实现
    pass


同时在文件开头添加导入：
from trip_api_v2 import (
    plan_trip_v2, batch_geocode_api, get_map_display_data,
    TripPlanV2Request, TripPlanV2Response,
    BatchGeocodeRequest, BatchGeocodeResponse,
    MapDisplayData
)

在lifespan函数中初始化高德API：
async def lifespan(app: FastAPI):
    global agent_instance, memory_manager, conversation_service, gaode_api_instance

    # ... 现有初始化代码 ...

    # 初始化高德地图API
    from core.agent_mcp.gaode_trip_wrapper import GaodeTripAPI
    gaode_api_instance = GaodeTripAPI()
    logger.info("✅ 高德地图API客户端已初始化")

    yield

    # 关闭时清理
    if gaode_api_instance:
        await gaode_api_instance.close()
"""
