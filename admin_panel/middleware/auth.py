# -*- coding: utf-8 -*-
"""
API 身份验证中间件
提供基于 API Key 的简单认证机制
"""

from typing import Dict, Any, Optional, Callable
from functools import wraps
from astrbot.core.log import LogManager

logger = LogManager.GetLogger(log_name="AdminPanelAuth")


class APIKeyAuth:
    """API Key 认证管理器"""
    
    def __init__(self, api_key: Optional[str] = None):
        """
        初始化认证管理器
        
        Args:
            api_key: API 密钥，如果为 None 则禁用认证
        """
        self.api_key = api_key
        self.enabled = bool(api_key)
        
        if self.enabled:
            logger.info("Admin Panel API 认证已启用")
        else:
            logger.warning("Admin Panel API 认证未启用，所有接口无需认证即可访问")
    
    def verify_request(self, request: Dict[str, Any]) -> bool:
        """
        验证请求是否包含有效的 API Key
        
        Args:
            request: 请求数据字典
            
        Returns:
            bool: 验证是否通过
        """
        # 如果认证未启用，直接通过
        if not self.enabled:
            return True
        
        # 从请求头中获取 API Key
        api_key = request.get('headers', {}).get('X-API-Key') or \
                  request.get('headers', {}).get('x-api-key') or \
                  request.get('api_key')
        
        if not api_key:
            logger.warning(f"请求缺少 API Key: {request.get('path', 'unknown')}")
            return False
        
        # 验证 API Key
        if api_key != self.api_key:
            logger.warning(f"无效的 API Key 尝试访问: {request.get('path', 'unknown')}")
            return False
        
        return True
    
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


def create_auth_middleware(api_key: Optional[str] = None) -> APIKeyAuth:
    """
    创建认证中间件实例
    
    Args:
        api_key: API 密钥
        
    Returns:
        APIKeyAuth 实例
    """
    return APIKeyAuth(api_key)