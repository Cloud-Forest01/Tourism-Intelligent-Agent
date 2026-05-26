# agent_tools/tools.py
from pydantic import BaseModel, SecretStr
import os
import sys
from pathlib import Path
import tempfile
import subprocess
import re
import logging
import json
import hashlib  # ✅ 添加 hashlib 模块
from typing import List, Dict, Any, Optional, Tuple, Union
from pathlib import Path
import uuid
import httpx
from datetime import datetime

# 导入API配置
# 添加项目根目录到系统路径
project_root = Path(__file__).resolve().parent.parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))
from config import Config

# ✅ 使用相对导入，因为此文件在 chat_agent_qwen 包内部
from ..agent_mcp.agent_mcp_gaode import MCPClient
import asyncio
from .Tavilysearch_tool import tavily_search_and_summarize
from tavily import TavilyClient  # 同步客户端
from jinja2 import Template
from ..utils.security import SecureFileManager, CodeSecurityChecker, SecurityError
from ..agent_memory.memory import MemoryManager
import html

# 设置日志
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)
import asyncio
import json
from typing import List, Dict, Any
from pydantic import BaseModel
import logging

logger = logging.getLogger(__name__)

# ======================
# Tools 模块
# ======================
class ToolParameter(BaseModel):
    name: str
    type: str
    description: str
    required: bool = True

class BaseTool:
    def __init__(self, name: str, description: str):
        self.name = name
        self.description = description
        self.parameters = self.define_parameters()
    
    def define_parameters(self) -> List[ToolParameter]:
        """定义工具参数（子类实现）"""
        return []
    
    def validate_parameters(self, params: Dict[str, Any]) -> bool:
        """验证参数是否符合要求"""
        for param in self.parameters:
            if param.required and param.name not in params:
                return False
            if param.name in params:
                try:
                    if param.type == "str":
                        params[param.name] = str(params[param.name])
                    elif param.type == "int":
                        params[param.name] = int(params[param.name])
                    elif param.type == "bool":
                        params[param.name] = bool(params[param.name])
                except ValueError:
                    return False
        return True
    
    def execute(self, params: Dict[str, Any]) -> Any:
        """执行工具（子类实现）"""
        raise NotImplementedError("工具执行方法必须由子类实现")
    
    def format_result(self, raw_result: Any) -> str:
        """将工具的原始返回值格式化为用户友好的字符串
        
        Args:
            raw_result: 工具的原始返回值
            
        Returns:
            格式化后的字符串（用于最终展示给用户）
        """
        # ✅ 如果是字典，使用JSON格式化提高可读性
        if isinstance(raw_result, dict):
            try:
                return json.dumps(raw_result, ensure_ascii=False, indent=2)
            except (TypeError, ValueError):
                return str(raw_result)
        return str(raw_result)


# --- Tavily 网络搜索工具管理器 ---
class TavilySearchTool(BaseTool):
    def __init__(self):
        super().__init__(
            name="web_search",
            description="使用 Tavily 实时搜索引擎查询最新网络信息，并返回 AI 生成的摘要和关键结果。适用于查询景点信息、开放时间、门票价格、新闻事件、技术趋势等。输入应为自然语言问题，例如“2025年人工智能发展趋势有哪些？”"
        )
        # ✅ 从 API_FROM 读取 API 密钥
        api_key = Config.TAVILY_API_KEY
        self.client = TavilyClient(api_key=api_key)

    def define_parameters(self) -> List[ToolParameter]:
        return [
            ToolParameter(
                name="query",
                type="str",
                description="要搜索的自然语言问题，例如“2025年云南旅游推荐”",
                required=True
            )
        ]

    async def arun(self, **params: Dict[str, Any]) -> Dict[str, Any]:
        """异步执行方法（推荐使用）"""
        query = params.get("query")
        if not query or not isinstance(query, str) or not query.strip():
            return {"error": "web_search 工具需要提供有效的 'query' 参数"}

        try:
            response = self.client.search(
                query=query.strip(),
                search_depth="advanced",
                include_answer=True,
                include_images=True,
                max_results=5,
                days=30
            )
            # ✅ 增强：尽可能提取图片 URL（兼容多种响应结构）
            if isinstance(response, dict):
                images_top = response.get("images", [])
                results = response.get("results", []) or []

                extracted: List[str] = []

                # 1) 顶层 images：可能是字符串 URL 列表，或对象列表
                if isinstance(images_top, list):
                    for img in images_top:
                        if isinstance(img, str):
                            extracted.append(img)
                        elif isinstance(img, dict):
                            url = img.get("url") or img.get("image_url") or img.get("link")
                            if isinstance(url, str):
                                extracted.append(url)

                # 2) results[*].images / image_urls / 以及内容中的图片链接
                img_url_regex = re.compile(r'https?://[^\s\'"<>]+?\.(?:jpg|jpeg|png|gif|webp)\b', re.IGNORECASE)
                if isinstance(results, list):
                    for item in results[:10]:  # 限前10条以控复杂度
                        if not isinstance(item, dict):
                            continue
                        imgs = item.get("images") or item.get("image_urls") or []
                        if isinstance(imgs, list):
                            for img in imgs:
                                if isinstance(img, str):
                                    extracted.append(img)
                                elif isinstance(img, dict):
                                    url = img.get("url") or img.get("image_url") or img.get("link")
                                    if isinstance(url, str):
                                        extracted.append(url)
                        # 从文本字段中正则提取潜在图片 URL
                        for field in ("content", "snippet", "url", "title", "description"):
                            val = item.get(field)
                            if isinstance(val, str):
                                extracted.extend(img_url_regex.findall(val))

                # 3) 去重与裁剪
                dedup: List[str] = []
                seen = set()
                for u in extracted:
                    us = u.strip()
                    if us and us not in seen:
                        seen.add(us)
                        dedup.append(us)

                image_urls = dedup[:10]

                logger.info(f"Tavily web_search: 提取到图片URL数量={len(image_urls)} for query='{query[:40]}...' ")
                if len(image_urls) == 0:
                    logger.warning("Tavily web_search: 未从响应中提取到图片URL，建议调整查询词（例如加上 '高清 图片'）")

                return {
                    "answer": (response.get("answer", "") or "").strip(),
                    "results": results[:5],
                    "images": images_top[:5] if isinstance(images_top, list) else [],
                    "image_urls": image_urls
                }
            # 如果不是 dict，直接字符串化返回
            return {"answer": str(response), "image_urls": []}
        except Exception as e:
            return {"error": f"搜索失败: {str(e)}"}

    def execute(self, params: Dict[str, Any]) -> str:
        """同步执行方法（兼容旧代码）"""
        result = asyncio.run(self.arun(**params))
        return self.format_result(result)
    
    def format_result(self, raw_result: Any) -> str:
        if isinstance(raw_result, dict):
            # 如果有错误，直接返回
            if "error" in raw_result:
                return raw_result["error"]
            
            answer = raw_result.get("answer", "").strip()
            image_urls = raw_result.get("image_urls", [])
            
            # 构建格式化输出
            result_parts = []
            if answer:
                result_parts.append(f"📝 搜索摘要：\n{answer}")
            
            if image_urls:
                result_parts.append(f"\n🖼️ 找到 {len(image_urls)} 张相关图片：")
                for i, url in enumerate(image_urls[:3], 1):
                    result_parts.append(f"   {i}. {url}")
            
            return "\n".join(result_parts) if result_parts else "未找到相关搜索结果。"
        
        return str(raw_result)
# --- 可视化工具 ---
logger = logging.getLogger(__name__)

# --- 文件工具 ---
class FileTool(BaseTool):
    def __init__(self, llm_model, memory_manager: MemoryManager):
        super().__init__(
            name="file_tool",
            description="生成 PDF 和 Excel 格式的行程文件"
        )
        self.memory_manager = memory_manager
        self.llm_model = llm_model # 传入 LLM 模型实例，用于生成代码

    def define_parameters(self) -> List[ToolParameter]:
        return [
            ToolParameter(name="format", type="str", description="文件格式，'pdf'、'excel' 或 'html'", required=True),
            ToolParameter(name="data", type="dict", description="用于生成文件的数据，格式根据 format 变化", required=True),
            ToolParameter(name="user_id", type="str", description="执行操作的用户ID", required=True)
        ]

    async def arun(self, **params: Dict[str, Any]) -> str:
        """异步执行方法（主要调用接口）"""
        return self.execute(params)
    
    def run(self, **params: Dict[str, Any]) -> str:
        """同步执行方法（使用 asyncio.run 包装 arun）"""
        return asyncio.run(self.arun(**params))
    
    def execute(self, params: Dict[str, Any]) -> str:
        file_format = params.get("format")
        data = params.get("data")
        # 兜底: 若未显式传入, 从环境变量读取或使用 'anonymous'
        user_id = params.get("user_id") or os.getenv("CURRENT_USER_ID") or ""

        if not user_id:
            return "错误: 'user_id' 是必填参数。建议：请在调用 file_tool 时提供 user_id，或确保已设置环境变量 CURRENT_USER_ID。"

        try:
            if file_format == "excel":
                return self._generate_excel(data, user_id) # type: ignore
            elif file_format == "html":  # ✅ 推荐: HTML 格式生成
                return self._generate_html(data, user_id) # type: ignore
            else:
                return f"未知的文件格式: {file_format}。请使用 'excel' 或 'html'。"
        except Exception as e:
            logger.error(f"文件工具执行失败: {str(e)}")
            return f"生成文件失败: {str(e)}"

    def _generate_excel(self, data: Dict[str, Any], user_id: str) -> str:
        """生成 Excel 行程文件，通过 LLM 生成代码"""
        # 准备 LLM 生成代码的 Prompt
        prompt = f"""
        你的任务是根据提供的行程数据，生成一段 Python 代码，使用 openpyxl 库创建一个结构清晰、格式美观的 Excel 文件。
        要求:
        1.  使用 openpyxl 库。
        2.  创建至少一个 "行程表" 工作表。
        3.  表格列: 包含 "日期", "时间段", "景点", "交通方式", "耗时", "费用", "备注" 等。
        4.  格式优化:
           - 设置表头行背景色。
           - 自动调整列宽以适应内容。
           - 为单元格添加边框。
           - (可选) 为特定列 (如费用) 设置数字格式。
        5.  代码应包含必要的库导入、工作簿/工作表创建、数据填充、格式设置、保存为文件的逻辑。
        6.  代码结构清晰，注释明确，易于理解。
        7.  输出应为可直接执行的 Python 代码字符串。
        输入数据 (JSON 格式): {json.dumps(data, ensure_ascii=False)}
        请直接输出生成的 Python 代码。
        """

        # 调用 LLM 生成代码
        python_code = self.llm_model.generate([{"role": "user", "content": prompt}]).strip() # type: ignore

        # --- 安全检查：对生成的 Python 代码进行安全检查 ---
        if not self._is_code_safe(python_code):
             logger.error("Generated Python code for Excel is unsafe.")
             return "生成的 Excel 代码不安全，无法执行。"

        # ✅ 使用 MemoryManager 获取文件路径
        absolute_path = self.memory_manager.add_file_reference(
            user_id=user_id,
            file_type="xlsx",
            file_name=f"itinerary_{uuid.uuid4().hex[:8]}.xlsx",
            description=data.get("title", "行程表")
        )
        user_facing_path = str(absolute_path.relative_to(Path("")))

        # 在沙箱环境中执行生成的代码
        # **警告：在生产环境中，必须使用安全的沙箱环境执行 LLM 生成的代码**
        try:
            # 将生成的代码写入临时文件
            with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False) as temp_file:
                # 在代码末尾添加保存文件的指令
                code_with_save = python_code + f"\nwb.save('{absolute_path}')\n" # openpyxl 通常以 wb.save 结尾
                temp_file.write(code_with_save)
                temp_file_path = temp_file.name

            # 执行临时文件
            result = subprocess.run(
                ["python", temp_file_path],
                capture_output=True,
                text=True,
                timeout=15 # 设置超时
            )

            # 清理临时文件
            os.unlink(temp_file_path)

            if result.returncode != 0:
                logger.error(f"执行 Excel 生成代码失败: {result.stderr}")
                return f"执行 Excel 生成代码失败: {result.stderr.strip()}"
            else:
                # 检查文件是否确实生成
                if absolute_path.exists():
                    logger.info(f"Excel 文件已生成: {absolute_path}")
                    return user_facing_path # 返回文件路径
                else:
                    logger.error(f"Excel 生成代码执行成功，但文件未找到: {absolute_path}")
                    return f"Excel 生成代码执行成功，但文件未找到: {absolute_path}"

        except subprocess.TimeoutExpired:
            logger.error("Excel 生成代码执行超时")
            return "Excel 生成代码执行超时"
        except Exception as e:
            logger.error(f"执行 Excel 生成代码时发生错误: {e}")
            return f"执行 Excel 生成代码时发生错误: {str(e)}"

    def _is_code_safe(self, code: str) -> Tuple[bool, str]:
        """增强的代码安全检查
        
        Returns:
            (is_safe, reason)
        """
        # ✅ 使用安全检查器
        is_safe, reason = CodeSecurityChecker.check_code_safety(code)
        if not is_safe:
            return False, reason
        
        # ✅ 验证导入语句
        import_valid, import_reason = CodeSecurityChecker.validate_imports(code)
        if not import_valid:
            return False, import_reason
        
        return True, "代码安全"

    def _generate_html(self, data: Dict[str, Any], user_id: str) -> str:
        """✅ 新增: 生成 HTML 文件
        
        Args:
            data: 包含 'content' 字段的字典，HTML 内容字符串
        
        Returns:
            生成的 HTML 文件路径
        """
        # 支持两种输入形式：
        # 1) data 包含 'content' (HTML 字符串) 和可选 'filename'
        # 2) data 是完整的行程结构（非 HTML） -> 返回明确错误，提示应先渲染为 HTML 字符串
        html_content = data.get("content")
        filename = data.get("filename") or data.get("file_name") or "document.html"

        if not html_content or not isinstance(html_content, str):
            return "错误: HTML 文件生成需要提供 'content' 字段（HTML 字符串）。如果您传入的是行程数据，请先让 Agent 或 LLM 将其渲染为 HTML 字符串后再调用 file_tool。"

        # 安全检查：禁止包含模板语法（例如 Jinja2 的 {{ }} 或 {% %}）
        if '{{' in html_content or '}}' in html_content or '{%' in html_content or '%}' in html_content:
            logger.error("检测到 HTML 内容包含模板语法（如 '{{' 或 '{%'），为安全起见拒绝生成此文件。")
            return "错误: HTML 内容包含不安全的模板语法（例如 '{{' 或 '{%}'），已拒绝生成。请提供纯静态HTML或先在Agent端渲染。"

        # ✅ 使用 MemoryManager 获取文件路径
        absolute_path = self.memory_manager.add_file_reference(
            user_id=user_id,
            file_type="html",
            file_name=filename,
            description=data.get("title", "HTML文档")
        )
        user_facing_path = str(absolute_path.relative_to(Path("")))

        try:
            # 直接写入 HTML 内容
            with open(absolute_path, "w", encoding="utf-8") as f:
                f.write(html_content)

            logger.info(f"HTML 文件已生成: {absolute_path}")
            return user_facing_path
        except Exception as e:
            logger.error(f"生成 HTML 文件失败: {e}")
            return f"生成 HTML 文件失败: {str(e)}"


# --- 其他现有工具 (保持不变) ---
class SecureCodeInterpreterTool(BaseTool):
    def __init__(self):
        super().__init__(
            name="secure_python_interpreter",
            description="在安全环境中执行Python代码并返回结果"
        )
        # 安全限制 - 只允许使用这些模块
        self.allowed_modules = ["math", "datetime", "json", "random", "re", "collections", "matplotlib", "reportlab", "openpyxl"]
        
        # 使用SecretStr存储API密钥（如果需要）
        self.api_key = SecretStr("")  # 可以配置API密钥
    
    def define_parameters(self) -> List[ToolParameter]:
        return [
            ToolParameter(name="code", type="str", description="要执行的Python代码", required=True),
            ToolParameter(name="timeout", type="int", description="执行超时时间(秒)", required=False)
        ]
    
    def execute(self, params: Dict[str, Any]) -> str:
        try:
            code = params.get("code", "")
            timeout = params.get("timeout", 10)  # 默认10秒超时
            
            # 安全检查
            if not self._is_code_safe(code):
                return "代码包含不安全操作，拒绝执行"
            
            # 在实际实现中，应使用沙箱环境执行代码
            # 这里简化处理，使用子进程执行
            result = self._execute_in_subprocess(code, timeout)
            return result
        except Exception as e:
            logger.error(f"代码执行失败: {str(e)}")
            return f"代码执行错误: {str(e)}"
    
    def _is_code_safe(self, code: str) -> bool:
        """检查代码安全性"""
        # 禁止危险操作
        dangerous_patterns = [
            r"__import__\s*\(", r"open\s*\(", r"os\.", r"subprocess\.",
            r"exec\s*\(", r"eval\s*\(", r"shutil\.", r"sys\.", r"import\s+os",
            r"import\s+sys", r"import\s+subprocess", r"import\s+shutil"
        ]
        
        for pattern in dangerous_patterns:
            if re.search(pattern, code):
                return False
        
        # 检查允许的模块
        import_lines = re.findall(r"import\s+([\w\.]+)", code)
        for imp in import_lines:
            if imp.split(".")[0] not in self.allowed_modules:
                return False
        
        return True
    
    def _execute_in_subprocess(self, code: str, timeout: int = 10) -> str:
        """在子进程中执行代码并获取输出"""
        tmp_path = None  # ✅ 初始化变量
        try:
            # 创建临时文件
            with tempfile.NamedTemporaryFile(suffix=".py", delete=False) as tmp:
                tmp.write(code.encode('utf-8'))
                tmp_path = tmp.name
            
            # 执行Python文件
            result = subprocess.run(
                ["python", tmp_path],
                capture_output=True,
                text=True,
                timeout=timeout
            )
            
            # 清理临时文件
            os.unlink(tmp_path)
            
            if result.returncode == 0:
                return result.stdout.strip() or "代码执行成功，但无输出"
            else:
                return f"执行错误: {result.stderr.strip()}"
        except subprocess.TimeoutExpired:
            return "执行超时"
        finally:
            if tmp_path and os.path.exists(tmp_path):  # ✅ 检查 tmp_path 是否已初始化
                os.unlink(tmp_path)

class FileRunnerTool(BaseTool):
    def __init__(self):
        super().__init__(
            name="run_created_file",
            description="执行Agent创建的文件（支持Python脚本）"
        )
        # 存储Agent创建的文件
        self.agent_files = {}
        
        # 安全限制 - 只允许执行Python文件
        self.allowed_extensions = [".py",".html"]
    
    def define_parameters(self) -> List[ToolParameter]:
        return [
            ToolParameter(name="file_id", type="str", description="要执行的文件ID", required=True),
            ToolParameter(name="timeout", type="int", description="执行超时时间(秒)", required=False)
        ]
    
    def save_file(self, content: str, extension: str) -> str:
        """保存Agent创建的文件并返回文件ID"""
        # 检查扩展名是否允许
        if extension not in self.allowed_extensions:
            raise ValueError(f"不支持的文件类型: {extension}")
        
        # 生成唯一文件ID
        file_id = f"agent_file_{len(self.agent_files) + 1}"
        
        # 保存文件内容
        self.agent_files[file_id] = {
            "content": content,
            "extension": extension
        }
        
        return file_id
    
    def execute(self, params: Dict[str, Any]) -> str:
        try:
            # 支持两种用法:
            # 1) 通过 file_id 执行已由 save_file 存储的内容
            # 2) 直接传入 file_path（字符串），打开该路径或执行（如果是 .py）
            timeout = params.get("timeout", 30)  # 默认30秒超时

            if "file_path" in params and params.get("file_path"):
                # ✅ 添加类型检查,确保file_path不是None
                file_path_str = params.get("file_path")
                if not file_path_str:
                    return "错误: file_path 参数为空"
                file_path = Path(file_path_str)
                if not file_path.exists():
                    return f"文件未找到: {file_path}。请先生成文件或传入正确的路径。"

                ext = file_path.suffix.lower()
                if ext == ".py":
                    return self._run_python_file(str(file_path), timeout)
                else:
                    # 尝试用系统默认程序打开（更适合 HTML 等）
                    try:
                        if os.name == 'nt':
                            os.startfile(str(file_path))
                        else:
                            import webbrowser
                            webbrowser.open(str(file_path))
                        return f"已打开文件: {file_path}"
                    except Exception as e:
                        logger.error(f"打开文件失败: {e}")
                        return f"打开文件失败: {e}"

            file_id = params.get("file_id", "")
            if not file_id:
                return "错误: 缺少 file_id 或 file_path 参数"

            timeout = params.get("timeout", 30)

            # 获取文件内容
            if file_id not in self.agent_files:
                return f"文件ID '{file_id}' 不存在"

            file_data = self.agent_files[file_id]
            content = file_data["content"]
            extension = file_data["extension"]

            # 创建临时文件
            with tempfile.NamedTemporaryFile(suffix=extension, delete=False) as tmp:
                tmp.write(content.encode('utf-8'))
                tmp_path = tmp.name

            # 根据文件类型执行
            output = ""
            if extension == ".py":
                output = self._run_python_file(tmp_path, timeout)
            else:
                # 非 python 文件直接返回路径
                output = tmp_path

            # 清理临时文件仅在我们不需要持久化时
            try:
                if extension == ".py":
                    os.unlink(tmp_path)
            except Exception:
                pass

            return output
        except Exception as e:
            logger.error(f"文件执行失败: {str(e)}")
            return f"文件执行错误: {str(e)}"
    
    def _run_python_file(self, file_path: str, timeout: int) -> str:
        """执行Python文件"""
        try:
            result = subprocess.run(
                ["python", file_path],
                capture_output=True,
                text=True,
                timeout=timeout
            )
            
            if result.returncode == 0:
                return result.stdout.strip() or "Python脚本执行成功，但无输出"
            else:
                return f"Python脚本执行错误: {result.stderr.strip()}"
        except subprocess.TimeoutExpired:
            return "执行超时"
