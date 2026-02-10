#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from __future__ import annotations

import os
import shutil
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from path_guard import normalize_and_validate_path, suggest_parent_path, PathGuardError


def _fmt_mtime(ts: float) -> str:
    try:
        return datetime.fromtimestamp(ts).isoformat(timespec="seconds")
    except Exception:
        return ""


def list_dir(root_dir: str, rel_dir: str) -> Dict[str, Any]:
    p = normalize_and_validate_path(root_dir, rel_dir)

    if not p.exists():
        parent = suggest_parent_path(root_dir, rel_dir)
        raise PathGuardError(f"路径不存在: {rel_dir}。可用上级路径建议: {parent}")

    if not p.is_dir():
        raise PathGuardError(f"不是目录: {rel_dir}")

    items: List[Dict[str, Any]] = []
    for child in sorted(p.iterdir(), key=lambda x: (not x.is_dir(), x.name.lower())):
        st = child.stat()
        items.append(
            {
                "name": child.name,
                "is_dir": child.is_dir(),
                "size_bytes": None if child.is_dir() else st.st_size,
                "mtime": _fmt_mtime(st.st_mtime),
            }
        )

    # 输出 path 统一为相对路径
    root_abs = Path(os.path.abspath(root_dir))
    rel_out = str(p.relative_to(root_abs)).replace("\\", "/") if p != root_abs else "."

    return {"path": rel_out, "items": items}


def read_text_file(root_dir: str, rel_file: str, max_bytes: int, max_lines: int) -> Dict[str, Any]:
    p = normalize_and_validate_path(root_dir, rel_file)

    if not p.exists():
        parent = suggest_parent_path(root_dir, rel_file)
        raise PathGuardError(f"路径不存在: {rel_file}。可用上级路径建议: {parent}")

    if p.is_dir():
        raise PathGuardError(f"目标是目录，无法读取文件: {rel_file}")

    # 以二进制读取，按utf-8尽力解码，避免编码异常阻塞
    read_bytes = 0
    read_lines = 0
    truncated = False
    chunks: List[str] = []

    with p.open("rb") as f:
        while True:
            if read_bytes >= max_bytes or read_lines >= max_lines:
                truncated = True
                break

            # 读取一行（上限按 bytes/lines 控）
            line = f.readline()
            if not line:
                break

            read_bytes += len(line)
            try:
                s = line.decode("utf-8", errors="replace")
            except Exception:
                s = str(line)
            chunks.append(s)
            read_lines += 1

            if read_bytes >= max_bytes or read_lines >= max_lines:
                truncated = True
                break

    st = p.stat()
    return {
        "path": str(p),
        "content": "".join(chunks),
        "truncated": truncated,
        "read_bytes": read_bytes,
        "read_lines": read_lines,
        "size_bytes": st.st_size,
        "mtime": _fmt_mtime(st.st_mtime),
    }


def _ensure_parent_dir(dest: Path) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)


def _resolve_conflict(dest: Path, conflict: str) -> Path:
    if not dest.exists():
        return dest

    if conflict == "overwrite":
        return dest

    # rename
    stem = dest.stem
    suffix = dest.suffix
    i = 1
    while True:
        cand = dest.with_name(f"{stem}_{i}{suffix}")
        if not cand.exists():
            return cand
        i += 1


def upload_file(
    root_dir: str,
    dest_rel_path: str,
    local_file: str,
    conflict: str,
    upload_max_bytes: int,
) -> Dict[str, Any]:
    if conflict not in ("overwrite", "rename"):
        raise PathGuardError(f"不支持的冲突策略: {conflict}")

    src = Path(local_file)
    if not src.exists() or not src.is_file():
        raise PathGuardError(f"本地文件不存在: {local_file}")

    st_src = src.stat()
    if st_src.st_size > upload_max_bytes:
        raise PathGuardError(
            f"上传内容超过大小限制: {st_src.st_size} > {upload_max_bytes}。请拆分/压缩后再上传。"
        )

    dest = normalize_and_validate_path(root_dir, dest_rel_path)
    _ensure_parent_dir(dest)

    final_dest = _resolve_conflict(dest, conflict)
    conflict_info: Optional[str] = None
    if dest.exists() and conflict == "overwrite":
        conflict_info = "overwrite"
    elif dest.exists() and conflict == "rename":
        conflict_info = f"rename:{final_dest.name}"

    if final_dest.exists() and conflict == "overwrite":
        # 尽量避免权限/只读问题：先删除再写
        final_dest.unlink()

    shutil.copy2(str(src), str(final_dest))

    st = final_dest.stat()
    return {
        "final_path": str(final_dest),
        "size_bytes": st.st_size,
        "mtime": _fmt_mtime(st.st_mtime),
        "conflict": conflict_info,
    }


# ============================================================================
# 文档检索（search）能力
# ============================================================================

# 支持的文本文件扩展名（用于内容检索）
TEXT_EXTENSIONS = {
    ".txt", ".md", ".markdown", ".rst", ".json", ".xml", ".yaml", ".yml",
    ".ini", ".cfg", ".conf", ".log", ".csv", ".tsv",
    ".py", ".js", ".ts", ".jsx", ".tsx", ".html", ".htm", ".css", ".scss",
    ".cpp", ".c", ".h", ".hpp", ".cs", ".java", ".go", ".rs", ".swift",
    ".sh", ".bat", ".ps1", ".cmd",
    ".sql", ".graphql",
}


def _is_text_file(path: Path) -> bool:
    """判断文件是否为可检索的文本文件"""
    return path.suffix.lower() in TEXT_EXTENSIONS


def _extract_snippet(content: str, keyword: str, context_chars: int = 80) -> Optional[Dict[str, Any]]:
    """从内容中提取包含关键词的片段
    
    Args:
        content: 文件内容
        keyword: 搜索关键词
        context_chars: 关键词前后的上下文字符数
        
    Returns:
        包含片段信息的字典，如果未找到则返回 None
    """
    # 不区分大小写搜索
    content_lower = content.lower()
    keyword_lower = keyword.lower()
    
    pos = content_lower.find(keyword_lower)
    if pos == -1:
        return None
    
    # 计算行号
    line_num = content[:pos].count('\n') + 1
    
    # 提取上下文片段
    start = max(0, pos - context_chars)
    end = min(len(content), pos + len(keyword) + context_chars)
    
    # 调整到行边界（尽量）
    if start > 0:
        newline_pos = content.rfind('\n', start, pos)
        if newline_pos != -1:
            start = newline_pos + 1
    
    if end < len(content):
        newline_pos = content.find('\n', pos + len(keyword), end + context_chars)
        if newline_pos != -1:
            end = newline_pos
    
    snippet = content[start:end].strip()
    
    # 添加省略号指示
    prefix = "..." if start > 0 else ""
    suffix = "..." if end < len(content) else ""
    
    return {
        "line": line_num,
        "snippet": f"{prefix}{snippet}{suffix}",
        "match_position": pos - start + len(prefix),
    }


def _calculate_relevance_score(
    file_path: Path,
    keyword: str,
    content_match: bool,
    name_match: bool,
    dir_match: bool
) -> float:
    """计算搜索结果的相关性得分
    
    权重规则：
    - 文件名完全匹配: 100
    - 文件名部分匹配: 50
    - 目录名匹配: 30
    - 内容匹配: 20
    """
    score = 0.0
    keyword_lower = keyword.lower()
    
    # 文件名匹配权重
    if name_match:
        file_name_lower = file_path.name.lower()
        if file_name_lower == keyword_lower:
            score += 100
        elif keyword_lower in file_name_lower:
            score += 50
    
    # 目录名匹配权重
    if dir_match:
        score += 30
    
    # 内容匹配权重
    if content_match:
        score += 20
    
    return score


def _search_in_file(
    file_path: Path,
    keywords: List[str],
    max_bytes: int = 1024 * 1024  # 默认最多读取 1MB
) -> Optional[Dict[str, Any]]:
    """在单个文件中搜索关键词
    
    Args:
        file_path: 文件路径
        keywords: 关键词列表
        max_bytes: 最大读取字节数
        
    Returns:
        搜索结果字典，如果无匹配则返回 None
    """
    try:
        # 检查文件大小
        file_size = file_path.stat().st_size
        if file_size > max_bytes:
            # 大文件只读取开头部分
            with file_path.open("rb") as f:
                raw = f.read(max_bytes)
        else:
            with file_path.open("rb") as f:
                raw = f.read()
        
        # 尝试解码
        try:
            content = raw.decode("utf-8", errors="replace")
        except Exception:
            return None
        
        # 检查文件名和目录名匹配
        file_name_lower = file_path.name.lower()
        parent_names_lower = [p.name.lower() for p in file_path.parents]
        
        matches = []
        total_score = 0.0
        
        for kw in keywords:
            kw_lower = kw.lower()
            
            name_match = kw_lower in file_name_lower
            dir_match = any(kw_lower in pn for pn in parent_names_lower)
            
            # 内容匹配
            snippet_info = _extract_snippet(content, kw)
            content_match = snippet_info is not None
            
            if name_match or dir_match or content_match:
                score = _calculate_relevance_score(
                    file_path, kw, content_match, name_match, dir_match
                )
                total_score += score
                
                match_info = {
                    "keyword": kw,
                    "name_match": name_match,
                    "dir_match": dir_match,
                    "content_match": content_match,
                }
                if snippet_info:
                    match_info["snippet"] = snippet_info
                
                matches.append(match_info)
        
        if not matches:
            return None
        
        return {
            "matches": matches,
            "score": total_score,
        }
        
    except Exception as e:
        # 文件读取错误，静默跳过
        return None


def search_documents(
    root_dir: str,
    keywords: List[str],
    search_dir: str = ".",
    top_k: int = 10,
    include_content: bool = True,
    max_file_size: int = 1024 * 1024,  # 1MB
) -> Dict[str, Any]:
    """在共享盘中搜索文档
    
    Args:
        root_dir: 共享盘根目录
        keywords: 搜索关键词列表
        search_dir: 搜索的子目录（相对路径），默认为根目录
        top_k: 返回的最大结果数
        include_content: 是否搜索文件内容
        max_file_size: 内容搜索时的最大文件大小
        
    Returns:
        搜索结果字典，包含:
        - results: 结果列表，每项包含 path, matches, score
        - total_found: 总匹配数
        - suggestions: 未命中时的建议
    """
    from path_guard import normalize_and_validate_path, PathGuardError
    
    if not keywords:
        return {
            "results": [],
            "total_found": 0,
            "suggestions": ["请提供搜索关键词"],
        }
    
    # 验证搜索目录
    try:
        search_path = normalize_and_validate_path(root_dir, search_dir)
    except PathGuardError as e:
        return {
            "results": [],
            "total_found": 0,
            "error": str(e),
            "suggestions": ["请检查搜索目录路径是否正确"],
        }
    
    if not search_path.exists():
        return {
            "results": [],
            "total_found": 0,
            "error": f"搜索目录不存在: {search_dir}",
            "suggestions": ["请检查目录是否存在，或尝试从根目录搜索"],
        }
    
    if not search_path.is_dir():
        return {
            "results": [],
            "total_found": 0,
            "error": f"搜索路径不是目录: {search_dir}",
            "suggestions": ["请提供有效的目录路径"],
        }
    
    root_abs = Path(os.path.abspath(root_dir))
    all_results: List[Dict[str, Any]] = []
    
    # 遍历目录搜索
    try:
        for item in search_path.rglob("*"):
            if item.is_file():
                # 决定是否搜索内容
                search_content = include_content and _is_text_file(item)
                
                if search_content:
                    result = _search_in_file(item, keywords, max_file_size)
                else:
                    # 只搜索文件名和目录名
                    file_name_lower = item.name.lower()
                    parent_names_lower = [p.name.lower() for p in item.parents]
                    
                    matches = []
                    total_score = 0.0
                    
                    for kw in keywords:
                        kw_lower = kw.lower()
                        name_match = kw_lower in file_name_lower
                        dir_match = any(kw_lower in pn for pn in parent_names_lower)
                        
                        if name_match or dir_match:
                            score = _calculate_relevance_score(
                                item, kw, False, name_match, dir_match
                            )
                            total_score += score
                            matches.append({
                                "keyword": kw,
                                "name_match": name_match,
                                "dir_match": dir_match,
                                "content_match": False,
                            })
                    
                    result = {"matches": matches, "score": total_score} if matches else None
                
                if result:
                    # 计算相对路径
                    try:
                        rel_path = str(item.relative_to(root_abs)).replace("\\", "/")
                    except ValueError:
                        rel_path = str(item)
                    
                    all_results.append({
                        "path": rel_path,
                        "name": item.name,
                        "size_bytes": item.stat().st_size,
                        "mtime": _fmt_mtime(item.stat().st_mtime),
                        "matches": result["matches"],
                        "score": result["score"],
                    })
    except PermissionError:
        pass  # 跳过无权限的目录
    except Exception as e:
        pass  # 其他错误静默处理
    
    # 按得分排序并取 Top-K
    all_results.sort(key=lambda x: x["score"], reverse=True)
    top_results = all_results[:top_k]
    
    # 生成建议
    suggestions = []
    if not top_results:
        suggestions = [
            f"未找到包含关键词 {keywords} 的文档",
            "建议: 尝试使用更通用的关键词",
            "建议: 检查关键词拼写是否正确",
            f"建议: 尝试在其他目录中搜索（当前: {search_dir}）",
        ]
    
    return {
        "results": top_results,
        "total_found": len(all_results),
        "search_dir": search_dir,
        "keywords": keywords,
        "suggestions": suggestions,
    }


def search_by_query(
    root_dir: str,
    query: str,
    search_dir: str = ".",
    top_k: int = 10,
) -> Dict[str, Any]:
    """基于自然语言查询搜索文档（简化版）
    
    将查询分词后调用 search_documents
    
    Args:
        root_dir: 共享盘根目录
        query: 自然语言查询
        search_dir: 搜索目录
        top_k: 返回结果数
        
    Returns:
        搜索结果
    """
    # 简单分词：按空格和常见标点分割
    import re
    
    # 移除标点，按空格分词
    tokens = re.split(r'[\s,，。.;；:：!！?？\-_/\\]+', query)
    
    # 过滤空字符串和过短的词
    keywords = [t.strip() for t in tokens if t.strip() and len(t.strip()) >= 2]
    
    if not keywords:
        # 如果分词后没有有效关键词，使用原始查询
        keywords = [query.strip()] if query.strip() else []
    
    return search_documents(
        root_dir=root_dir,
        keywords=keywords,
        search_dir=search_dir,
        top_k=top_k,
        include_content=True,
    )


# ============================================================================
# "只基于文档回答"的约束模式 (Document-Only Mode)
# ============================================================================

class DocumentReference:
    """文档引用信息，用于追踪回答来源"""
    
    def __init__(
        self,
        file_path: str,
        line_start: Optional[int] = None,
        line_end: Optional[int] = None,
        section_title: Optional[str] = None,
        snippet: Optional[str] = None,
    ):
        self.file_path = file_path
        self.line_start = line_start
        self.line_end = line_end
        self.section_title = section_title
        self.snippet = snippet
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典格式"""
        result = {"file_path": self.file_path}
        if self.line_start is not None:
            result["line_start"] = self.line_start
        if self.line_end is not None:
            result["line_end"] = self.line_end
        if self.section_title:
            result["section_title"] = self.section_title
        if self.snippet:
            result["snippet"] = self.snippet
        return result
    
    def format_citation(self) -> str:
        """格式化为引用字符串"""
        parts = [f"[{self.file_path}"]
        if self.line_start is not None:
            if self.line_end is not None and self.line_end != self.line_start:
                parts.append(f":L{self.line_start}-{self.line_end}")
            else:
                parts.append(f":L{self.line_start}")
        if self.section_title:
            parts.append(f" §{self.section_title}")
        parts.append("]")
        return "".join(parts)


class DocumentOnlyContext:
    """文档约束上下文，用于管理"只基于文档回答"模式
    
    功能：
    1. 收集和管理检索到的文档片段
    2. 追踪所有引用来源
    3. 生成带引用的回答格式
    4. 验证回答是否符合约束（所有结论都有来源）
    """
    
    def __init__(self, root_dir: str, document_only: bool = True):
        """初始化文档约束上下文
        
        Args:
            root_dir: 共享盘根目录
            document_only: 是否启用只基于文档回答模式
        """
        self.root_dir = root_dir
        self.document_only = document_only
        self.collected_documents: List[Dict[str, Any]] = []
        self.references: List[DocumentReference] = []
        self._search_history: List[Dict[str, Any]] = []
    
    def search_and_collect(
        self,
        query: str,
        search_dir: str = ".",
        top_k: int = 5,
    ) -> Dict[str, Any]:
        """搜索并收集文档片段
        
        Args:
            query: 搜索查询
            search_dir: 搜索目录
            top_k: 返回结果数
            
        Returns:
            搜索结果，同时将结果添加到上下文中
        """
        result = search_by_query(
            root_dir=self.root_dir,
            query=query,
            search_dir=search_dir,
            top_k=top_k,
        )
        
        # 记录搜索历史
        self._search_history.append({
            "query": query,
            "search_dir": search_dir,
            "result_count": result.get("total_found", 0),
        })
        
        # 收集文档
        for item in result.get("results", []):
            doc_info = {
                "path": item["path"],
                "name": item["name"],
                "matches": item.get("matches", []),
                "score": item.get("score", 0),
            }
            
            # 避免重复添加
            if not any(d["path"] == doc_info["path"] for d in self.collected_documents):
                self.collected_documents.append(doc_info)
        
        return result
    
    def read_and_collect(
        self,
        rel_file: str,
        max_bytes: int = 100 * 1024,
        max_lines: int = 500,
    ) -> Dict[str, Any]:
        """读取文件并添加到上下文
        
        Args:
            rel_file: 相对文件路径
            max_bytes: 最大读取字节数
            max_lines: 最大读取行数
            
        Returns:
            文件读取结果
        """
        result = read_text_file(
            root_dir=self.root_dir,
            rel_file=rel_file,
            max_bytes=max_bytes,
            max_lines=max_lines,
        )
        
        # 添加完整引用
        ref = DocumentReference(
            file_path=rel_file,
            line_start=1,
            line_end=result.get("read_lines", 1),
        )
        self.references.append(ref)
        
        return result
    
    def add_reference(
        self,
        file_path: str,
        line_start: Optional[int] = None,
        line_end: Optional[int] = None,
        section_title: Optional[str] = None,
        snippet: Optional[str] = None,
    ) -> DocumentReference:
        """手动添加一个文档引用
        
        Args:
            file_path: 文件路径
            line_start: 起始行号
            line_end: 结束行号
            section_title: 章节标题
            snippet: 引用片段
            
        Returns:
            创建的引用对象
        """
        ref = DocumentReference(
            file_path=file_path,
            line_start=line_start,
            line_end=line_end,
            section_title=section_title,
            snippet=snippet,
        )
        self.references.append(ref)
        return ref
    
    def get_context_summary(self) -> Dict[str, Any]:
        """获取当前上下文的摘要信息
        
        Returns:
            上下文摘要，包含收集的文档数、引用数等
        """
        return {
            "document_only_mode": self.document_only,
            "collected_documents_count": len(self.collected_documents),
            "references_count": len(self.references),
            "search_history": self._search_history,
            "collected_documents": [
                {"path": d["path"], "name": d["name"], "score": d.get("score", 0)}
                for d in self.collected_documents
            ],
        }
    
    def format_answer_with_citations(
        self,
        answer_points: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        """格式化带引用的回答
        
        Args:
            answer_points: 回答要点列表，每项包含:
                - content: 回答内容
                - reference: DocumentReference 或引用信息字典
                
        Returns:
            格式化后的回答，包含:
            - formatted_answer: 带引用标记的回答文本
            - citations: 引用列表
            - validation: 验证结果
        """
        formatted_lines = []
        citations = []
        missing_citations = []
        
        for i, point in enumerate(answer_points, 1):
            content = point.get("content", "")
            ref_info = point.get("reference")
            
            if ref_info:
                # 处理引用
                if isinstance(ref_info, DocumentReference):
                    ref = ref_info
                elif isinstance(ref_info, dict):
                    ref = DocumentReference(**ref_info)
                else:
                    ref = None
                
                if ref:
                    citation_mark = f"[{len(citations) + 1}]"
                    formatted_lines.append(f"{content} {citation_mark}")
                    citations.append({
                        "index": len(citations) + 1,
                        "citation": ref.format_citation(),
                        "details": ref.to_dict(),
                    })
                else:
                    formatted_lines.append(content)
                    if self.document_only:
                        missing_citations.append(i)
            else:
                formatted_lines.append(content)
                if self.document_only:
                    missing_citations.append(i)
        
        # 验证结果
        validation = {
            "valid": len(missing_citations) == 0 or not self.document_only,
            "missing_citations": missing_citations,
            "message": None,
        }
        
        if missing_citations and self.document_only:
            validation["message"] = (
                f"警告: 以下回答要点缺少文档引用 (索引: {missing_citations})。"
                f"在 documentOnly 模式下，所有结论必须有来源引用。"
            )
        
        return {
            "formatted_answer": "\n".join(formatted_lines),
            "citations": citations,
            "validation": validation,
        }
    
    def generate_reference_section(self) -> str:
        """生成引用章节文本
        
        Returns:
            格式化的引用列表文本
        """
        if not self.references:
            return ""
        
        lines = ["", "---", "**参考文档:**", ""]
        for i, ref in enumerate(self.references, 1):
            lines.append(f"{i}. {ref.format_citation()}")
            if ref.snippet:
                # 截断过长的片段
                snippet = ref.snippet[:200] + "..." if len(ref.snippet) > 200 else ref.snippet
                lines.append(f"   > {snippet}")
        
        return "\n".join(lines)
    
    def to_prompt_context(self) -> str:
        """生成用于 AI 提示的上下文文本
        
        Returns:
            格式化的上下文文本，包含约束说明和已收集的文档信息
        """
        lines = []
        
        if self.document_only:
            lines.extend([
                "=== 文档约束模式 ===",
                "【重要约束】当前处于'只基于文档回答'模式：",
                "1. 所有回答必须基于以下检索到的文档内容",
                "2. 每条结论必须标注来源引用（文件路径+行号/章节）",
                "3. 如果文档中没有相关信息，请明确说明'文档中未找到相关信息'",
                "4. 禁止使用文档之外的知识进行推测或补充",
                "",
            ])
        
        if self.collected_documents:
            lines.append("=== 已检索到的文档 ===")
            for doc in self.collected_documents:
                lines.append(f"- {doc['path']} (相关度: {doc.get('score', 0):.1f})")
                for match in doc.get("matches", [])[:3]:  # 最多显示3个匹配
                    if match.get("snippet"):
                        snippet_text = match["snippet"].get("snippet", "")[:100]
                        lines.append(f"  > L{match['snippet'].get('line', '?')}: {snippet_text}")
            lines.append("")
        
        if self._search_history:
            lines.append("=== 搜索历史 ===")
            for search in self._search_history:
                lines.append(f"- 查询: {search['query']} -> 找到 {search['result_count']} 个结果")
            lines.append("")
        
        return "\n".join(lines)


def create_document_only_context(
    root_dir: str,
    document_only: bool = True,
) -> DocumentOnlyContext:
    """创建文档约束上下文（工厂函数）
    
    Args:
        root_dir: 共享盘根目录
        document_only: 是否启用只基于文档回答模式
        
    Returns:
        DocumentOnlyContext 实例
    """
    return DocumentOnlyContext(root_dir=root_dir, document_only=document_only)


def answer_from_documents(
    root_dir: str,
    question: str,
    search_dirs: Optional[List[str]] = None,
    top_k: int = 5,
    document_only: bool = True,
) -> Dict[str, Any]:
    """基于文档回答问题的便捷函数
    
    这是一个高级封装，自动执行：
    1. 创建文档约束上下文
    2. 搜索相关文档
    3. 返回搜索结果和上下文信息
    
    Args:
        root_dir: 共享盘根目录
        question: 用户问题
        search_dirs: 要搜索的目录列表，默认为根目录
        top_k: 每个目录返回的最大结果数
        document_only: 是否启用只基于文档回答模式
        
    Returns:
        包含搜索结果和上下文信息的字典
    """
    if search_dirs is None:
        search_dirs = ["."]
    
    ctx = create_document_only_context(root_dir, document_only)
    
    all_results = []
    for search_dir in search_dirs:
        result = ctx.search_and_collect(
            query=question,
            search_dir=search_dir,
            top_k=top_k,
        )
        all_results.extend(result.get("results", []))
    
    # 按得分重新排序并去重
    seen_paths = set()
    unique_results = []
    for r in sorted(all_results, key=lambda x: x.get("score", 0), reverse=True):
        if r["path"] not in seen_paths:
            seen_paths.add(r["path"])
            unique_results.append(r)
    
    return {
        "question": question,
        "document_only_mode": document_only,
        "results": unique_results[:top_k],
        "total_found": len(unique_results),
        "context_summary": ctx.get_context_summary(),
        "prompt_context": ctx.to_prompt_context(),
        "instruction": (
            "请基于以上检索到的文档内容回答问题。"
            "每条结论请标注来源引用，格式: [文件路径:行号]。"
            if document_only else
            "请参考以上文档内容回答问题，可结合其他知识补充。"
        ),
    }


# ============================================================================
# 项目规范定位与提炼 (Review 前置功能)
# ============================================================================

# 默认的规范文档搜索关键词
DEFAULT_STANDARD_KEYWORDS = [
    "规范", "Standard", "Guideline", "Guidelines", "Convention", "Conventions",
    "编码规范", "代码规范", "命名规范", "开发规范", "设计规范",
    "Coding Standard", "Code Style", "Style Guide", "Best Practice",
    "架构规范", "接口规范", "API规范", "注释规范",
]

# 默认的规范文档目录路径（相对于共享盘根目录）
# 注意：Review 功能只搜索这些目录，其他功能（如 search）可搜索整个共享盘
DEFAULT_STANDARD_PATHS = [
    "规范",
    "规范文档",  # S1 项目规范文档目录
    "Standards",
    "Guidelines",
    "Docs/规范",
    "Docs/Standards",
    "Documentation/Standards",
    "项目规范",
    "开发规范",
    "CodeStandards",
]

# 规范文档的文件扩展名
STANDARD_DOC_EXTENSIONS = {
    ".md", ".markdown", ".txt", ".rst", ".doc", ".docx", ".pdf",
    ".html", ".htm", ".wiki",
}


class StandardRule:
    """单条规范规则"""
    
    def __init__(
        self,
        rule_id: str,
        title: str,
        description: str,
        keywords: List[str],
        severity: str = "warning",  # error, warning, info
        source_file: str = "",
        source_line: Optional[int] = None,
        source_section: Optional[str] = None,
        category: str = "general",
        examples: Optional[List[str]] = None,
        counter_examples: Optional[List[str]] = None,
    ):
        self.rule_id = rule_id
        self.title = title
        self.description = description
        self.keywords = keywords
        self.severity = severity
        self.source_file = source_file
        self.source_line = source_line
        self.source_section = source_section
        self.category = category
        self.examples = examples or []
        self.counter_examples = counter_examples or []
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典格式"""
        return {
            "rule_id": self.rule_id,
            "title": self.title,
            "description": self.description,
            "keywords": self.keywords,
            "severity": self.severity,
            "source": {
                "file": self.source_file,
                "line": self.source_line,
                "section": self.source_section,
            },
            "category": self.category,
            "examples": self.examples,
            "counter_examples": self.counter_examples,
        }
    
    def format_for_review(self) -> str:
        """格式化为用于 Review 的检查项文本"""
        lines = [
            f"### [{self.rule_id}] {self.title}",
            f"- **严重级别**: {self.severity}",
            f"- **类别**: {self.category}",
            f"- **描述**: {self.description}",
        ]
        
        if self.keywords:
            lines.append(f"- **关键词**: {', '.join(self.keywords)}")
        
        if self.source_file:
            source_ref = self.source_file
            if self.source_line:
                source_ref += f":L{self.source_line}"
            if self.source_section:
                source_ref += f" §{self.source_section}"
            lines.append(f"- **来源**: {source_ref}")
        
        if self.examples:
            lines.append("- **正确示例**:")
            for ex in self.examples[:2]:  # 最多显示2个示例
                lines.append(f"  ```\n  {ex}\n  ```")
        
        if self.counter_examples:
            lines.append("- **错误示例**:")
            for ex in self.counter_examples[:2]:
                lines.append(f"  ```\n  {ex}\n  ```")
        
        return "\n".join(lines)


class StandardChecklist:
    """规范检查清单，包含多条规则"""
    
    def __init__(self, name: str = "项目规范检查清单"):
        self.name = name
        self.rules: List[StandardRule] = []
        self.source_documents: List[str] = []
        self.categories: Dict[str, List[StandardRule]] = {}
        self.created_at: str = datetime.now().isoformat()
    
    def add_rule(self, rule: StandardRule) -> None:
        """添加一条规则"""
        self.rules.append(rule)
        
        # 按类别组织
        if rule.category not in self.categories:
            self.categories[rule.category] = []
        self.categories[rule.category].append(rule)
    
    def add_source_document(self, doc_path: str) -> None:
        """添加来源文档"""
        if doc_path not in self.source_documents:
            self.source_documents.append(doc_path)
    
    def get_rules_by_category(self, category: str) -> List[StandardRule]:
        """按类别获取规则"""
        return self.categories.get(category, [])
    
    def get_rules_by_severity(self, severity: str) -> List[StandardRule]:
        """按严重级别获取规则"""
        return [r for r in self.rules if r.severity == severity]
    
    def search_rules_by_keyword(self, keyword: str) -> List[StandardRule]:
        """按关键词搜索规则"""
        keyword_lower = keyword.lower()
        results = []
        for rule in self.rules:
            # 在标题、描述、关键词中搜索
            if (keyword_lower in rule.title.lower() or
                keyword_lower in rule.description.lower() or
                any(keyword_lower in kw.lower() for kw in rule.keywords)):
                results.append(rule)
        return results
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典格式"""
        return {
            "name": self.name,
            "created_at": self.created_at,
            "total_rules": len(self.rules),
            "source_documents": self.source_documents,
            "categories": list(self.categories.keys()),
            "rules": [r.to_dict() for r in self.rules],
            "summary": {
                "by_severity": {
                    "error": len(self.get_rules_by_severity("error")),
                    "warning": len(self.get_rules_by_severity("warning")),
                    "info": len(self.get_rules_by_severity("info")),
                },
                "by_category": {
                    cat: len(rules) for cat, rules in self.categories.items()
                },
            },
        }
    
    def format_for_review(self) -> str:
        """格式化为完整的 Review 检查清单文本"""
        lines = [
            f"# {self.name}",
            f"",
            f"**生成时间**: {self.created_at}",
            f"**规则总数**: {len(self.rules)}",
            f"**来源文档**: {len(self.source_documents)} 个",
            "",
        ]
        
        # 按类别输出规则
        for category, rules in self.categories.items():
            lines.append(f"## {category} ({len(rules)} 条规则)")
            lines.append("")
            for rule in rules:
                lines.append(rule.format_for_review())
                lines.append("")
        
        # 来源文档列表
        if self.source_documents:
            lines.append("---")
            lines.append("## 参考文档")
            for i, doc in enumerate(self.source_documents, 1):
                lines.append(f"{i}. {doc}")
        
        return "\n".join(lines)


def _extract_markdown_sections(content: str) -> List[Dict[str, Any]]:
    """从 Markdown 内容中提取章节结构
    
    Args:
        content: Markdown 文件内容
        
    Returns:
        章节列表，每项包含 level, title, content, line_start, line_end
    """
    import re
    
    sections = []
    lines = content.split('\n')
    
    current_section = None
    section_content_lines = []
    
    header_pattern = re.compile(r'^(#{1,6})\s+(.+)$')
    
    for i, line in enumerate(lines, 1):
        match = header_pattern.match(line)
        if match:
            # 保存上一个章节
            if current_section is not None:
                current_section["content"] = "\n".join(section_content_lines)
                current_section["line_end"] = i - 1
                sections.append(current_section)
            
            # 开始新章节
            level = len(match.group(1))
            title = match.group(2).strip()
            current_section = {
                "level": level,
                "title": title,
                "line_start": i,
                "line_end": None,
                "content": "",
            }
            section_content_lines = []
        else:
            section_content_lines.append(line)
    
    # 保存最后一个章节
    if current_section is not None:
        current_section["content"] = "\n".join(section_content_lines)
        current_section["line_end"] = len(lines)
        sections.append(current_section)
    
    return sections


def _extract_rules_from_section(
    section: Dict[str, Any],
    source_file: str,
    category: str,
    rule_id_prefix: str,
) -> List[StandardRule]:
    """从单个章节中提取规范规则
    
    基于启发式规则识别：
    - 列表项（- 或 * 或数字.）通常是规则
    - 包含"必须"、"禁止"、"应该"等词语的句子
    - 代码块前后的描述
    
    Args:
        section: 章节信息
        source_file: 来源文件路径
        category: 规则类别
        rule_id_prefix: 规则ID前缀
        
    Returns:
        提取的规则列表
    """
    import re
    
    rules = []
    content = section.get("content", "")
    section_title = section.get("title", "")
    line_start = section.get("line_start", 1)
    
    # 关键词映射到严重级别
    severity_keywords = {
        "error": ["必须", "禁止", "不得", "不允许", "强制", "must", "shall", "required", "forbidden", "never"],
        "warning": ["应该", "建议", "推荐", "避免", "should", "recommended", "avoid", "prefer"],
        "info": ["可以", "可选", "注意", "说明", "may", "optional", "note", "consider"],
    }
    
    # 提取列表项作为规则
    list_pattern = re.compile(r'^[\s]*[-*]\s+(.+)$|^[\s]*\d+\.\s+(.+)$', re.MULTILINE)
    
    rule_index = 0
    for match in list_pattern.finditer(content):
        rule_text = match.group(1) or match.group(2)
        if not rule_text or len(rule_text) < 10:  # 跳过太短的内容
            continue
        
        # 确定严重级别
        severity = "info"
        rule_text_lower = rule_text.lower()
        for sev, keywords in severity_keywords.items():
            if any(kw in rule_text_lower for kw in keywords):
                severity = sev
                break
        
        # 提取关键词（从规则文本中提取名词短语）
        keywords = _extract_keywords_from_text(rule_text)
        
        # 计算行号
        text_before = content[:match.start()]
        local_line = text_before.count('\n') + 1
        actual_line = line_start + local_line
        
        rule_index += 1
        rule = StandardRule(
            rule_id=f"{rule_id_prefix}{rule_index:03d}",
            title=rule_text[:50] + ("..." if len(rule_text) > 50 else ""),
            description=rule_text,
            keywords=keywords,
            severity=severity,
            source_file=source_file,
            source_line=actual_line,
            source_section=section_title,
            category=category,
        )
        rules.append(rule)
    
    return rules


def _extract_keywords_from_text(text: str) -> List[str]:
    """从文本中提取关键词
    
    Args:
        text: 输入文本
        
    Returns:
        关键词列表
    """
    import re
    
    keywords = []
    
    # 提取英文单词（可能是技术术语）
    english_words = re.findall(r'\b[A-Z][a-zA-Z]+\b|\b[a-z]+[A-Z][a-zA-Z]*\b', text)
    keywords.extend(english_words[:5])  # 最多5个
    
    # 提取带引号的内容
    quoted = re.findall(r'[「」『』""\'\'`]([^「」『』""\'\'`]+)[「」『』""\'\'`]', text)
    keywords.extend(quoted[:3])
    
    # 提取代码相关术语
    code_terms = re.findall(r'\b(class|function|method|variable|const|enum|struct|interface)\b', text.lower())
    keywords.extend(code_terms)
    
    # 去重
    return list(dict.fromkeys(keywords))[:8]  # 最多8个关键词


def _infer_category_from_path(file_path: str, section_title: str) -> str:
    """根据文件路径和章节标题推断规则类别
    
    Args:
        file_path: 文件路径
        section_title: 章节标题
        
    Returns:
        推断的类别名称
    """
    path_lower = file_path.lower()
    title_lower = section_title.lower()
    combined = path_lower + " " + title_lower
    
    category_keywords = {
        "命名规范": ["naming", "命名", "name", "标识符", "identifier"],
        "代码格式": ["format", "格式", "style", "样式", "缩进", "indent", "空格", "space"],
        "注释规范": ["comment", "注释", "文档", "document", "doc"],
        "架构设计": ["architecture", "架构", "设计", "design", "pattern", "模式"],
        "错误处理": ["error", "错误", "异常", "exception", "handle"],
        "性能优化": ["performance", "性能", "优化", "optimize", "效率"],
        "安全规范": ["security", "安全", "权限", "permission", "auth"],
        "测试规范": ["test", "测试", "单元", "unit", "coverage"],
        "Git/版本控制": ["git", "version", "版本", "commit", "branch"],
        "API设计": ["api", "接口", "interface", "rest", "http"],
        "数据库": ["database", "数据库", "sql", "db", "table"],
        "日志规范": ["log", "日志", "logging", "trace"],
    }
    
    for category, keywords in category_keywords.items():
        if any(kw in combined for kw in keywords):
            return category
    
    return "通用规范"


def locate_standard_documents(
    root_dir: str,
    custom_paths: Optional[List[str]] = None,
    custom_keywords: Optional[List[str]] = None,
    max_results: int = 20,
) -> Dict[str, Any]:
    """定位项目规范文档
    
    在共享盘中搜索规范相关的文档。
    
    Args:
        root_dir: 共享盘根目录
        custom_paths: 自定义搜索路径列表（相对路径）
        custom_keywords: 自定义搜索关键词
        max_results: 最大返回结果数
        
    Returns:
        定位结果，包含:
        - documents: 找到的规范文档列表
        - search_paths: 实际搜索的路径
        - suggestions: 如果未找到，给出建议
    """
    from path_guard import normalize_and_validate_path, PathGuardError
    
    # 合并自定义和默认配置
    search_paths = custom_paths if custom_paths else DEFAULT_STANDARD_PATHS.copy()
    search_keywords = custom_keywords if custom_keywords else DEFAULT_STANDARD_KEYWORDS.copy()
    
    found_documents: List[Dict[str, Any]] = []
    searched_paths: List[str] = []
    inaccessible_paths: List[str] = []
    
    root_abs = Path(os.path.abspath(root_dir))
    
    # 1. 首先检查默认路径是否存在
    for rel_path in search_paths:
        try:
            full_path = normalize_and_validate_path(root_dir, rel_path)
            if full_path.exists() and full_path.is_dir():
                searched_paths.append(rel_path)
                
                # 遍历目录查找规范文档
                for item in full_path.rglob("*"):
                    if item.is_file() and item.suffix.lower() in STANDARD_DOC_EXTENSIONS:
                        try:
                            rel_doc_path = str(item.relative_to(root_abs)).replace("\\", "/")
                        except ValueError:
                            rel_doc_path = str(item)
                        
                        st = item.stat()
                        found_documents.append({
                            "path": rel_doc_path,
                            "name": item.name,
                            "size_bytes": st.st_size,
                            "mtime": _fmt_mtime(st.st_mtime),
                            "source": "path_match",
                            "matched_path": rel_path,
                        })
        except PathGuardError:
            inaccessible_paths.append(rel_path)
        except PermissionError:
            inaccessible_paths.append(rel_path)
        except Exception:
            pass
    
    # 2. 如果路径搜索结果不足，使用关键词在规范目录下搜索（不搜索整个共享盘）
    if len(found_documents) < max_results and searched_paths:
        for search_path in searched_paths:
            keyword_results = search_documents(
                root_dir=root_dir,
                keywords=search_keywords[:5],  # 使用前5个关键词
                search_dir=search_path,  # 只在规范目录下搜索
                top_k=max_results - len(found_documents),
                include_content=True,
            )
            
            # 过滤出文档类型的文件
            for result in keyword_results.get("results", []):
                file_ext = Path(result["path"]).suffix.lower()
                if file_ext in STANDARD_DOC_EXTENSIONS:
                    # 避免重复
                    if not any(d["path"] == result["path"] for d in found_documents):
                        found_documents.append({
                            "path": result["path"],
                            "name": result["name"],
                            "size_bytes": result.get("size_bytes", 0),
                            "mtime": result.get("mtime", ""),
                            "source": "keyword_match",
                            "matched_keywords": [
                                m["keyword"] for m in result.get("matches", [])
                            ],
                            "score": result.get("score", 0),
                        })
            
            # 如果已经找到足够的文档，停止搜索
            if len(found_documents) >= max_results:
                break
    
    # 3. 生成建议
    suggestions = []
    if not found_documents:
        suggestions = [
            "未找到规范文档，请检查以下可能的问题：",
            f"1. 规范文档是否存放在以下目录之一: {', '.join(DEFAULT_STANDARD_PATHS[:5])}",
            "2. 规范文档文件名是否包含关键词（如：规范、Standard、Guideline）",
            "3. 可以使用 custom_paths 参数指定自定义搜索路径",
            "4. 可以使用 custom_keywords 参数指定自定义搜索关键词",
        ]
    
    # 按得分排序
    found_documents.sort(key=lambda x: x.get("score", 0), reverse=True)
    
    return {
        "documents": found_documents[:max_results],
        "total_found": len(found_documents),
        "searched_paths": searched_paths,
        "inaccessible_paths": inaccessible_paths,
        "search_keywords": search_keywords[:10],
        "suggestions": suggestions,
    }


def extract_checklist_from_document(
    root_dir: str,
    doc_rel_path: str,
    max_bytes: int = 500 * 1024,  # 最大读取 500KB
    rule_id_prefix: Optional[str] = None,
) -> Dict[str, Any]:
    """从单个规范文档中提取检查清单
    
    Args:
        root_dir: 共享盘根目录
        doc_rel_path: 文档相对路径
        max_bytes: 最大读取字节数
        rule_id_prefix: 规则ID前缀，默认使用文件名
        
    Returns:
        提取结果，包含:
        - checklist: StandardChecklist 字典形式
        - raw_sections: 原始章节信息
        - warnings: 提取过程中的警告
    """
    warnings = []
    
    # 读取文档内容
    try:
        result = read_text_file(
            root_dir=root_dir,
            rel_file=doc_rel_path,
            max_bytes=max_bytes,
            max_lines=10000,
        )
    except PathGuardError as e:
        return {
            "error": str(e),
            "checklist": None,
            "warnings": [f"无法读取文档: {e}"],
        }
    
    content = result.get("content", "")
    if not content:
        return {
            "error": "文档内容为空",
            "checklist": None,
            "warnings": ["文档内容为空"],
        }
    
    if result.get("truncated"):
        warnings.append(f"文档已截断，仅读取了 {result.get('read_bytes', 0)} 字节")
    
    # 生成规则ID前缀
    if rule_id_prefix is None:
        file_name = Path(doc_rel_path).stem
        # 简化文件名作为前缀
        rule_id_prefix = "".join(c for c in file_name if c.isalnum())[:10].upper()
        if not rule_id_prefix:
            rule_id_prefix = "RULE"
        rule_id_prefix += "_"
    
    # 创建检查清单
    checklist = StandardChecklist(name=f"规范检查清单 - {Path(doc_rel_path).name}")
    checklist.add_source_document(doc_rel_path)
    
    # 提取章节
    sections = _extract_markdown_sections(content)
    
    if not sections:
        # 如果没有章节结构，将整个内容作为一个章节处理
        sections = [{
            "level": 1,
            "title": "规范内容",
            "content": content,
            "line_start": 1,
            "line_end": content.count('\n') + 1,
        }]
        warnings.append("文档缺少章节结构，已作为单一章节处理")
    
    # 从每个章节提取规则
    for section in sections:
        category = _infer_category_from_path(doc_rel_path, section.get("title", ""))
        rules = _extract_rules_from_section(
            section=section,
            source_file=doc_rel_path,
            category=category,
            rule_id_prefix=rule_id_prefix,
        )
        
        for rule in rules:
            checklist.add_rule(rule)
    
    if not checklist.rules:
        warnings.append("未能从文档中提取到规则，可能文档格式不符合预期")
    
    return {
        "checklist": checklist.to_dict(),
        "formatted_checklist": checklist.format_for_review(),
        "raw_sections": sections,
        "warnings": warnings,
    }


def build_project_checklist(
    root_dir: str,
    doc_paths: Optional[List[str]] = None,
    auto_locate: bool = True,
    custom_search_paths: Optional[List[str]] = None,
    custom_keywords: Optional[List[str]] = None,
    max_documents: int = 10,
) -> Dict[str, Any]:
    """构建项目规范检查清单
    
    综合功能：定位规范文档 + 提取检查清单
    
    Args:
        root_dir: 共享盘根目录
        doc_paths: 指定的文档路径列表（优先使用）
        auto_locate: 如果未指定文档，是否自动定位
        custom_search_paths: 自动定位时的自定义搜索路径
        custom_keywords: 自动定位时的自定义关键词
        max_documents: 最大处理文档数
        
    Returns:
        构建结果，包含:
        - checklist: 合并后的检查清单
        - processed_documents: 已处理的文档信息
        - warnings: 警告信息
        - suggestions: 建议
    """
    processed_documents: List[Dict[str, Any]] = []
    all_warnings: List[str] = []
    
    # 确定要处理的文档列表
    target_docs = []
    
    if doc_paths:
        target_docs = doc_paths[:max_documents]
    elif auto_locate:
        locate_result = locate_standard_documents(
            root_dir=root_dir,
            custom_paths=custom_search_paths,
            custom_keywords=custom_keywords,
            max_results=max_documents,
        )
        
        if locate_result.get("suggestions"):
            all_warnings.extend(locate_result["suggestions"])
        
        target_docs = [doc["path"] for doc in locate_result.get("documents", [])]
    
    if not target_docs:
        return {
            "error": "未找到任何规范文档",
            "checklist": None,
            "processed_documents": [],
            "warnings": all_warnings,
            "suggestions": [
                "请使用 doc_paths 参数指定规范文档路径",
                "或确保规范文档存放在标准目录下（如 '规范/'、'Standards/'）",
            ],
        }
    
    # 创建合并的检查清单
    merged_checklist = StandardChecklist(name="项目规范检查清单")
    
    # 处理每个文档
    for doc_path in target_docs:
        result = extract_checklist_from_document(
            root_dir=root_dir,
            doc_rel_path=doc_path,
        )
        
        if result.get("error"):
            processed_documents.append({
                "path": doc_path,
                "status": "failed",
                "error": result["error"],
            })
            all_warnings.append(f"处理 {doc_path} 失败: {result['error']}")
            continue
        
        checklist_data = result.get("checklist", {})
        rules_count = checklist_data.get("total_rules", 0)
        
        processed_documents.append({
            "path": doc_path,
            "status": "success",
            "rules_extracted": rules_count,
            "categories": checklist_data.get("categories", []),
        })
        
        # 合并规则
        merged_checklist.add_source_document(doc_path)
        for rule_data in checklist_data.get("rules", []):
            rule = StandardRule(
                rule_id=rule_data["rule_id"],
                title=rule_data["title"],
                description=rule_data["description"],
                keywords=rule_data.get("keywords", []),
                severity=rule_data.get("severity", "warning"),
                source_file=rule_data.get("source", {}).get("file", ""),
                source_line=rule_data.get("source", {}).get("line"),
                source_section=rule_data.get("source", {}).get("section"),
                category=rule_data.get("category", "general"),
                examples=rule_data.get("examples", []),
                counter_examples=rule_data.get("counter_examples", []),
            )
            merged_checklist.add_rule(rule)
        
        if result.get("warnings"):
            all_warnings.extend(result["warnings"])
    
    return {
        "checklist": merged_checklist.to_dict(),
        "formatted_checklist": merged_checklist.format_for_review(),
        "processed_documents": processed_documents,
        "total_rules": len(merged_checklist.rules),
        "total_documents": len(processed_documents),
        "warnings": all_warnings,
        "suggestions": [],
    }


class StandardLocator:
    """规范定位器类，提供规范文档的定位和管理功能
    
    支持：
    1. 自动定位规范文档
    2. 用户指定替代路径
    3. 缓存已定位的文档
    4. 提取和管理检查清单
    """
    
    def __init__(
        self,
        root_dir: str,
        custom_paths: Optional[List[str]] = None,
        custom_keywords: Optional[List[str]] = None,
    ):
        """初始化规范定位器
        
        Args:
            root_dir: 共享盘根目录
            custom_paths: 自定义搜索路径
            custom_keywords: 自定义搜索关键词
        """
        self.root_dir = root_dir
        self.custom_paths = custom_paths or []
        self.custom_keywords = custom_keywords or []
        
        self._located_documents: Optional[List[Dict[str, Any]]] = None
        self._checklist: Optional[StandardChecklist] = None
        self._last_locate_result: Optional[Dict[str, Any]] = None
    
    def locate(self, force_refresh: bool = False) -> Dict[str, Any]:
        """定位规范文档
        
        Args:
            force_refresh: 是否强制刷新（忽略缓存）
            
        Returns:
            定位结果
        """
        if self._last_locate_result is not None and not force_refresh:
            return self._last_locate_result
        
        result = locate_standard_documents(
            root_dir=self.root_dir,
            custom_paths=self.custom_paths if self.custom_paths else None,
            custom_keywords=self.custom_keywords if self.custom_keywords else None,
        )
        
        self._located_documents = result.get("documents", [])
        self._last_locate_result = result
        
        return result
    
    def set_custom_paths(self, paths: List[str]) -> None:
        """设置自定义搜索路径
        
        Args:
            paths: 路径列表
        """
        self.custom_paths = paths
        # 清除缓存
        self._located_documents = None
        self._last_locate_result = None
        self._checklist = None
    
    def set_custom_keywords(self, keywords: List[str]) -> None:
        """设置自定义搜索关键词
        
        Args:
            keywords: 关键词列表
        """
        self.custom_keywords = keywords
        # 清除缓存
        self._located_documents = None
        self._last_locate_result = None
    
    def get_located_documents(self) -> List[Dict[str, Any]]:
        """获取已定位的文档列表
        
        Returns:
            文档列表
        """
        if self._located_documents is None:
            self.locate()
        return self._located_documents or []
    
    def build_checklist(
        self,
        doc_paths: Optional[List[str]] = None,
        force_refresh: bool = False,
    ) -> Dict[str, Any]:
        """构建检查清单
        
        Args:
            doc_paths: 指定的文档路径（可选）
            force_refresh: 是否强制刷新
            
        Returns:
            构建结果
        """
        if self._checklist is not None and not force_refresh and doc_paths is None:
            return {
                "checklist": self._checklist.to_dict(),
                "formatted_checklist": self._checklist.format_for_review(),
                "source": "cache",
            }
        
        # 如果没有指定文档，使用已定位的文档
        if doc_paths is None:
            docs = self.get_located_documents()
            doc_paths = [d["path"] for d in docs]
        
        result = build_project_checklist(
            root_dir=self.root_dir,
            doc_paths=doc_paths,
            auto_locate=False,  # 已经有文档列表了
        )
        
        # 缓存检查清单
        if result.get("checklist"):
            checklist_data = result["checklist"]
            self._checklist = StandardChecklist(name=checklist_data.get("name", "项目规范检查清单"))
            # 重建 checklist 对象...（简化处理，直接使用 result）
        
        return result
    
    def get_checklist(self) -> Optional[StandardChecklist]:
        """获取检查清单对象
        
        Returns:
            StandardChecklist 对象，如果未构建则返回 None
        """
        return self._checklist
    
    def get_status(self) -> Dict[str, Any]:
        """获取定位器状态
        
        Returns:
            状态信息
        """
        return {
            "root_dir": self.root_dir,
            "custom_paths": self.custom_paths,
            "custom_keywords": self.custom_keywords,
            "located_documents_count": len(self._located_documents) if self._located_documents else 0,
            "checklist_ready": self._checklist is not None,
            "checklist_rules_count": len(self._checklist.rules) if self._checklist else 0,
        }


def create_standard_locator(
    root_dir: str,
    custom_paths: Optional[List[str]] = None,
    custom_keywords: Optional[List[str]] = None,
) -> StandardLocator:
    """创建规范定位器实例（工厂函数）
    
    Args:
        root_dir: 共享盘根目录
        custom_paths: 自定义搜索路径
        custom_keywords: 自定义搜索关键词
        
    Returns:
        StandardLocator 实例
    """
    return StandardLocator(
        root_dir=root_dir,
        custom_paths=custom_paths,
        custom_keywords=custom_keywords,
    )


# ============================================================================
# 代码 Review 输出器
# ============================================================================

@dataclass
class ReviewIssue:
    """单个 Review 问题"""
    rule_id: str
    rule_title: str
    severity: str  # error, warning, info
    description: str
    file_path: str
    line_start: Optional[int] = None
    line_end: Optional[int] = None
    code_snippet: Optional[str] = None
    suggestion: Optional[str] = None
    rule_reference: Optional[str] = None  # 规范来源引用
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "rule_id": self.rule_id,
            "rule_title": self.rule_title,
            "severity": self.severity,
            "description": self.description,
            "location": {
                "file": self.file_path,
                "line_start": self.line_start,
                "line_end": self.line_end,
            },
            "code_snippet": self.code_snippet,
            "suggestion": self.suggestion,
            "rule_reference": self.rule_reference,
        }
    
    def format_markdown(self) -> str:
        """格式化为 Markdown"""
        severity_icon = {"error": "❌", "warning": "⚠️", "info": "ℹ️"}.get(self.severity, "•")
        lines = [
            f"### {severity_icon} [{self.rule_id}] {self.rule_title}",
            f"",
            f"**严重级别**: {self.severity}",
            f"**文件**: `{self.file_path}`",
        ]
        
        if self.line_start:
            if self.line_end and self.line_end != self.line_start:
                lines.append(f"**行号**: L{self.line_start}-L{self.line_end}")
            else:
                lines.append(f"**行号**: L{self.line_start}")
        
        lines.append(f"")
        lines.append(f"**问题描述**: {self.description}")
        
        if self.code_snippet:
            lines.append(f"")
            lines.append(f"**问题代码**:")
            lines.append(f"```")
            lines.append(self.code_snippet)
            lines.append(f"```")
        
        if self.suggestion:
            lines.append(f"")
            lines.append(f"**修复建议**: {self.suggestion}")
        
        if self.rule_reference:
            lines.append(f"")
            lines.append(f"**规范引用**: {self.rule_reference}")
        
        return "\n".join(lines)


@dataclass
class FileReviewResult:
    """单个文件的 Review 结果"""
    file_path: str
    issues: List[ReviewIssue]
    reviewed_at: str
    
    def __init__(self, file_path: str):
        self.file_path = file_path
        self.issues = []
        self.reviewed_at = datetime.now().isoformat()
    
    def add_issue(self, issue: ReviewIssue) -> None:
        self.issues.append(issue)
    
    @property
    def error_count(self) -> int:
        return len([i for i in self.issues if i.severity == "error"])
    
    @property
    def warning_count(self) -> int:
        return len([i for i in self.issues if i.severity == "warning"])
    
    @property
    def info_count(self) -> int:
        return len([i for i in self.issues if i.severity == "info"])
    
    @property
    def has_blocking_issues(self) -> bool:
        """是否有阻塞性问题（error级别）"""
        return self.error_count > 0
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "file_path": self.file_path,
            "reviewed_at": self.reviewed_at,
            "summary": {
                "total_issues": len(self.issues),
                "errors": self.error_count,
                "warnings": self.warning_count,
                "infos": self.info_count,
                "has_blocking_issues": self.has_blocking_issues,
            },
            "issues": [i.to_dict() for i in self.issues],
        }
    
    def format_markdown(self) -> str:
        """格式化为 Markdown"""
        lines = [
            f"## 📄 {self.file_path}",
            f"",
            f"**Review 时间**: {self.reviewed_at}",
            f"**问题统计**: {self.error_count} 错误, {self.warning_count} 警告, {self.info_count} 提示",
            f"",
        ]
        
        if not self.issues:
            lines.append("✅ 未发现问题")
        else:
            # 按严重级别排序（error > warning > info）
            severity_order = {"error": 0, "warning": 1, "info": 2}
            sorted_issues = sorted(self.issues, key=lambda x: severity_order.get(x.severity, 3))
            
            for issue in sorted_issues:
                lines.append(issue.format_markdown())
                lines.append("")
        
        return "\n".join(lines)


@dataclass
class ReviewReport:
    """完整的 Review 报告"""
    file_results: List[FileReviewResult]
    checklist_name: str
    checklist_rules_count: int
    created_at: str
    
    def __init__(self, checklist_name: str = "项目规范检查清单", checklist_rules_count: int = 0):
        self.file_results = []
        self.checklist_name = checklist_name
        self.checklist_rules_count = checklist_rules_count
        self.created_at = datetime.now().isoformat()
    
    def add_file_result(self, result: FileReviewResult) -> None:
        self.file_results.append(result)
    
    @property
    def total_files(self) -> int:
        return len(self.file_results)
    
    @property
    def total_issues(self) -> int:
        return sum(len(r.issues) for r in self.file_results)
    
    @property
    def total_errors(self) -> int:
        return sum(r.error_count for r in self.file_results)
    
    @property
    def total_warnings(self) -> int:
        return sum(r.warning_count for r in self.file_results)
    
    @property
    def total_infos(self) -> int:
        return sum(r.info_count for r in self.file_results)
    
    @property
    def has_blocking_issues(self) -> bool:
        return any(r.has_blocking_issues for r in self.file_results)
    
    @property
    def files_with_issues(self) -> List[FileReviewResult]:
        return [r for r in self.file_results if r.issues]
    
    @property
    def clean_files(self) -> List[FileReviewResult]:
        return [r for r in self.file_results if not r.issues]
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "created_at": self.created_at,
            "checklist": {
                "name": self.checklist_name,
                "rules_count": self.checklist_rules_count,
            },
            "summary": {
                "total_files": self.total_files,
                "files_with_issues": len(self.files_with_issues),
                "clean_files": len(self.clean_files),
                "total_issues": self.total_issues,
                "errors": self.total_errors,
                "warnings": self.total_warnings,
                "infos": self.total_infos,
                "has_blocking_issues": self.has_blocking_issues,
                "verdict": "BLOCKED" if self.has_blocking_issues else ("PASSED_WITH_WARNINGS" if self.total_warnings > 0 else "PASSED"),
            },
            "file_results": [r.to_dict() for r in self.file_results],
        }
    
    def format_markdown(self) -> str:
        """格式化为完整的 Markdown 报告"""
        verdict = "🚫 阻塞" if self.has_blocking_issues else ("⚠️ 通过(有警告)" if self.total_warnings > 0 else "✅ 通过")
        
        lines = [
            f"# 代码 Review 报告",
            f"",
            f"**生成时间**: {self.created_at}",
            f"**使用规范**: {self.checklist_name} ({self.checklist_rules_count} 条规则)",
            f"",
            f"---",
            f"",
            f"## 📊 总体结果: {verdict}",
            f"",
            f"| 指标 | 数量 |",
            f"|------|------|",
            f"| 检查文件数 | {self.total_files} |",
            f"| 有问题的文件 | {len(self.files_with_issues)} |",
            f"| 无问题的文件 | {len(self.clean_files)} |",
            f"| 总问题数 | {self.total_issues} |",
            f"| ❌ 错误 (阻塞项) | {self.total_errors} |",
            f"| ⚠️ 警告 (建议项) | {self.total_warnings} |",
            f"| ℹ️ 提示 | {self.total_infos} |",
            f"",
        ]
        
        # 阻塞项汇总
        if self.total_errors > 0:
            lines.append(f"## 🚫 阻塞项汇总 ({self.total_errors} 项)")
            lines.append("")
            for result in self.file_results:
                for issue in result.issues:
                    if issue.severity == "error":
                        loc = f"`{issue.file_path}`"
                        if issue.line_start:
                            loc += f":L{issue.line_start}"
                        lines.append(f"- **[{issue.rule_id}]** {issue.description} - {loc}")
            lines.append("")
        
        # 建议项汇总
        if self.total_warnings > 0:
            lines.append(f"## ⚠️ 建议项汇总 ({self.total_warnings} 项)")
            lines.append("")
            for result in self.file_results:
                for issue in result.issues:
                    if issue.severity == "warning":
                        loc = f"`{issue.file_path}`"
                        if issue.line_start:
                            loc += f":L{issue.line_start}"
                        lines.append(f"- **[{issue.rule_id}]** {issue.description} - {loc}")
            lines.append("")
        
        # 各文件详细报告
        lines.append("---")
        lines.append("")
        lines.append("# 详细报告")
        lines.append("")
        
        for result in self.file_results:
            lines.append(result.format_markdown())
            lines.append("")
            lines.append("---")
            lines.append("")
        
        return "\n".join(lines)


class CodeReviewer:
    """代码 Review 执行器
    
    基于规范检查清单对代码进行 Review，输出问题描述、严重级别、规范引用和修复建议。
    """
    
    def __init__(
        self,
        root_dir: str,
        checklist: Optional[StandardChecklist] = None,
        locator: Optional[StandardLocator] = None,
    ):
        """初始化 Review 执行器
        
        Args:
            root_dir: 共享盘根目录
            checklist: 已构建的检查清单（可选）
            locator: 规范定位器（可选，用于自动构建检查清单）
        """
        self.root_dir = root_dir
        self._checklist = checklist
        self._locator = locator
        self._report: Optional[ReviewReport] = None
    
    def ensure_checklist(self) -> StandardChecklist:
        """确保检查清单已准备好
        
        Returns:
            StandardChecklist 对象
            
        Raises:
            RuntimeError: 如果无法获取或构建检查清单
        """
        if self._checklist is not None:
            return self._checklist
        
        # 尝试从 locator 获取
        if self._locator is not None:
            result = self._locator.build_checklist()
            checklist_data = result.get("checklist", {})
            
            # 重建 StandardChecklist 对象
            self._checklist = StandardChecklist(name=checklist_data.get("name", "项目规范检查清单"))
            
            for rule_data in checklist_data.get("rules", []):
                rule = StandardRule(
                    rule_id=rule_data.get("rule_id", ""),
                    title=rule_data.get("title", ""),
                    description=rule_data.get("description", ""),
                    keywords=rule_data.get("keywords", []),
                    severity=rule_data.get("severity", "warning"),
                    source_file=rule_data.get("source", {}).get("file", ""),
                    source_line=rule_data.get("source", {}).get("line"),
                    source_section=rule_data.get("source", {}).get("section"),
                    category=rule_data.get("category", "general"),
                    examples=rule_data.get("examples", []),
                    counter_examples=rule_data.get("counter_examples", []),
                )
                self._checklist.add_rule(rule)
            
            return self._checklist
        
        raise RuntimeError("无法获取规范检查清单：请先提供 checklist 或 locator")
    
    def review_code_snippet(
        self,
        code: str,
        file_path: str = "<snippet>",
        language: Optional[str] = None,
    ) -> FileReviewResult:
        """Review 代码片段
        
        Args:
            code: 代码内容
            file_path: 文件路径（用于报告）
            language: 编程语言（可选，用于语言特定检查）
            
        Returns:
            FileReviewResult 对象
        """
        checklist = self.ensure_checklist()
        result = FileReviewResult(file_path)
        
        # 对每条规则进行检查
        for rule in checklist.rules:
            issues = self._check_rule_against_code(rule, code, file_path, language)
            for issue in issues:
                result.add_issue(issue)
        
        return result
    
    def review_file(
        self,
        file_path: str,
        workspace_root: Optional[str] = None,
    ) -> FileReviewResult:
        """Review 单个文件
        
        Args:
            file_path: 文件路径（相对于 workspace_root 或绝对路径）
            workspace_root: 工作区根目录（可选）
            
        Returns:
            FileReviewResult 对象
        """
        # 解析文件路径
        if workspace_root:
            full_path = os.path.join(workspace_root, file_path)
        else:
            full_path = file_path
        
        full_path = os.path.normpath(full_path)
        
        # 读取文件内容
        if not os.path.isfile(full_path):
            result = FileReviewResult(file_path)
            result.add_issue(ReviewIssue(
                rule_id="SYSTEM",
                rule_title="文件不存在",
                severity="error",
                description=f"无法找到文件: {full_path}",
                file_path=file_path,
            ))
            return result
        
        try:
            with open(full_path, "r", encoding="utf-8", errors="replace") as f:
                code = f.read()
        except Exception as e:
            result = FileReviewResult(file_path)
            result.add_issue(ReviewIssue(
                rule_id="SYSTEM",
                rule_title="文件读取失败",
                severity="error",
                description=f"读取文件时出错: {e}",
                file_path=file_path,
            ))
            return result
        
        # 根据文件扩展名推断语言
        ext = os.path.splitext(file_path)[1].lower()
        language = self._detect_language(ext)
        
        return self.review_code_snippet(code, file_path, language)
    
    def review_files(
        self,
        file_paths: List[str],
        workspace_root: Optional[str] = None,
    ) -> ReviewReport:
        """Review 多个文件
        
        Args:
            file_paths: 文件路径列表
            workspace_root: 工作区根目录（可选）
            
        Returns:
            ReviewReport 对象
        """
        checklist = self.ensure_checklist()
        report = ReviewReport(
            checklist_name=checklist.name,
            checklist_rules_count=len(checklist.rules),
        )
        
        for file_path in file_paths:
            result = self.review_file(file_path, workspace_root)
            report.add_file_result(result)
        
        self._report = report
        return report
    
    def review_diff(
        self,
        diff_content: str,
        base_path: str = "",
    ) -> ReviewReport:
        """Review Git diff 内容
        
        Args:
            diff_content: Git diff 输出内容
            base_path: 基础路径（用于定位文件）
            
        Returns:
            ReviewReport 对象
        """
        checklist = self.ensure_checklist()
        report = ReviewReport(
            checklist_name=checklist.name,
            checklist_rules_count=len(checklist.rules),
        )
        
        # 解析 diff 内容
        diff_files = self._parse_diff(diff_content)
        
        for file_info in diff_files:
            file_path = file_info["path"]
            added_lines = file_info.get("added_lines", [])
            
            if not added_lines:
                continue
            
            # 只检查新增的代码
            result = FileReviewResult(file_path)
            
            for line_info in added_lines:
                line_num = line_info["line_num"]
                line_content = line_info["content"]
                
                # 对每条规则检查这一行
                for rule in checklist.rules:
                    issue = self._check_rule_against_line(rule, line_content, file_path, line_num)
                    if issue:
                        result.add_issue(issue)
            
            if result.issues:
                report.add_file_result(result)
        
        self._report = report
        return report
    
    def get_report(self) -> Optional[ReviewReport]:
        """获取最近的 Review 报告"""
        return self._report
    
    def _detect_language(self, ext: str) -> str:
        """根据文件扩展名检测编程语言"""
        lang_map = {
            ".py": "python",
            ".js": "javascript",
            ".ts": "typescript",
            ".jsx": "javascript",
            ".tsx": "typescript",
            ".java": "java",
            ".cpp": "cpp",
            ".cc": "cpp",
            ".cxx": "cpp",
            ".c": "c",
            ".h": "cpp",
            ".hpp": "cpp",
            ".cs": "csharp",
            ".go": "go",
            ".rs": "rust",
            ".rb": "ruby",
            ".php": "php",
            ".swift": "swift",
            ".kt": "kotlin",
            ".scala": "scala",
            ".lua": "lua",
            ".sh": "shell",
            ".bash": "shell",
            ".ps1": "powershell",
            ".sql": "sql",
            ".html": "html",
            ".css": "css",
            ".scss": "scss",
            ".less": "less",
            ".json": "json",
            ".xml": "xml",
            ".yaml": "yaml",
            ".yml": "yaml",
            ".md": "markdown",
            ".ini": "ini",
            ".cfg": "ini",
            ".toml": "toml",
        }
        return lang_map.get(ext, "unknown")
    
    def _check_rule_against_code(
        self,
        rule: StandardRule,
        code: str,
        file_path: str,
        language: Optional[str],
    ) -> List[ReviewIssue]:
        """检查代码是否违反某条规则
        
        基于关键词匹配和模式匹配进行启发式检查
        """
        issues = []
        lines = code.split('\n')
        
        # 针对每个关键词进行检查
        for keyword in rule.keywords:
            keyword_lower = keyword.lower()
            
            for line_num, line in enumerate(lines, 1):
                line_lower = line.lower()
                
                # 简单的关键词匹配
                if keyword_lower in line_lower:
                    # 检查是否是反例模式
                    is_violation = self._is_violation_pattern(rule, line, keyword)
                    
                    if is_violation:
                        # 获取代码上下文（前后各2行）
                        start_idx = max(0, line_num - 3)
                        end_idx = min(len(lines), line_num + 2)
                        snippet = '\n'.join(lines[start_idx:end_idx])
                        
                        # 生成规范引用
                        rule_ref = rule.source_file
                        if rule.source_line:
                            rule_ref += f":L{rule.source_line}"
                        if rule.source_section:
                            rule_ref += f" §{rule.source_section}"
                        
                        issue = ReviewIssue(
                            rule_id=rule.rule_id,
                            rule_title=rule.title,
                            severity=rule.severity,
                            description=rule.description,
                            file_path=file_path,
                            line_start=line_num,
                            code_snippet=snippet,
                            suggestion=self._generate_suggestion(rule, line),
                            rule_reference=rule_ref if rule_ref else None,
                        )
                        issues.append(issue)
                        break  # 每条规则每个文件只报告一次主要问题
        
        return issues
    
    def _check_rule_against_line(
        self,
        rule: StandardRule,
        line: str,
        file_path: str,
        line_num: int,
    ) -> Optional[ReviewIssue]:
        """检查单行代码是否违反某条规则"""
        line_lower = line.lower()
        
        for keyword in rule.keywords:
            if keyword.lower() in line_lower:
                if self._is_violation_pattern(rule, line, keyword):
                    rule_ref = rule.source_file
                    if rule.source_line:
                        rule_ref += f":L{rule.source_line}"
                    
                    return ReviewIssue(
                        rule_id=rule.rule_id,
                        rule_title=rule.title,
                        severity=rule.severity,
                        description=rule.description,
                        file_path=file_path,
                        line_start=line_num,
                        code_snippet=line.strip(),
                        suggestion=self._generate_suggestion(rule, line),
                        rule_reference=rule_ref if rule_ref else None,
                    )
        
        return None
    
    def _is_violation_pattern(self, rule: StandardRule, line: str, keyword: str) -> bool:
        """判断是否为违规模式
        
        基于规则的反例进行匹配
        """
        # 如果有反例，检查是否匹配
        if rule.counter_examples:
            line_normalized = line.strip().lower()
            for counter_ex in rule.counter_examples:
                counter_normalized = counter_ex.strip().lower()
                # 简单的包含检查
                if counter_normalized in line_normalized or line_normalized in counter_normalized:
                    return True
        
        # 基于关键词的启发式检查
        # 如果规则严重级别为 error，且包含"禁止"、"不得"等词，认为匹配即违规
        negative_keywords = ["禁止", "不得", "不允许", "forbidden", "never", "must not", "shall not"]
        if rule.severity == "error":
            for neg_kw in negative_keywords:
                if neg_kw in rule.description.lower():
                    return True
        
        # 默认不认为是违规（避免误报）
        return False
    
    def _generate_suggestion(self, rule: StandardRule, line: str) -> str:
        """生成修复建议"""
        # 如果规则有正确示例，使用第一个作为参考
        if rule.examples:
            return f"参考正确示例: {rule.examples[0]}"
        
        # 否则返回通用建议
        return f"请根据规范 [{rule.rule_id}] 修改此处代码"
    
    def _parse_diff(self, diff_content: str) -> List[Dict[str, Any]]:
        """解析 Git diff 内容
        
        Returns:
            文件信息列表，每项包含 path, added_lines
        """
        import re
        
        files = []
        current_file = None
        current_line_num = 0
        
        lines = diff_content.split('\n')
        
        # 匹配文件头
        file_header_pattern = re.compile(r'^diff --git a/(.+) b/(.+)$')
        # 匹配 hunk 头
        hunk_pattern = re.compile(r'^@@ -\d+(?:,\d+)? \+(\d+)(?:,\d+)? @@')
        
        for line in lines:
            # 检查文件头
            file_match = file_header_pattern.match(line)
            if file_match:
                if current_file:
                    files.append(current_file)
                current_file = {
                    "path": file_match.group(2),
                    "added_lines": [],
                }
                continue
            
            # 检查 hunk 头
            hunk_match = hunk_pattern.match(line)
            if hunk_match:
                current_line_num = int(hunk_match.group(1))
                continue
            
            # 检查新增行
            if current_file and line.startswith('+') and not line.startswith('+++'):
                current_file["added_lines"].append({
                    "line_num": current_line_num,
                    "content": line[1:],  # 去掉 + 前缀
                })
                current_line_num += 1
            elif current_file and line.startswith(' '):
                # 上下文行
                current_line_num += 1
            elif current_file and line.startswith('-'):
                # 删除行不增加行号
                pass
        
        if current_file:
            files.append(current_file)
        
        return files


def review_code(
    root_dir: str,
    code: Optional[str] = None,
    file_path: Optional[str] = None,
    file_paths: Optional[List[str]] = None,
    diff_content: Optional[str] = None,
    workspace_root: Optional[str] = None,
    custom_standard_paths: Optional[List[str]] = None,
    custom_standard_keywords: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """执行代码 Review 的统一入口函数
    
    Args:
        root_dir: 共享盘根目录（用于定位规范文档）
        code: 代码片段内容（与 file_path/file_paths/diff_content 互斥）
        file_path: 单个文件路径
        file_paths: 多个文件路径
        diff_content: Git diff 内容
        workspace_root: 工作区根目录（用于解析相对文件路径）
        custom_standard_paths: 自定义规范文档路径
        custom_standard_keywords: 自定义规范关键词
        
    Returns:
        Review 结果字典
    """
    try:
        # 创建规范定位器
        locator = create_standard_locator(
            root_dir=root_dir,
            custom_paths=custom_standard_paths,
            custom_keywords=custom_standard_keywords,
        )
        
        # 定位规范文档
        locate_result = locator.locate()
        # 修复：使用 documents 列表判断是否找到文档，而不是不存在的 found 字段
        if not locate_result.get("documents"):
            return {
                "ok": False,
                "error": "未找到规范文档",
                "suggestions": locate_result.get("suggestions", []),
            }
        
        # 构建检查清单
        checklist_result = locator.build_checklist()
        if not checklist_result.get("checklist"):
            return {
                "ok": False,
                "error": "无法构建检查清单",
            }
        
        # 创建 Reviewer
        reviewer = CodeReviewer(
            root_dir=root_dir,
            locator=locator,
        )
        
        # 根据输入类型执行 Review
        if code is not None:
            # Review 代码片段
            result = reviewer.review_code_snippet(code, file_path or "<snippet>")
            report = ReviewReport(
                checklist_name=checklist_result["checklist"].get("name", "项目规范检查清单"),
                checklist_rules_count=checklist_result["checklist"].get("total_rules", 0),
            )
            report.add_file_result(result)
        elif file_path is not None:
            # Review 单个文件
            result = reviewer.review_file(file_path, workspace_root)
            report = ReviewReport(
                checklist_name=checklist_result["checklist"].get("name", "项目规范检查清单"),
                checklist_rules_count=checklist_result["checklist"].get("total_rules", 0),
            )
            report.add_file_result(result)
        elif file_paths is not None:
            # Review 多个文件
            report = reviewer.review_files(file_paths, workspace_root)
        elif diff_content is not None:
            # Review diff
            report = reviewer.review_diff(diff_content)
        else:
            return {
                "ok": False,
                "error": "请提供代码片段(code)、文件路径(file_path/file_paths)或diff内容(diff_content)",
            }
        
        return {
            "ok": True,
            "report": report.to_dict(),
            "formatted_report": report.format_markdown(),
            "standards_used": {
                "documents": [d["path"] for d in locate_result.get("documents", [])],
                "rules_count": checklist_result["checklist"].get("total_rules", 0),
            },
        }
        
    except Exception as e:
        return {
            "ok": False,
            "error": f"Review 执行出错: {str(e)}",
        }


# =============================================================================
# DocStore 统一门面类 - 整合所有功能供外部调用
# =============================================================================

class DocStore:
    """共享盘文档存储统一接口
    
    整合 list/read/upload/search/review 等功能，提供统一的调用入口。
    
    Usage:
        store = DocStore(root_dir="W:/S1UnrealSharedDoc")
        
        # 目录浏览
        result = store.list_dir("docs")
        
        # 文件读取
        result = store.read_file("docs/readme.md")
        
        # 文件上传
        result = store.upload_file("uploads/new.txt", "content")
        
        # 文档检索
        result = store.search("关键词")
        
        # 代码 Review
        result = store.review_code(snippet="def foo(): pass")
    """
    
    def __init__(
        self,
        root_dir: str,
        upload_max_bytes: int = 10 * 1024 * 1024,  # 10MB
        read_max_bytes: int = 1024 * 1024,  # 1MB
        read_max_lines: int = 5000,
    ):
        """初始化 DocStore
        
        Args:
            root_dir: 共享盘根目录路径
            upload_max_bytes: 上传文件大小限制（字节）
            read_max_bytes: 读取文件大小限制（字节）
            read_max_lines: 读取文件行数限制
        """
        self.root_dir = root_dir
        self.upload_max_bytes = upload_max_bytes
        self.read_max_bytes = read_max_bytes
        self.read_max_lines = read_max_lines
        
        # 懒加载的组件
        self._locator: Optional[StandardLocator] = None
    
    # -------------------------------------------------------------------------
    # 目录浏览
    # -------------------------------------------------------------------------
    
    def list_dir(self, rel_path: str = ".") -> Dict[str, Any]:
        """列出目录内容
        
        Args:
            rel_path: 相对于根目录的路径（默认为根目录）
            
        Returns:
            {
                "success": bool,
                "path": str,
                "items": [{"name", "type", "size", "modified"}, ...],
                "error": str (if failed)
            }
        """
        try:
            result = list_dir(self.root_dir, rel_path)
            # 统一返回格式
            result["success"] = result.pop("ok", True)
            return result
        except PathGuardError as e:
            return {"success": False, "error": str(e), "path": rel_path, "items": []}
        except Exception as e:
            return {"success": False, "error": f"列目录失败: {e}", "path": rel_path, "items": []}
    
    def read_file(
        self,
        rel_path: str,
        max_bytes: Optional[int] = None,
        max_lines: Optional[int] = None,
        offset: int = 0,
    ) -> Dict[str, Any]:
        """读取文件内容
        
        Args:
            rel_path: 相对于根目录的文件路径
            max_bytes: 最大读取字节数（可选）
            max_lines: 最大读取行数（可选）
            offset: 起始行偏移（从0开始）
            
        Returns:
            {
                "success": bool,
                "content": str,
                "truncated": bool,
                "total_lines": int,
                "error": str (if failed)
            }
        """
        try:
            mb = max_bytes if max_bytes is not None else self.read_max_bytes
            ml = max_lines if max_lines is not None else self.read_max_lines
            
            result = read_text_file(self.root_dir, rel_path, mb, ml)
            
            # 统一返回格式
            result["success"] = result.pop("ok", True)
            
            # 处理行偏移
            if result.get("success") and offset > 0 and "content" in result:
                lines = result["content"].split("\n")
                if offset < len(lines):
                    result["content"] = "\n".join(lines[offset:])
                else:
                    result["content"] = ""
            
            return result
        except PathGuardError as e:
            return {"success": False, "error": str(e), "content": ""}
        except Exception as e:
            return {"success": False, "error": f"读取文件失败: {e}", "content": ""}
    
    def upload_file(
        self,
        rel_path: str,
        content: str,
        conflict: str = "error",
    ) -> Dict[str, Any]:
        """上传文件（直接写入内容）
        
        Args:
            rel_path: 相对于根目录的目标路径
            content: 文件内容
            conflict: 冲突处理策略 ("error", "overwrite", "rename")
            
        Returns:
            {
                "success": bool,
                "path": str (实际保存的相对路径),
                "error": str (if failed)
            }
        """
        try:
            # 检查大小限制
            content_bytes = content.encode("utf-8")
            if len(content_bytes) > self.upload_max_bytes:
                return {
                    "success": False,
                    "error": f"文件大小超过限制 ({self.upload_max_bytes} 字节)",
                }
            
            # 直接写入文件（不使用底层 upload_file 函数，因为它需要本地文件路径）
            dest = normalize_and_validate_path(self.root_dir, rel_path)
            _ensure_parent_dir(dest)
            
            # 处理冲突
            if dest.exists():
                if conflict == "error":
                    return {
                        "success": False,
                        "error": f"文件已存在: {rel_path}",
                    }
                elif conflict == "rename":
                    dest = _resolve_conflict(dest, conflict)
            
            # 写入文件
            dest.write_text(content, encoding="utf-8")
            
            # 计算相对路径
            root_abs = Path(os.path.abspath(self.root_dir))
            final_rel = str(dest.relative_to(root_abs)).replace("\\", "/")
            
            return {
                "success": True,
                "path": final_rel,
            }
        except PathGuardError as e:
            return {"success": False, "error": str(e)}
        except Exception as e:
            return {"success": False, "error": f"上传文件失败: {e}"}
    
    # -------------------------------------------------------------------------
    # 文档检索
    # -------------------------------------------------------------------------
    
    def search(
        self,
        query: str,
        topk: int = 10,
        include_content: bool = False,
        file_types: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """检索文档
        
        Args:
            query: 搜索关键词（空格分隔多个关键词）
            topk: 返回结果数量上限
            include_content: 是否包含内容片段
            file_types: 限制文件类型（如 [".md", ".txt"]）
            
        Returns:
            {
                "success": bool,
                "results": [{"path", "score", "snippets"}, ...],
                "total": int,
                "error": str (if failed)
            }
        """
        try:
            # 将 query 分割为关键词列表
            keywords = [k.strip() for k in query.split() if k.strip()]
            if not keywords:
                keywords = [query] if query else []
            
            result = search_documents(
                root_dir=self.root_dir,
                keywords=keywords,
                search_dir=".",
                top_k=topk,
                include_content=include_content,
            )
            
            # 统一返回格式
            results = result.get("results", [])
            
            # 添加 snippets 字段
            for r in results:
                if "snippets" not in r and "matches" in r:
                    r["snippets"] = [m.get("snippet", "") for m in r.get("matches", [])]
            
            return {
                "success": True,
                "results": results,
                "total": result.get("total_found", len(results)),
            }
        except PathGuardError as e:
            return {"success": False, "error": str(e), "results": [], "total": 0}
        except Exception as e:
            return {"success": False, "error": f"搜索失败: {e}", "results": [], "total": 0}
    
    # -------------------------------------------------------------------------
    # 规范与 Review
    # -------------------------------------------------------------------------
    
    def locate_standards(self, subdir: str = "") -> Dict[str, Any]:
        """定位规范文档
        
        Args:
            subdir: 限制搜索的子目录
            
        Returns:
            {
                "success": bool,
                "files": [{"path", "type", "sections"}, ...],
                "error": str (if failed)
            }
        """
        try:
            result = locate_standard_documents(self.root_dir, subdir)
            
            # 统一返回格式
            success = result.get("ok", True)
            files = result.get("documents", [])
            
            return {
                "success": success,
                "files": files,
            }
        except PathGuardError as e:
            return {"success": False, "error": str(e), "files": []}
        except Exception as e:
            return {"success": False, "error": f"定位规范失败: {e}", "files": []}
    
    def extract_checklist(self, subdir: str = "") -> Dict[str, Any]:
        """提取规范检查清单
        
        Args:
            subdir: 限制搜索的子目录
            
        Returns:
            {
                "success": bool,
                "checklist": [{"id", "title", "description", "category"}, ...],
                "error": str (if failed)
            }
        """
        try:
            result = build_project_checklist(self.root_dir, subdir)
            
            # 统一返回格式
            success = result.get("ok", True)
            
            # 转换 checklist 格式
            checklist_data = result.get("checklist", {})
            if isinstance(checklist_data, dict):
                rules = checklist_data.get("rules", [])
            else:
                rules = []
            
            return {
                "success": success,
                "checklist": rules,
            }
        except PathGuardError as e:
            return {"success": False, "error": str(e), "checklist": []}
        except Exception as e:
            return {"success": False, "error": f"提取检查清单失败: {e}", "checklist": []}
    
    def review_code(
        self,
        snippet: Optional[str] = None,
        file_path: Optional[str] = None,
        checklist: Optional[List[Dict]] = None,
    ) -> Dict[str, Any]:
        """基于规范 Review 代码
        
        Args:
            snippet: 代码片段（与 file_path 二选一）
            file_path: 文件路径（相对于根目录）
            checklist: 自定义检查清单（可选）
            
        Returns:
            {
                "success": bool,
                "issues": [{"description", "severity", "line", "rule"}, ...],
                "summary": {"total_issues", "by_severity"},
                "error": str (if failed)
            }
        """
        try:
            # 如果指定了 file_path，先读取文件内容
            code_content = snippet
            source_path = file_path or "<snippet>"
            
            if file_path and not snippet:
                read_result = self.read_file(file_path)
                if not read_result.get("success"):
                    return {
                        "success": False,
                        "error": read_result.get("error", "无法读取文件"),
                        "issues": [],
                        "summary": {"total_issues": 0, "by_severity": {}},
                    }
                code_content = read_result.get("content", "")
            
            if not code_content:
                return {
                    "success": False,
                    "error": "请提供代码片段(snippet)或文件路径(file_path)",
                    "issues": [],
                    "summary": {"total_issues": 0, "by_severity": {}},
                }
            
            # 调用 review_code 函数
            result = review_code(
                root_dir=self.root_dir,
                code=code_content,
                file_path=source_path,
            )
            
            # 检查结果
            success = result.get("ok", False)
            
            if not success:
                return {
                    "success": False,
                    "error": result.get("error", "Review 执行失败"),
                    "issues": [],
                    "summary": {"total_issues": 0, "by_severity": {}},
                }
            
            # 转换结果格式
            report = result.get("report", {})
            issues = []
            
            for file_result in report.get("files", []):
                for issue in file_result.get("issues", []):
                    issues.append({
                        "description": issue.get("description", ""),
                        "severity": issue.get("severity", "info"),
                        "line": issue.get("line_number"),
                        "rule": issue.get("rule_title", ""),
                        "rule_id": issue.get("rule_id", ""),
                        "suggestion": issue.get("suggestion", ""),
                    })
            
            return {
                "success": True,
                "issues": issues,
                "summary": {
                    "total_issues": report.get("total_issues", len(issues)),
                    "by_severity": report.get("issues_by_severity", {}),
                },
            }
        except PathGuardError as e:
            return {
                "success": False,
                "error": str(e),
                "issues": [],
                "summary": {"total_issues": 0, "by_severity": {}},
            }
        except Exception as e:
            return {
                "success": False,
                "error": f"Review 执行出错: {e}",
                "issues": [],
                "summary": {"total_issues": 0, "by_severity": {}},
            }
