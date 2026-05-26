"""
认证界面模块
包含登录和注册界面组件
"""
import gradio as gr


def create_login_box():
    """
    创建登录/注册界面

    Returns:
        tuple: (login_box, login_username, login_password, login_btn, login_result,
                reg_username, reg_password, reg_confirm_password, reg_email, reg_btn, reg_result)
    """
    with gr.Column(visible=True) as login_box:
        gr.Markdown("# 🎓 大学生穷游助手")
        gr.Markdown("### 💰 预算有限也要看世界！AI帮你规划高性价比学生旅行")
        gr.Markdown("---")

        with gr.Tabs():
            # ========== 登录 Tab ==========
            with gr.Tab("登录"):
                login_username = gr.Textbox(
                    label="用户名",
                    placeholder="请输入用户名"
                )
                login_password = gr.Textbox(
                    label="密码",
                    type="password",
                    placeholder="请输入密码"
                )
                login_btn = gr.Button("登录", variant="primary")
                login_result = gr.Markdown("")

            # ========== 注册 Tab ==========
            with gr.Tab("注册"):
                reg_username = gr.Textbox(
                    label="用户名",
                    placeholder="3-20个字符"
                )
                reg_password = gr.Textbox(
                    label="密码",
                    type="password",
                    placeholder="至少6个字符"
                )
                reg_confirm_password = gr.Textbox(
                    label="确认密码",
                    type="password",
                    placeholder="再次输入密码"
                )
                reg_email = gr.Textbox(
                    label="邮箱（可选）",
                    placeholder="用于找回密码"
                )
                reg_btn = gr.Button("注册", variant="primary")
                reg_result = gr.Markdown("")

    return (
        login_box,
        login_username, login_password, login_btn, login_result,
        reg_username, reg_password, reg_confirm_password, reg_email, reg_btn, reg_result
    )


def get_login_components():
    """
    获取登录界面组件的辅助函数

    用于简化 main_gradio.py 中的组件引用

    Returns:
        dict: 组件字典
    """
    (
        login_box,
        login_username, login_password, login_btn, login_result,
        reg_username, reg_password, reg_confirm_password, reg_email, reg_btn, reg_result
    ) = create_login_box()

    return {
        "login_box": login_box,
        "login_username": login_username,
        "login_password": login_password,
        "login_btn": login_btn,
        "login_result": login_result,
        "reg_username": reg_username,
        "reg_password": reg_password,
        "reg_confirm_password": reg_confirm_password,
        "reg_email": reg_email,
        "reg_btn": reg_btn,
        "reg_result": reg_result
    }
