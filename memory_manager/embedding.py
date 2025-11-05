"""
Embedding 提供商包装模块
用于统一处理 AstrBot 框架提供的 embedding provider
"""

from astrbot.core.provider.provider import EmbeddingProvider


class EmbeddingProviderWrapper:
    """
    AstrBot Embedding Provider 包装类
    提供统一的接口来调用框架中的 embedding 服务
    """

    def __init__(self, provider: EmbeddingProvider):
        """
        初始化 Embedding Provider 包装器

        Args:
            provider: AstrBot 的 EmbeddingProvider 实例
        """
        if not provider:
            raise ValueError("Embedding provider 不能为 None")
        self.provider = provider

    def embed(self, texts: str | list[str]) -> list[list[float]]:
        """
        获取文本的嵌入向量

        Args:
            texts: 输入文本（单条字符串或字符串列表）

        Returns:
            嵌入向量列表

        Raises:
            ConnectionError: 调用 provider 失败时
        """
        try:
            if isinstance(texts, str):
                texts = [texts]

            # 调用 provider 的 embed 方法
            # M24 修复: 添加类型忽略注释
            embeddings = self.provider.embed(texts)  # type: ignore
            if not embeddings:
                raise ConnectionError("Embedding provider 返回空结果")

            return embeddings

        except Exception as e:
            raise ConnectionError(
                f"获取 embedding 失败: {e}\n请检查 embedding provider 配置是否正确"
            )

    def get_embedding_dim(self) -> int:
        """
        获取嵌入向量的维度

        Returns:
            向量维度，如果无法获取返回 -1
        """
        try:
            if hasattr(self.provider, "embedding_dim"):
                # M24 修复: 添加类型忽略注释
                return self.provider.embedding_dim  # type: ignore
            return -1
        except Exception:
            return -1
