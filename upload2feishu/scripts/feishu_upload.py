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
    "raw": true
}

说明:
- raw=true: 直接上传原始文件（不依赖 feishu-docx）
- raw=false: 优先上传为云文档（若 feishu-docx 不可用，则自动降级为 raw 上传）
- 对于 .md/.markdown 文件，会强制按 raw 上传，避免飞书排版
"""

#pragma region Engine ZXB

import argparse
import json
import os
import platform
import shutil
import subprocess
import sys

# 自动检测并安装 requests 模块（如果需要）
try:
    import requests as http_requests
except ImportError:
    print("正在检测 requests 模块...")
    try:
        # 尝试安装 requests
        result = subprocess.run(
            [sys.executable, "-m", "pip", "install", "--user", "requests"],
            capture_output=True,
            text=True,
            timeout=120
        )
        if result.returncode == 0:
            print("✓ requests 安装成功")
            # 清除模块缓存并重新导入
            if 'requests' in sys.modules:
                del sys.modules['requests']
            import requests as http_requests
        else:
            print("❌ 自动安装 requests 失败")
            print("请手动运行以下命令安装:")
            print(f"  {sys.executable} -m pip install --user requests")
            sys.exit(1)
    except Exception as e:
        print(f"❌ 安装 requests 时出错: {e}")
        print("请手动运行以下命令安装:")
        print(f"  {sys.executable} -m pip install --user requests")
        sys.exit(1)


DEFAULT_FOLDER_TOKEN = "LftxfwYm3lttjjdtO3DcscIEncA"

# 跨平台路径处理
def _get_skill_root_dir():
    """获取 skill 根目录，支持 macOS 和 Windows"""
    script_dir = os.path.dirname(os.path.abspath(__file__))
    return os.path.abspath(os.path.join(script_dir, os.pardir))

def _get_config_path():
    """获取配置文件路径，支持跨平台"""
    skill_root = _get_skill_root_dir()
    return os.path.join(skill_root, "config", "feishu_auth.json")

def _get_legacy_config_path():
    """获取兼容的旧配置文件路径"""
    home = os.path.expanduser("~")
    if platform.system() == "Windows":
        return os.path.join(home, ".feishu-docx", "config.json")
    else:
        return os.path.join(home, ".feishu-docx", "config.json")

SKILL_ROOT_DIR = _get_skill_root_dir()
SKILL_AUTH_CONFIG_PATH = _get_config_path()
LEGACY_FEISHU_DOCX_CONFIG_PATH = _get_legacy_config_path()


def _is_markdown_file(file_path: str) -> bool:
    return os.path.splitext(file_path)[1].lower() in {".md", ".markdown"}


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
    """查找 feishu-docx 可执行文件，支持 macOS 和 Windows"""
    # 首先尝试通过 PATH 查找
    command = shutil.which("feishu-docx")
    if command:
        return command
    
    # 平台特定的查找路径
    system = platform.system()
    home = os.path.expanduser("~")
    
    if system == "Windows":
        # Windows 特定路径
        candidates = [
            os.path.join(os.path.dirname(sys.executable), "Scripts", "feishu-docx.exe"),
            os.path.join(home, "AppData", "Local", "Programs", "Python", "Python311", "Scripts", "feishu-docx.exe"),
            os.path.join(home, "AppData", "Local", "Programs", "Python", "Python310", "Scripts", "feishu-docx.exe"),
            os.path.join(home, "AppData", "Local", "Programs", "Python", "Python39", "Scripts", "feishu-docx.exe"),
        ]
    else:
        # macOS/Linux 特定路径
        candidates = [
            os.path.join(os.path.dirname(sys.executable), "feishu-docx"),
            os.path.join(home, ".local", "bin", "feishu-docx"),
            os.path.join(home, "Library", "Python", "3.11", "bin", "feishu-docx"),
            os.path.join(home, "Library", "Python", "3.10", "bin", "feishu-docx"),
            os.path.join(home, "Library", "Python", "3.9", "bin", "feishu-docx"),
        ]
    
    for candidate in candidates:
        if os.path.exists(candidate):
            return candidate
    return None


def _load_app_credentials():
    """加载飞书应用凭据，支持环境变量和配置文件"""
    # 优先级1: 环境变量
    app_id = os.getenv("FEISHU_APP_ID")
    app_secret = os.getenv("FEISHU_APP_SECRET")
    if app_id and app_secret:
        return app_id, app_secret

    # 优先级2: 配置文件
    config_paths = [SKILL_AUTH_CONFIG_PATH, LEGACY_FEISHU_DOCX_CONFIG_PATH]
    for path in config_paths:
        if os.path.exists(path):
            try:
                config = _read_json(path)
                app_id = config.get("app_id")
                app_secret = config.get("app_secret")
                # 检查是否是模板占位符
                if app_id and app_secret and app_id != "cli_xxx" and app_secret != "xxx":
                    return app_id, app_secret
                elif app_id == "cli_xxx" or app_secret == "xxx":
                    print(f"⚠️  配置文件 {path} 包含模板占位符，需要填写真实凭据")
            except json.JSONDecodeError as e:
                print(f"警告: 配置文件格式错误 {path}: {e}")
                continue
            except Exception as e:
                print(f"警告: 读取配置文件失败 {path}: {e}")
                continue

    # 优先级3: 尝试从模板创建配置文件（如果不存在）
    template_path = os.path.join(SKILL_ROOT_DIR, "config", "feishu_auth.template.json")
    if not os.path.exists(SKILL_AUTH_CONFIG_PATH) and os.path.exists(template_path):
        try:
            import shutil
            shutil.copy(template_path, SKILL_AUTH_CONFIG_PATH)
            print(f"ℹ️  已从模板创建配置文件: {SKILL_AUTH_CONFIG_PATH}")
            print("   请编辑该文件，填写你的 app_id 和 app_secret")
        except Exception as e:
            print(f"⚠️  无法从模板创建配置文件: {e}")

    # 未找到有效凭据
    print("❌ 错误: 未找到有效的飞书应用凭据。")
    print("\n请任选其一完成配置：")
    print("1) 环境变量方式（推荐用于 CI/CD）:")
    print("   export FEISHU_APP_ID='your_app_id'")
    print("   export FEISHU_APP_SECRET='your_app_secret'")
    print(f"\n2) Skill 本地配置文件（推荐用于本地开发）:")
    print(f"   {SKILL_AUTH_CONFIG_PATH}")
    if os.path.exists(template_path):
        print("   已从模板自动创建，请编辑并填写 app_id 和 app_secret")
    else:
        print("   从 config/feishu_auth.template.json 复制并填写 app_id 和 app_secret")
    print(f"\n3) 兼容旧配置文件:")
    print(f"   {LEGACY_FEISHU_DOCX_CONFIG_PATH}")
    print("\n💡 提示: 如果 skill 已包含默认配置文件，可以直接使用，无需额外配置。")
    sys.exit(1)


def _get_tenant_token():
    """获取飞书访问令牌"""
    app_id, app_secret = _load_app_credentials()
    try:
        response = http_requests.post(
            "https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal",
            json={"app_id": app_id, "app_secret": app_secret},
            timeout=15,
        )
        response.raise_for_status()
        result = response.json()
        if result.get("code") != 0:
            print(f"❌ 错误: 获取 tenant_access_token 失败")
            print(f"   错误码: {result.get('code')}")
            print(f"   错误信息: {result.get('msg')}")
            print("\n请检查:")
            print("1. app_id 和 app_secret 是否正确")
            print("2. 网络连接是否正常")
            print("3. 飞书应用是否已启用")
            sys.exit(1)
        return result["tenant_access_token"]
    except http_requests.RequestException as e:
        print(f"❌ 网络请求失败: {e}")
        print("\n请检查网络连接或稍后重试")
        sys.exit(1)


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

    try:
        result = response.json()
    except json.JSONDecodeError:
        print(f"❌ 上传失败: 服务器返回了无效的 JSON 响应")
        print(f"   响应状态码: {response.status_code}")
        print(f"   响应内容: {response.text[:200]}")
        sys.exit(1)
    
    if result.get("code") != 0:
        error_code = result.get("code")
        error_msg = result.get("msg", "未知错误")
        print(f"❌ 上传失败!")
        print(f"   错误码: {error_code}")
        print(f"   错误信息: {error_msg}")
        
        # 常见错误提示
        if error_code == 99991663:
            print("\n提示: 可能是权限问题，请确保:")
            print("1. 飞书应用有文件上传权限")
            print("2. 目标文件夹已添加应用为协作者")
        elif error_code == 99991664:
            print("\n提示: 文件夹 token 可能无效，请检查 folder 参数")
        
        sys.exit(1)

    file_token = result.get("data", {}).get("file_token", "")
    if not file_token:
        print("❌ 上传失败: 服务器未返回文件 token")
        print(f"   响应: {result}")
        sys.exit(1)
    
    file_url = f"https://sarosgame.feishu.cn/file/{file_token}"
    print("✅ 上传成功!")
    print(f"📎 文件链接: {file_url}")
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

    if _is_markdown_file(file_path):
        if not raw_mode:
            print("提示: 检测到 Markdown 文件，已强制使用原始文件上传模式（不进行飞书排版）。")
        raw_mode = True

    if raw_mode:
        upload_raw_file(file_path, folder_token, title)
    else:
        upload_to_feishu(file_path, folder_token, title, strict_cloud=args.strict_cloud)


if __name__ == "__main__":
    main()

#pragma endregion
