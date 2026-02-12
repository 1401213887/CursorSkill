# -*- coding: utf-8 -*-
"""
飞书上传工具（upload2feishu 自包含版）

用法1 - 命令行参数:
    python feishu_upload.py <文件路径> [--folder <文件夹token>] [--title <文档标题>]

用法2 - JSON 配置文件（推荐，解决 Windows 中文编码问题）:
    python feishu_upload.py --json <配置文件.json>

配置文件示例:
{
    "file": "文件路径",
    "title": "文档标题（可选）",
    "folder": "文件夹token（可选）",
    "raw": false
}

说明:
- raw=true: 直接上传原始文件（不依赖 feishu-docx）
- raw=false: 优先上传为云文档（若 feishu-docx 不可用，则自动降级为 raw 上传）
"""

#pragma region Engine ZXB

import argparse
import json
import os
import shutil
import subprocess
import sys

import requests as http_requests


DEFAULT_FOLDER_TOKEN = "LftxfwYm3lttjjdtO3DcscIEncA"
SKILL_ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir))
SKILL_AUTH_CONFIG_PATH = os.path.join(SKILL_ROOT_DIR, "config", "feishu_auth.json")
LEGACY_FEISHU_DOCX_CONFIG_PATH = os.path.join(os.path.expanduser("~"), ".feishu-docx", "config.json")


def _print_console_safe(text: str, stream=None):
    if not text:
        return
    target = stream or sys.stdout
    encoding = getattr(target, "encoding", None) or "utf-8"
    safe_text = text.encode(encoding, errors="replace").decode(encoding, errors="replace")
    target.write(safe_text)
    if not safe_text.endswith("\n"):
        target.write("\n")


def _read_json(path: str):
    with open(path, "r", encoding="utf-8") as file:
        return json.load(file)


def _resolve_feishu_docx_executable():
    command = shutil.which("feishu-docx")
    if command:
        return command

    candidates = [
        os.path.join(os.path.dirname(sys.executable), "Scripts", "feishu-docx.exe"),
        os.path.join(os.path.expanduser("~"), "AppData", "Local", "Programs", "Python", "Python311", "Scripts", "feishu-docx.exe"),
    ]
    for candidate in candidates:
        if os.path.exists(candidate):
            return candidate
    return None


def _load_app_credentials():
    app_id = os.getenv("FEISHU_APP_ID")
    app_secret = os.getenv("FEISHU_APP_SECRET")
    if app_id and app_secret:
        return app_id, app_secret

    config_paths = [SKILL_AUTH_CONFIG_PATH, LEGACY_FEISHU_DOCX_CONFIG_PATH]
    for path in config_paths:
        if os.path.exists(path):
            try:
                config = _read_json(path)
            except Exception:
                continue
            app_id = config.get("app_id")
            app_secret = config.get("app_secret")
            if app_id and app_secret:
                return app_id, app_secret

    print("错误: 未找到飞书应用凭据。")
    print("请任选其一完成配置：")
    print("1) 环境变量 FEISHU_APP_ID / FEISHU_APP_SECRET")
    print(f"2) Skill 本地配置文件: {SKILL_AUTH_CONFIG_PATH}")
    print(f"3) 兼容配置文件: {LEGACY_FEISHU_DOCX_CONFIG_PATH}")
    sys.exit(1)


def _get_tenant_token():
    app_id, app_secret = _load_app_credentials()
    response = http_requests.post(
        "https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal",
        json={"app_id": app_id, "app_secret": app_secret},
        timeout=15,
    )
    response.raise_for_status()
    result = response.json()
    if result.get("code") != 0:
        print(f"错误: 获取 tenant_access_token 失败 - {result.get('msg')}")
        sys.exit(1)
    return result["tenant_access_token"]


def upload_raw_file(file_path: str, folder_token: str, title: str = None):
    if not os.path.exists(file_path):
        print(f"错误: 文件不存在 - {file_path}")
        sys.exit(1)

    extension = os.path.splitext(file_path)[1]
    if title:
        file_name = title + extension if not title.endswith(extension) else title
    else:
        file_name = os.path.basename(file_path)

    file_size = os.path.getsize(file_path)
    token = _get_tenant_token()

    print("正在上传原始文件...")
    print(f"  文件: {file_path}")
    print(f"  上传名称: {file_name}")
    print(f"  文件大小: {file_size} bytes")
    print(f"  目标文件夹: {folder_token}")
    print()

    url = "https://open.feishu.cn/open-apis/drive/v1/files/upload_all"
    headers = {"Authorization": f"Bearer {token}"}

    with open(file_path, "rb") as file:
        form_data = {
            "file_name": (None, file_name),
            "parent_type": (None, "explorer"),
            "parent_node": (None, folder_token),
            "size": (None, str(file_size)),
            "file": (file_name, file, "application/octet-stream"),
        }
        response = http_requests.post(url, headers=headers, files=form_data, timeout=60)

    result = response.json()
    if result.get("code") != 0:
        print(f"上传失败! 错误码: {result.get('code')}, 信息: {result.get('msg')}")
        sys.exit(1)

    file_token = result.get("data", {}).get("file_token", "")
    file_url = f"https://sarosgame.feishu.cn/file/{file_token}"
    print("上传成功!")
    print(f"文件链接: {file_url}")
    print("上传完成!")


def _upload_cloud_with_feishu_docx(file_path: str, folder_token: str, title: str):
    executable = _resolve_feishu_docx_executable()
    if not executable:
        return False

    command = [executable, "create", title, "-f", file_path, "--folder", folder_token]
    environment = os.environ.copy()
    environment["PYTHONIOENCODING"] = "utf-8"

    result = subprocess.run(
        command,
        capture_output=True,
        text=True,
        encoding="utf-8",
        env=environment,
    )

    if result.stdout:
        _print_console_safe(result.stdout, sys.stdout)
    if result.stderr:
        _print_console_safe(result.stderr, sys.stderr)

    return result.returncode == 0


def upload_to_feishu(file_path: str, folder_token: str, title: str = None, strict_cloud: bool = False):
    if not os.path.exists(file_path):
        print(f"错误: 文件不存在 - {file_path}")
        sys.exit(1)

    if not title:
        title = os.path.splitext(os.path.basename(file_path))[0]

    print("正在上传文档（优先云文档）...")
    print(f"  文件: {file_path}")
    print(f"  标题: {title}")
    print(f"  目标文件夹: {folder_token}")
    print()

    if _upload_cloud_with_feishu_docx(file_path, folder_token, title):
        print("云文档上传完成!")
        return

    if strict_cloud:
        print("上传失败: 当前未能使用 feishu-docx 完成云文档上传，且 strict_cloud 已启用。")
        sys.exit(1)

    print("提示: 未检测到可用的 feishu-docx（或执行失败），自动降级为原始文件上传。")
    upload_raw_file(file_path, folder_token, title)


def main():
    parser = argparse.ArgumentParser(description="上传文档至飞书")
    parser.add_argument("file", nargs="?", default=None, help="要上传的文件路径（支持 .md/.txt/.json 等）")
    parser.add_argument("--folder", default=DEFAULT_FOLDER_TOKEN, help=f"飞书文件夹 token（默认: {DEFAULT_FOLDER_TOKEN}）")
    parser.add_argument("--title", default=None, help="文档标题（默认使用文件名）")
    parser.add_argument("--json", dest="json_config", default=None, help="JSON 配置文件路径")
    parser.add_argument("--raw", action="store_true", default=False, help="直接上传原始文件，不转为飞书云文档")
    parser.add_argument("--strict-cloud", action="store_true", default=False, help="强制云文档模式，不允许自动降级为 raw 上传")
    args = parser.parse_args()

    if args.json_config:
        config = _read_json(args.json_config)
        file_path = config["file"]
        folder_token = config.get("folder", DEFAULT_FOLDER_TOKEN)
        title = config.get("title")
        raw_mode = bool(config.get("raw", False) or args.raw)
    elif args.file:
        file_path = args.file
        folder_token = args.folder
        title = args.title
        raw_mode = args.raw
    else:
        parser.print_help()
        sys.exit(1)

    if raw_mode:
        upload_raw_file(file_path, folder_token, title)
    else:
        upload_to_feishu(file_path, folder_token, title, strict_cloud=args.strict_cloud)


if __name__ == "__main__":
    main()

#pragma endregion
