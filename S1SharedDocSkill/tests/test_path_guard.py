#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""路径规范化与越权防护模块测试

测试覆盖：
1. 正常相对路径规范化
2. 越权路径拒绝（..、绝对路径、盘符路径）
3. Windows 大小写不敏感
4. 符号链接越界防护（如有条件）
5. 路径不存在时的上级建议
"""

import os
import sys
import tempfile
import unittest
from pathlib import Path

# 添加 src 目录到路径
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from path_guard import (
    normalize_and_validate_path,
    suggest_parent_path,
    validate_path_exists,
    get_relative_path,
    PathNotAllowedError,
    PathNotFoundError,
    InvalidPathError,
)


class TestNormalizeAndValidatePath(unittest.TestCase):
    """路径规范化与验证测试"""

    def setUp(self):
        """创建临时测试目录结构"""
        self.temp_dir = tempfile.mkdtemp(prefix="test_shared_")
        self.root_dir = self.temp_dir
        
        # 创建测试目录结构
        # root/
        #   docs/
        #     readme.txt
        #     规范/
        #       coding.md
        #   data/
        #     sample.json
        
        docs_dir = Path(self.root_dir) / "docs"
        docs_dir.mkdir()
        (docs_dir / "readme.txt").write_text("Hello", encoding="utf-8")
        
        standards_dir = docs_dir / "规范"
        standards_dir.mkdir()
        (standards_dir / "coding.md").write_text("# 编码规范", encoding="utf-8")
        
        data_dir = Path(self.root_dir) / "data"
        data_dir.mkdir()
        (data_dir / "sample.json").write_text('{"key": "value"}', encoding="utf-8")

    def tearDown(self):
        """清理临时目录"""
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_normalize_root_path(self):
        """测试根目录路径（'.' 或 ''）"""
        result = normalize_and_validate_path(self.root_dir, ".")
        self.assertEqual(str(result), os.path.abspath(self.root_dir))
        
        result = normalize_and_validate_path(self.root_dir, "")
        self.assertEqual(str(result), os.path.abspath(self.root_dir))

    def test_normalize_relative_path(self):
        """测试正常相对路径"""
        result = normalize_and_validate_path(self.root_dir, "docs")
        expected = Path(self.root_dir) / "docs"
        self.assertEqual(str(result), str(expected.resolve()))
        
        result = normalize_and_validate_path(self.root_dir, "docs/readme.txt")
        expected = Path(self.root_dir) / "docs" / "readme.txt"
        self.assertEqual(str(result), str(expected.resolve()))

    def test_normalize_backslash_path(self):
        """测试反斜杠路径（Windows 风格）"""
        result = normalize_and_validate_path(self.root_dir, "docs\\规范\\coding.md")
        expected = Path(self.root_dir) / "docs" / "规范" / "coding.md"
        self.assertEqual(str(result), str(expected.resolve()))

    def test_reject_parent_traversal(self):
        """测试拒绝父目录遍历（..）"""
        with self.assertRaises(PathNotAllowedError) as ctx:
            normalize_and_validate_path(self.root_dir, "../outside")
        self.assertIn("越权", str(ctx.exception))
        
        with self.assertRaises(PathNotAllowedError):
            normalize_and_validate_path(self.root_dir, "docs/../../outside")

    def test_reject_absolute_path(self):
        """测试拒绝绝对路径"""
        with self.assertRaises(PathNotAllowedError) as ctx:
            normalize_and_validate_path(self.root_dir, "/etc/passwd")
        self.assertIn("越权", str(ctx.exception))

    def test_reject_windows_drive_path(self):
        """测试拒绝 Windows 盘符路径"""
        with self.assertRaises(PathNotAllowedError) as ctx:
            normalize_and_validate_path(self.root_dir, "C:/Windows/System32")
        self.assertIn("绝对路径", str(ctx.exception))
        
        with self.assertRaises(PathNotAllowedError):
            normalize_and_validate_path(self.root_dir, "D:\\secret")

    def test_case_insensitive_on_windows(self):
        """测试 Windows 下大小写不敏感"""
        if sys.platform != "win32":
            self.skipTest("仅在 Windows 下测试大小写不敏感")
        
        # 两种大小写应该都能访问
        result1 = normalize_and_validate_path(self.root_dir, "DOCS")
        result2 = normalize_and_validate_path(self.root_dir, "docs")
        # Windows 下路径应该都能规范化成功（实际文件系统比较时不敏感）
        self.assertIsNotNone(result1)
        self.assertIsNotNone(result2)


class TestSuggestParentPath(unittest.TestCase):
    """路径建议测试"""

    def setUp(self):
        self.temp_dir = tempfile.mkdtemp(prefix="test_suggest_")
        self.root_dir = self.temp_dir
        
        docs_dir = Path(self.root_dir) / "docs"
        docs_dir.mkdir()
        (docs_dir / "readme.txt").write_text("Hello", encoding="utf-8")

    def tearDown(self):
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_suggest_existing_parent(self):
        """测试建议存在的上级目录"""
        # docs 存在，docs/nonexistent 不存在
        suggestion = suggest_parent_path(self.root_dir, "docs/nonexistent/file.txt")
        self.assertEqual(suggestion, "docs")

    def test_suggest_root_for_invalid(self):
        """测试无效路径返回根目录"""
        suggestion = suggest_parent_path(self.root_dir, "../invalid")
        self.assertEqual(suggestion, ".")


class TestValidatePathExists(unittest.TestCase):
    """路径存在性验证测试"""

    def setUp(self):
        self.temp_dir = tempfile.mkdtemp(prefix="test_validate_")
        self.root_dir = self.temp_dir
        
        docs_dir = Path(self.root_dir) / "docs"
        docs_dir.mkdir()
        (docs_dir / "readme.txt").write_text("Hello", encoding="utf-8")

    def tearDown(self):
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_validate_existing_file(self):
        """测试验证存在的文件"""
        abs_path, rel_path = validate_path_exists(self.root_dir, "docs/readme.txt", must_be_file=True)
        self.assertTrue(abs_path.exists())
        self.assertTrue(abs_path.is_file())
        self.assertEqual(rel_path, "docs/readme.txt")

    def test_validate_existing_dir(self):
        """测试验证存在的目录"""
        abs_path, rel_path = validate_path_exists(self.root_dir, "docs", must_be_dir=True)
        self.assertTrue(abs_path.exists())
        self.assertTrue(abs_path.is_dir())
        self.assertEqual(rel_path, "docs")

    def test_reject_nonexistent_path(self):
        """测试拒绝不存在的路径"""
        with self.assertRaises(PathNotFoundError) as ctx:
            validate_path_exists(self.root_dir, "nonexistent/file.txt")
        self.assertIn("不存在", str(ctx.exception))

    def test_reject_file_as_dir(self):
        """测试拒绝文件当目录访问"""
        with self.assertRaises(InvalidPathError) as ctx:
            validate_path_exists(self.root_dir, "docs/readme.txt", must_be_dir=True)
        self.assertIn("不是目录", str(ctx.exception))

    def test_reject_dir_as_file(self):
        """测试拒绝目录当文件访问"""
        with self.assertRaises(InvalidPathError) as ctx:
            validate_path_exists(self.root_dir, "docs", must_be_file=True)
        self.assertIn("不是文件", str(ctx.exception))


class TestGetRelativePath(unittest.TestCase):
    """相对路径转换测试"""

    def setUp(self):
        self.temp_dir = tempfile.mkdtemp(prefix="test_rel_")
        self.root_dir = self.temp_dir

    def tearDown(self):
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_get_relative_path(self):
        """测试获取相对路径"""
        abs_path = Path(self.root_dir) / "docs" / "readme.txt"
        rel = get_relative_path(self.root_dir, abs_path)
        self.assertEqual(rel, "docs/readme.txt")

    def test_get_relative_root(self):
        """测试根目录返回 '.'"""
        abs_path = Path(self.root_dir)
        rel = get_relative_path(self.root_dir, abs_path)
        self.assertEqual(rel, ".")


if __name__ == "__main__":
    unittest.main(verbosity=2)
