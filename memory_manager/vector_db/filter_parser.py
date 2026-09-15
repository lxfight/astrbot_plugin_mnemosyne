"""
通用过滤条件解析器
将 Milvus 风格的过滤表达式转换为各种数据库的原生过滤格式
"""

import re
from typing import Any


class FilterParser:
    """
    解析 Milvus 风格的过滤表达式

    支持的表达式：
    - 相等：field == "value" 或 field == value
    - 不等：field != "value"
    - 大于：field > value
    - 小于：field < value
    - 大于等于：field >= value
    - 小于等于：field <= value
    - IN：field in ["a", "b"]
    - NOT IN：field not in ["a", "b"]
    - AND：expr1 and expr2
    - OR：expr1 or expr2
    - NOT：not expr
    - 括号：(expr)
    """

    # 操作符优先级
    OPERATORS = {
        "==": "eq",
        "!=": "ne",
        ">": "gt",
        "<": "lt",
        ">=": "gte",
        "<=": "lte",
        "in": "in",
        "not in": "nin",
    }

    @staticmethod
    def parse(expr: str) -> dict[str, Any]:
        """
        解析 Milvus 表达式为抽象语法树 (AST)

        Args:
            expr: Milvus 风格的过滤表达式

        Returns:
            dict: 抽象语法树，格式：
                {
                    "type": "comparison" | "logical" | "not",
                    "operator": "eq" | "gt" | "and" | "or" | "not" ...,
                    "field": "field_name",  # 仅 comparison 类型
                    "value": value,         # 仅 comparison 类型
                    "left": {...},          # 仅 logical 类型
                    "right": {...},         # 仅 logical 类型
                    "operand": {...}        # 仅 not 类型
                }
        """
        if not expr or not expr.strip():
            return {}

        expr = expr.strip()

        # 处理 NOT
        if expr.lower().startswith("not "):
            operand_expr = expr[4:].strip()
            return {
                "type": "not",
                "operator": "not",
                "operand": FilterParser.parse(operand_expr),
            }

        # 处理括号
        if expr.startswith("(") and expr.endswith(")"):
            return FilterParser.parse(expr[1:-1])

        # 查找最外层的 AND/OR
        logical_op = FilterParser._find_logical_operator(expr)
        if logical_op:
            op_keyword, op_pos = logical_op
            left_expr = expr[:op_pos].strip()
            right_expr = expr[op_pos + len(op_keyword) :].strip()

            return {
                "type": "logical",
                "operator": "and" if op_keyword.lower() == "and" else "or",
                "left": FilterParser.parse(left_expr),
                "right": FilterParser.parse(right_expr),
            }

        # 处理比较表达式
        return FilterParser._parse_comparison(expr)

    @staticmethod
    def _find_logical_operator(expr: str) -> tuple[str, int] | None:
        """
        查找最外层的逻辑操作符（AND/OR）

        Returns:
            (operator, position) 或 None
        """
        paren_level = 0
        i = 0

        while i < len(expr):
            if expr[i] == "(":
                paren_level += 1
            elif expr[i] == ")":
                paren_level -= 1
            elif paren_level == 0:
                # 在括号外，查找 AND/OR
                if i + 3 <= len(expr) and expr[i : i + 3].lower() == "and":
                    if (i == 0 or not expr[i - 1].isalnum()) and (
                        i + 3 == len(expr) or not expr[i + 3].isalnum()
                    ):
                        return ("and", i)
                elif i + 2 <= len(expr) and expr[i : i + 2].lower() == "or":
                    if (i == 0 or not expr[i - 1].isalnum()) and (
                        i + 2 == len(expr) or not expr[i + 2].isalnum()
                    ):
                        return ("or", i)
            i += 1

        return None

    @staticmethod
    def _parse_comparison(expr: str) -> dict[str, Any]:
        """解析比较表达式"""
        expr = expr.strip()

        # 尝试匹配各种操作符
        # 按长度从长到短匹配，避免 >= 被匹配成 >
        operators = ["not in", "==", "!=", ">=", "<=", ">", "<", "in"]

        for op in operators:
            pattern = r"(\w+)\s*" + re.escape(op) + r"\s*(.+)"
            match = re.match(pattern, expr, re.IGNORECASE)

            if match:
                field = match.group(1).strip()
                value_str = match.group(2).strip()

                # 解析值
                value = FilterParser._parse_value(value_str)

                return {
                    "type": "comparison",
                    "operator": FilterParser.OPERATORS.get(op.lower(), op.lower()),
                    "field": field,
                    "value": value,
                }

        # 无法解析
        raise ValueError(f"无法解析表达式: {expr}")

    @staticmethod
    def _parse_value(value_str: str) -> Any:
        """解析值（字符串、数字、列表等）"""
        value_str = value_str.strip()

        # 字符串（带引号）
        if (value_str.startswith('"') and value_str.endswith('"')) or (
            value_str.startswith("'") and value_str.endswith("'")
        ):
            return value_str[1:-1]

        # 列表
        if value_str.startswith("[") and value_str.endswith("]"):
            items_str = value_str[1:-1].strip()
            if not items_str:
                return []

            items = []
            for item in items_str.split(","):
                item = item.strip()
                if (item.startswith('"') and item.endswith('"')) or (
                    item.startswith("'") and item.endswith("'")
                ):
                    items.append(item[1:-1])
                else:
                    # 尝试解析为数字
                    try:
                        if "." in item:
                            items.append(float(item))
                        else:
                            items.append(int(item))
                    except ValueError:
                        items.append(item)
            return items

        # 布尔值
        if value_str.lower() in ("true", "false"):
            return value_str.lower() == "true"

        # 数字
        try:
            if "." in value_str:
                return float(value_str)
            else:
                return int(value_str)
        except ValueError:
            pass

        # 默认作为字符串
        return value_str


class ChromaFilterConverter:
    """将 AST 转换为 Chroma Where 条件"""

    @staticmethod
    def convert(ast: dict[str, Any]) -> dict[str, Any] | None:
        """转换 AST 为 Chroma where 条件"""
        if not ast:
            return None

        ast_type = ast.get("type")

        if ast_type == "comparison":
            return ChromaFilterConverter._convert_comparison(ast)
        elif ast_type == "logical":
            return ChromaFilterConverter._convert_logical(ast)
        elif ast_type == "not":
            return ChromaFilterConverter._convert_not(ast)

        return None

    @staticmethod
    def _convert_comparison(ast: dict) -> dict:
        """转换比较表达式"""
        field = ast["field"]
        operator = ast["operator"]
        value = ast["value"]

        # Chroma 的 where 格式
        op_map = {
            "eq": "$eq",
            "ne": "$ne",
            "gt": "$gt",
            "lt": "$lt",
            "gte": "$gte",
            "lte": "$lte",
            "in": "$in",
            "nin": "$nin",
        }

        chroma_op = op_map.get(operator, "$eq")

        return {field: {chroma_op: value}}

    @staticmethod
    def _convert_logical(ast: dict) -> dict:
        """转换逻辑表达式"""
        operator = ast["operator"]
        left = ChromaFilterConverter.convert(ast["left"])
        right = ChromaFilterConverter.convert(ast["right"])

        if operator == "and":
            return {"$and": [left, right]}
        elif operator == "or":
            return {"$or": [left, right]}

        return {}

    @staticmethod
    def _convert_not(ast: dict) -> dict:
        """转换 NOT 表达式"""
        operand = ChromaFilterConverter.convert(ast["operand"])
        return {"$not": operand}


class QdrantFilterConverter:
    """将 AST 转换为 Qdrant Filter"""

    @staticmethod
    def convert(ast: dict[str, Any]) -> Any:
        """转换 AST 为 Qdrant Filter"""
        if not ast:
            return None

        ast_type = ast.get("type")

        if ast_type == "comparison":
            return QdrantFilterConverter._convert_comparison(ast)
        elif ast_type == "logical":
            return QdrantFilterConverter._convert_logical(ast)
        elif ast_type == "not":
            return QdrantFilterConverter._convert_not(ast)

        return None

    @staticmethod
    def _convert_comparison(ast: dict) -> Any:
        """转换比较表达式"""
        from qdrant_client.models import (
            FieldCondition,
            Filter,
            MatchAny,
            MatchValue,
            Range,
        )

        field = ast["field"]
        operator = ast["operator"]
        value = ast["value"]

        if operator == "eq":
            return Filter(
                must=[FieldCondition(key=field, match=MatchValue(value=value))]
            )
        elif operator == "ne":
            return Filter(
                must_not=[FieldCondition(key=field, match=MatchValue(value=value))]
            )
        elif operator in ["gt", "lt", "gte", "lte"]:
            range_kwargs = {}
            if operator == "gt":
                range_kwargs["gt"] = value
            elif operator == "lt":
                range_kwargs["lt"] = value
            elif operator == "gte":
                range_kwargs["gte"] = value
            elif operator == "lte":
                range_kwargs["lte"] = value

            return Filter(must=[FieldCondition(key=field, range=Range(**range_kwargs))])
        elif operator == "in":
            return Filter(must=[FieldCondition(key=field, match=MatchAny(any=value))])
        elif operator == "nin":
            return Filter(
                must_not=[FieldCondition(key=field, match=MatchAny(any=value))]
            )

        return None

    @staticmethod
    def _convert_logical(ast: dict) -> Any:
        """转换逻辑表达式"""
        from qdrant_client.models import Filter

        operator = ast["operator"]
        left = QdrantFilterConverter.convert(ast["left"])
        right = QdrantFilterConverter.convert(ast["right"])

        if operator == "and":
            # 合并 must 条件
            must_conditions = []
            if left and hasattr(left, "must"):
                must_conditions.extend(left.must or [])
            if right and hasattr(right, "must"):
                must_conditions.extend(right.must or [])

            return Filter(must=must_conditions)
        elif operator == "or":
            # Qdrant 使用 should 表示 OR
            should_conditions = []
            if left:
                should_conditions.append(left)
            if right:
                should_conditions.append(right)

            return Filter(should=should_conditions)

        return None

    @staticmethod
    def _convert_not(ast: dict) -> Any:
        """转换 NOT 表达式"""
        from qdrant_client.models import Filter

        operand = QdrantFilterConverter.convert(ast["operand"])

        if operand and hasattr(operand, "must"):
            # 将 must 转换为 must_not
            return Filter(must_not=operand.must)

        return operand


class WeaviateFilterConverter:
    """将 AST 转换为 Weaviate Where 条件"""

    @staticmethod
    def convert(ast: dict[str, Any]) -> dict[str, Any] | None:
        """转换 AST 为 Weaviate where 条件"""
        if not ast:
            return None

        ast_type = ast.get("type")

        if ast_type == "comparison":
            return WeaviateFilterConverter._convert_comparison(ast)
        elif ast_type == "logical":
            return WeaviateFilterConverter._convert_logical(ast)
        elif ast_type == "not":
            return WeaviateFilterConverter._convert_not(ast)

        return None

    @staticmethod
    def _convert_comparison(ast: dict) -> dict:
        """转换比较表达式"""
        field = ast["field"]
        operator = ast["operator"]
        value = ast["value"]

        # Weaviate 的操作符映射
        op_map = {
            "eq": "Equal",
            "ne": "NotEqual",
            "gt": "GreaterThan",
            "lt": "LessThan",
            "gte": "GreaterThanEqual",
            "lte": "LessThanEqual",
        }

        weaviate_op = op_map.get(operator, "Equal")

        # 确定值的类型
        value_key = "valueText"
        if isinstance(value, int):
            value_key = "valueInt"
        elif isinstance(value, float):
            value_key = "valueNumber"
        elif isinstance(value, bool):
            value_key = "valueBoolean"

        where_filter = {"path": [field], "operator": weaviate_op, value_key: value}

        return where_filter

    @staticmethod
    def _convert_logical(ast: dict) -> dict:
        """转换逻辑表达式"""
        operator = ast["operator"]
        left = WeaviateFilterConverter.convert(ast["left"])
        right = WeaviateFilterConverter.convert(ast["right"])

        weaviate_op = "And" if operator == "and" else "Or"

        return {"operator": weaviate_op, "operands": [left, right]}

    @staticmethod
    def _convert_not(ast: dict) -> dict:
        """转换 NOT 表达式（Weaviate 不直接支持，使用反向操作符）"""
        # Weaviate 没有直接的 NOT，需要反转内部的操作符
        operand = ast["operand"]

        if operand.get("type") == "comparison":
            # 反转比较操作符
            op = operand["operator"]
            reverse_map = {
                "eq": "ne",
                "ne": "eq",
                "gt": "lte",
                "lt": "gte",
                "gte": "lt",
                "lte": "gt",
            }

            reversed_operand = operand.copy()
            reversed_operand["operator"] = reverse_map.get(op, "ne")

            return WeaviateFilterConverter._convert_comparison(reversed_operand)

        # 其他情况直接返回（可能不完美）
        return WeaviateFilterConverter.convert(operand)
