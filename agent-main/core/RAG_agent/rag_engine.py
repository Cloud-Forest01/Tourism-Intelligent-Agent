"""
RAG Engine 基础实现（使用阿里云千问 Embedding）：
- 支持文档入库（embedding + FAISS 向量存储）
- 支持问题检索与召回
- 可与主Agent集成

API配置来源：API_FROM.py
"""
from langchain_community.vectorstores import FAISS
from langchain_text_splitters import CharacterTextSplitter
from langchain_core.documents import Document
import os
import sys
from pathlib import Path
import numpy as np
from typing import List
import dashscope
from dashscope import TextEmbedding

# 导入API配置
# 添加项目根目录到系统路径
project_root = Path(__file__).resolve().parent.parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

from config import Config

# 阿里云千问 Embedding 配置（延迟初始化）
# 注意：不在模块级别调用 Config.DASHSCOPE_API_KEY，避免导入时就抛出异常
DASHSCOPE_API_KEY = None
EMBEDDING_MODEL = "text-embedding-v2"


def _get_dashscope_api_key() -> str:
    """延迟获取API密钥"""
    global DASHSCOPE_API_KEY
    if DASHSCOPE_API_KEY is None:
        DASHSCOPE_API_KEY = Config.DASHSCOPE_API_KEY
        dashscope.api_key = DASHSCOPE_API_KEY
    return DASHSCOPE_API_KEY


class DashScopeEmbeddings:
    """阿里云千问 Embedding 封装类，兼容 LangChain 接口"""

    def __init__(self, model: str = EMBEDDING_MODEL):
        self.model = model

    def embed_documents(self, texts: List[str]) -> List[List[float]]:
        """将文档列表转换为向量"""
        embeddings = []
        for text in texts:
            result = self._get_embedding(text)
            embeddings.append(result)
        return embeddings

    def embed_query(self, text: str) -> List[float]:
        """将查询文本转换为向量"""
        return self._get_embedding(text)

    def _get_embedding(self, text: str) -> List[float]:
        """调用阿里云千问 API 获取文本向量"""
        try:
            # 确保API密钥已初始化
            _get_dashscope_api_key()

            response = TextEmbedding.call(
                model=self.model,
                input=text,
                text_type="document"
            )

            if response.status_code == 200:
                # 返回 embedding 向量
                return response.output['embeddings'][0]['embedding']
            else:
                raise Exception(f"API 调用失败: {response.message}")

        except Exception as e:
            print(f"Embedding API 调用出错: {e}")
            # 返回零向量作为兜底
            return [0.0] * 1536  # text-embedding-v2 的维度是 1536


class RAGEngine:
    def __init__(self, persist_path=None):
        """初始化 RAG 引擎

        Args:
            persist_path: FAISS 索引保存路径
        """
        # 使用阿里云千问 Embedding
        self.embedder = DashScopeEmbeddings(model=EMBEDDING_MODEL)
        self.persist_path = persist_path or os.path.join(os.path.dirname(__file__), 'faiss_index')
        self.vectorstore = None

    def build_index(self, docs: List[str]):
        """将文档列表分割、embedding、构建FAISS索引

        Args:
            docs: 文档文本列表
        """
        print(f"开始构建索引，共 {len(docs)} 个文档...")

        # 分割文档
        splitter = CharacterTextSplitter(chunk_size=500, chunk_overlap=50)
        doc_chunks = []
        for doc in docs:
            chunks = splitter.split_text(doc)
            doc_chunks.extend([Document(page_content=chunk) for chunk in chunks])

        print(f"文档分割完成，共 {len(doc_chunks)} 个文本块")

        # 生成 embeddings
        print("正在生成 embeddings...")
        texts = [doc.page_content for doc in doc_chunks]
        embeddings = self.embedder.embed_documents(texts)

        # 构建 FAISS 索引
        print("正在构建 FAISS 索引...")
        import faiss
        embedding_matrix = np.array(embeddings).astype('float32')
        dimension = embedding_matrix.shape[1]

        # 使用 L2 距离构建索引
        index = faiss.IndexFlatL2(dimension)
        index.add(embedding_matrix)

        # 保存索引和文档
        self.vectorstore = FAISS(
            embedding_function=self.embedder,  # 修正：传递 Embeddings 对象，而不是方法
            index=index,
            docstore=FAISS.get_docstore_from_docs(doc_chunks),
            index_to_docstore_id={i: i for i in range(len(doc_chunks))}
        )

        # 保存到磁盘
        self.vectorstore.save_local(self.persist_path)
        print(f"索引构建完成，已保存到: {self.persist_path}")

    def load_index(self):
        """加载已保存的FAISS索引"""
        if not os.path.exists(self.persist_path):
            raise FileNotFoundError(f"索引文件不存在: {self.persist_path}")

        print(f"正在加载索引: {self.persist_path}")
        self.vectorstore = FAISS.load_local(
            self.persist_path,
            self.embedder,
            allow_dangerous_deserialization=True
        )
        print("索引加载完成")

    def query(self, question: str, top_k: int = 3) -> str:
        """检索相关文档片段，并美化输出

        Args:
            question: 查询问题
            top_k: 返回最相关的 k 个文档片段

        Returns:
            格式化的检索结果
        """
        if self.vectorstore is None:
            try:
                self.load_index()
            except FileNotFoundError:
                return "未找到索引文件，请先构建索引。"

        # 检索相关文档
        try:
            docs = self.vectorstore.similarity_search(question, k=top_k)
        except TypeError:
            docs = self.vectorstore.similarity_search(question, top_k=top_k)

        if not docs:
            return "未检索到相关内容。"

        # 美化输出：编号+分段
        result = "\n\n".join([f"【片段{i+1}】\n{d.page_content.strip()}" for i, d in enumerate(docs)])
        return result


# 测试代码
if __name__ == "__main__":
    # 测试 embedding
    embedder = DashScopeEmbeddings()
    test_text = "这是一个测试文本"
    embedding = embedder.embed_query(test_text)
    print(f"Embedding 维度: {len(embedding)}")
    print(f"前10个值: {embedding[:10]}")
