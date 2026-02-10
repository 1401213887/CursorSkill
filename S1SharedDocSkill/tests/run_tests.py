#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""SharedDriveDocSkill 测试运行器

用法:
    python run_tests.py [options]

选项:
    --skip-integration  跳过集成测试（不访问真实共享盘）
    --verbose, -v       详细输出
    --pattern PATTERN   只运行匹配的测试（如 test_path*）
"""

import os
import sys
import argparse
import unittest
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description="SharedDriveDocSkill 测试运行器")
    parser.add_argument(
        "--skip-integration",
        action="store_true",
        help="跳过集成测试（不访问真实共享盘）"
    )
    parser.add_argument(
        "-v", "--verbose",
        action="store_true",
        help="详细输出"
    )
    parser.add_argument(
        "--pattern",
        default="test*.py",
        help="测试文件匹配模式（默认: test*.py）"
    )
    
    args = parser.parse_args()
    
    # 设置环境变量控制集成测试
    if args.skip_integration:
        os.environ["SKIP_INTEGRATION_TESTS"] = "1"
        print("[INFO] 跳过集成测试（不访问真实共享盘）\n")
    else:
        os.environ.pop("SKIP_INTEGRATION_TESTS", None)
        print("[INFO] 包含集成测试（将尝试访问 W:\\S1UnrealDoc）\n")
    
    # 获取测试目录
    test_dir = Path(__file__).parent
    
    # 添加 src 目录到路径
    src_dir = test_dir.parent / "src"
    if str(src_dir) not in sys.path:
        sys.path.insert(0, str(src_dir))
    
    # 发现并运行测试
    loader = unittest.TestLoader()
    suite = loader.discover(str(test_dir), pattern=args.pattern)
    
    # 运行测试
    verbosity = 2 if args.verbose else 1
    runner = unittest.TextTestRunner(verbosity=verbosity)
    
    print("=" * 60)
    print("SharedDriveDocSkill 单元测试")
    print("=" * 60)
    print()
    
    result = runner.run(suite)
    
    print()
    print("=" * 60)
    print("测试汇总")
    print("=" * 60)
    print(f"运行: {result.testsRun}")
    print(f"成功: {result.testsRun - len(result.failures) - len(result.errors)}")
    print(f"失败: {len(result.failures)}")
    print(f"错误: {len(result.errors)}")
    print(f"跳过: {len(result.skipped)}")
    
    # 返回退出码
    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    sys.exit(main())
