"""
统一后端API服务器
================================
项目启动入口：运行此文件启动完整服务
访问地址：http://localhost:8000/

架构说明：
---------
【Web前端】
- 主页: http://localhost:8000/ (index.html)
- 规划页: http://localhost:8000/planner (planner.html)
- 功能: 旅行规划表单、AI聊天、地图展示、图片预览

【API后端】
- /api/chat - 聊天接口
- /api/chat/stream - 流式聊天
- /api/trip/plan - 行程规划
- /api/trip/plan/stream - 流式行程规划
- /api/conversations - 会话管理
- API文档: http://localhost:8000/docs

【开发工具】
- dev_gradio.py - Gradio开发界面（仅用于开发测试）

技术栈：
- FastAPI: Web框架
- Web前端: HTML/CSS/JavaScript
- Agent: 通义千问(Qwen) + 高德地图 + Tavily搜索
"""
import os
import sys
import asyncio
import logging
from pathlib import Path
from datetime import datetime
from typing import List, Optional, Dict, Any, AsyncGenerator, Annotated
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Query, Request, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse, FileResponse, StreamingResponse
from pydantic import BaseModel, Field
import uvicorn

# ==================== 配置加载 ====================
# 导入统一配置（会自动加载 .env 文件）
from config import Config

# 验证必需的API密钥
all_ok, missing = Config.validate_required_keys()
if not all_ok:
    print("\n" + "=" * 60)
    print("[错误] 缺少必需的API密钥，无法启动服务")
    print("=" * 60)
    for key in missing:
        print(f"   - {key}")
    print("\n请在 .env 文件中配置以上API密钥")
    print("=" * 60 + "\n")
    sys.exit(1)

# 导入Agent系统
from core.agent_self.chat_agent_qwen_3_max import QwenModel
from core.agent_memory.memory import MemoryManager
from core.agent_self.agent import Agent

# 导入会话服务
from core.user_system.conversation_service import ConversationService

# ==================== 用户认证系统 =====================
# 导入数据库和认证服务
from core.database.repository import DatabaseRepository
from core.auth.auth_service import AuthService

# 导入认证 API 路由
from api import auth_routes, profile_routes
# ==================== 用户认证系统 =====================

# 导入高德地图Agent
from core.agent_mcp.agent_mcp_gaode import MCPClient

# 导入新版行程规划API (V2)
from trip_api_v2 import (
    plan_trip_v2,
    batch_geocode_api,
    get_map_display_data
)
from data_models_design import (
    TripPlanV2Request, TripPlanV2Response,
    BatchGeocodeRequest, BatchGeocodeResponse,
    MapDisplayData
)

# 设置日志
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ===================== 全局变量 =====================

agent_instance: Optional[Agent] = None
memory_manager: Optional[MemoryManager] = None
conversation_service: Optional[ConversationService] = None
gaode_agent: Optional[MCPClient] = None
gaode_trip_api = None  # 新版高德地图API封装（用于V2规划）

# ==================== 用户认证系统 ====================
# 数据库和认证服务
db_repository: Optional[DatabaseRepository] = None
auth_service: Optional[AuthService] = None
# ==================== 用户认证系统 ====================

# 导入认证依赖
from typing import Annotated


# ===================== 数据模型 =====================

class ApiResponse(BaseModel):
    """统一API响应格式"""
    success: bool
    message: str
    data: Optional[Any] = None


class ChatRequest(BaseModel):
    """聊天请求"""
    message: str = Field(..., description="用户消息")
    user_id: Optional[str] = Field(None, description="用户ID")
    conversation_id: Optional[str] = Field(None, description="会话ID")
    deep_thinking: bool = Field(False, description="是否启用深度思考")


class TripPlanRequest(BaseModel):
    """行程规划请求"""
    destination: str = Field(..., description="目的地")
    start_date: str = Field(..., description="开始日期 YYYY-MM-DD")
    end_date: str = Field(..., description="结束日期 YYYY-MM-DD")
    preferences: List[str] = Field(default_factory=list, description="旅游偏好")
    budget: Optional[str] = Field(None, description="预算")
    travelers: int = Field(1, ge=1, le=20, description="旅行人数（1-20人）")
    user_requirements: Optional[str] = Field(None, description="其他要求")
    user_id: Optional[str] = Field(None, description="用户ID")
    deep_thinking: bool = Field(False, description="是否启用深度思考")


class GeocodeRequest(BaseModel):
    """地理编码请求"""
    address: str = Field(..., description="地址或地点名称")
    city: Optional[str] = Field(None, description="城市")


class GeocodeResponse(BaseModel):
    """地理编码响应"""
    success: bool
    address: Optional[str] = None
    longitude: Optional[float] = None
    latitude: Optional[float] = None
    formatted_address: Optional[str] = None
    error: Optional[str] = None


class StaticMapRequest(BaseModel):
    """静态地图生成请求"""
    locations: List[Dict[str, Any]] = Field(..., description="地点列表，每个包含 name, lng, lat")
    center: Optional[Dict[str, float]] = Field(None, description="地图中心 {lng, lat}")
    zoom: Optional[int] = Field(12, description="缩放级别 (1-18)")
    width: Optional[int] = Field(800, description="地图宽度")
    height: Optional[int] = Field(500, description="地图高度")
    show_route: Optional[bool] = Field(True, description="是否显示路线")
    route_color: Optional[str] = Field("0x0000FF", description="路线颜色 (RGB hex)")
    marker_color: Optional[str] = Field("0xFF0000", description="标记颜色 (RGB hex)")


# ===================== 认证依赖注入 =====================

def get_auth_service(request: Request):
    """从应用状态获取认证服务"""
    return request.app.state.auth_service


def get_db_repository(request: Request):
    """从应用状态获取数据库仓储"""
    return request.app.state.db_repository


async def get_current_user_required(
    request: Request
) -> dict:
    """
    获取当前用户（必需）

    用于需要认证的API端点
    如果用户未登录，抛出401错误
    """
    authorization = request.headers.get("Authorization")

    if not authorization:
        raise HTTPException(
            status_code=401,
            detail="未提供认证令牌，请先登录"
        )

    if not authorization.startswith("Bearer "):
        raise HTTPException(
            status_code=401,
            detail="无效的认证格式"
        )

    try:
        auth_service = get_auth_service(request)
        token = authorization[7:]  # 移除 "Bearer " 前缀

        user_data = auth_service.verify_token(token)
        if not user_data:
            raise HTTPException(
                status_code=401,
                detail="认证令牌无效或已过期，请重新登录"
            )

        return user_data
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=401,
            detail=f"认证失败: {str(e)}"
        )


# 类型别名，方便使用
CurrentUser = Annotated[dict, Depends(get_current_user_required)]


# ===================== 生命周期管理 =====================

@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期管理"""
    global agent_instance, memory_manager, conversation_service, gaode_agent, db_repository, auth_service

    logger.info("🚀 正在初始化后端服务...")

    try:
        # ==================== 用户认证系统 ====================
        # 初始化数据库
        database_url = os.getenv('DATABASE_URL', 'sqlite:///./data/trip_planner.db')
        db_repository = DatabaseRepository(database_url)
        logger.info("✅ 数据库初始化成功")

        # 初始化认证服务
        auth_service = AuthService(db_repository)
        logger.info("✅ 认证服务初始化成功")
        # ==================== 用户认证系统 ====================

        # 初始化模型
        model = QwenModel(
            provider="qwen",
            mode="fast",
            enable_thinking=True,
            thinking_tokens=2000
        )
        logger.info("✅ Qwen模型初始化成功 (已启用思考模式)")


        # 初始化记忆管理器
        memory_manager = MemoryManager(use_conversation_system=True)
        logger.info("✅ 记忆管理器初始化成功")

        # 初始化Agent
        agent_instance = Agent(model, memory_manager, use_conversation_system=True)
        logger.info("✅ Agent系统初始化成功")

        # 初始化会话服务
        conversation_service = ConversationService()
        logger.info("✅ 会话服务初始化成功")

        # 初始化高德地图Agent
        try:
            gaode_agent = MCPClient()
            if gaode_agent.gaode_client:
                logger.info("✅ 高德地图Agent初始化成功")
            else:
                logger.warning("⚠️ 高德地图Agent初始化失败：gaode_client为None")
                gaode_agent = None
        except Exception as e:
            logger.warning(f"⚠️ 高德地图Agent初始化失败: {e}")
            gaode_agent = None

        # 初始化高德地图API封装（用于V2规划）
        try:
            from core.agent_mcp.gaode_trip_wrapper import GaodeTripAPI
            global gaode_trip_api
            gaode_trip_api = GaodeTripAPI()
            logger.info("✅ 高德地图API封装初始化成功 (V2规划)")
        except Exception as e:
            logger.warning(f"⚠️ 高德地图API封装初始化失败: {e}")
            gaode_trip_api = None

        # ==================== 用户认证系统 ====================
        # 将服务设置到 app.state，供依赖注入使用
        app.state.db_repository = db_repository
        app.state.auth_service = auth_service
        logger.info("✅ 应用状态设置完成")
        # ==================== 用户认证系统 ====================

        # ==================== 管理员系统 ====================
        # 初始化管理员系统
        try:
            set_db_repository(db_repository)
            init_admin_system(db_repository)
            logger.info("✅ 管理员系统初始化成功")
        except Exception as e:
            logger.warning(f"⚠️ 管理员系统初始化失败: {e}")
        # ==================== 管理员系统 ====================

        # ✅ 启动时清理超过7天的已删除会话（自动清理）
        try:
            deleted_count = db_repository.purge_deleted_conversations(max_age_days=7)
            if deleted_count > 0:
                logger.info(f"🗑️ 自动清理了 {deleted_count} 个超过7天的已删除会话")
        except Exception as e:
            logger.warning(f"⚠️ 自动清理已删除会话时出错: {e}")

        # ✅ 启动时归档超过90天的活跃会话（自动归档旧会话）
        # 注意：此功能需要使用 conversation_repository，暂时注释掉
        # try:
        #     archived_count = conversation_service.cleanup_old_conversations(user_id="system", max_age_days=90)
        #     if archived_count > 0:
        #         logger.info(f"📦 自动归档了 {archived_count} 个超过90天的活跃会话")
        # except Exception as e:
        #     logger.warning(f"⚠️ 自动归档旧会话时出错: {e}")

        logger.info("🎉 后端服务启动完成!")

    except Exception as e:
        logger.error(f"❌ 初始化失败: {e}", exc_info=True)

    yield

    # 关闭时清理
    logger.info("👋 后端服务正在关闭...")
    if gaode_trip_api:
        try:
            import asyncio
            asyncio.create_task(gaode_trip_api.close())
            logger.info("✅ 高德地图API封装已关闭")
        except Exception as e:
            logger.warning(f"⚠️ 关闭高德地图API封装时出错: {e}")


# ===================== 创建FastAPI应用 =====================

app = FastAPI(
    title="下一站Youth API",
    description="大学生穷游助手 - 统一后端接口（精简版）",
    version="2.1.0",
    lifespan=lifespan
)

# 配置CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 挂载静态文件目录
frontend_dir = Path(__file__).parent / "static"
web_frontend_dir = Path(__file__).parent / "web_frontend" / "frontend"
temp_visualizations_dir = Path(__file__).parent / "temp_visualizations"

# 自定义StaticFiles，添加缓存控制
from fastapi.staticfiles import StaticFiles
from fastapi.responses import Response

class NoCacheStaticFiles(StaticFiles):
    async def get_response(self, path: str, scope):
        response = await super().get_response(path, scope)
        if isinstance(response, Response):
            # 禁用缓存
            response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
            response.headers["Pragma"] = "no-cache"
            response.headers["Expires"] = "0"
        return response

# 优先使用 static 目录（新的认证页面）
if frontend_dir.exists():
    app.mount("/static", NoCacheStaticFiles(directory=str(frontend_dir)), name="static")
elif web_frontend_dir.exists():
    app.mount("/static", NoCacheStaticFiles(directory=str(web_frontend_dir)), name="static")

if temp_visualizations_dir.exists():
    app.mount("/visualizations", StaticFiles(directory=str(temp_visualizations_dir)), name="visualizations")

# ==================== 管理员系统 =====================
# 挂载管理员静态文件
admin_dir = Path(__file__).parent / "admin"
if admin_dir.exists():
    app.mount("/admin", StaticFiles(directory=str(admin_dir), html=True), name="admin")
    logger.info("✅ 管理员静态文件挂载成功")
# ==================== 管理员系统 ====================

# ==================== 用户认证系统 ====================
# 注册认证路由
app.include_router(auth_routes.router, tags=['认证'])
app.include_router(profile_routes.router, tags=['用户资料'])

# ==================== 管理员系统 =====================
# 导入管理员路由
from api.admin_routes import admin_router, init_admin_system, set_db_repository

app.include_router(admin_router)
# ==================== 管理员系统 =====================
# ==================== 用户认证系统 ====================


# ===================== 辅助函数 =====================

async def stream_agent_response(
    prompt: str,
    user_id: Optional[str] = None,
    conversation_id: Optional[str] = None,
    deep_thinking: bool = False,
    skip_agent_planning: bool = False
) -> AsyncGenerator[str, None]:
    """流式获取Agent响应

    Args:
        prompt: 提示词
        user_id: 用户ID
        conversation_id: 会话ID（需要skip_agent_planning=False时生效）
        deep_thinking: 是否使用深度思考模式
        skip_agent_planning: 是否跳过Agent任务规划，直接调用模型
                           - True: 直接返回LLM文本（用于表单行程规划）
                           - False: 使用Agent.run()进行任务规划（用于聊天）
    """
    global agent_instance

    if agent_instance is None:
        raise HTTPException(status_code=503, detail="Agent系统未初始化")

    # 设置模型
    if deep_thinking:
        agent_instance.model.llm.model_name = Config.QWEN_MODEL_DEEP
        logger.info(f"🧠 使用深度思考模式 ({Config.QWEN_MODEL_DEEP})")
    else:
        agent_instance.model.llm.model_name = Config.QWEN_MODEL_FAST
        logger.info(f"⚡ 使用快速模式 ({Config.QWEN_MODEL_FAST})")

    # 设置用户ID
    os.environ["CURRENT_USER_ID"] = str(user_id or "anonymous")

    # 根据参数选择调用方式
    if skip_agent_planning:
        # ✅ 直接调用模型，跳过Agent任务规划（用于表单行程规划）
        logger.info("📝 直接调用LLM模型（跳过Agent规划）")
        messages = [{"role": "user", "content": prompt}]
        response = await agent_instance.model.agenerate(messages)
        yield response
    else:
        # ✅ 使用Agent.run()进行任务规划（支持会话管理）
        async for chunk in agent_instance.run(prompt, user_id=user_id, conversation_id=conversation_id):
            yield chunk


def form_to_prompt(start_date: str, end_date: str, destination: str,
                   preferences: List[str], budget: Optional[str],
                   travelers: int = 1,
                   user_requirements: Optional[str] = None) -> str:
    """将表单数据转换为AI提示词 - 穷游专属版本"""
    from datetime import datetime as dt

    # 计算天数
    try:
        start = dt.strptime(start_date, "%Y-%m-%d")
        end = dt.strptime(end_date, "%Y-%m-%d")
        days_count = (end - start).days + 1
    except:
        days_count = 3

    # 偏好描述映射 - 穷游优化版（与前端一致）
    TRAVEL_PREFERENCES = {
        "🎓 经典打卡": "必去景点（优先选择有学生优惠的标志性景点，如故宫、兵马俑、大雁塔等）",
        "🍜 平价美食": "本地人常去的平价美食街、大学食堂、夜市小吃（人均15-40元）",
        "🆓 免费景点": "免费公园、广场、城市地标、博物馆免费日、大学校园开放日",
        "🏨 青年旅舍": "青年旅舍（30-80元/床位）、沙发客、学生拼房、青旅推荐",
        "🎫 学生优惠": "重点推荐有学生票优惠的景点、学生公交卡、学生专线等",
        "📚 文化探索": "免费博物馆、历史文化街区（学生票半价）、城市漫步路线",
        "🏔️ 自然风光": "免费登山步道、城市公园、江河湖畔（避开收费景区）",
        "📸 拍照圣地": "免费网红打卡点、城市夜景、特色建筑外观、拍照角度推荐",
        "🚲 青春冒险": "免费徒步路线、城市骑行、公共体育设施、户外运动",
        "🎒 背包徒步": "轻装徒步、城市漫步、免费登山路线、背包客路线"
    }

    pref_descriptions = [TRAVEL_PREFERENCES.get(pref, "") for pref in preferences if pref in TRAVEL_PREFERENCES]

    # 判断是否选择"青年旅舍"偏好
    has_youth_hostel = "🏨 青年旅舍" in [p for p in preferences if "青年旅舍" in p or "youth-hostel" in p]

    # 计算人均预算
    daily_budget_text = ""
    per_person_budget_text = ""
    if budget:
        try:
            budget_int = int(budget)
            daily_avg = budget_int // days_count
            per_person = budget_int // travelers
            daily_budget_text = f"\n   - 日均预算: {daily_avg}元/天 (严格控制)"
            per_person_budget_text = f" (人均{per_person}元)" if travelers > 1 else ""
        except:
            per_person_budget_text = ""

    # 人数相关的提示文本
    travelers_type = "可拼房省钱" if travelers > 1 else "单人出行"
    travelers_note = f" ({travelers_type})"

    # 美食分享建议
    food_sharing_tip = f"💡 {travelers}人可以点不同菜分享，人均更便宜" if travelers > 1 else ""

    # 交通分摊建议
    transport_sharing_tip = f"💡 {travelers}人可以打车分摊，人均成本更低" if travelers > 2 else ""

    # 住宿类型说明
    accommodation_type = f"{travelers}人拼房" if travelers > 1 else "青旅床位"

    # 预算状态
    budget_status = "✅ 未超预算" if budget else "请控制预算"
    per_person_desc = f"总预算÷{travelers}人" if budget else "估算人均"

    # 团队建议
    team_tip = f"团队建议: {travelers}人出行建议分工（导航、财务、拍照等），避免走丢" if travelers > 1 else ""

    # 根据人数和偏好生成住宿建议
    if has_youth_hostel:
        # 用户选择了"青年旅舍"偏好
        same_room_note = f" - {travelers}人可住同一间" if travelers > 1 else ""
        accommodation_guide = f"""✅ **3. 住宿推荐**
   - 青年旅舍: 30-80元/床位 (推荐位置、交通、评价){same_room_note}
   - 多人拼房: 2-4人拼房更省钱 (人均约40-60元)
   - 沙发客、民宿等其他选项
   - 避雷：不推荐××区域（价格虚高/交通不便）"""
    else:
        # 用户未选择"青年旅舍"偏好，优先推荐经济型酒店
        if travelers == 1:
            accommodation_guide = """✅ **3. 住宿推荐**
   - 经济型酒店: 100-180元/间 (安全舒适)
   - 青年旅舍: 40-80元/床位 (性价比高，可结交朋友)
   - 沙发客、民宿等其他选项
   - 避雷：不推荐××区域（价格虚高/交通不便）"""
        else:
            hotel_cost_range = f"{100//travelers}-{180//travelers}"
            accommodation_guide = f"""✅ **3. 住宿推荐**
   - 经济型酒店: 100-180元/间 ({travelers}人拼房人均约{hotel_cost_range}元)
   - 青年旅舍: 30-80元/床位 (床位充足，社交氛围好)
   - 家庭房/三人间: 适合{travelers}人同住
   - 避雷：不推荐××区域（价格虚高/交通不便）"""

    # 构建预算信息
    budget_display = f"{budget}元" if budget else "未设限制（按最低成本规划）"

    # 构建预算信息
    budget_display = f"{budget}元" if budget else "未设限制（按最低成本规划）"

    prompt = f"""收到！我是小You，{travelers}人去{destination}玩{days_count}天，预算{budget_display}{per_person_budget_text}！

📋 **基本信息**
- 目的地：{destination}
- 时间：{start_date} 至 {end_date}（{days_count}天）
- 人数：{travelers}人{travelers_note}
- 偏好：{', '.join(pref_descriptions) if pref_descriptions else '经典穷游'}

⚠️ **核心约束**：
1. 用工具查询：天气/景点/美食/住宿/交通
2. 禁止编造：只用工具返回的真实POI和搜索结果
3. 景点图片：从maps_search_detail的photos字段获取
4. 美食住宿：根据搜索结果填写，无具体信息则如实说明

🚨 **输出语言规范 - 严禁技术性说明**：
❌ 禁止在输出中出现以下内容：
   - "（基于web_search结果）"
   - "web_search未返回"
   - "web_search调用失败"
   - "根据搜索结果"
   - "根据工具返回"
   - "根据以下信息"
   - "（用户偏好XXX）"
   - "（单人出行）"
   - "（多人出行）"
   - 任何涉及工具名、API名、技术实现细节的说明

✅ 正确做法：
   - 直接给出建议，如"推荐住在东街口附近"
   - 如果没有具体信息，自然说明"建议在当地咨询"
   - 用自然的语言表达，不要暴露技术实现细节

📝 **排版要求（确保整洁）**：
- 每个section之间用空行分隔
- 标题层级清晰：### 三级标题用于每天，**加粗**用于景点名称
- emoji适度使用：每个section开头1-2个，不要过多
- 表格统一：费用明细、行程对比用表格
- 图片位置：紧跟在景点描述下方，单独一行

---

✨ 穷游原则：高性价比、学生优惠、实用避坑

## 📅 每日详细行程

⚠️ **重要**：
- 将搜索到的景点合理分配到{days_count}天中
- 每天景点数量均衡，避免某天过于紧张
- 每个景点独立成段，包含：地址、门票、开放时间、避坑提醒
- 每个景点必须插入实景图片（从maps_search_detail的photos字段获取）
- 如果景点数量不够{days_count}天，明确说明并建议用户要求搜索更多

📋 **景点描述格式示例**：
```
📍 **[景点名称]**
🎫 **门票**: 学生票XX元（原价XX元），记得带学生证！
⏰ **开放时间**: XX:00-XX:00
📍 **地址**: XXXXX
💡 **穷游提示**: 提前预约/早去避开人流
🚫 **避坑提醒**: 商业化严重/不用请导游
![景点名称](图片URL)
```

---

### 🌞 Day 1 - {destination}探索

**上午行程 (08:30-12:00)**
⏰ 建议8:30前出发，避开人流
📍 行程安排：
- [根据工具搜索结果填写景点A]
- [根据工具搜索结果填写景点B]

📸 [景点A实景图]

**下午行程 (14:00-18:00)**
📍 行程安排：
- [根据工具搜索结果填写景点C]
- [根据工具搜索结果填写景点D]

📸 [景点C实景图]

**晚上安排 (19:00-21:00)**
🌙 夜游推荐

---

### 🌞 Day 2 - {destination}探索

**上午行程 (08:30-12:00)**
📍 行程安排：
- [根据工具搜索结果填写]

**下午行程 (14:00-18:00)**
📍 行程安排：
- [根据工具搜索结果填写]

**晚上安排 (19:00-21:00)**
🌙 夜游推荐

---

### 🌞 Day 3 - {destination}探索

**上午行程 (08:30-12:00)**
📍 行程安排：
- [根据工具搜索结果填写]

**下午行程 (14:00-18:00)**
📍 行程安排：
- [根据工具搜索结果填写]

**晚上安排 (19:00-21:00)**
🌙 夜游推荐

---

## 🏨 住宿推荐

{accommodation_guide}

💡 **穷游住宿小贴士**：
- 提前在美团/携程青旅频道预订，价格更优惠
- 查看评论时重点关注"位置"和"卫生"两条
- 到店后可以先看房间，不满意可以换

---

## 🍜 美食攻略

- 推荐去南京东路步行街、城隍庙美食街寻找平价美食
- 具体推荐：XX小笼包（人均25元）、XX面馆（人均15元）

{food_sharing_tip}

---

## 🚌 交通省钱方案

**到达{destination}**
- ✅ 推荐：填写具体的交通方式（如：高铁/动车/飞机/汽车），说明票价和大致时长
- ❌ 避免：填写太贵的交通方式（如：飞机头等舱、专车）

**市内交通**
- 🚌 公交/地铁：填写具体票价（如：地铁起步价3元）和办理方式（如：学生卡办理点）
- 🚲 共享单车：日卡约10-15元，短途必备
- 🚶 步行：推荐路线填写实际行程规划（如：从XX景点到XX景点步行约15分钟）

{transport_sharing_tip}

---

## 💰 费用预算表

| 项目 | 金额(元) | 说明 |
|------|----------|------|
| 住宿 | 填写具体金额 | {accommodation_type} × {days_count}晚 |
| 餐饮 | 填写具体金额 | {travelers}人 × 每日餐饮预算 × {days_count}天 |
| 交通 | 填写具体金额 | 包含往返、市内交通 |
| 门票 | 填写具体金额 | 根据搜索景点的学生票价格汇总 |
| 应急 | 填写具体金额 | 预留应急费用（如50-100元） |
|------|----------|------|
| **总计** | **计算填写** | {budget_status} |
| **人均** | **计算填写** | {per_person_desc} |

---

## 🎓 学生优惠大
⚠️ **列出学生票优惠**：
- 只列出搜索到的景点的学生票信息
- 如果POI数据中有门票信息，使用真实数据
- 如果POI中没有门票信息，说明"建议现场咨询"或"需提前查询"

⚠️ **学生证使用提示**
- 大学生证（研究生证也可用）：大部分景点通用
- 要带实体证件，照片可能不被认可
- 部分景点需要提前1-2天预约

**其他学生优惠**
- 学生公交卡：填写办理方式（如：可在XX地铁站办理，需携带学生证）
- 学生套餐：填写具体餐厅和优惠（如：XX餐厅凭学生证8折）

---

## ⚠️ 避坑指南

⚠️ **提供真实避坑信息**：
- 根据搜索到的POI详情和用户评价
- 如果搜索结果中没有具体避坑信息，说明"暂无具体避坑提醒，建议提前查询最新评价"

**🚫 游客陷阱**
填写具体的游客陷阱（如：XX景点商业化严重，门票贵不值得去）

**🚫 住宿避雷区**
填写具体区域（如：不要住XX区域，价格虚高且交通不便）

**💡 省钱小技巧**
填写具体方法（如：提前在美团预订青旅，可享优惠）

---

## 📝 实用贴士

**最佳游览时间**
- 避开节假日和周末，人少体验好
- 早上开门就去，避开旅行团人流
- 傍晚和日落时分拍照最美

**天气预案**
- 🌧️ 下雨天：填写免费博物馆/商场/室内景点（如：推荐去XX博物馆）
- ☀️ 晴天：填写户外景点推荐（如：适合去XX公园）

**安全提醒**
- 保管好贵重物品，晚上出行最好2人以上
- 记住紧急电话：填写当地旅游热线（如：12345）、填写学生救援电话
- 住宿选择安全评分高的地方

**超支应对**
- 如果预算超了，可以砍掉：填写可选项目（如：XX景点门票较高）
- 替换为免费项目：填写免费景点推荐（如：XX公园、XX广场）

{team_tip}

---

## 📸 景点图片推荐

我帮你们找了每个景点的实景图，这些图片来自高德地图POI数据，都是真实照片：

**Day 1 景点图片**
1. [景点A] - ![景点A](使用maps_search_detail返回的photos字段中的真实图片URL)
2. [景点B] - ![景点B](使用maps_search_detail返回的photos字段中的真实图片URL)

**Day 2 景点图片**
1. [景点C] - ![景点C](使用maps_search_detail返回的photos字段中的真实图片URL)
2. [景点D] - ![景点D](使用maps_search_detail返回的photos字段中的真实图片URL)

---

## 💬 最后的话

这份攻略是我根据{travelers}人{days_count}天{budget_display}的预算精心设计的，每一项都考虑了性价比和实用性。

如果你们在实际游玩过程中发现了更好的选择，欢迎随时告诉我！祝你们在{destination}玩得开心，既省钱又有收获！✨

有任何问题随时问我~

小You敬上 🎓
---

"""

    return prompt


# ===================== 页面路由 =====================

@app.get("/favicon.ico")
async def favicon():
    """网站图标"""
    favicon_path = Path(__file__).parent / "static" / "favicon.ico"
    if favicon_path.exists():
        return FileResponse(path=str(favicon_path), media_type="image/x-icon")
    # 返回一个简单的SVG图标
    svg_content = '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100"><text y=".9em" font-size="90">✈️</text></svg>'
    return Response(content=svg_content, media_type="image/svg+xml")

@app.get("/", response_class=HTMLResponse)
async def read_root():
    """主页 - 优先使用static目录，回退到旧版前端"""
    # 优先使用 static/index.html（新版本）
    static_index = Path(__file__).parent / "static" / "index.html"
    # 回退到 web_frontend/frontend/index.html（旧版本）
    old_index = Path(__file__).parent / "web_frontend" / "frontend" / "index.html"

    if static_index.exists():
        with open(static_index, "r", encoding="utf-8") as f:
            return f.read()
    elif old_index.exists():
        with open(old_index, "r", encoding="utf-8") as f:
            return f.read()
    return """
    <h1>🌍 下一站Youth API</h1>
    <p>欢迎访问下一站Youth后端服务</p>
    <ul>
        <li><a href="/docs">API 文档</a></li>
        <li><a href="/planner">行程规划</a></li>
    </ul>
    """

@app.get("/auth.html", response_class=HTMLResponse)
async def auth_page():
    """认证页面（只提供页面，API已暂时禁用）"""
    auth_file = frontend_dir / "auth.html"
    if auth_file.exists():
        with open(auth_file, "r", encoding="utf-8") as f:
            return f.read()
    return "<h1>认证页面不存在</h1>"


@app.get("/dashboard.html", response_class=HTMLResponse)
async def dashboard_page():
    """用户仪表板页面（只提供页面，API已暂时禁用）"""
    dashboard_file = frontend_dir / "dashboard.html"
    if dashboard_file.exists():
        with open(dashboard_file, "r", encoding="utf-8") as f:
            return f.read()
    return "<h1>仪表板页面不存在</h1>"


@app.get("/profile.html", response_class=HTMLResponse)
async def profile_page():
    """个人资料页面（只提供页面，API已暂时禁用）"""
    profile_file = frontend_dir / "profile.html"
    if profile_file.exists():
        with open(profile_file, "r", encoding="utf-8") as f:
            return f.read()
    return "<h1>个人资料页面不存在</h1>"


@app.get("/planner", response_class=HTMLResponse)
async def read_planner():
    """行程规划页"""
    planner_file = frontend_dir / "planner.html"
    if planner_file.exists():
        with open(planner_file, "r", encoding="utf-8") as f:
            return f.read()
    return "<h1>行程规划工具</h1><p>前端文件未找到</p>"


@app.get("/test", response_class=HTMLResponse)
async def read_test():
    """前端测试页面"""
    test_file = frontend_dir / "test.html"
    if test_file.exists():
        with open(test_file, "r", encoding="utf-8") as f:
            return f.read()
    return "<h1>测试页面</h1><p>测试页面未找到</p>"


@app.get("/test-js", response_class=HTMLResponse)
async def read_test_js():
    """JS加载测试页面"""
    test_file = frontend_dir / "test-js.html"
    if test_file.exists():
        with open(test_file, "r", encoding="utf-8") as f:
            return f.read()
    return "<h1>测试页面未找到</h1>"


@app.get("/simple-test", response_class=HTMLResponse)
async def read_simple_test():
    """简单测试页面"""
    test_file = frontend_dir / "simple-test.html"
    if test_file.exists():
        with open(test_file, "r", encoding="utf-8") as f:
            return f.read()
    return "<h1>测试页面未找到</h1>"


# ===================== 性能测试页面 =====================

@app.get("/map-perf-test", response_class=HTMLResponse)
async def map_performance_test():
    """地图渲染性能测试页面"""
    test_file = Path(__file__).parent / "性能测试" / "map_render_test.html"
    if test_file.exists():
        with open(test_file, "r", encoding="utf-8") as f:
            return f.read()
    return "<h1>测试页面未找到</h1><p>请确保 性能测试/map_render_test.html 文件存在</p>"


# ===================== 健康检查 =====================

@app.get("/api/health")
async def health_check():
    """健康检查"""
    return {
        "status": "ok",
        "timestamp": datetime.now().isoformat(),
        "services": {
            "agent": agent_instance is not None,
            "memory": memory_manager is not None,
            "conversation": conversation_service is not None,
            "gaode_map": gaode_agent is not None
        }
    }


# ===================== 聊天接口 =====================

@app.post("/api/chat", response_model=ApiResponse)
async def chat(request: ChatRequest, current_user: CurrentUser):
    """
    聊天接口 - 非流式

    返回完整的AI回复
    """
    try:
        if agent_instance is None:
            raise HTTPException(status_code=503, detail="Agent系统未初始化")

        # 使用认证用户的user_id（如果未提供则使用认证用户的ID）
        request_user_id = request.user_id or current_user.get("user_id")
        request_conversation_id = request.conversation_id

        # ✅ 创建会话（如果提供了用户ID且没有conversation_id）- 参考表单模式
        if request_user_id and conversation_service and not request_conversation_id:
            try:
                conv_result = conversation_service.create_from_form(
                    user_id=request_user_id,
                    start_date="",
                    end_date="",
                    destination="未指定",
                    preferences=[],
                    budget=None,
                    travelers=1,
                    user_requirements=request.message  # 使用用户消息作为备注
                )
                if conv_result["success"]:
                    request_conversation_id = conv_result["conversation_id"]
            except Exception as e:
                logger.warning(f"创建会话失败: {e}")

        # 收集完整响应
        full_response = ""
        async for chunk in stream_agent_response(
            request.message,
            request_user_id,
            request_conversation_id,
            request.deep_thinking
        ):
            full_response += chunk

        # ✅ 已移除 clean_external_images 调用，允许AI返回外部图片链接
        # full_response = clean_external_images(full_response)

        return ApiResponse(
            success=True,
            message="聊天成功",
            data={
                "response": full_response,
                "conversation_id": request_conversation_id
            }
        )

    except Exception as e:
        logger.error(f"聊天失败: {e}", exc_info=True)
        return ApiResponse(
            success=False,
            message=f"聊天失败: {str(e)}"
        )


@app.post("/api/trip/generate", response_model=ApiResponse)
async def trip_generate(request: ChatRequest, current_user: CurrentUser):
    """
    旅行规划生成接口（简化版聊天接口）

    这是前端调用的简化接口，实际功能与 /api/chat 相同
    接受 {prompt: string} 格式的请求
    """
    try:
        if agent_instance is None:
            raise HTTPException(status_code=503, detail="Agent系统未初始化")

        # 使用认证用户的user_id
        request_user_id = request.user_id or current_user.get("user_id")
        request_conversation_id = request.conversation_id

        # ✅ 创建会话（如果提供了用户ID且没有conversation_id）- 参考表单模式
        if request_user_id and conversation_service and not request_conversation_id:
            try:
                conv_result = conversation_service.create_from_form(
                    user_id=request_user_id,
                    start_date="",
                    end_date="",
                    destination="未指定",
                    preferences=[],
                    budget=None,
                    travelers=1,
                    user_requirements=request.message  # 使用用户消息作为备注
                )
                if conv_result["success"]:
                    request_conversation_id = conv_result["conversation_id"]
            except Exception as e:
                logger.warning(f"创建会话失败: {e}")

        # 收集完整响应
        full_response = ""
        async for chunk in stream_agent_response(
            request.message,
            request_user_id,
            request_conversation_id,
            request.deep_thinking
        ):
            full_response += chunk

        return ApiResponse(
            success=True,
            message="生成成功",
            data={
                "response": full_response,
                "conversation_id": request_conversation_id
            }
        )

    except Exception as e:
        logger.error(f"旅行规划生成失败: {e}", exc_info=True)
        return ApiResponse(
            success=False,
            message=f"生成失败: {str(e)}"
        )


# ===================== 行程规划接口 =====================

@app.post("/api/trip/plan", response_model=ApiResponse)
async def plan_trip(request: TripPlanRequest, current_user: CurrentUser):
    """
    行程规划接口 - 非流式

    使用表单数据生成旅行计划
    """
    try:
        if agent_instance is None:
            raise HTTPException(status_code=503, detail="Agent系统未初始化")

        # 使用认证用户的user_id
        request_user_id = request.user_id or current_user.get("user_id")

        # 创建会话（如果提供了用户ID）
        conversation_id = None
        if request_user_id and conversation_service:
            try:
                conv_result = conversation_service.create_from_form(
                    user_id=request_user_id,
                    start_date=request.start_date,
                    end_date=request.end_date,
                    destination=request.destination,
                    preferences=request.preferences,
                    budget=request.budget,
                    travelers=request.travelers,  # 添加人数参数
                    user_requirements=request.user_requirements
                )
                if conv_result["success"]:
                    conversation_id = conv_result["conversation_id"]
            except Exception as e:
                logger.warning(f"创建会话失败: {e}")

        # 转换为提示词
        prompt = form_to_prompt(
            request.start_date,
            request.end_date,
            request.destination,
            request.preferences,
            request.budget,
            request.travelers,  # 添加人数参数
            request.user_requirements
        )

        # 💡 根据用户选择动态切换模型
        original_model = agent_instance.model.llm.model_name
        if request.deep_thinking:
            agent_instance.model.llm.model_name = Config.QWEN_MODEL_DEEP
            logger.info(f"🧠 深度思考模式启用，使用 {Config.QWEN_MODEL_DEEP}")
        else:
            agent_instance.model.llm.model_name = Config.QWEN_MODEL_FAST
            logger.info(f"⚡ 快速模式启用，使用 {Config.QWEN_MODEL_FAST}")

        # 💡 启用Agent工具调用以获取实时真实信息（天气、POI、真实避坑指南等）
        # 注意：这会增加响应时间（约10-20秒），但能提供更实用的内容

        # ✅ 移除超时限制，允许完整生成攻略（复杂规划可能需要3-5分钟）
        full_response = ""
        try:
            # 直接收集响应，不设置超时限制
            async def collect_response():
                nonlocal full_response
                async for chunk in stream_agent_response(
                    prompt,
                    request.user_id,
                    conversation_id,
                    request.deep_thinking,  # ✅ 根据用户选择决定是否深度思考
                    skip_agent_planning=False  # ✅ 启用Agent工具调用，获取实时真实数据
                ):
                    # ✅ 跳过None值，只拼接字符串
                    if chunk is not None:
                        full_response += chunk

            await collect_response()
            logger.info(f"✅ 行程规划完成，响应长度: {len(full_response)} 字符")

            # ✅ 移除模型恢复逻辑，保持使用qwen3-max
            # ✅ 已移除 clean_external_images 调用，允许AI返回外部图片链接
            # full_response = clean_external_images(full_response)

            return ApiResponse(
                success=True,
                message="行程规划成功",
                data={
                    "plan": full_response,
                    "conversation_id": conversation_id,
                    "destination": request.destination,
                    "dates": {
                        "start": request.start_date,
                        "end": request.end_date
                    }
                }
            )

        except Exception as inner_e:
            logger.error(f"行程规划生成失败: {inner_e}", exc_info=True)
            return ApiResponse(
                success=False,
                message=f"行程规划失败: {str(inner_e)}"
            )

    except Exception as e:
        logger.error(f"行程规划失败: {e}", exc_info=True)
        return ApiResponse(
            success=False,
            message=f"行程规划失败: {str(e)}"
        )


# ===================== 会话管理接口 =====================

@app.get("/api/conversations", response_model=ApiResponse)
async def get_conversations(
    current_user: CurrentUser,
    user_id: str = Query(..., description="用户ID")
):
    """获取用户的会话列表（返回所有状态：活跃、归档、已删除）"""
    try:
        if conversation_service is None:
            raise HTTPException(status_code=503, detail="会话系统未初始化")

        # ✅ 验证user_id参数匹配认证用户
        if current_user.get("user_id") != user_id:
            raise HTTPException(status_code=403, detail="无权访问其他用户的会话")

        # ✅ 获取所有状态的会话（前端会进行客户端过滤）
        result = conversation_service.get_conversation_list_ui(user_id, status="all")

        return ApiResponse(
            success=True,
            message="获取会话列表成功",
            data={
                "conversations": result.get("conversations", []),
                "quota_info": result.get("quota_info", {}),
                "display_info": result.get("display_info", "")
            }
        )

    except Exception as e:
        logger.error(f"获取会话列表失败: {e}", exc_info=True)
        return ApiResponse(
            success=False,
            message=f"获取失败: {str(e)}"
        )


@app.post("/api/conversations", response_model=ApiResponse)
async def create_conversation(
    current_user: CurrentUser,
    title: str = Query(..., description="会话标题"),
    destination: str = Query(None, description="目的地"),
    start_date: str = Query(None, description="开始日期"),
    end_date: str = Query(None, description="结束日期"),
    preferences: List[str] = Query(default=[], description="旅行偏好")
):
    """创建新会话"""
    try:
        if conversation_service is None:
            raise HTTPException(status_code=503, detail="会话系统未初始化")

        # ✅ 使用认证用户的ID
        user_id = current_user.get("user_id")

        # 构建偏好数据
        trip_preferences = {
            "destination": destination or "未指定",
            "start_date": start_date,
            "end_date": end_date,
            "selected_preferences": preferences
        }

        result = conversation_service.create_from_form(
            user_id=user_id,
            start_date=start_date or "",
            end_date=end_date or "",
            destination=destination or "",
            preferences=preferences,
            budget=None,
            travelers=1,
            user_requirements=title
        )

        if result["success"]:
            return ApiResponse(
                success=True,
                message="会话创建成功",
                data={
                    "conversation_id": result["conversation_id"],
                    "title": title,
                    "trip_preferences": trip_preferences
                }
            )
        else:
            return ApiResponse(
                success=False,
                message=result.get("message", "创建失败")
            )

    except Exception as e:
        logger.error(f"创建会话失败: {e}", exc_info=True)
        return ApiResponse(
            success=False,
            message=f"创建失败: {str(e)}"
        )


@app.get("/api/conversations/{conversation_id}", response_model=ApiResponse)
async def get_conversation(conversation_id: str):
    """获取会话详情"""
    try:
        if conversation_service is None:
            raise HTTPException(status_code=503, detail="会话系统未初始化")

        conversation = conversation_service.get_conversation_by_id(conversation_id)

        if conversation:
            return ApiResponse(
                success=True,
                message="获取会话成功",
                data={"conversation": conversation}
            )
        else:
            return ApiResponse(
                success=False,
                message="会话不存在"
            )

    except Exception as e:
        logger.error(f"获取会话失败: {e}", exc_info=True)
        return ApiResponse(
            success=False,
            message=f"获取失败: {str(e)}"
        )


@app.get("/api/conversations/{conversation_id}/messages", response_model=ApiResponse)
async def get_conversation_messages(
    current_user: CurrentUser,
    conversation_id: str,
    limit: int = Query(100, description="返回消息数量限制"),
    offset: int = Query(0, description="跳过的消息数量")
):
    """获取会话的消息列表（支持分页）"""
    try:
        if conversation_service is None:
            raise HTTPException(status_code=503, detail="会话系统未初始化")

        # ✅ 验证会话属于当前用户
        conv = conversation_service.get_conversation_by_id(conversation_id)
        if not conv or conv.get("user_id") != current_user.get("user_id"):
            raise HTTPException(status_code=404, detail="会话不存在")

        messages = conversation_service.get_conversation_messages(conversation_id, limit, offset)

        if messages is not None:
            return ApiResponse(
                success=True,
                message="获取消息成功",
                data={
                    "messages": messages,
                    "limit": limit,
                    "offset": offset,
                    "total": len(messages)
                }
            )
        else:
            return ApiResponse(
                success=False,
                message="会话不存在或获取失败"
            )

    except Exception as e:
        logger.error(f"获取会话消息失败: {e}", exc_info=True)
        return ApiResponse(
            success=False,
            message=f"获取失败: {str(e)}"
        )


@app.delete("/api/conversations/{conversation_id}", response_model=ApiResponse)
async def delete_conversation(
    conversation_id: str,
    user_id: str = Query(..., description="用户ID"),
    permanently: bool = Query(False, description="是否永久删除")
):
    """删除会话"""
    try:
        if conversation_service is None:
            raise HTTPException(status_code=503, detail="会话系统未初始化")

        result = conversation_service.delete_conversation(conversation_id, user_id, permanently)

        return ApiResponse(
            success=result["success"],
            message=result.get("message", "删除成功" if result["success"] else "删除失败")
        )

    except Exception as e:
        logger.error(f"删除会话失败: {e}", exc_info=True)
        return ApiResponse(
            success=False,
            message=f"删除失败: {str(e)}"
        )


@app.post("/api/conversations/{conversation_id}/archive")
async def archive_conversation(
    conversation_id: str,
    user_id: str = Query(..., description="用户ID")
):
    """归档会话"""
    try:
        if conversation_service is None:
            raise HTTPException(status_code=503, detail="会话系统未初始化")

        result = conversation_service.archive_conversation_ui(user_id, conversation_id)

        return ApiResponse(
            success=result["success"],
            message=result.get("message", "归档成功" if result["success"] else "归档失败")
        )

    except Exception as e:
        logger.error(f"归档会话失败: {e}", exc_info=True)
        return ApiResponse(
            success=False,
            message=f"归档失败: {str(e)}"
        )


@app.post("/api/conversations/{conversation_id}/restore")
async def restore_conversation(
    conversation_id: str,
    user_id: str = Query(..., description="用户ID")
):
    """恢复会话（从归档或回收站）"""
    try:
        if conversation_service is None:
            raise HTTPException(status_code=503, detail="会话系统未初始化")

        result = conversation_service.restore_conversation_ui(user_id, conversation_id)

        return ApiResponse(
            success=result["success"],
            message=result.get("message", "恢复成功" if result["success"] else "恢复失败")
        )

    except Exception as e:
        logger.error(f"恢复会话失败: {e}", exc_info=True)
        return ApiResponse(
            success=False,
            message=f"恢复失败: {str(e)}"
        )


class RenameRequest(BaseModel):
    """重命名请求"""
    user_id: str = Field(..., description="用户ID")
    new_title: str = Field(..., description="新标题")


@app.post("/api/conversations/{conversation_id}/rename")
async def rename_conversation(
    conversation_id: str,
    request: RenameRequest
):
    """重命名会话"""
    try:
        if conversation_service is None:
            raise HTTPException(status_code=503, detail="会话系统未初始化")

        result = conversation_service.rename_conversation_ui(
            request.user_id,
            conversation_id,
            request.new_title
        )

        return ApiResponse(
            success=result["success"],
            message=result.get("message", "重命名成功" if result["success"] else "重命名失败")
        )

    except Exception as e:
        logger.error(f"重命名会话失败: {e}", exc_info=True)
        return ApiResponse(
            success=False,
            message=f"重命名失败: {str(e)}"
        )


@app.get("/api/conversations/{conversation_id}/expiration", response_model=ApiResponse)
async def get_conversation_expiration(
    conversation_id: str,
    user_id: str = Query(..., description="用户ID")
):
    """获取会话过期信息（用于回收站显示）"""
    try:
        from core.user_system.conversation_repository import ConversationRepository

        # 使用 ConversationRepository 来查询（因为会话数据存储在 JSON 文件中）
        conv_repo = ConversationRepository()

        # 获取会话信息
        conversation = conv_repo.get_conversation(user_id, conversation_id)
        if not conversation:
            raise HTTPException(status_code=404, detail="会话不存在")

        # 计算过期信息
        from datetime import datetime, timedelta

        # ✅ ConversationModel 是 Pydantic 模型，使用 model_dump() 方法获取数据
        conv_dict = conversation.model_dump() if hasattr(conversation, 'model_dump') else conversation.dict()

        # ✅ status 在 metadata 中
        status = conv_dict.get('metadata', {}).get('status')
        updated_at_str = conv_dict.get('metadata', {}).get('updated_at') or conv_dict.get('metadata', {}).get('created_at')
        deleted_at_str = conv_dict.get('metadata', {}).get('deleted_at')

        # 已删除会话：7天后永久删除
        if status == 'deleted':
            # 如果有 deleted_at 时间，使用它；否则使用 updated_at
            base_time = deleted_at_str or updated_at_str
            if base_time:
                try:
                    base_datetime = datetime.fromisoformat(base_time)
                except:
                    base_datetime = datetime.now()
            else:
                base_datetime = datetime.now()

            # ✅ 计算剩余天数：按照日期计算（忽略时间部分）
            # 删除日期 + 7天 - 当前日期 = 剩余天数
            from datetime import date
            deletion_date = (base_datetime + timedelta(days=7)).date()
            current_date = datetime.now().date()
            days_remaining = max(0, (deletion_date - current_date).days)

            will_be_deleted_on = (base_datetime + timedelta(days=7)).strftime("%Y-%m-%d")

            return ApiResponse(
                success=True,
                message="获取成功",
                data={
                    "conversation_id": conversation_id,
                    "status": "deleted",
                    "days_remaining": days_remaining,
                    "will_be_deleted_on": will_be_deleted_on,
                    "deleted_at": deleted_at_str,
                    "updated_at": updated_at_str
                }
            )
        else:
            # 其他状态不过期
            return ApiResponse(
                success=True,
                message="该会话不在回收站中",
                data={
                    "conversation_id": conversation_id,
                    "status": status,
                    "days_remaining": None,
                    "will_be_deleted_on": None
                }
            )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"获取会话过期信息失败: {e}", exc_info=True)
        return ApiResponse(
            success=False,
            message=f"获取失败: {str(e)}"
        )


# ===================== 地图接口 =====================

@app.post("/api/map/geocode", response_model=GeocodeResponse)
async def geocode_place(request: GeocodeRequest):
    """
    地理编码接口 - 将地址转换为坐标

    输入: 地址或地点名称
    输出: 经纬度坐标和格式化地址
    """
    try:
        if gaode_agent is None:
            return GeocodeResponse(
                success=False,
                error="高德地图服务未初始化"
            )

        # 调用高德地理编码API (MCPClient使用geocoding方法)
        result = await gaode_agent.geocoding(request.address, request.city or "全国")

        if result.get("success") and result.get("geocodes"):
            geocode = result["geocodes"][0]

            # location 是字符串格式 "经度,纬度"，需要解析
            location_str = geocode.get("location", "")
            lng, lat = 0.0, 0.0
            if location_str:
                try:
                    parts = location_str.split(",")
                    if len(parts) == 2:
                        lng = float(parts[0])
                        lat = float(parts[1])
                except ValueError:
                    pass

            return GeocodeResponse(
                success=True,
                address=geocode.get("formatted_address"),
                longitude=lng,
                latitude=lat,
                formatted_address=geocode.get("formatted_address")
            )
        else:
            return GeocodeResponse(
                success=False,
                error=result.get("error", "地理编码失败")
            )

    except Exception as e:
        logger.error(f"地理编码失败: {e}", exc_info=True)
        return GeocodeResponse(
            success=False,
            error=f"地理编码失败: {str(e)}"
        )


@app.post("/api/map/static", response_model=ApiResponse)
async def generate_static_map(request: StaticMapRequest):
    """
    静态地图生成接口

    根据提供的坐标点生成静态地图图片，包含标记和路线
    """
    try:
        if gaode_agent is None:
            return ApiResponse(
                success=False,
                message="高德地图服务未初始化"
            )

        if not request.locations:
            return ApiResponse(
                success=False,
                message="请提供至少一个地点"
            )

        # 计算地图中心（如果未提供）
        center_lng, center_lat = None, None
        if request.center:
            center_lng = request.center.get("lng")
            center_lat = request.center.get("lat")
        elif len(request.locations) >= 1:
            # 使用第一个地点作为中心
            center_lng = request.locations[0].get("lng")
            center_lat = request.locations[0].get("lat")

        # 构建标记点字符串
        markers = []
        for i, loc in enumerate(request.locations):
            name = loc.get("name", "")
            lng = loc.get("lng")
            lat = loc.get("lat")
            if lng and lat:
                # 格式: 经度,纬度;标记样式
                marker_str = f"{lng},{lat};{request.marker_color}"
                markers.append(marker_str)

        # 构建路线字符串（如果需要）
        paths = []
        if request.show_route and len(request.locations) > 1:
            # 连接所有点的路线
            path_coords = ";".join([f"{loc['lng']},{loc['lat']}" for loc in request.locations if loc.get('lng') and loc.get('lat')])
            paths.append(f"{path_coords}:{request.route_color}:5:true")

        # 调用高德静态地图API (MCPClient使用static_map方法)
        result = await gaode_agent.static_map(
            location=f"{center_lng},{center_lat}" if center_lng and center_lat else None,
            zoom=request.zoom,
            size=f"{request.width}*{request.height}",
            markers="|".join(markers) if markers else None,  # 将列表转换为用|连接的字符串
            paths="|".join(paths) if paths else None,  # 将列表转换为用|连接的字符串
            labels=None
        )

        if result.get("success"):
            return ApiResponse(
                success=True,
                message="静态地图生成成功",
                data={
                    "image_url": result.get("map_url"),  # maps_static_map 返回的是 map_url
                    "image_base64": result.get("image_base64"),
                    "locations_count": len(request.locations),
                    "has_route": request.show_route and len(request.locations) > 1,
                    "markers_count": result.get("markers_count", 0),
                    "paths_count": result.get("paths_count", 0)
                }
            )
        else:
            return ApiResponse(
                success=False,
                message=result.get("error", "静态地图生成失败")
            )

    except Exception as e:
        logger.error(f"静态地图生成失败: {e}", exc_info=True)
        return ApiResponse(
            success=False,
            message=f"静态地图生成失败: {str(e)}"
        )


@app.post("/api/map/batch-geocode", response_model=ApiResponse)
async def batch_geocode_places(addresses: List[str], city: Optional[str] = None):
    """
    批量地理编码接口

    一次转换多个地址为坐标
    """
    try:
        if gaode_agent is None:
            return ApiResponse(
                success=False,
                message="高德地图服务未初始化"
            )

        results = []
        for address in addresses:
            if not address or not address.strip():
                continue

            result = await gaode_agent.geocoding(address.strip(), city or "全国")

            if result.get("success") and result.get("geocodes"):
                geocode = result["geocodes"][0]

                # location 是字符串格式 "经度,纬度"，需要解析
                location_str = geocode.get("location", "")
                lng, lat = 0.0, 0.0
                if location_str:
                    try:
                        parts = location_str.split(",")
                        if len(parts) == 2:
                            lng = float(parts[0])
                            lat = float(parts[1])
                    except ValueError:
                        pass

                results.append({
                    "address": address,
                    "longitude": lng,
                    "latitude": lat,
                    "formatted_address": geocode.get("formatted_address"),
                    "success": True
                })
            else:
                results.append({
                    "address": address,
                    "success": False,
                    "error": result.get("error", "地理编码失败")
                })

        return ApiResponse(
            success=True,
            message=f"批量地理编码完成，成功 {sum(1 for r in results if r.get('success'))}/{len(results)}",
            data={
                "results": results,
                "total": len(results),
                "success_count": sum(1 for r in results if r.get('success'))
            }
        )

    except Exception as e:
        logger.error(f"批量地理编码失败: {e}", exc_info=True)
        return ApiResponse(
            success=False,
            message=f"批量地理编码失败: {str(e)}"
        )


# ===================== 新版行程规划接口 (V2) =====================

@app.post("/api/trip/plan-v2", response_model=TripPlanV2Response)
async def plan_trip_v2_endpoint(request: TripPlanV2Request):
    """
    行程规划V2 - 返回结构化JSON数据

    新版智能规划接口，直接返回结构化的行程数据，
    包含POI坐标、路线、时间等完整信息
    """
    global agent_instance, gaode_trip_api

    if agent_instance is None:
        raise HTTPException(status_code=503, detail="Agent系统未初始化")

    try:
        result = await plan_trip_v2(request, agent_instance, gaode_trip_api)

        # ✅ 调试：检查返回数据结构
        logger.info(f"📊 V2 API 返回数据检查:")
        logger.info(f"  - success: {result.success}")
        logger.info(f"  - message: {result.message}")
        logger.info(f"  - itinerary 存在: {result.itinerary is not None}")
        if result.itinerary:
            logger.info(f"  - itinerary.days 长度: {len(result.itinerary.days) if result.itinerary.days else 0}")
            logger.info(f"  - itinerary 数据: {result.itinerary.model_dump() if hasattr(result.itinerary, 'model_dump') else result.itinerary}")

        # 如果成功，可以将行程数据保存到数据库（可选）
        # if result.success and result.itinerary:
        #     await save_itinerary_to_db(result.itinerary)

        return result

    except Exception as e:
        logger.error(f"V2行程规划失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"行程规划失败: {str(e)}")


@app.post("/api/map/batch-geocode-v2", response_model=BatchGeocodeResponse)
async def batch_geocode_v2_endpoint(request: BatchGeocodeRequest):
    """
    批量地理编码V2 - 使用新版API封装

    更高效的批量地理编码接口，支持并发请求
    """
    global gaode_trip_api

    if gaode_trip_api is None:
        return BatchGeocodeResponse(
            success=False,
            city=request.city,
            locations=[],
            total=len(request.addresses),
            failed=len(request.addresses)
        )

    try:
        result = await batch_geocode_api(request, gaode_trip_api)
        return result

    except Exception as e:
        logger.error(f"批量地理编码V2失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"批量地理编码失败: {str(e)}")


# ===================== 文件接口 =====================

@app.get("/api/files/visualizations/{filename}")
async def get_visualization(filename: str):
    """获取可视化文件（地图、图表）"""
    file_path = temp_visualizations_dir / filename
    if file_path.exists():
        return FileResponse(file_path)
    raise HTTPException(status_code=404, detail="文件不存在")


# ===================== 启动服务器 =====================

if __name__ == "__main__":
    print("""
    [启动] 下一站Youth 统一API服务器启动中...

    [地址]
       - 主页: http://localhost:8000/
       - 规划页: http://localhost:8000/planner
       - API文档: http://localhost:8000/docs
       - 管理员界面：http://localhost:8000/admin/login.html

    [提示] 按 Ctrl+C 停止服务器
    """)

    # 提示：关闭自动重载避免频繁检测文件变化
    # 如需修改代码后自动重启，将 reload=False 改为 reload=True
    uvicorn.run(
        "unified_server:app",
        host="0.0.0.0",
        port=8000,
        reload=False,  # 关闭自动重载，避免 user_data/ 等目录频繁变化导致重载
        log_level="info"
    )
