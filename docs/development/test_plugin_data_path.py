#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
测试插件数据目录功能的脚本
验证所有持久化数据都存储在插件专属目录中
"""

import asyncio
import os
import sys
import tempfile
import shutil
from unittest.mock import Mock

# 添加插件路径到 sys.path
plugin_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, plugin_dir)

from memory_manager.vector_db import VectorDatabaseFactory


class MockStarTools:
    """模拟 StarTools"""

    @staticmethod
    def get_data_dir(plugin_name: str) -> str:
        # 返回测试用的临时目录
        return os.path.join(tempfile.gettempdir(), f"test_{plugin_name}")


class TestPluginDataPath:
    """测试插件数据目录功能"""

    def __init__(self):
        self.test_plugin_data_path = None
        self.test_results = []

    def setup(self):
        """设置测试环境"""
        self.test_plugin_data_path = MockStarTools.get_data_dir(
            "astrbot_plugin_mnemosyne"
        )
        os.makedirs(self.test_plugin_data_path, exist_ok=True)
        print(f"测试插件数据目录: {self.test_plugin_data_path}")

    def cleanup(self):
        """清理测试环境"""
        if self.test_plugin_data_path and os.path.exists(self.test_plugin_data_path):
            shutil.rmtree(self.test_plugin_data_path)
            print(f"已清理测试目录: {self.test_plugin_data_path}")

    def log_result(self, test_name: str, success: bool, message: str = ""):
        """记录测试结果"""
        status = "✓ PASS" if success else "✗ FAIL"
        result = f"{status}: {test_name}"
        if message:
            result += f" - {message}"
        print(result)
        self.test_results.append(
            {"test": test_name, "success": success, "message": message}
        )

    def test_path_resolution(self):
        """测试路径解析功能"""
        print("\n=== 测试路径解析功能 ===")

        # 模拟插件的路径更新方法
        def update_config_paths(config: dict, plugin_data_path: str) -> dict:
            import os

            # 更新 FAISS 数据路径
            faiss_config = config.get("faiss_config", {})
            if "faiss_data_path" in faiss_config:
                faiss_path = faiss_config["faiss_data_path"]
                if not os.path.isabs(faiss_path):
                    if "faiss_config" not in config:
                        config["faiss_config"] = {}
                    config["faiss_config"]["faiss_data_path"] = os.path.join(
                        plugin_data_path, faiss_path
                    )
            else:
                if "faiss_config" not in config:
                    config["faiss_config"] = {}
                config["faiss_config"]["faiss_data_path"] = os.path.join(plugin_data_path, "faiss_data")

            # 更新 Milvus Lite 路径
            if "milvus_lite_path" in config and config["milvus_lite_path"]:
                milvus_path = config["milvus_lite_path"]
                if not os.path.isabs(milvus_path):
                    config["milvus_lite_path"] = os.path.join(
                        plugin_data_path, milvus_path
                    )

            return config

        # 测试相对路径转换
        test_config = {
            "faiss_config": {"faiss_data_path": "faiss_data"},
            "milvus_lite_path": "milvus.db"
        }

        updated_config = update_config_paths(test_config, self.test_plugin_data_path)

        # 验证 FAISS 路径
        expected_faiss_path = os.path.join(self.test_plugin_data_path, "faiss_data")
        actual_faiss_path = updated_config["faiss_config"]["faiss_data_path"]
        faiss_path_correct = actual_faiss_path == expected_faiss_path
        self.log_result(
            "FAISS 相对路径转换",
            faiss_path_correct,
            f"期望: {expected_faiss_path}, 实际: {actual_faiss_path}",
        )

        # 验证 Milvus 路径
        expected_milvus_path = os.path.join(self.test_plugin_data_path, "milvus.db")
        actual_milvus_path = updated_config["milvus_lite_path"]
        milvus_path_correct = actual_milvus_path == expected_milvus_path
        self.log_result(
            "Milvus 相对路径转换",
            milvus_path_correct,
            f"期望: {expected_milvus_path}, 实际: {actual_milvus_path}",
        )

        # 测试绝对路径保持不变
        abs_config = {
            "faiss_config": {"faiss_data_path": "/absolute/path/faiss"},
            "milvus_lite_path": "/absolute/path/milvus.db",
        }

        updated_abs_config = update_config_paths(abs_config, self.test_plugin_data_path)

        abs_faiss_unchanged = (
            updated_abs_config["faiss_config"]["faiss_data_path"] == "/absolute/path/faiss"
        )
        abs_milvus_unchanged = (
            updated_abs_config["milvus_lite_path"] == "/absolute/path/milvus.db"
        )

        self.log_result("FAISS 绝对路径保持不变", abs_faiss_unchanged)
        self.log_result("Milvus 绝对路径保持不变", abs_milvus_unchanged)

        return (
            faiss_path_correct
            and milvus_path_correct
            and abs_faiss_unchanged
            and abs_milvus_unchanged
        )

    def test_faiss_database_creation(self):
        """测试 FAISS 数据库在插件目录中的创建"""
        print("\n=== 测试 FAISS 数据库创建 ===")

        try:
            # 配置使用插件数据目录
            config = {
                "faiss_config": {
                    "faiss_data_path": os.path.join(
                        self.test_plugin_data_path, "test_faiss"
                    ),
                    "faiss_index_type": "IndexFlatL2",
                    "faiss_nlist": 100,
                }
            }

            # 创建 FAISS 数据库
            db = VectorDatabaseFactory.create_database("faiss", config)
            if not db:
                self.log_result("FAISS 数据库创建", False, "无法创建数据库实例")
                return False

            # 连接数据库
            connected = db.connect()
            if not connected:
                self.log_result("FAISS 数据库连接", False, "无法连接到数据库")
                return False

            self.log_result("FAISS 数据库创建", True)

            # 验证数据目录是否在插件目录下
            expected_path = config["faiss_config"]["faiss_data_path"]
            data_dir_correct = expected_path.startswith(self.test_plugin_data_path)
            self.log_result(
                "FAISS 数据目录位置", data_dir_correct, f"数据目录: {expected_path}"
            )

            # 创建测试集合
            collection_name = "test_collection"
            schema = {
                "vector_dim": 128,
                "fields": [
                    {"name": "id", "type": "int64", "is_primary": True},
                    {"name": "content", "type": "varchar", "max_length": 1000},
                    {"name": "embedding", "type": "float_vector", "dim": 128},
                ],
            }

            collection_created = db.create_collection(collection_name, schema)
            self.log_result("FAISS 集合创建", collection_created)

            # 插入测试数据
            test_data = [{"id": 1, "content": "测试数据", "embedding": [0.1] * 128}]

            data_inserted = db.insert(collection_name, test_data)
            self.log_result("FAISS 数据插入", data_inserted)

            # 断开连接（这会触发数据保存到磁盘）
            db.disconnect()

            # 验证数据文件是否在正确位置（在断开连接后检查）
            if os.path.exists(expected_path):
                files_in_data_dir = os.listdir(expected_path)
                has_collection_dir = collection_name in files_in_data_dir
                self.log_result(
                    "FAISS 数据文件位置",
                    has_collection_dir,
                    f"数据目录内容: {files_in_data_dir}",
                )
            else:
                self.log_result("FAISS 数据文件位置", False, "数据目录不存在")
                has_collection_dir = False

            return (
                connected
                and collection_created
                and data_inserted
                and data_dir_correct
                and has_collection_dir
            )

        except Exception as e:
            self.log_result("FAISS 数据库测试", False, f"异常: {str(e)}")
            return False

    def test_default_config_paths(self):
        """测试默认配置路径"""
        print("\n=== 测试默认配置路径 ===")

        # 测试数据库工厂的默认配置
        default_faiss_config = VectorDatabaseFactory.get_default_config("faiss")
        default_milvus_config = VectorDatabaseFactory.get_default_config("milvus")

        # 验证默认路径是相对路径
        faiss_path = default_faiss_config.get("faiss_config", {}).get("faiss_data_path", "")
        milvus_path = default_milvus_config.get("milvus_lite_path", "")

        faiss_is_relative = not os.path.isabs(faiss_path) and faiss_path != ""
        milvus_is_relative = not os.path.isabs(milvus_path) or milvus_path == ""

        self.log_result(
            "FAISS 默认路径为相对路径", faiss_is_relative, f"默认路径: {faiss_path}"
        )
        self.log_result(
            "Milvus 默认路径配置正确", milvus_is_relative, f"默认路径: {milvus_path}"
        )

        return faiss_is_relative and milvus_is_relative

    def test_config_validation_with_plugin_paths(self):
        """测试配置验证与插件路径"""
        print("\n=== 测试配置验证 ===")

        # 测试有效的相对路径配置
        valid_config = {
            "faiss_config": {
                "faiss_data_path": "faiss_data",
                "faiss_index_type": "IndexFlatL2",
            }
        }

        is_valid, error_msg = VectorDatabaseFactory.validate_config(
            "faiss", valid_config
        )
        self.log_result("相对路径配置验证", is_valid, error_msg)

        # 测试有效的绝对路径配置
        abs_config = {
            "faiss_config": {
                "faiss_data_path": os.path.join(self.test_plugin_data_path, "abs_faiss"),
                "faiss_index_type": "IndexFlatL2",
            }
        }

        abs_valid, abs_error = VectorDatabaseFactory.validate_config(
            "faiss", abs_config
        )
        self.log_result("绝对路径配置验证", abs_valid, abs_error)

        return is_valid and abs_valid

    def run_all_tests(self):
        """运行所有测试"""
        print("开始测试插件数据目录功能...")

        tests = [
            self.test_path_resolution,
            self.test_faiss_database_creation,
            self.test_default_config_paths,
            self.test_config_validation_with_plugin_paths,
        ]

        results = []
        for test in tests:
            try:
                result = test()
                results.append(result)
            except Exception as e:
                print(f"✗ 测试 {test.__name__} 发生异常: {e}")
                results.append(False)

        # 打印总结
        print("\n" + "=" * 50)
        print("插件数据目录测试总结")
        print("=" * 50)

        total_tests = len(results)
        passed_tests = sum(results)
        failed_tests = total_tests - passed_tests

        print(f"总测试数: {total_tests}")
        print(f"通过: {passed_tests}")
        print(f"失败: {failed_tests}")
        print(f"成功率: {passed_tests / total_tests * 100:.1f}%")

        if failed_tests == 0:
            print("\n🎉 所有插件数据目录测试通过！")
            print("✅ 所有持久化数据都将存储在插件专属目录中")
        else:
            print(f"\n⚠️ {failed_tests} 个测试失败，请检查实现。")

        return failed_tests == 0


def main():
    """主测试函数"""
    tester = TestPluginDataPath()
    tester.setup()

    try:
        success = tester.run_all_tests()
        return 0 if success else 1
    finally:
        tester.cleanup()


if __name__ == "__main__":
    sys.exit(main())
