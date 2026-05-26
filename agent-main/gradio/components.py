"""
UI 组件库
包含可复用的 Gradio 组件构建函数
"""
import gradio as gr
from datetime import datetime, timedelta


def create_date_inputs():
    """创建日期选择组件"""
    with gr.Row():
        start_date = gr.Textbox(
            label="开始日期",
            placeholder="",
            value=(datetime.now() + timedelta(days=7)).strftime("%Y-%m-%d")
        )
        end_date = gr.Textbox(
            label="结束日期",
            placeholder="",
            value=(datetime.now() + timedelta(days=10)).strftime("%Y-%m-%d")
        )
    return start_date, end_date


def create_destination_input():
    """创建目的地输入组件"""
    destination = gr.Textbox(
        label="📍 想去哪个城市？",
        placeholder="例如：北京、上海、西安、成都、重庆...",
        info="推荐学生友好型城市：西安、成都、重庆、长沙、武汉"
    )
    return destination


def create_preference_checkboxes():
    """创建旅行偏好复选框组件"""
    gr.Markdown("#### 🎯 选择你的旅行风格（最多选3个）")

    preference_count_label = gr.Textbox(
        label="已选择数量",
        value="已选择0个偏好",
        interactive=False,
        scale=1
    )

    with gr.Row():
        with gr.Column(scale=1):
            classic_pref = gr.Checkbox(label="🎓 经典打卡", value=False, elem_classes="preference-checkbox")
            food_pref = gr.Checkbox(label="🍜 平价美食", value=False, elem_classes="preference-checkbox")
            niche_pref = gr.Checkbox(label="🆓 免费景点", value=False, elem_classes="preference-checkbox")
            culture_pref = gr.Checkbox(label="📚 文化探索", value=False, elem_classes="preference-checkbox")

        with gr.Column(scale=1):
            nature_pref = gr.Checkbox(label="🏔️ 自然风光", value=False, elem_classes="preference-checkbox")
            photo_pref = gr.Checkbox(label="📸 拍照圣地", value=False, elem_classes="preference-checkbox")
            nightlife_pref = gr.Checkbox(label="🌙 夜生活", value=False, elem_classes="preference-checkbox")
            adventure_pref = gr.Checkbox(label="🚲 青春冒险", value=False, elem_classes="preference-checkbox")

        with gr.Column(scale=1):
            shopping_pref = gr.Checkbox(label="🛍️ 淘货逛街", value=False, elem_classes="preference-checkbox")
            social_pref = gr.Checkbox(label="👥 社交交友", value=False, elem_classes="preference-checkbox")

    checkboxes = [
        classic_pref, food_pref, niche_pref, culture_pref,
        nature_pref, photo_pref, nightlife_pref, adventure_pref,
        shopping_pref, social_pref
    ]

    return preference_count_label, checkboxes


def create_budget_input():
    """创建预算输入组件"""
    budget = gr.Textbox(
        label="💰 总预算（元）",
        placeholder="建议：2-3天500-1000元，5-7天1500-2500元",
        value="1500",
        info="💡 包括交通、住宿、餐饮、门票等所有费用"
    )
    return budget


def create_requirements_input():
    """创建额外需求输入组件"""
    user_requirements = gr.Textbox(
        label="💬 其他要求（选填）",
        placeholder="例如：想去特定景点、几个人一起、有没有忌口等...",
        lines=3
    )
    return user_requirements


def create_submit_button():
    """创建表单提交按钮"""
    submit_btn = gr.Button("🚀 开始规划我的穷游之旅", variant="primary", size="lg")
    return submit_btn


def create_result_display():
    """创建结果展示区域"""
    gr.Markdown("### 📋 你的专属穷游攻略")

    time_display = gr.Textbox(
        label="⏱️ 生成耗时",
        value="等待生成...",
        interactive=False,
        visible=True
    )

    plan_output = gr.Markdown(
        label="穷游攻略",
        value="✨ **在这里填写你的旅行计划，AI将为你生成超详细的穷游攻略！**\n\n📋 包含内容：\n- 📅 每日行程安排\n- 🎓 学生优惠景点\n- 🍜 平价美食推荐\n- 🏠 青年旅舍推荐\n- 💰 费用明细（控制在预算内）\n- 🗺️ 交互式地图",
        visible=True
    )

    with gr.Row():
        form_map_display = gr.HTML(label="地图展示", visible=False, elem_id="form_map_display")
        form_img_display = gr.Gallery(label="图片预览", visible=False, columns=3, height=200)

    show_map_btn = gr.Button("🗺️ 查看交互式地图", variant="secondary", visible=False)

    return time_display, plan_output, form_map_display, form_img_display, show_map_btn


def create_chat_tab():
    """创建自由问答Tab组件"""
    with gr.Tab("💬 自由问答"):
        gr.Markdown("### 💭 想问什么就问什么")
        gr.Markdown("💡 **提示**: 可以问：\"成都有哪些免费的景点？\" \"学生证有什么优惠？\" \"如何在500元内游西安？\"")

        chatbot = gr.Chatbot(label="聊天窗口", elem_id="chatbot")

        with gr.Row():
            chat_map_display = gr.HTML(label="地图展示", visible=False, elem_id="chat_map_display")
            chat_img_display = gr.Gallery(label="图片预览", visible=False, columns=3, height=200)

        with gr.Row():
            deep_thinking_toggle = gr.Checkbox(
                label="🧠 启用深度思考模式",
                value=True,
                info="开启后使用更强的模型进行深度推理"
            )

        with gr.Row():
            user_input = gr.Textbox(placeholder="比如：西安3天2夜怎么安排最省钱？...", lines=1, scale=8)
            send_btn = gr.Button("发送", scale=1, variant="primary")

    return chatbot, chat_map_display, chat_img_display, deep_thinking_toggle, user_input, send_btn


def create_conversation_sidebar():
    """创建会话列表侧边栏"""
    with gr.Column(scale=1):
        gr.Markdown("### 📚 我的旅行计划")

        # 新建会话按钮
        new_plan_btn = gr.Button("➕ 新建计划", variant="primary")

        # 会话列表
        conversation_list = gr.Radio(
            choices=[],
            label="选择历史计划",
            value=None,
            interactive=True
        )

        # 配额显示
        quota_display = gr.Markdown("💾 **0/10** 个活跃计划")

        # 会话操作按钮
        with gr.Row():
            rename_input = gr.Textbox(
                placeholder="新标题",
                scale=3,
                visible=False
            )
            rename_btn = gr.Button("✏️ 重命名", variant="secondary", size="sm")
            delete_btn = gr.Button("🗑️ 删除", variant="stop", size="sm")

    return new_plan_btn, conversation_list, quota_display, rename_input, rename_btn, delete_btn


def create_header():
    """创建页面头部"""
    with gr.Row():
        gr.Markdown("### 🎓 大学生穷游助手")
        user_info_display = gr.Markdown("")
        logout_btn = gr.Button("登出", size="sm")

    gr.Markdown("---")

    return user_info_display, logout_btn


def create_current_trip_info():
    """创建当前会话信息显示"""
    current_trip_info = gr.Markdown("### 📍 当前计划：新建旅行")
    return current_trip_info


def create_auth_message():
    """创建认证消息显示"""
    auth_message = gr.Markdown("", visible=True)
    return auth_message


def create_global_states():
    """创建全局状态变量"""
    user_id = gr.State("")
    session_token = gr.State("")
    conversation_id = gr.State("")  # 当前会话ID
    chat_history = gr.State([])
    current_map = gr.State()
    current_map_path = gr.State("")
    current_images = gr.State([])
    selected_preferences = gr.State([])

    return (
        user_id, session_token, conversation_id,
        chat_history, current_map, current_map_path,
        current_images, selected_preferences
    )
