"""
Schema 工具模块
提供字典格式与 CollectionSchema 对象之间的转换功能
"""

from typing import Any

from pymilvus import CollectionSchema, DataType, FieldSchema


def dict_to_collection_schema(schema_dict: dict[str, Any]) -> CollectionSchema:
    """
    将字典格式转换为 CollectionSchema 对象

    Args:
        schema_dict (Dict[str, Any]): 包含集合模式定义的字典
            必须包含 'fields' 键，值为字段定义列表
            可选包含 'description' 键，值为集合描述

    Returns:
        CollectionSchema: 转换后的 CollectionSchema 对象

    Raises:
        ValueError: 当输入字典缺少必要字段或格式不正确时
        KeyError: 当字段定义缺少必要键时
    """
    if not isinstance(schema_dict, dict):
        raise ValueError("schema_dict 必须是一个字典")

    if "fields" not in schema_dict:
        raise ValueError("schema_dict 必须包含 'fields' 键")

    if not isinstance(schema_dict["fields"], list):
        raise ValueError("schema_dict['fields'] 必须是一个列表")

    if not schema_dict["fields"]:
        raise ValueError("schema_dict['fields'] 不能为空")

    # 转换字段定义
    fields = []
    for field_def in schema_dict["fields"]:
        if not isinstance(field_def, dict):
            raise ValueError("每个字段定义必须是一个字典")

        # 检查必要字段
        if "name" not in field_def:
            raise KeyError("字段定义必须包含 'name' 键")
        if "dtype" not in field_def:
            raise KeyError("字段定义必须包含 'dtype' 键")

        # 提取字段参数
        field_name = field_def["name"]
        field_dtype = field_def["dtype"]

        # 构建字段参数字典
        field_kwargs = {}

        # 处理通用参数
        for param in ["is_primary", "auto_id", "is_nullable", "description"]:
            if param in field_def:
                field_kwargs[param] = field_def[param]

        # 处理特定类型的参数
        if field_dtype == DataType.VARCHAR:
            if "max_length" not in field_def:
                raise KeyError("VARCHAR 字段必须包含 'max_length' 键")
            field_kwargs["max_length"] = field_def["max_length"]
        elif field_dtype in [DataType.FLOAT_VECTOR, DataType.BINARY_VECTOR]:
            if "dim" not in field_def:
                raise KeyError(f"{field_dtype} 字段必须包含 'dim' 键")
            field_kwargs["dim"] = field_def["dim"]

        # 创建字段对象
        field = FieldSchema(name=field_name, dtype=field_dtype, **field_kwargs)
        fields.append(field)

    # 创建集合模式
    collection_kwargs = {
        "fields": fields,
        "description": schema_dict.get("description", ""),
    }

    # 处理可选参数
    for param in ["primary_field", "enable_dynamic_field"]:
        if param in schema_dict:
            collection_kwargs[param] = schema_dict[param]

    return CollectionSchema(**collection_kwargs)


def collection_schema_to_dict(schema: CollectionSchema) -> dict[str, Any]:
    """
    将 CollectionSchema 转换为字典格式

    Args:
        schema (CollectionSchema): 要转换的 CollectionSchema 对象

    Returns:
        Dict[str, Any]: 转换后的字典格式模式定义

    Raises:
        ValueError: 当输入不是 CollectionSchema 对象时
    """
    if not isinstance(schema, CollectionSchema):
        raise ValueError("输入必须是 CollectionSchema 对象")

    # 转换字段定义
    fields = []
    for field in schema.fields:
        field_dict = {"name": field.name, "dtype": field.dtype}

        # 添加通用参数
        for param in ["is_primary", "auto_id", "is_nullable", "description"]:
            if hasattr(field, param):
                value = getattr(field, param)
                if value is not None:
                    field_dict[param] = value

        # 添加特定类型的参数
        if field.dtype == DataType.VARCHAR and hasattr(field, "max_length"):
            field_dict["max_length"] = field.max_length
        elif field.dtype in [DataType.FLOAT_VECTOR, DataType.BINARY_VECTOR] and hasattr(
            field, "params"
        ):
            # 向量字段的维度信息在 params 中
            if hasattr(field, "params") and field.params and "dim" in field.params:
                field_dict["dim"] = field.params["dim"]
            elif hasattr(field, "dim"):
                field_dict["dim"] = field.dim

        fields.append(field_dict)

    # 构建结果字典
    result = {"fields": fields, "description": schema.description}

    # 添加可选参数
    for param in ["primary_field", "enable_dynamic_field"]:
        if hasattr(schema, param):
            value = getattr(schema, param)
            if value is not None:
                result[param] = value

    return result


def merge_schema_dicts(
    base_schema: dict[str, Any], update_schema: dict[str, Any]
) -> dict[str, Any]:
    """
    合并两个模式字典，update_schema 中的字段会覆盖 base_schema 中的对应字段

    Args:
        base_schema (Dict[str, Any]): 基础模式字典
        update_schema (Dict[str, Any]): 更新模式字典

    Returns:
        Dict[str, Any]: 合并后的模式字典
    """
    if not isinstance(base_schema, dict) or not isinstance(update_schema, dict):
        raise ValueError("两个参数都必须是字典")

    # 创建基础模式的深拷贝
    result = {
        "fields": base_schema.get("fields", []).copy(),
        "description": update_schema.get(
            "description", base_schema.get("description", "")
        ),
    }

    # 处理可选参数
    for param in ["primary_field", "enable_dynamic_field"]:
        if param in update_schema:
            result[param] = update_schema[param]
        elif param in base_schema:
            result[param] = base_schema[param]

    # 合并字段定义
    base_fields = {field["name"]: field for field in base_schema.get("fields", [])}
    update_fields = {field["name"]: field for field in update_schema.get("fields", [])}

    # 更新或添加字段
    merged_fields = []
    for field_name, field_def in update_fields.items():
        merged_fields.append(field_def)

    # 添加基础模式中存在但更新模式中不存在的字段
    for field_name, field_def in base_fields.items():
        if field_name not in update_fields:
            merged_fields.append(field_def)

    result["fields"] = merged_fields
    return result


def validate_schema_dict(schema_dict: dict[str, Any]) -> bool:
    """
    验证模式字典的格式是否正确

    Args:
        schema_dict (Dict[str, Any]): 要验证的模式字典

    Returns:
        bool: 如果格式正确返回 True，否则返回 False

    Raises:
        ValueError: 当输入不是字典时
    """
    try:
        dict_to_collection_schema(schema_dict)
        return True
    except (ValueError, KeyError):
        return False
