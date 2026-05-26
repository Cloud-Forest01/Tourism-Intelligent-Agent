"""
config.py - 项目统一配置管理
================================
说明：
- 集中管理所有API密钥和配置参数
- 环境变量从 .env 文件加载（仅加载一次）
- 提供全局单例访问

使用方法：
    from config import Config
    api_key = Config.DASHSCOPE_API_KEY
"""
import os
import sys
from pathlib import Path
from typing import Optional
from dotenv import load_dotenv

# ==================== 环境变量加载 ====================
# 获取项目根目录
PROJECT_ROOT = Path(__file__).parent.resolve()
ENV_FILE = PROJECT_ROOT / '.env'

# 加载 .env 文件（仅加载一次）
if ENV_FILE.exists():
    load_dotenv(ENV_FILE, override=False)
else:
    print(f"[警告] .env 文件不存在: {ENV_FILE}")
    print(f"[提示] 请创建 .env 文件并配置API密钥")


# ==================== 配置类 ====================
class Config:
    """
    全局配置类
    所有配置属性在首次访问时从环境变量读取
    """

    # ==================== AI 提供商配置 ====================
    # AI 提供商选择 (qwen, openai, deepseek, anthropic, zhipu)
    AI_PROVIDER: str = os.getenv("AI_PROVIDER", "qwen").lower()

    # ==================== 通义千问 API ====================
    DASHSCOPE_API_KEY: str = os.getenv("DASHSCOPE_API_KEY", "")
    QWEN_BASE_URL: str = "https://dashscope.aliyuncs.com/compatible-mode/v1"
    QWEN_MODEL_FAST: str = os.getenv("QWEN_MODEL_FAST")    # 快速模式（日常对话）
    QWEN_MODEL_DEEP: str = os.getenv("QWEN_MODEL_DEEP")     # 深度思考模式（复杂任务）

    # ==================== 高德地图 API ====================
    # Web 服务 API 密钥（用于后端调用 REST API）
    GAODE_REST_API_KEY: str = os.getenv("GAODE_REST_API_KEY", "")

    # Web 端 JS API 密钥（用于前端显示地图）
    GAODE_JS_API_KEY: str = os.getenv("GAODE_API_KEY", "")

    # 兼容旧代码（如果 GAODE_REST_API_KEY 未设置，尝试使用 GAODE_API_KEY）
    @property
    def GAODE_API_KEY(self) -> str:
        """
        获取高德 Web 服务 API 密钥

        优先使用 GAODE_REST_API_KEY，如果未设置则回退到 GAODE_API_KEY
        """
        return self.GAODE_REST_API_KEY or os.getenv("GAODE_API_KEY", "")

    GAODE_BASE_URL_V3: str = "https://restapi.amap.com/v3"
    GAODE_BASE_URL_V5: str = "https://restapi.amap.com/v5"

    # ==================== Tavily 搜索 API ====================
    TAVILY_API_KEY: str = os.getenv("TAVILY_API_KEY", "")
    TAVILY_BASE_URL: str = "https://api.tavily.com"

    # ==================== OpenAI API ====================
    OPENAI_API_KEY: str = os.getenv("OPENAI_API_KEY", "")
    OPENAI_BASE_URL: str = os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1")
    OPENAI_MODEL_FAST: str = os.getenv("OPENAI_MODEL_FAST", "gpt-3.5-turbo")
    OPENAI_MODEL_DEEP: str = os.getenv("OPENAI_MODEL_DEEP", "gpt-4-turbo")

    # ==================== DeepSeek API ====================
    DEEPSEEK_API_KEY: str = os.getenv("DEEPSEEK_API_KEY", "")
    DEEPSEEK_BASE_URL: str = "https://api.deepseek.com/v1"
    DEEPSEEK_MODEL_FAST: str = "deepseek-chat"
    DEEPSEEK_MODEL_DEEP: str = "deepseek-reasoner"

    # ==================== Anthropic Claude API ====================
    ANTHROPIC_API_KEY: str = os.getenv("ANTHROPIC_API_KEY", "")
    ANTHROPIC_BASE_URL: str = os.getenv("ANTHROPIC_BASE_URL", "https://api.anthropic.com/v1")
    ANTHROPIC_MODEL_FAST: str = os.getenv("ANTHROPIC_MODEL_FAST", "claude-3-haiku-20240307")
    ANTHROPIC_MODEL_DEEP: str = os.getenv("ANTHROPIC_MODEL_DEEP", "claude-3-opus-20240229")

    # ==================== 智谱AI API ====================
    ZHIPU_API_KEY: str = os.getenv("ZHIPU_API_KEY", "")
    ZHIPU_BASE_URL: str = "https://open.bigmodel.cn/api/paas/v4"
    ZHIPU_MODEL_FAST: str = os.getenv("ZHIPU_MODEL_FAST", "glm-4-flash")
    ZHIPU_MODEL_DEEP: str = os.getenv("ZHIPU_MODEL_DEEP", "glm-4-plus")

    # ==================== Unsplash API（可选）====================
    UNSPLASH_ACCESS_KEY: Optional[str] = os.getenv("UNSPLASH_ACCESS_KEY")
    UNSPLASH_BASE_URL: str = "https://api.unsplash.com/search/photos"

    # ==================== 其他配置 ====================
    LOG_LEVEL: str = os.getenv("LOG_LEVEL", "INFO")
    GRADIO_PORT: int = int(os.getenv("GRADIO_PORT", "7860"))
    GRADIO_SERVER_NAME: str = os.getenv("GRADIO_SERVER_NAME", "0.0.0.0")

    # ==================== 类方法 ====================

    @classmethod
    def validate_required_keys(cls) -> tuple[bool, list[str]]:
        """
        验证必需的API密钥是否已配置

        Returns:
            tuple[bool, list[str]]: (是否全部配置, 缺失的密钥列表)
        """
        required_keys = {
            'DASHSCOPE_API_KEY': cls.DASHSCOPE_API_KEY,
            'TAVILY_API_KEY': cls.TAVILY_API_KEY,
            'GAODE_REST_API_KEY': cls.GAODE_REST_API_KEY  # 后端 REST API 密钥
        }

        missing = [key for key, value in required_keys.items() if not value]

        return len(missing) == 0, missing

    @classmethod
    def get_ai_config(cls, provider: str = None) -> dict:
        """
        获取指定AI提供商的配置

        Args:
            provider: AI提供商名称 (qwen, openai, deepseek, anthropic)
                     如果为None，则使用 AI_PROVIDER 配置

        Returns:
            dict: {
                "provider": "qwen",
                "api_key": "sk-xxx",
                "base_url": "https://...",
                "model_fast": "qwen3-max-2026-01-23",
                "model_deep": "qwen3-max-2026-01-23"
            }
        """
        provider = provider or cls.AI_PROVIDER
        provider = provider.lower()

        configs = {
            "qwen": {
                "provider": "qwen",
                "api_key": cls.DASHSCOPE_API_KEY,
                "base_url": cls.QWEN_BASE_URL,
                "model_fast": cls.QWEN_MODEL_FAST,
                "model_deep": cls.QWEN_MODEL_DEEP
            },
            "openai": {
                "provider": "openai",
                "api_key": cls.OPENAI_API_KEY,
                "base_url": cls.OPENAI_BASE_URL,
                "model_fast": cls.OPENAI_MODEL_FAST,
                "model_deep": cls.OPENAI_MODEL_DEEP
            },
            "deepseek": {
                "provider": "deepseek",
                "api_key": cls.DEEPSEEK_API_KEY,
                "base_url": cls.DEEPSEEK_BASE_URL,
                "model_fast": cls.DEEPSEEK_MODEL_FAST,
                "model_deep": cls.DEEPSEEK_MODEL_DEEP
            },
            "anthropic": {
                "provider": "anthropic",
                "api_key": cls.ANTHROPIC_API_KEY,
                "base_url": cls.ANTHROPIC_BASE_URL,
                "model_fast": cls.ANTHROPIC_MODEL_FAST,
                "model_deep": cls.ANTHROPIC_MODEL_DEEP
            },
            "zhipu": {
                "provider": "zhipu",
                "api_key": cls.ZHIPU_API_KEY,
                "base_url": cls.ZHIPU_BASE_URL,
                "model_fast": cls.ZHIPU_MODEL_FAST,
                "model_deep": cls.ZHIPU_MODEL_DEEP
            }
        }

        if provider not in configs:
            raise ValueError(f"不支持的AI提供商: {provider}，请从以下选择: {list(configs.keys())}")

        config = configs[provider]

        # 验证API密钥是否存在
        if not config["api_key"]:
            raise ValueError(f"AI提供商 '{provider}' 的API密钥未配置，请在 .env 文件中设置相应的 API_KEY")

        return config

    @classmethod
    def get_qwen_model(cls, mode: str = "fast") -> str:
        """
        获取通义千问模型名称（保留向后兼容）

        Args:
            mode: 模型模式
                - "fast": 快速模式（qwen3-max-2026-01-23）
                - "deep": 深度思考模式（qwen3-max-2026-01-23）

        Returns:
            str: 模型名称
        """
        return cls.QWEN_MODEL_DEEP if mode == "deep" else cls.QWEN_MODEL_FAST

    @classmethod
    def get_model_name(cls, mode: str = "fast", provider: str = None) -> str:
        """
        获取指定提供商的模型名称

        Args:
            mode: 模型模式 ("fast" 或 "deep")
            provider: AI提供商，默认使用 AI_PROVIDER 配置

        Returns:
            str: 模型名称
        """
        config = cls.get_ai_config(provider)
        return config["model_deep"] if mode == "deep" else config["model_fast"]

    @classmethod
    def print_config_status(cls):
        """打印配置状态（用于调试）"""
        print("\n" + "=" * 60)
        print("配置状态检查")
        print("=" * 60)

        # 检查必需密钥
        all_ok, missing = cls.validate_required_keys()

        if all_ok:
            print("[OK] 所有必需的API密钥已配置")
        else:
            print("[X] 缺少必需的API密钥:")
            for key in missing:
                print(f"   - {key}")

        print()
        print("AI提供商配置:")
        print(f"  当前AI提供商: {cls.AI_PROVIDER.upper()}")
        print(f"  通义千问: {'[OK]' if cls.DASHSCOPE_API_KEY else '[X]'}")
        print(f"  OpenAI: {'[OK]' if cls.OPENAI_API_KEY else '[_] 未配置'}")
        print(f"  DeepSeek: {'[OK]' if cls.DEEPSEEK_API_KEY else '[_] 未配置'}")
        print(f"  Anthropic: {'[OK]' if cls.ANTHROPIC_API_KEY else '[_] 未配置'}")
        print(f"  智谱AI: {'[OK]' if cls.ZHIPU_API_KEY else '[_] 未配置'}")
        print()
        print("其他配置:")
        print(f"  高德地图: {'[OK]' if cls.GAODE_API_KEY else '[X]'}")
        print(f"  Tavily搜索: {'[OK]' if cls.TAVILY_API_KEY else '[X]'}")
        print(f"  Unsplash: {'[OK]' if cls.UNSPLASH_ACCESS_KEY else '[_] 未配置（可选）'}")
        print("=" * 60 + "\n")


# ==================== 模块导入时验证 ====================
# 当模块被导入时，自动检查配置
if __name__ != "__main__":
    Config.print_config_status()

