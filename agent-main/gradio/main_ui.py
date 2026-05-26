"""
主界面模块
包含登录后的主应用界面
"""
import gradio as gr
from .components import (
    create_header,
    create_conversation_sidebar,
    create_current_trip_info,
    create_date_inputs,
    create_destination_input,
    create_preference_checkboxes,
    create_budget_input,
    create_requirements_input,
    create_submit_button,
    create_result_display,
    create_chat_tab
)


def create_main_box():
    """
    创建主界面容器

    Returns:
        tuple: (main_box, user_info_display, logout_btn, current_trip_info,
                new_plan_btn, conversation_list, quota_display,
                rename_input, rename_btn, delete_btn,
                start_date, end_date, destination,
                preference_count_label, preference_checkboxes,
                budget, user_requirements, submit_form_btn,
                time_display, plan_output, form_map_display, form_img_display, show_map_btn,
                chatbot, chat_map_display, chat_img_display, deep_thinking_toggle,
                user_input, send_btn)
    """
    with gr.Column(visible=False) as main_box:

        # ========== 顶部导航栏 ==========
        user_info_display, logout_btn = create_header()

        # ========== 主布局 ==========
        with gr.Row():
            # ========== 左侧：会话列表 ==========
            (
                new_plan_btn,
                conversation_list,
                quota_display,
                rename_input,
                rename_btn,
                delete_btn
            ) = create_conversation_sidebar()

            # ========== 右侧：主要内容区域 ==========
            with gr.Column(scale=4):
                # 当前会话信息
                current_trip_info = create_current_trip_info()

                # Tab：表单规划 / 自由问答
                with gr.Tabs():
                    # ========== 表单规划 Tab ==========
                    with gr.Tab("📝 表单规划"):
                        form_components = create_form_planning_tab()

                        (
                            start_date, end_date, destination,
                            preference_count_label, preference_checkboxes,
                            budget, user_requirements, submit_form_btn,
                            time_display, plan_output,
                            form_map_display, form_img_display, show_map_btn
                        ) = form_components

                    # ========== 自由问答 Tab ==========
                    (
                        chatbot, chat_map_display, chat_img_display,
                        deep_thinking_toggle, user_input, send_btn
                    ) = create_chat_tab()

    return (
        main_box, user_info_display, logout_btn, current_trip_info,
        new_plan_btn, conversation_list, quota_display,
        rename_input, rename_btn, delete_btn,
        start_date, end_date, destination,
        preference_count_label, preference_checkboxes,
        budget, user_requirements, submit_form_btn,
        time_display, plan_output, form_map_display, form_img_display, show_map_btn,
        chatbot, chat_map_display, chat_img_display, deep_thinking_toggle,
        user_input, send_btn
    )


def create_form_planning_tab():
    """
    创建表单规划Tab的内容

    Returns:
        tuple: 所有表单组件
    """
    with gr.Row():
        with gr.Column(scale=2):
            gr.Markdown("### ✏️ 填写你的穷游计划")

            # 日期选择
            start_date, end_date = create_date_inputs()

            # 目的地
            destination = create_destination_input()

            # 旅游偏好
            preference_count_label, preference_checkboxes = create_preference_checkboxes()

            # 预算
            budget = create_budget_input()

            # 额外需求
            user_requirements = create_requirements_input()

            # 提交按钮
            submit_form_btn = create_submit_button()

        with gr.Column(scale=3):
            # 结果展示
            (
                time_display, plan_output,
                form_map_display, form_img_display, show_map_btn
            ) = create_result_display()

    return (
        start_date, end_date, destination,
        preference_count_label, preference_checkboxes,
        budget, user_requirements, submit_form_btn,
        time_display, plan_output,
        form_map_display, form_img_display, show_map_btn
    )


def create_footer():
    """创建页面底部信息"""
    gr.Markdown("---")
    gr.Markdown("""
    ### 🎓 穷游小贴士

    💰 **省钱技巧**：
    - 🎫 学生证半价：大部分景点学生票5折
    - 🏠 青年旅舍：50-100元/晚，还能认识新朋友
    - 🍜 街边小吃：人均20-30元吃得超满足
    - 🚇 公共交通：地铁+公交+共享单车，出行成本低
    - 🆓 免费景点：公园、博物馆免费日、城市漫步

    📱 **必备APP**：
    - 12306（火车票）、飞猪/携程（比价）
    - 大众点评（找美食）、高德地图（导航）
    - 穷游/马蜂窝（攻略）、小红书（种草）

    ⚠️ **注意**：本AI助手仅供参考，具体费用请以实际情况为准
    """)
