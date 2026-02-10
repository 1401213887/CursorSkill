#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""S1SharedDocSkill - AI 优化的共享盘资料库 CLI

该脚本提供共享盘文档访问/上传/检索/规范Review能力。

约定：
- 默认共享盘根目录：W:\\S1UnrealSharedDoc
- --ai-mode: stdout 仅输出一个 JSON 对象（便于被上层解析）
- 非 ai-mode: stdout 输出人类可读内容；stderr 可输出提示
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


# ============================================================================
# Windows 中文路径编码修复
# ============================================================================
def _fix_windows_encoding() -> None:
    """修复 Windows 控制台中文编码问题
    
    在 Windows 上，命令行参数默认使用系统编码（通常是 GBK/CP936），
    当路径包含中文时可能导致乱码。此函数确保 stdin/stdout/stderr
    使用 UTF-8 编码，并重新解码命令行参数。
    """
    if sys.platform != 'win32':
        return
    
    # 设置环境变量，确保 Python 使用 UTF-8
    os.environ.setdefault('PYTHONIOENCODING', 'utf-8')
    
    # 尝试设置 Windows 控制台代码页为 UTF-8 (65001)
    try:
        import ctypes
        kernel32 = ctypes.windll.kernel32
        # SetConsoleOutputCP(65001) - 设置输出代码页为 UTF-8
        kernel32.SetConsoleOutputCP(65001)
        # SetConsoleCP(65001) - 设置输入代码页为 UTF-8
        kernel32.SetConsoleCP(65001)
    except Exception:
        pass
    
    # 重新配置 stdout/stderr 为 UTF-8（如果尚未配置）
    try:
        if hasattr(sys.stdout, 'reconfigure'):
            sys.stdout.reconfigure(encoding='utf-8', errors='replace')
        if hasattr(sys.stderr, 'reconfigure'):
            sys.stderr.reconfigure(encoding='utf-8', errors='replace')
    except Exception:
        pass  # 某些环境下可能不支持 reconfigure
    
    # 尝试修复命令行参数编码
    # 当从某些终端传入时，中文参数可能被错误解码
    try:
        _fix_argv_encoding()
    except Exception:
        pass  # 如果修复失败，继续使用原始参数


def _fix_argv_encoding() -> None:
    """尝试修复 sys.argv 中的中文编码问题
    
    在某些 Windows 环境中，命令行参数可能以错误的编码传入。
    此函数尝试检测并修复这种情况。
    """
    if sys.platform != 'win32':
        return
    
    # 方法1: 使用 Windows API 直接获取 Unicode 命令行
    try:
        import ctypes
        from ctypes import wintypes
        
        # GetCommandLineW 返回完整的 Unicode 命令行
        GetCommandLineW = ctypes.windll.kernel32.GetCommandLineW
        GetCommandLineW.restype = wintypes.LPWSTR
        
        # CommandLineToArgvW 将命令行拆分为参数数组
        CommandLineToArgvW = ctypes.windll.shell32.CommandLineToArgvW
        CommandLineToArgvW.argtypes = [wintypes.LPCWSTR, ctypes.POINTER(ctypes.c_int)]
        CommandLineToArgvW.restype = ctypes.POINTER(wintypes.LPWSTR)
        
        LocalFree = ctypes.windll.kernel32.LocalFree
        
        cmd_line = GetCommandLineW()
        argc = ctypes.c_int(0)
        argv_ptr = CommandLineToArgvW(cmd_line, ctypes.byref(argc))
        
        if argv_ptr:
            try:
                # 提取所有参数
                new_argv = [argv_ptr[i] for i in range(argc.value)]
                
                # 只有当参数数量匹配时才替换
                # （某些情况下 Python 可能已经正确处理了参数）
                if len(new_argv) == len(sys.argv):
                    # 检查是否有实际差异（即是否需要修复）
                    needs_fix = False
                    for i in range(len(sys.argv)):
                        if sys.argv[i] != new_argv[i]:
                            # 检查是否是编码问题导致的差异
                            # 如果原参数包含乱码字符，则需要修复
                            try:
                                sys.argv[i].encode('utf-8')
                            except UnicodeEncodeError:
                                needs_fix = True
                                break
                            # 如果原参数是乱码但新参数是有效中文，也需要修复
                            if _looks_like_garbled(sys.argv[i]) and not _looks_like_garbled(new_argv[i]):
                                needs_fix = True
                                break
                    
                    if needs_fix:
                        sys.argv = new_argv
            finally:
                LocalFree(argv_ptr)
    except Exception:
        pass  # Windows API 调用失败，使用备选方案


def _looks_like_garbled(s: str) -> bool:
    """检测字符串是否看起来像乱码
    
    乱码通常包含大量不常见的 Unicode 字符或替换字符。
    """
    if not s:
        return False
    
    # 统计可疑字符
    suspicious_count = 0
    for ch in s:
        code = ord(ch)
        # 替换字符
        if code == 0xFFFD:
            suspicious_count += 1
        # 私用区字符
        elif 0xE000 <= code <= 0xF8FF:
            suspicious_count += 1
        # 控制字符（除了常见的 \t \n \r）
        elif code < 32 and code not in (9, 10, 13):
            suspicious_count += 1
    
    # 如果超过 20% 的字符是可疑的，认为是乱码
    return suspicious_count > len(s) * 0.2


# 在模块加载时立即执行编码修复
_fix_windows_encoding()

from config_manager import ConfigManager
from path_guard import normalize_and_validate_path, PathGuardError
from doc_store import (
    list_dir,
    read_text_file,
    upload_file,
    search_documents,
    search_by_query,
    review_code,
)


def _ai_response(tool: str, data: Any) -> Dict[str, Any]:
    return {
        "schema_version": "1.0",
        "tool": tool,
        "data": data,
    }


def _print_json(obj: Any) -> None:
    """输出 JSON 到 stdout
    
    在 Windows 上，由于终端/管道可能使用非 UTF-8 编码捕获输出，
    直接输出中文字符可能导致乱码。
    
    解决方案：使用 ensure_ascii=True 输出 Unicode 转义序列 (\\uXXXX)，
    JSON 解析器会自动将这些转义序列还原为正确的中文字符。
    """
    if sys.platform == 'win32':
        # Windows: 使用 ASCII 转义输出，避免任何编码问题
        # 中文字符会被转义为 \uXXXX 形式
        json_str = json.dumps(obj, ensure_ascii=True)
        print(json_str)
    else:
        # 非 Windows 系统，直接输出 UTF-8
        json_str = json.dumps(obj, ensure_ascii=False)
        print(json_str)


@dataclass
class CommonArgs:
    ai_mode: bool


class AICli:
    def __init__(self) -> None:
        self.config = ConfigManager()

    def _get_root_dir(self) -> str:
        # 测试时允许覆盖 root_dir
        test_root = self.config.get("test_root_dir")
        if test_root:
            return str(test_root)
        return str(self.config.get("root_dir"))

    def cmd_list(self, args: argparse.Namespace) -> int:
        ai_mode = bool(args.ai_mode)
        root_dir = self._get_root_dir()

        try:
            result = list_dir(root_dir, args.dir)
        except PathGuardError as e:
            if ai_mode:
                _print_json(_ai_response("shared_drive.list", {"ok": False, "error": str(e)}))
            else:
                print(f"✗ {e}")
            return 1
        except Exception as e:
            if ai_mode:
                _print_json(_ai_response("shared_drive.list", {"ok": False, "error": f"内部错误: {e}"}))
            else:
                print(f"✗ 内部错误: {e}")
            return 1

        if ai_mode:
            _print_json(_ai_response("shared_drive.list", {"ok": True, "root_dir": root_dir, **result}))
        else:
            print(f"Root: {root_dir}")
            print(f"Dir:  {result['path']}")
            for it in result["items"]:
                t = "DIR " if it["is_dir"] else "FILE"
                print(f"{t}  {it['name']}  {it.get('size_bytes','-')}  {it.get('mtime','-')}")
        return 0

    def cmd_read(self, args: argparse.Namespace) -> int:
        ai_mode = bool(args.ai_mode)
        root_dir = self._get_root_dir()

        max_bytes = int(self.config.get("max_read_bytes"))
        max_lines = int(self.config.get("max_read_lines"))

        try:
            data = read_text_file(root_dir, args.file, max_bytes=max_bytes, max_lines=max_lines)
        except PathGuardError as e:
            if ai_mode:
                _print_json(_ai_response("shared_drive.read", {"ok": False, "error": str(e)}))
            else:
                print(f"✗ {e}")
            return 1
        except Exception as e:
            if ai_mode:
                _print_json(_ai_response("shared_drive.read", {"ok": False, "error": f"内部错误: {e}"}))
            else:
                print(f"✗ 内部错误: {e}")
            return 1

        if ai_mode:
            _print_json(_ai_response("shared_drive.read", {"ok": True, "root_dir": root_dir, **data}))
        else:
            print(f"Path: {data['path']}")
            if data.get("truncated"):
                print(f"[TRUNCATED] bytes={data.get('read_bytes')} lines={data.get('read_lines')}")
            print(data["content"])
        return 0

    def cmd_upload(self, args: argparse.Namespace) -> int:
        ai_mode = bool(args.ai_mode)
        root_dir = self._get_root_dir()

        upload_max_bytes = int(self.config.get("upload_max_bytes"))

        try:
            data = upload_file(
                root_dir=root_dir,
                dest_rel_path=args.dest,
                local_file=args.from_file,
                conflict=args.conflict,
                upload_max_bytes=upload_max_bytes,
            )
        except PathGuardError as e:
            if ai_mode:
                _print_json(_ai_response("shared_drive.upload", {"ok": False, "error": str(e)}))
            else:
                print(f"✗ {e}")
            return 1
        except Exception as e:
            if ai_mode:
                _print_json(_ai_response("shared_drive.upload", {"ok": False, "error": f"内部错误: {e}"}))
            else:
                print(f"✗ 内部错误: {e}")
            return 1

        if ai_mode:
            _print_json(_ai_response("shared_drive.upload", {"ok": True, "root_dir": root_dir, **data}))
        else:
            print(f"OK: {data['final_path']}")
            print(f"Size: {data['size_bytes']} bytes")
            print(f"MTime: {data['mtime']}")
            if data.get("conflict"):
                print(f"Conflict: {data['conflict']}")
        return 0

    def cmd_search(self, args: argparse.Namespace) -> int:
        """搜索共享盘文档"""
        ai_mode = bool(args.ai_mode)
        root_dir = self._get_root_dir()

        try:
            # 如果提供了 keywords 参数，使用关键词搜索
            if args.keywords:
                keywords = [k.strip() for k in args.keywords.split(",") if k.strip()]
                result = search_documents(
                    root_dir=root_dir,
                    keywords=keywords,
                    search_dir=args.dir,
                    top_k=args.top_k,
                    include_content=not args.name_only,
                )
            else:
                # 使用自然语言查询
                result = search_by_query(
                    root_dir=root_dir,
                    query=args.query,
                    search_dir=args.dir,
                    top_k=args.top_k,
                )
        except PathGuardError as e:
            if ai_mode:
                _print_json(_ai_response("shared_drive.search", {"ok": False, "error": str(e)}))
            else:
                print(f"✗ {e}")
            return 1
        except Exception as e:
            if ai_mode:
                _print_json(_ai_response("shared_drive.search", {"ok": False, "error": f"内部错误: {e}"}))
            else:
                print(f"✗ 内部错误: {e}")
            return 1

        if ai_mode:
            _print_json(_ai_response("shared_drive.search", {"ok": True, "root_dir": root_dir, **result}))
        else:
            print(f"Root: {root_dir}")
            print(f"Search Dir: {result.get('search_dir', '.')}")
            print(f"Keywords: {result.get('keywords', [])}")
            print(f"Total Found: {result.get('total_found', 0)}")
            print("-" * 60)
            
            for i, item in enumerate(result.get("results", []), 1):
                print(f"\n[{i}] {item['path']}")
                print(f"    Score: {item['score']:.1f}  Size: {item['size_bytes']} bytes")
                for match in item.get("matches", []):
                    match_types = []
                    if match.get("name_match"):
                        match_types.append("文件名")
                    if match.get("dir_match"):
                        match_types.append("目录名")
                    if match.get("content_match"):
                        match_types.append("内容")
                    print(f"    - '{match['keyword']}' 匹配: {', '.join(match_types)}")
                    if "snippet" in match:
                        snippet = match["snippet"]
                        print(f"      Line {snippet.get('line', '?')}: {snippet.get('snippet', '')[:100]}")
            
            if result.get("suggestions"):
                print("\n建议:")
                for sug in result["suggestions"]:
                    print(f"  • {sug}")
        
        return 0

    def cmd_review(self, args: argparse.Namespace) -> int:
        """基于项目规范进行代码 Review"""
        ai_mode = bool(args.ai_mode)
        root_dir = self._get_root_dir()

        # 确定输入类型
        code = None
        file_path = None
        file_paths = None
        diff_content = None
        workspace_root = args.workspace if hasattr(args, 'workspace') and args.workspace else None

        # 读取代码片段（从 --snippet 或 stdin）
        if hasattr(args, 'snippet') and args.snippet:
            code = args.snippet
        elif hasattr(args, 'snippet_file') and args.snippet_file:
            try:
                with open(args.snippet_file, 'r', encoding='utf-8') as f:
                    code = f.read()
            except Exception as e:
                if ai_mode:
                    _print_json(_ai_response("shared_drive.review", {"ok": False, "error": f"读取代码文件失败: {e}"}))
                else:
                    print(f"✗ 读取代码文件失败: {e}")
                return 1

        # 读取要 Review 的文件
        if hasattr(args, 'file') and args.file:
            file_path = args.file
        
        # 读取多个文件
        if hasattr(args, 'files') and args.files:
            file_paths = [f.strip() for f in args.files.split(',') if f.strip()]

        # 读取 diff 内容
        if hasattr(args, 'diff') and args.diff:
            diff_content = args.diff
        elif hasattr(args, 'diff_file') and args.diff_file:
            try:
                with open(args.diff_file, 'r', encoding='utf-8') as f:
                    diff_content = f.read()
            except Exception as e:
                if ai_mode:
                    _print_json(_ai_response("shared_drive.review", {"ok": False, "error": f"读取 diff 文件失败: {e}"}))
                else:
                    print(f"✗ 读取 diff 文件失败: {e}")
                return 1

        # 检查是否有有效输入
        if not any([code, file_path, file_paths, diff_content]):
            if ai_mode:
                _print_json(_ai_response("shared_drive.review", {
                    "ok": False, 
                    "error": "请提供要 Review 的内容：--snippet, --snippet-file, --file, --files, --diff, 或 --diff-file"
                }))
            else:
                print("✗ 请提供要 Review 的内容")
                print("  使用 --snippet <code> 或 --snippet-file <path> 提供代码片段")
                print("  使用 --file <path> 或 --files <path1,path2,...> 提供文件路径")
                print("  使用 --diff <content> 或 --diff-file <path> 提供 Git diff")
            return 1

        # 自定义规范路径和关键词
        custom_paths = None
        custom_keywords = None
        if hasattr(args, 'standard_paths') and args.standard_paths:
            custom_paths = [p.strip() for p in args.standard_paths.split(',') if p.strip()]
        if hasattr(args, 'standard_keywords') and args.standard_keywords:
            custom_keywords = [k.strip() for k in args.standard_keywords.split(',') if k.strip()]

        try:
            result = review_code(
                root_dir=root_dir,
                code=code,
                file_path=file_path,
                file_paths=file_paths,
                diff_content=diff_content,
                workspace_root=workspace_root,
                custom_standard_paths=custom_paths,
                custom_standard_keywords=custom_keywords,
            )
        except Exception as e:
            if ai_mode:
                _print_json(_ai_response("shared_drive.review", {"ok": False, "error": f"Review 执行出错: {e}"}))
            else:
                print(f"✗ Review 执行出错: {e}")
            return 1

        if ai_mode:
            _print_json(_ai_response("shared_drive.review", result))
        else:
            if not result.get("ok"):
                print(f"✗ {result.get('error', '未知错误')}")
                if result.get("suggestions"):
                    print("\n建议:")
                    for sug in result["suggestions"]:
                        print(f"  • {sug}")
                return 1
            
            # 打印格式化的报告
            print(result.get("formatted_report", ""))
            
            # 打印使用的规范信息
            standards = result.get("standards_used", {})
            print("\n---")
            print(f"使用的规范文档: {len(standards.get('documents', []))} 个")
            print(f"检查规则数: {standards.get('rules_count', 0)} 条")

        return 0 if result.get("ok") else 1

    def cmd_config(self, args: argparse.Namespace) -> int:
        if args.config_cmd == "show":
            cfg = self.config.get_all()
            if args.ai_mode:
                _print_json(_ai_response("shared_drive.config.show", {"ok": True, "config": cfg}))
            else:
                print(json.dumps(cfg, ensure_ascii=False, indent=2))
            return 0

        if args.config_cmd == "set-root":
            self.config.set("root_dir", args.path)
            if args.ai_mode:
                _print_json(_ai_response("shared_drive.config.set_root", {"ok": True, "root_dir": args.path}))
            else:
                print(f"OK root_dir={args.path}")
            return 0

        if args.config_cmd == "set-test-root":
            self.config.set("test_root_dir", args.path)
            if args.ai_mode:
                _print_json(_ai_response("shared_drive.config.set_test_root", {"ok": True, "test_root_dir": args.path}))
            else:
                print(f"OK test_root_dir={args.path}")
            return 0

        print("✗ 未知 config 子命令", file=sys.stderr)
        return 1


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="S1SharedDocSkill CLI",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    sub = parser.add_subparsers(dest="command", help="command")

    # list
    p_list = sub.add_parser("list", help="List directory")
    p_list.add_argument("dir", nargs="?", default=".", help="relative dir under root")
    p_list.add_argument("--ai-mode", action="store_true", help="Output JSON only")

    # read
    p_read = sub.add_parser("read", help="Read file")
    p_read.add_argument("file", help="relative file path under root")
    p_read.add_argument("--ai-mode", action="store_true", help="Output JSON only")

    # upload
    p_up = sub.add_parser("upload", help="Upload local file to shared drive")
    p_up.add_argument("dest", help="destination relative path under root")
    p_up.add_argument("--from", dest="from_file", required=True, help="local file path")
    p_up.add_argument("--conflict", choices=["overwrite", "rename"], default="rename")
    p_up.add_argument("--ai-mode", action="store_true", help="Output JSON only")

    # search
    p_search = sub.add_parser("search", help="Search documents in shared drive")
    p_search.add_argument("query", nargs="?", default="", help="Natural language query")
    p_search.add_argument("--keywords", "-k", help="Comma-separated keywords (overrides query)")
    p_search.add_argument("--dir", "-d", default=".", help="Search directory (relative to root)")
    p_search.add_argument("--top-k", "-n", type=int, default=10, help="Max results to return")
    p_search.add_argument("--name-only", action="store_true", help="Only search file/dir names, not content")
    p_search.add_argument("--ai-mode", action="store_true", help="Output JSON only")

    # review - 代码 Review
    p_review = sub.add_parser("review", help="Review code based on project standards")
    p_review.add_argument("--snippet", help="Code snippet to review (inline)")
    p_review.add_argument("--snippet-file", help="File containing code snippet to review")
    p_review.add_argument("--file", "-f", help="Single file path to review")
    p_review.add_argument("--files", help="Comma-separated file paths to review")
    p_review.add_argument("--diff", help="Git diff content to review (inline)")
    p_review.add_argument("--diff-file", help="File containing git diff to review")
    p_review.add_argument("--workspace", "-w", help="Workspace root for resolving relative file paths")
    p_review.add_argument("--standard-paths", help="Comma-separated custom standard document paths")
    p_review.add_argument("--standard-keywords", help="Comma-separated custom standard keywords")
    p_review.add_argument("--ai-mode", action="store_true", help="Output JSON only")

    # config
    p_cfg = sub.add_parser("config", help="Config")
    cfg_sub = p_cfg.add_subparsers(dest="config_cmd")
    cfg_show = cfg_sub.add_parser("show", help="Show config")
    cfg_show.add_argument("--ai-mode", action="store_true")

    cfg_root = cfg_sub.add_parser("set-root", help="Set root_dir")
    cfg_root.add_argument("--path", required=True)
    cfg_root.add_argument("--ai-mode", action="store_true")

    cfg_test_root = cfg_sub.add_parser("set-test-root", help="Set test_root_dir")
    cfg_test_root.add_argument("--path", required=True)
    cfg_test_root.add_argument("--ai-mode", action="store_true")

    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        return 1

    cli = AICli()

    if args.command == "list":
        return cli.cmd_list(args)
    if args.command == "read":
        return cli.cmd_read(args)
    if args.command == "upload":
        return cli.cmd_upload(args)
    if args.command == "config":
        return cli.cmd_config(args)
    if args.command == "search":
        return cli.cmd_search(args)
    if args.command == "review":
        return cli.cmd_review(args)

    print("✗ 未知命令", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
