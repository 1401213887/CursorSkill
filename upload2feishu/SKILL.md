---
name: upload2feishu
description: 将本地文本文件上传到飞书云文档或原始文件空间，并自动处理 Windows 中文参数编码问题。用于用户提到“上传到飞书/飞书文档/upload2feishu/Feishu 上传”时。
---

# Upload2feishu

## 作用

将指定文件上传到飞书，支持两种模式：

- 默认模式：直接上传原始文件（`raw=true`，保留 `.md/.txt` 等格式，不依赖 `feishu-docx`）
- 云文档模式（可选）：仅在明确要求时使用 `raw=false`，尝试转换为飞书云文档

默认目标文件夹：`LftxfwYm3lttjjdtO3DcscIEncA`

## 目录结构（本 Skill 自包含）

```text
upload2feishu/
├─ SKILL.md
├─ install.ps1
├─ config/
│  ├─ README.md
│  └─ feishu_auth.template.json
└─ scripts/
   ├─ feishu_upload.py
   └─ requirements.txt
```

迁移到其他机器时，保持上述目录结构即可。

## 一键安装与自检（推荐）

在新机器首次使用前，先执行：

```powershell
powershell -ExecutionPolicy Bypass -File "$env:USERPROFILE/.cursor/skills/upload2feishu/install.ps1"
```

说明：
- 脚本会检查 Python 3.11、安装依赖、验证上传脚本可执行。
- 若检测到旧凭据 `~/.feishu-docx/config.json`，会自动复制到本 skill 的 `config/feishu_auth.json`。
- 若无凭据，会从模板创建 `config/feishu_auth.json`，你只需填入 `app_id/app_secret`。
- 若只想做快速验证不安装依赖，可用：
  - `powershell -ExecutionPolicy Bypass -File "$env:USERPROFILE/.cursor/skills/upload2feishu/install.ps1" -SkipPip`

## 执行流程

0. 预检查（必须执行）：
   - 定位 skill 根目录：`$SkillRoot = Join-Path $env:USERPROFILE ".cursor/skills/upload2feishu"`
   - 确认上传脚本存在：`Test-Path (Join-Path $SkillRoot "scripts/feishu_upload.py")`
   - 如需本地凭据文件，确认存在：`Test-Path (Join-Path $SkillRoot "config/feishu_auth.json")`
   - 禁止使用历史路径（已废弃）：`d:/GR_release/Tools/feishu_upload.py`
   - 确认 Python 3.11 可用：`py -3.11 --version`
1. 确认上传文件路径（优先顺序：用户 `@` 引用 > 用户明确路径 > 当前打开文件）。
2. 如果用户提供飞书文件夹 URL，从 URL 中提取 folder token；否则使用默认 token。
3. 在工作区根目录创建临时配置文件 `_feishu_upload_config.json`，内容如下：

```json
{
  "file": "待上传文件绝对路径",
  "title": "文档标题（可选）",
  "folder": "飞书文件夹token（可选）",
  "raw": true
}
```

4. 执行上传命令（必须走 JSON 配置，避免 Windows 中文编码问题）：

```bash
py -3.11 "$SkillRoot/scripts/feishu_upload.py" --json "<工作区>/_feishu_upload_config.json"
```

5. 上传结束后删除 `_feishu_upload_config.json`（成功和失败都要清理）。
6. 向用户汇报结果：标题、模式（原始文件/云文档）、链接（若有）。

## 处理规则

- 不直接在命令行拼中文参数；统一通过 JSON 传参。
- `raw=true`（默认）时上传原始文件。
- `.md/.markdown` 文件一律按原始文件上传，避免飞书排版（即使未显式传 `raw`）。
- 仅当用户明确要求飞书云文档时，才设置 `raw=false`。
- `raw=false` 时尝试云文档；若未安装 `feishu-docx` 或执行失败，自动降级为原始文件上传（保证命令可独立执行）。
- 如果报权限错误，提醒用户把应用 `CursorFeishuDoc` 添加为目标文件夹协作者。
- 凭据读取优先级（脚本内置）：
  - 1) 环境变量：`FEISHU_APP_ID` / `FEISHU_APP_SECRET`
  - 2) Skill 本地配置：`$SkillRoot/config/feishu_auth.json`
  - 3) 兼容旧配置：`$env:USERPROFILE/.feishu-docx/config.json`
- 若使用 `feishu-docx.exe` 的 PowerShell 命令，必须用调用操作符 `&`，否则会出现 `UnexpectedToken ... config`。
- 上传输出可能出现中文乱码（终端编码问题），结果判断以“返回码 + 链接正则”优先：
  - 云文档：`https://feishu.cn/docx/<id>`
  - 原始文件：`https://*.feishu.cn/file/<id>`

## 依赖

- Python 3.11（建议使用 `py -3.11` 调用）
- `requests`（必需，见 `scripts/requirements.txt`）
- `feishu-docx`（可选，仅用于显式云文档模式）
- 首次安装依赖建议执行：
  - `py -3.11 -m pip install -r "$SkillRoot/scripts/requirements.txt"`

## 飞书凭据配置文件（记录）

- 推荐凭据文件：`$SkillRoot/config/feishu_auth.json`（由 `feishu_auth.template.json` 复制并填写）
- 环境变量方式：`FEISHU_APP_ID` + `FEISHU_APP_SECRET`
- 兼容旧凭据文件：`$env:USERPROFILE/.feishu-docx/config.json`
- 迁移到新机器时，优先复制 `feishu_auth.json` 到 skill 的 `config` 目录，避免依赖 `feishu-docx` 安装状态。
- 安全要求：上述文件包含敏感凭据，不要提交到仓库，不要写入 `SKILL.md` 明文。

## 已验证参数（2026-02-12）

- Python 启动命令：`py -3.11`
- 上传脚本路径：`$env:USERPROFILE/.cursor/skills/upload2feishu/scripts/feishu_upload.py`
- 本地凭据模板：`$env:USERPROFILE/.cursor/skills/upload2feishu/config/feishu_auth.template.json`
- 本地凭据文件：`$env:USERPROFILE/.cursor/skills/upload2feishu/config/feishu_auth.json`
- `feishu-docx` 可执行文件路径（可选）：`$env:USERPROFILE/AppData/Local/Programs/Python/Python311/Scripts/feishu-docx.exe`
- 兼容旧飞书配置文件：`$env:USERPROFILE/.feishu-docx/config.json`
- 已配置 App ID：`cli_a900126691b99cb3`
- 默认 folder token：`LftxfwYm3lttjjdtO3DcscIEncA`
- 默认 folder URL：`https://sarosgame.feishu.cn/drive/folder/LftxfwYm3lttjjdtO3DcscIEncA`

## 快速自检（下次优先执行，避免重复排障）

1. 或直接执行一键安装与自检：
   - `powershell -ExecutionPolicy Bypass -File "$env:USERPROFILE/.cursor/skills/upload2feishu/install.ps1"`
2. 手动检查 Python 版本：
   - `py -3.11 --version`
3. 检查上传脚本存在：
   - `Test-Path (Join-Path $SkillRoot "scripts/feishu_upload.py")`
4. 检查凭据（任一方式可用即可）：
   - `Test-Path (Join-Path $SkillRoot "config/feishu_auth.json")`
   - 或检查环境变量：`$env:FEISHU_APP_ID` / `$env:FEISHU_APP_SECRET`
5. 可选检查 `feishu-docx`（仅云文档优先路径需要）：
   - `feishu-docx --version`
6. 如果以上都正常，直接进入上传，不再重复安装/配置流程。

## 已通过的端到端测试样例

- 测试文件：`F:/UnrealEngine/Engine/Source/Runtime/Renderer/Private/InstanceCulling/InstanceCulling_BasePass_Integration.md`
- 云文档模式（`raw=false`，显式请求时）成功链接：
  - `https://feishu.cn/docx/DOTedTVbSo7EPox0sQvcMTyonYQ`
- 云文档模式（`raw=false`，显式请求时）成功链接（本次会话）：
  - `https://feishu.cn/docx/IEUvdHalfo5KU7xaer2cKdgrnlc`
- 原始文件模式（`raw=true`）成功链接：
  - `https://sarosgame.feishu.cn/file/Mv0db81muoFt4lxETQJctpqinvg`

## 已知问题与处理

- 若云文档模式偶发 `SSL EOF`，按相同参数重试一次，通常可恢复。
- 若执行 `feishu-docx.exe` 报 `UnexpectedToken ... config`，说明 PowerShell 调用方式错误，改为：
  - `& "$env:USERPROFILE/AppData/Local/Programs/Python/Python311/Scripts/feishu-docx.exe" config show`
- 若未安装 `feishu-docx`，云文档模式会自动降级为原始文件上传，这属于预期行为。
