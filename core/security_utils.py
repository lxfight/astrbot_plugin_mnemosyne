"""
Mnemosyne 插件安全工具模块
提供输入验证、SQL注入防护、路径遍历防护等安全功能
"""

import re
from pathlib import Path

from astrbot.core.log import LogManager

logger = LogManager.GetLogger(log_name="MnemosyneSecurity")


# ==================== SQL注入防护 ====================


def validate_session_id(session_id: str) -> bool:
    """
    验证 session_id 格式，防止注入攻击

    Args:
        session_id: 要验证的会话ID

    Returns:
        bool: 如果格式有效返回True，否则返回False
    """
    if not session_id or not isinstance(session_id, str):
        return False

    # 只允许字母数字、连字符、下划线和冒号（某些平台的session_id可能包含冒号）
    # 长度限制：1-255字符
    pattern = r"^[a-zA-Z0-9_:-]+$"

    if not re.match(pattern, session_id):
        logger.warning("session_id 格式验证失败: 包含非法字符")
        return False

    if len(session_id) > 255:
        logger.warning("session_id 格式验证失败: 长度超过255")
        return False

    return True


def validate_personality_id(personality_id: str) -> bool:
    """
    验证 personality_id 格式，防止注入攻击

    Args:
        personality_id: 要验证的人格ID

    Returns:
        bool: 如果格式有效返回True，否则返回False
    """
    if not personality_id or not isinstance(personality_id, str):
        return False

    # 只允许字母数字、连字符、下划线、空格和中文字符
    # 长度限制：1-256字符
    pattern = r"^[a-zA-Z0-9_\-\s\u4e00-\u9fa5]+$"

    if not re.match(pattern, personality_id):
        logger.warning("personality_id 格式验证失败: 包含非法字符")
        return False

    if len(personality_id) > 256:
        logger.warning("personality_id 格式验证失败: 长度超过256")
        return False

    return True


def safe_build_milvus_expression(field: str, value: str, operator: str = "==") -> str:
    """
    安全构建 Milvus 查询表达式，防止注入攻击

    Args:
        field: 字段名（必须在白名单中）
        value: 字段值（将被转义）
        operator: 操作符（==、in等）

    Returns:
        str: 安全的查询表达式

    Raises:
        ValueError: 如果字段名不在白名单或操作符不支持
    """
    # 字段名白名单
    allowed_fields = ["session_id", "personality_id", "user_id", "memory_id"]
    if field not in allowed_fields:
        raise ValueError(
            f"不允许的字段名: {field}. 只允许: {', '.join(allowed_fields)}"
        )

    # 操作符白名单
    allowed_operators = ["==", "in", ">", ">=", "<", "<=", "!="]
    if operator not in allowed_operators:
        raise ValueError(f"不支持的操作符: {operator}")

    # 转义特殊字符，防止注入
    # Milvus 表达式中的字符串需要转义反斜杠和双引号
    escaped_value = value.replace("\\", "\\\\").replace('"', '\\"')

    # 构建表达式
    if operator == "==":
        return f'{field} == "{escaped_value}"'
    elif operator == "in":
        return f'{field} in ["{escaped_value}"]'
    else:
        # 对于比较操作符，直接使用（数值类型）
        return f"{field} {operator} {escaped_value}"


# ==================== 路径遍历防护 ====================


def validate_safe_path(
    file_path: str, base_dir: str, allow_creation: bool = True
) -> Path:
    """
    验证路径安全性，防止路径遍历攻击

    Args:
        file_path: 要验证的文件路径（相对路径或绝对路径）
        base_dir: 允许的基础目录
        allow_creation: 是否允许创建不存在的目录

    Returns:
        Path: 验证通过的绝对路径对象

    Raises:
        ValueError: 如果路径不安全或无效
    """
    try:
        # 转换为 Path 对象并获取绝对路径
        base = Path(base_dir).resolve()

        # 处理 file_path：如果是绝对路径，需要检查；如果是相对路径，则相对于 base_dir
        target_path = Path(file_path)
        if target_path.is_absolute():
            target = target_path.resolve()
        else:
            target = (base / file_path).resolve()

        # 安全检查：确保目标路径在允许的基础目录内
        # 使用字符串比较确保没有符号链接绕过
        try:
            target.relative_to(base)
        except ValueError:
            raise ValueError(
                f"路径遍历检测: 路径 '{file_path}' 试图访问基础目录 '{base_dir}' 之外的位置"
            )

        # 检查路径中是否包含危险模式
        path_str = str(target)
        dangerous_patterns = ["..", "~", "$"]
        for pattern in dangerous_patterns:
            if pattern in path_str:
                raise ValueError(f"路径包含危险字符或模式: '{pattern}'")

        # 如果允许创建目录，确保父目录存在
        if allow_creation:
            parent_dir = target.parent
            if not parent_dir.exists():
                try:
                    parent_dir.mkdir(parents=True, exist_ok=True)
                    logger.info(f"创建目录: {parent_dir}")
                except OSError as e:
                    raise ValueError(f"无法创建目录 '{parent_dir}': {e}")

        return target

    except Exception as e:
        if isinstance(e, ValueError):
            raise
        raise ValueError(f"路径验证失败: {file_path}") from e


def normalize_db_path(db_file: str | None, default_base_dir: str) -> str:
    """
    规范化数据库文件路径，确保安全性

    Args:
        db_file: 数据库文件路径（可为None）
        default_base_dir: 默认基础目录

    Returns:
        str: 安全的数据库文件路径
    """
    if db_file is None:
        # 使用默认路径
        base_path = Path(default_base_dir).resolve()
        base_path.mkdir(parents=True, exist_ok=True)
        return str(base_path / "message_counters.db")

    # 验证用户提供的路径
    try:
        safe_path = validate_safe_path(db_file, default_base_dir, allow_creation=True)
        return str(safe_path)
    except ValueError as e:
        logger.error(f"数据库路径验证失败: {e}")
        raise


# ==================== Provider 验证 ====================


def validate_provider_id(
    provider_id: str | None, available_providers: list
) -> tuple[bool, str | None]:
    """
    验证 provider_id 的有效性

    Args:
        provider_id: 要验证的 provider ID
        available_providers: 可用的 provider 列表

    Returns:
        tuple[bool, Optional[str]]: (是否有效, 错误消息)
    """
    if not provider_id:
        return False, "provider_id 未配置"

    if not isinstance(provider_id, str):
        return (
            False,
            f"provider_id 类型无效: 期望 str，得到 {type(provider_id).__name__}",
        )

    # 检查格式（只允许字母数字、下划线、连字符）
    if not re.match(r"^[a-zA-Z0-9_-]+$", provider_id):
        return False, "provider_id 格式无效: 包含非法字符"

    # 检查是否在可用列表中
    if available_providers and provider_id not in [
        p.get("id") for p in available_providers if isinstance(p, dict) and "id" in p
    ]:
        return False, f"provider_id '{provider_id}' 不在可用的 provider 列表中"

    return True, None


# ==================== 异常信息清理 ====================


def sanitize_error_message(
    error_msg: str, remove_paths: bool = True, remove_values: bool = True
) -> str:
    """
    清理错误消息，移除敏感信息

    Args:
        error_msg: 原始错误消息
        remove_paths: 是否移除文件路径
        remove_values: 是否移除配置值

    Returns:
        str: 清理后的错误消息
    """
    sanitized = error_msg

    if remove_paths:
        # 移除文件路径（Windows 和 Unix 风格）
        sanitized = re.sub(r"[A-Za-z]:[\\\/][^\s]+", "[PATH]", sanitized)
        sanitized = re.sub(r"\/[^\s]+\/[^\s]+", "[PATH]", sanitized)

    if remove_values:
        # 移除可能的配置值（引号中的内容）
        sanitized = re.sub(r'["\']([^"\']{20,})["\']', '"[CONFIG_VALUE]"', sanitized)

    return sanitized


def create_safe_error_response(operation: str, log_details: str = "") -> str:
    """
    创建安全的用户友好错误消息

    Args:
        operation: 操作名称
        log_details: 详细错误信息（仅记录到日志）

    Returns:
        str: 用户友好的错误消息
    """
    if log_details:
        logger.error(f"{operation} 失败: {log_details}")

    return f"{operation} 失败。请检查配置或联系管理员查看日志获取详细信息。"
