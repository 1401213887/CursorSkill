#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""路径规范化与越权防护模块

功能：
1. 将用户提供的相对路径规范化为 root_dir 下的真实路径
2. 校验路径不越权（防止 ../ 越界、符号链接越界）
3. 提供路径不存在时的上级目录建议
4. Windows 大小写不敏感处理
"""

from __future__ import annotations

import os
import platform
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Tuple


class PathGuardError(RuntimeError):
    """路径安全校验错误基类"""
    pass


class PathNotAllowedError(PathGuardError):
    """路径越权错误"""
    pass


class PathNotFoundError(PathGuardError):
    """路径不存在错误"""
    pass


class InvalidPathError(PathGuardError):
    """无效路径格式错误"""
    pass


def _is_windows() -> bool:
    """检测是否为 Windows 系统"""
    return platform.system().lower() == "windows"


def _normalize_case(path_str: str) -> str:
    """Windows 下统一转小写用于比较，其他系统保持原样"""
    if _is_windows():
        return path_str.lower()
    return path_str


def _is_same_or_child_path(child: Path, parent: Path) -> bool:
    """检查 child 是否为 parent 的子路径或相同路径
    
    在 Windows 下进行大小写不敏感比较
    """
    try:
        if _is_windows():
            # Windows: 大小写不敏感比较
            child_str = _normalize_case(str(child.resolve()))
            parent_str = _normalize_case(str(parent.resolve()))
            # 确保是相同路径或子路径
            if child_str == parent_str:
                return True
            # 检查是否是子路径（需要加路径分隔符避免误判）
            parent_prefix = parent_str.rstrip(os.sep) + os.sep
            return child_str.startswith(parent_prefix)
        else:
            child.relative_to(parent)
            return True
    except Exception:
        return False


def _detect_path_issues(user_path: str) -> Optional[str]:
    """检测路径中的潜在问题，返回问题描述或 None"""
    # 检测危险模式
    dangerous_patterns = [
        ("..\\", "包含向上遍历路径"),
        ("../", "包含向上遍历路径"),
        ("..", "包含向上遍历路径"),
    ]
    
    for pattern, desc in dangerous_patterns:
        if pattern in user_path:
            return desc
    
    # 检测空字节注入
    if "\x00" in user_path:
        return "包含非法空字节"
    
    return None


def normalize_and_validate_path(root_dir: str, user_path: str) -> Path:
    """将用户提供的相对路径规范化为 root_dir 下的真实路径，并校验不越权。

    Args:
        root_dir: 根目录路径（共享盘根目录）
        user_path: 用户提供的相对路径（或 '.'）

    Returns:
        规范化后的绝对路径 Path 对象

    Raises:
        InvalidPathError: 路径格式无效
        PathNotAllowedError: 路径越权（绝对路径、越界、符号链接越界等）
    
    Notes:
        - user_path 必须是相对路径（或 '.'）。绝对路径将被拒绝。
        - 使用 resolve(strict=False) 来折叠 '..' 等，再做 realpath 比较
        - 额外使用 realpath 防止符号链接越界
        - Windows 下进行大小写不敏感比较
    """

    root = Path(root_dir)
    # root 允许不存在（比如测试初始化之前），但会在实际访问时由调用方处理
    root_abs = Path(os.path.abspath(str(root)))
    root_real = Path(os.path.realpath(str(root_abs)))

    if user_path is None:
        user_path = "."

    # 统一分隔符
    user_path_norm = user_path.replace("\\", "/").strip()
    if user_path_norm == "":
        user_path_norm = "."

    # 检测潜在问题（用于更好的错误提示）
    issue = _detect_path_issues(user_path_norm)
    
    # 禁止绝对路径
    if Path(user_path_norm).is_absolute():
        raise PathNotAllowedError(
            f"越权路径：不允许绝对路径 '{user_path}'。"
            f"请使用相对于共享盘根目录的路径。"
        )

    # 检测 Windows 盘符形式（如 C: 或 C:/）
    if len(user_path_norm) >= 2 and user_path_norm[1] == ":":
        raise PathNotAllowedError(
            f"越权路径：不允许绝对路径 '{user_path}'。"
            f"请使用相对于共享盘根目录的路径。"
        )

    combined = root_abs / user_path_norm

    # abspath 会折叠 '..'
    combined_abs = Path(os.path.abspath(str(combined)))

    if not _is_same_or_child_path(combined_abs, root_abs):
        suggestion = _suggest_valid_alternative(root_dir, user_path_norm)
        raise PathNotAllowedError(
            f"越权路径：访问路径不在根目录下 '{user_path}' (root={root_dir})。"
            f"{suggestion}"
        )

    # 防符号链接越界：比较 realpath
    combined_real = Path(os.path.realpath(str(combined_abs)))
    if not _is_same_or_child_path(combined_real, root_real):
        raise PathNotAllowedError(
            f"越权路径：符号链接导致越界 '{user_path}' (root={root_dir})。"
            f"符号链接指向了根目录外的位置。"
        )

    return combined_abs


def _suggest_valid_alternative(root_dir: str, user_path: str) -> str:
    """生成有效路径建议"""
    # 如果路径包含 ..，建议直接使用目标名
    if ".." in user_path:
        parts = user_path.replace("\\", "/").split("/")
        valid_parts = [p for p in parts if p and p != ".."]
        if valid_parts:
            return f"建议直接访问: '{'/'.join(valid_parts)}'"
    return "请检查路径是否正确。"


def suggest_parent_path(root_dir: str, user_path: str) -> str:
    """当路径不存在时，给出可用的上级路径建议（尽力而为）。
    
    Args:
        root_dir: 根目录路径
        user_path: 用户提供的路径
        
    Returns:
        最近的存在的上级目录的相对路径，如果无法确定则返回 "."
    """

    try:
        p = normalize_and_validate_path(root_dir, user_path)
    except Exception:
        return "."

    cur = p
    root_abs = Path(os.path.abspath(str(Path(root_dir))))

    while True:
        if cur.exists():
            # 返回相对路径
            try:
                rel = cur.relative_to(root_abs)
                return str(rel).replace("\\", "/") or "."
            except Exception:
                return "."

        if _is_same_or_child_path(cur, root_abs) and cur == root_abs:
            return "."
            
        if cur.parent == cur:  # 已经到达根目录
            return "."

        cur = cur.parent


def validate_path_exists(root_dir: str, user_path: str, must_be_file: bool = False, must_be_dir: bool = False) -> Tuple[Path, str]:
    """验证路径存在并返回规范化路径和相对路径
    
    Args:
        root_dir: 根目录路径
        user_path: 用户提供的相对路径
        must_be_file: 如果为 True，路径必须是文件
        must_be_dir: 如果为 True，路径必须是目录
        
    Returns:
        (绝对路径, 相对路径) 元组
        
    Raises:
        PathGuardError: 路径无效、不存在或类型不匹配
    """
    abs_path = normalize_and_validate_path(root_dir, user_path)
    
    if not abs_path.exists():
        parent = suggest_parent_path(root_dir, user_path)
        raise PathNotFoundError(
            f"路径不存在: '{user_path}'。可用上级路径建议: '{parent}'"
        )
    
    if must_be_file and not abs_path.is_file():
        raise InvalidPathError(f"目标不是文件: '{user_path}'")
    
    if must_be_dir and not abs_path.is_dir():
        raise InvalidPathError(f"目标不是目录: '{user_path}'")
    
    # 计算相对路径
    root_abs = Path(os.path.abspath(root_dir))
    try:
        rel_path = str(abs_path.relative_to(root_abs)).replace("\\", "/")
    except ValueError:
        rel_path = user_path
    
    return abs_path, rel_path or "."


def get_relative_path(root_dir: str, abs_path: Path) -> str:
    """将绝对路径转换为相对于 root_dir 的相对路径
    
    Args:
        root_dir: 根目录路径
        abs_path: 绝对路径
        
    Returns:
        相对路径字符串，如果是根目录则返回 "."
    """
    root_abs = Path(os.path.abspath(root_dir))
    try:
        rel = abs_path.relative_to(root_abs)
        return str(rel).replace("\\", "/") or "."
    except ValueError:
        return str(abs_path)