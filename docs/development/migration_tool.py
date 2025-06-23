#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Mnemosyne 插件迁移工具
帮助用户从旧版本迁移到新版本，支持数据库后端迁移
"""

import asyncio
import os
import sys
import json
import argparse
from typing import Dict, Any, Optional
import shutil
from datetime import datetime

# 添加插件路径到 sys.path
plugin_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, plugin_dir)

from memory_manager.vector_db import VectorDatabaseFactory


class MnemosyneMigrationTool:
    """Mnemosyne 迁移工具"""

    def __init__(self):
        self.backup_dir = None

    def create_backup(self, config_path: str) -> bool:
        """创建配置备份"""
        try:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            self.backup_dir = f"mnemosyne_backup_{timestamp}"
            os.makedirs(self.backup_dir, exist_ok=True)

            # 备份配置文件
            if os.path.exists(config_path):
                shutil.copy2(
                    config_path, os.path.join(self.backup_dir, "config_backup.json")
                )
                print(f"✓ 配置文件已备份到: {self.backup_dir}")

            return True
        except Exception as e:
            print(f"✗ 创建备份失败: {e}")
            return False

    def load_old_config(self, config_path: str) -> Optional[Dict[str, Any]]:
        """加载旧版本配置"""
        try:
            if not os.path.exists(config_path):
                print(f"✗ 配置文件不存在: {config_path}")
                return None

            with open(config_path, "r", encoding="utf-8") as f:
                config = json.load(f)

            print(f"✓ 已加载旧配置文件")
            return config
        except Exception as e:
            print(f"✗ 加载配置文件失败: {e}")
            return None

    def migrate_config(self, old_config: Dict[str, Any]) -> Dict[str, Any]:
        """迁移配置到新格式"""
        print("\n开始迁移配置...")

        new_config = old_config.copy()

        # 添加新的向量数据库类型配置
        if "vector_database_type" not in new_config:
            # 如果有 Milvus 配置，默认使用 Milvus
            if old_config.get("milvus_lite_path") or old_config.get("address"):
                new_config["vector_database_type"] = "milvus"
                print("✓ 检测到 Milvus 配置，设置数据库类型为 milvus")
            else:
                # 否则默认使用 FAISS
                new_config["vector_database_type"] = "faiss"
                print("✓ 未检测到 Milvus 配置，设置数据库类型为 faiss")

        # 添加 FAISS 默认配置
        if "faiss_config" not in new_config:
            new_config["faiss_config"] = {}

        faiss_config = new_config["faiss_config"]
        if "faiss_data_path" not in faiss_config:
            faiss_config["faiss_data_path"] = "faiss_data"
        if "faiss_index_type" not in faiss_config:
            faiss_config["faiss_index_type"] = "IndexFlatL2"
        if "faiss_nlist" not in faiss_config:
            faiss_config["faiss_nlist"] = 100

        # 添加嵌入服务提供商ID配置
        if "embedding_provider_id" not in new_config:
            new_config["embedding_provider_id"] = ""
            print("✓ 添加了 embedding_provider_id 配置项")

        # 更新版本信息
        new_config["_migration_version"] = "0.6.0"
        new_config["_migration_date"] = datetime.now().isoformat()

        print("✓ 配置迁移完成")
        return new_config

    def save_new_config(self, config: Dict[str, Any], config_path: str) -> bool:
        """保存新配置"""
        try:
            with open(config_path, "w", encoding="utf-8") as f:
                json.dump(config, f, ensure_ascii=False, indent=2)

            print(f"✓ 新配置已保存到: {config_path}")
            return True
        except Exception as e:
            print(f"✗ 保存配置失败: {e}")
            return False

    async def migrate_database(
        self, old_config: Dict[str, Any], new_config: Dict[str, Any]
    ) -> bool:
        """迁移数据库数据"""
        print("\n开始数据库迁移...")

        old_db_type = "milvus"  # 旧版本只支持 Milvus
        new_db_type = new_config.get("vector_database_type", "milvus")

        if old_db_type == new_db_type:
            print("✓ 数据库类型未变更，无需迁移数据")
            return True

        print(f"检测到数据库类型变更: {old_db_type} -> {new_db_type}")

        try:
            # 创建源数据库连接
            source_db = VectorDatabaseFactory.create_database(old_db_type, old_config)
            if not source_db or not source_db.connect():
                print("✗ 无法连接到源数据库")
                return False

            # 创建目标数据库连接
            target_db = VectorDatabaseFactory.create_database(new_db_type, new_config)
            if not target_db or not target_db.connect():
                print("✗ 无法连接到目标数据库")
                source_db.disconnect()
                return False

            # 获取集合名称
            collection_name = old_config.get("collection_name", "mnemosyne_default")

            # 检查源集合是否存在
            if not source_db.has_collection(collection_name):
                print(f"✓ 源数据库中不存在集合 '{collection_name}'，无需迁移")
                source_db.disconnect()
                target_db.disconnect()
                return True

            # 执行数据迁移
            print(f"开始迁移集合 '{collection_name}' 的数据...")
            success = VectorDatabaseFactory.migrate_data(
                source_db=source_db,
                target_db=target_db,
                collection_name=collection_name,
                batch_size=1000,
            )

            # 断开连接
            source_db.disconnect()
            target_db.disconnect()

            if success:
                print("✓ 数据库迁移完成")
            else:
                print("✗ 数据库迁移失败")

            return success

        except Exception as e:
            print(f"✗ 数据库迁移过程中发生错误: {e}")
            return False

    def validate_migration(self, config: Dict[str, Any]) -> bool:
        """验证迁移结果"""
        print("\n验证迁移结果...")

        # 验证配置完整性
        required_fields = [
            "vector_database_type",
            "faiss_data_path",
            "faiss_index_type",
            "embedding_provider_id",
        ]

        missing_fields = [field for field in required_fields if field not in config]
        if missing_fields:
            print(f"✗ 配置缺少必要字段: {missing_fields}")
            return False

        # 验证数据库配置
        db_type = config["vector_database_type"]
        is_valid, error_msg = VectorDatabaseFactory.validate_config(db_type, config)
        if not is_valid:
            print(f"✗ 数据库配置验证失败: {error_msg}")
            return False

        print("✓ 迁移验证通过")
        return True

    def print_migration_summary(self, success: bool):
        """打印迁移总结"""
        print("\n" + "=" * 50)
        print("迁移总结")
        print("=" * 50)

        if success:
            print("✓ 迁移成功完成！")
            print("\n新功能:")
            print("  - 支持 FAISS 向量数据库（高性能本地存储）")
            print("  - 支持 AstrBot 原生嵌入服务")
            print("  - 改进的错误处理和日志记录")
            print("  - 更好的配置验证")

            if self.backup_dir:
                print(f"\n备份文件位置: {self.backup_dir}")
                print("如果遇到问题，可以从备份恢复")
        else:
            print("✗ 迁移失败")
            print("请检查错误信息并手动修复配置")
            if self.backup_dir:
                print(f"可以从备份恢复: {self.backup_dir}")


async def main():
    """主函数"""
    parser = argparse.ArgumentParser(description="Mnemosyne 插件迁移工具")
    parser.add_argument("--config", "-c", required=True, help="配置文件路径")
    parser.add_argument(
        "--target-db",
        "-t",
        choices=["milvus", "faiss"],
        help="目标数据库类型（可选，默认保持现有类型）",
    )
    parser.add_argument("--no-backup", action="store_true", help="跳过备份创建")
    parser.add_argument(
        "--config-only", action="store_true", help="仅迁移配置，不迁移数据"
    )

    args = parser.parse_args()

    print("Mnemosyne 插件迁移工具 v0.6.0")
    print("=" * 40)

    migrator = MnemosyneMigrationTool()

    # 创建备份
    if not args.no_backup:
        if not migrator.create_backup(args.config):
            print("备份创建失败，是否继续？(y/N): ", end="")
            if input().lower() != "y":
                return

    # 加载旧配置
    old_config = migrator.load_old_config(args.config)
    if not old_config:
        return

    # 迁移配置
    new_config = migrator.migrate_config(old_config)

    # 如果指定了目标数据库类型，更新配置
    if args.target_db:
        new_config["vector_database_type"] = args.target_db
        print(f"✓ 设置目标数据库类型为: {args.target_db}")

    # 保存新配置
    if not migrator.save_new_config(new_config, args.config):
        return

    # 迁移数据库数据（如果需要）
    data_migration_success = True
    if not args.config_only:
        data_migration_success = await migrator.migrate_database(old_config, new_config)

    # 验证迁移结果
    validation_success = migrator.validate_migration(new_config)

    # 打印总结
    overall_success = data_migration_success and validation_success
    migrator.print_migration_summary(overall_success)

    return 0 if overall_success else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
