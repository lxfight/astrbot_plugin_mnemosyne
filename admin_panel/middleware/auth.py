# -*- coding: utf-8 -*-
"""
API 身份验证中间件
提供基于 API Key 的强制认证机制
"""

from typing import Dict, Any, Optional, Callable
from functools import wraps
import secrets
import hashlib
from pathlib import Path
from astrbot.core.log import LogManager
from astrbot.api.star import StarTools

logger = LogManager.GetLogger(log_name="AdminPanelAuth")


def generate_secure_token(length: int = 32) -> str:
    """
    生成加密安全的随机 token
    
    Args:
        length: token 长度（字节数）
        
    Returns:
        str: 十六进制格式的安全 token
    """
    return secrets.token_hex(length)


def save_token_to_file(token: str, file_path: Path) -> bool:
    """
    将 token 安全地保存到文件
    
    Args:
        token: 要保存的 token
        file_path: 文件路径
        
    Returns:
        bool: 是否保存成功
    """
    try:
        # 确保目录存在
        file_path.parent.mkdir(parents=True, exist_ok=True)
        
        # 写入文件（覆盖模式）
        with open(file_path, 'w', encoding='utf-8') as f:
            f.write(token)
        
        # 设置文件权限（仅所有者可读写）
        try:
            import os
            os.chmod(file_path, 0o600)
        except Exception as e:
            logger.warning(f"无法设置文件权限: {e}")
        
        return True
    except Exception as e:
        logger.error(f"保存 token 到文件失败: {e}")
        return False


def load_token_from_file(file_path: Path) -> Optional[str]:
    """
    从文件加载 token
    
    Args:
        file_path: 文件路径
        
    Returns:
        Optional[str]: 加载的 token，失败返回 None
    """
    try:
        if not file_path.exists():
            return None
        
        with open(file_path, 'r', encoding='utf-8') as f:
            token = f.read().strip()
        
        # 验证 token 格式（应该是十六进制字符串）
        if not token or not all(c in '0123456789abcdef' for c in token.lower()):
            logger.warning(f"Token 文件包含无效格式的内容")
            return None
        
        return token
    except Exception as e:
        logger.error(f"从文件加载 token 失败: {e}")
        return None


class APIKeyAuth:
    """API Key 强制认证管理器"""
    
    def __init__(self, api_key: Optional[str] = None, data_dir: Optional[Path] = None):
        """
        初始化认证管理器
        
        Args:
            api_key: API 密钥，如果为 None 或空则生成动态 token
            data_dir: 数据目录路径，用于存储生成的 token（使用 StarTools.get_data_dir() 获取）
        """
        # 使用 AstrBot 标准 API 获取插件数据目录
        if data_dir is None:
            data_dir = Path(StarTools.get_data_dir()) / "admin_panel"
        self.data_dir = Path(data_dir)
        self.token_file = self.data_dir / ".api_token"
        self.api_key = None
        self.is_auto_generated = False
        
        # 处理用户配置的 api_key
        if api_key and api_key.strip():
            # 用户提供了有效的 api_key
            self.api_key = api_key.strip()
            self.is_auto_generated = False
            logger.info("Admin Panel API 认证已启用（使用用户配置的密钥）")
        else:
            # 未配置或配置为空，生成强制的动态 token
            logger.warning("⚠️ 未配置 API 密钥，正在生成动态强 token 进行保护")
            
            # 尝试从文件加载已存在的 token
            existing_token = load_token_from_file(self.token_file)
            
            if existing_token:
                self.api_key = existing_token
                logger.info(f"已加载现有的动态 token（文件: {self.token_file}）")
            else:
                # 生成新的强 token
                self.api_key = generate_secure_token(32)  # 64字符的十六进制 token
                
                # 保存到文件
                if save_token_to_file(self.api_key, self.token_file):
                    logger.critical(
                        f"🔒 已生成动态强 token 并保存到: {self.token_file}\n"
                        f"   Token: {self.api_key}\n"
                        f"   请妥善保管此 token，用于访问管理面板。\n"
                        f"   建议在配置文件中设置 admin_panel.api_key 以使用自定义密钥。"
                    )
                else:
                    logger.error("无法保存动态 token 到文件，token 仅在本次运行中有效")
            
            self.is_auto_generated = True
        
        # 强制启用认证，不允许禁用
        self.enabled = True
        
        # 计算 token 的哈希值用于日志（不记录完整 token）
        token_hash = hashlib.sha256(self.api_key.encode()).hexdigest()[:8]
        logger.info(f"Admin Panel API 强制认证已启用（Token Hash: {token_hash}...）")
    
    def verify_request(self, request: Dict[str, Any]) -> bool:
        """
        验证请求是否包含有效的 API Key
        
        Args:
            request: 请求数据字典
            
        Returns:
            bool: 验证是否通过
        """
        # 强制要求认证，不再允许跳过
        if not self.api_key:
            logger.error("认证系统配置错误：API Key 未设置")
            return False
        
        # 从请求头中获取 API Key
        api_key = request.get('headers', {}).get('X-API-Key') or \
                  request.get('headers', {}).get('x-api-key') or \
                  request.get('api_key')
        
        if not api_key:
            logger.warning(f"请求缺少 API Key: {request.get('path', 'unknown')}")
            return False
        
        # 使用常量时间比较防止时序攻击
        if not secrets.compare_digest(str(api_key), str(self.api_key)):
            logger.warning(f"无效的 API Key 尝试访问: {request.get('path', 'unknown')}")
            return False
        
        return True
    
    def get_token_info(self) -> Dict[str, Any]:
        """
        获取 token 信息（用于显示给管理员）
        
        Returns:
            Dict: token 信息
        """
        token_hash = hashlib.sha256(self.api_key.encode()).hexdigest()[:16]
        
        return {
            "is_auto_generated": self.is_auto_generated,
            "token_file": str(self.token_file) if self.is_auto_generated else None,
            "token_hash": token_hash,
            "token_length": len(self.api_key),
            "full_token": self.api_key if self.is_auto_generated else "[用户自定义密钥]"
        }
    
    def require_auth(self, handler: Callable):
        """
        装饰器：要求请求必须通过身份验证
        
        Args:
            handler: 路由处理函数
            
        Returns:
            包装后的处理函数
        """
        @wraps(handler)
        async def wrapper(request: Dict[str, Any]) -> Dict[str, Any]:
            # 验证请求
            if not self.verify_request(request):
                return {
                    "success": False,
                    "error": "Unauthorized",
                    "message": "需要有效的 API Key 才能访问此资源",
                    "status_code": 401
                }
            
            # 调用原始处理函数
            return await handler(request)
        
        return wrapper


def create_auth_middleware(api_key: Optional[str] = None, data_dir: Optional[Path] = None) -> APIKeyAuth:
    """
    创建认证中间件实例（强制认证）
    
    Args:
        api_key: API 密钥（如果为空则自动生成强 token）
        data_dir: 数据目录路径
        
    Returns:
        APIKeyAuth 实例
    """
    return APIKeyAuth(api_key, data_dir)