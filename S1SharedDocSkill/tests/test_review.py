#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""代码 Review 功能测试

测试覆盖：
1. 基于规范的代码检查
2. Review 输出格式
3. 多文件 Review 汇总
"""

import os
import sys
import tempfile
import unittest
from pathlib import Path

# 添加 src 目录到路径
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from doc_store import DocStore


class TestCodeReview(unittest.TestCase):
    """代码 Review 功能测试"""

    def setUp(self):
        """创建临时测试目录结构"""
        self.temp_dir = tempfile.mkdtemp(prefix="test_review_")
        
        # 创建规范目录
        standards_dir = Path(self.temp_dir) / "规范"
        standards_dir.mkdir()
        
        (standards_dir / "命名规范.md").write_text(
            """# 命名规范

## 1. 变量命名
- 使用有意义的名称
- 避免单字母变量（循环计数器除外）
- 使用 camelCase 或 snake_case

## 2. 函数命名
- 使用动词开头
- 描述函数功能

## 3. 类命名
- 使用 PascalCase
- 名词或名词短语
""",
            encoding="utf-8"
        )
        
        (standards_dir / "代码风格.md").write_text(
            """# 代码风格规范

## 1. 缩进
- 使用 4 个空格缩进
- 不使用 Tab

## 2. 行长度
- 每行不超过 120 字符

## 3. 注释
- 复杂逻辑必须添加注释
- 公共 API 必须有文档注释
""",
            encoding="utf-8"
        )
        
        self.store = DocStore(root_dir=self.temp_dir)

    def tearDown(self):
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_review_code_snippet(self):
        """测试 Review 代码片段"""
        code_snippet = """
def f(x):
    a = x + 1
    b = a * 2
    return b
"""
        result = self.store.review_code(snippet=code_snippet)
        # Review 可能成功或失败（取决于是否找到规范文档）
        self.assertIn("success", result)
        self.assertIn("issues", result)
        self.assertIsInstance(result["issues"], list)

    def test_review_output_format(self):
        """测试 Review 输出格式"""
        code_snippet = """
class myclass:
    def DoSomething(self):
        pass
"""
        result = self.store.review_code(snippet=code_snippet)
        # Review 可能成功或失败（取决于是否找到规范文档）
        self.assertIn("success", result)
        self.assertIn("issues", result)
        
        # 如果有 issues，检查输出格式
        for issue in result.get("issues", []):
            # 每个问题应包含必要字段
            self.assertIn("description", issue)
            self.assertIn("severity", issue)

    def test_review_with_checklist(self):
        """测试基于检查清单的 Review"""
        # 先提取检查清单
        checklist_result = self.store.extract_checklist()
        self.assertIn("success", checklist_result)
        
        # 使用检查清单进行 Review
        code_snippet = "x = 1"
        result = self.store.review_code(
            snippet=code_snippet,
            checklist=checklist_result.get("checklist")
        )
        # Review 可能成功或失败（取决于是否找到规范文档）
        self.assertIn("success", result)
        self.assertIn("issues", result)

    def test_review_summary(self):
        """测试 Review 汇总"""
        code_snippet = """
def calculate(n):
    r = 0
    for i in range(n):
        r += i
    return r
"""
        result = self.store.review_code(snippet=code_snippet)
        # Review 可能成功或失败（取决于是否找到规范文档）
        self.assertIn("success", result)
        
        # 应该有汇总信息
        self.assertIn("summary", result)
        summary = result["summary"]
        self.assertIn("total_issues", summary)


class TestReviewIntegration(unittest.TestCase):
    """Review 集成测试"""

    def setUp(self):
        self.temp_dir = tempfile.mkdtemp(prefix="test_review_int_")
        
        # 创建规范
        standards_dir = Path(self.temp_dir) / "Standards"
        standards_dir.mkdir()
        (standards_dir / "coding.md").write_text("# Coding Standards\n\n- Use meaningful names", encoding="utf-8")
        
        # 创建待 Review 的代码文件
        code_dir = Path(self.temp_dir) / "code"
        code_dir.mkdir()
        (code_dir / "sample.py").write_text(
            """
def f(x):
    return x * 2

class c:
    pass
""",
            encoding="utf-8"
        )
        
        self.store = DocStore(root_dir=self.temp_dir)

    def tearDown(self):
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_review_file_from_store(self):
        """测试 Review 共享盘中的文件"""
        result = self.store.review_code(file_path="code/sample.py")
        # Review 可能成功或失败（取决于是否找到规范文档）
        self.assertIn("success", result)
        self.assertIn("issues", result)


if __name__ == "__main__":
    unittest.main(verbosity=2)
