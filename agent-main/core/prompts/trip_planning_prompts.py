"""
AI提示词生成 - 行程规划（结构化JSON版本）
===========================================
生成新的智能规划API所需的结构化JSON输出
"""
from typing import List, Optional, Dict, Any


def get_structured_trip_prompt(
    destination: str,
    start_date: str,
    end_date: str,
    days_count: int,
    preferences: List[str],
    budget: Optional[float],
    travelers: int = 1,
    user_requirements: Optional[str] = None
) -> str:
    """
    生成结构化JSON输出的行程规划提示词

    Args:
        destination: 目的地
        start_date: 开始日期 (YYYY-MM-DD)
        end_date: 结束日期 (YYYY-MM-DD)
        days_count: 天数
        preferences: 用户偏好列表
        budget: 预算（元）
        travelers: 旅行人数
        user_requirements: 其他要求

    Returns:
        str: AI提示词
    """

    # 计算每日预算
    daily_budget = int(budget / days_count) if budget else None
    budget_text = f"总预算: {budget}元 (约{daily_budget}元/天)" if budget else "未设预算限制"

    prompt = f"""你是一个专业的旅行规划助手。请为用户生成一个结构化的JSON格式的{destination}旅行计划。

## 旅行信息
- 目的地: {destination}
- 旅行日期: {start_date} 至 {end_date} (共{days_count}天)
- 旅行人数: {travelers}人
- {budget_text}
- 用户偏好: {', '.join(preferences) if preferences else '无特定偏好'}
- 其他要求: {user_requirements if user_requirements else '无'}

## ⚠️ 关键约束 - 数据准确性要求

### 1. POI坐标数据要求
   - ✅ **必须字段**: lng（经度）、lat（纬度）
   - ✅ **数据类型**: 必须是浮点数，不是字符串
   - ✅ **格式示例**: "lng": 116.397428, "lat": 39.90923
   - ❌ **禁止**: 使用字符串 "116.397428,39.90923"
   - ❌ **禁止**: 编造不存在的坐标

### 2. 地址数据要求
   - ✅ **推荐**: 使用真实的POI地址
   - ✅ **格式**: 省市区街道门牌号
   - ❌ **禁止**: 仅写"市中心"、"市区"等模糊地址

### 3. 坐标获取指南
   如果不确定某个景点的准确坐标：
   - ✅ 优先使用知名景点的标准坐标（可从公开数据获取）
   - ✅ 如果坐标不确定，设置为 null（而不是 0 或编造值）
   - ❌ **禁止**: 随意生成坐标

### 4. 数据真实性要求
   - ✅ **推荐**: 使用真实的POI名称和地址
   - ✅ **推荐**: 参考实际的开放时间
   - ❌ **禁止**: 编造不存在的景点
   - ❌ **禁止**: 提供虚假的门票价格

## 输出要求

**最关键的要求**: 请只输出一个完整的JSON对象，格式如下：

1. **最外层必须是一个大括号 {{}} 包围的对象**
2. **不要返回数组**
3. **所有字段都在这个对象内**
4. **不要在JSON后面添加额外的数组**

正确的输出格式示例：
```json
{{
    "destination": "{destination}",
    "start_date": "{start_date}",
    "end_date": "{end_date}",
    "total_days": {days_count},
    "estimated_total_cost": {budget or 0},
    "days": [
        {{
            "day": 1,
            "date": "{start_date}",
            "pois": [
                {{
                    "id": "poi_1_1",
                    "name": "景点名称",
                    "lng": 116.397428,  // ← 浮点数
                    "lat": 39.90923,   // ← 浮点数
                    "address": "详细地址",
                    "start_time": "09:00",
                    "end_time": "11:00",
                    "duration": 120,
                    "order": 1,
                    "image_url": null,
                    "description": "景点简介",
                    "category": "景点",
                    "cost": 50,
                    "ticket_price": 50,
                    "notes": "备注信息",
                    "rating": 4.8,
                    "tags": ["经典打卡"]
                }}
            ],
            "route_color": "#10B981",
            "total_cost": 130,
            "day_summary": "当天行程总结",
            "tips": ["提示1", "提示2"]
        }}
    ],
    "recommendations": ["建议1", "建议2", "建议3"]
}}
```

## 规划要点

1. **时间安排**: 每天安排3-5个POI，合理分配时间
2. **地理位置**: 按地理位置就近安排，减少路程时间
3. **预算控制**: {f'每日预算约{daily_budget}元' if daily_budget else '注意控制成本'}
4. **坐标准确**: 尽量提供准确的经纬度坐标
5. **时间格式**: 使用24小时制，如 09:00、14:30
6. **费用估算**: 合理估算每个POI的花费

请直接输出JSON数据，不要包含任何其他说明文字。"""

    return prompt


def parse_json_from_ai_response(response_text: str) -> Optional[Dict[str, Any]]:
    """
    从AI响应中解析JSON数据

    Args:
        response_text: AI返回的原始文本

    Returns:
        解析后的JSON字典，失败返回None
    """
    import json
    import re

    # 尝试1: 直接解析
    try:
        return json.loads(response_text)
    except json.JSONDecodeError:
        pass

    # 尝试2: 提取JSON代码块
    json_pattern = r'```json\s*(.*?)\s*```'
    matches = re.findall(json_pattern, response_text, re.DOTALL)
    if matches:
        try:
            return json.loads(matches[0])
        except json.JSONDecodeError:
            pass

    # 尝试3: 提取完整JSON对象（处理额外数据）
    # 找到第一个 { 和匹配的 }
    first_brace = response_text.find('{')
    if first_brace != -1:
        # 使用栈来找到匹配的闭合大括号
        brace_count = 0
        in_string = False
        escape_next = False
        i = first_brace

        while i < len(response_text):
            char = response_text[i]

            if escape_next:
                escape_next = False
            elif char == '\\':
                escape_next = True
            elif char == '"':
                in_string = not in_string
            elif not in_string:
                if char == '{':
                    brace_count += 1
                elif char == '}':
                    brace_count -= 1
                    if brace_count == 0:
                        # 找到完整的JSON对象
                        json_str = response_text[first_brace:i + 1]
                        try:
                            return json.loads(json_str)
                        except json.JSONDecodeError:
                            break
            i += 1

    # 尝试4: 清理常见问题后重试
    cleaned = response_text.strip()
    # 移除markdown代码块标记
    cleaned = re.sub(r'```(json)?\s*', '', cleaned)
    cleaned = re.sub(r'\s*```\s*', '', cleaned)

    # 移除可能的尾随数组（如独立的recommendations数组）
    # 查找最后一个}，并移除之后的所有内容
    last_brace = cleaned.rfind('}')
    if last_brace != -1:
        # 检查}后面是否有非空白字符（除了可能的逗号和空白）
        remaining = cleaned[last_brace + 1:].strip()
        if remaining and remaining.startswith('['):
            # 删除尾随的数组
            cleaned = cleaned[:last_brace + 1]

    first_brace = cleaned.find('{')
    last_brace = cleaned.rfind('}')
    if first_brace != -1 and last_brace != -1:
        cleaned = cleaned[first_brace:last_brace + 1]
        try:
            return json.loads(cleaned)
        except json.JSONDecodeError:
            pass

    return None
