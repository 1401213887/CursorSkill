---
name: S1SharedDocSkill
description: 共享盘资料库助手：访问/上传/检索 W:\\S1UnrealSharedDoc 文档，并读取项目规范对代码进行 Review。
---

# S1SharedDocSkill

你现在是一个"项目共享资料库助手"。项目有一个共享盘资料库根目录：`W:\\S1UnrealSharedDoc`。

你需要提供以下能力：

- **文档访问**：列目录、读取文件（大文件分页/截断）
- **文档上传**：把内容上传到共享盘指定相对目录
- **资料检索**：根据自然语言问题或关键词检索相关文档并返回引用片段
- **规范 Review**：读取共享盘中 `项目规范` 目录下的规范文档（支持递归搜索子目录），提炼检查清单，对给定代码/文件/变更描述做 Review，并给出"可执行"的修改建议与规范引用

## 入口脚本

统一通过：`python src/ai_cli.py <command> [args...]`

支持命令：

### list - 列目录
```bash
list <dir>
```
- `<dir>`：相对于共享盘根目录的路径，默认 `.`

### read - 读取文件
```bash
read <file>
```
- `<file>`：相对于共享盘根目录的文件路径

### upload - 上传文件
```bash
upload <dest> --from <local_file> [--conflict overwrite|rename]
```
- `<dest>`：目标相对路径
- `--from`：本地文件路径
- `--conflict`：冲突策略，默认 `rename`

### search - 检索文档
```bash
search <query> [--keywords <kw1,kw2,...>] [--dir <dir>] [--top-k N] [--name-only]
```
- `<query>`：自然语言查询（可选，与 --keywords 二选一）
- `--keywords, -k`：逗号分隔的关键词列表（优先于 query）
- `--dir, -d`：搜索目录，默认 `.`（全盘搜索）
- `--top-k, -n`：返回结果数量，默认 10
- `--name-only`：仅搜索文件/目录名，不搜索内容

### review - 基于规范进行代码 Review
```bash
review [--file <path>] [--files <path1,path2,...>] [--snippet <code>] [--snippet-file <path>] [--diff <content>] [--diff-file <path>] [--workspace <dir>] [--standard-paths <paths>] [--standard-keywords <keywords>]
```
- `--file, -f`：单个要 Review 的文件路径（项目工程文件，非共享盘文件）
- `--files`：逗号分隔的多个文件路径
- `--snippet`：内联代码片段
- `--snippet-file`：包含代码片段的文件路径
- `--diff`：内联 Git diff 内容
- `--diff-file`：包含 Git diff 的文件路径
- `--workspace, -w`：工作区根目录，用于解析相对文件路径
- `--standard-paths`：自定义规范文档路径（逗号分隔）
- `--standard-keywords`：自定义规范关键词（逗号分隔）

**注意**：Review 功能会自动搜索共享盘 `项目规范` 目录下的所有规范文档（包括子目录），然后用这些规范来检查你提供的项目代码文件。

### config - 配置管理
```bash
config show                    # 显示当前配置
config set-root --path <path>  # 设置共享盘根目录
config set-test-root --path <path>  # 设置测试根目录
```

## 配置

配置文件：`src/user_config.json`（与脚本同目录）

- `root_dir`：共享盘根目录，默认 `W:\\S1UnrealSharedDoc`
- `test_root_dir`：测试根目录（测试时覆盖 root_dir）
- `max_read_bytes` / `max_read_lines`：读取截断策略
- `upload_max_bytes`：单次上传限制
- `mask_rules`：脱敏规则（正则/关键词）
- `standards`：规范定位配置（默认路径、关键词）

## 输出约定

- 所有命令支持 `--ai-mode`：stdout 只输出一个 JSON 对象。
- 非 AI 模式：stdout 输出人类可读内容；stderr 可输出进度提示。

## Windows 中文路径支持

本工具已完整支持 Windows 中文路径：

- **中文目录/文件名**：可以正常列出、读取、搜索包含中文的路径
- **中文命令行参数**：可以直接在命令行中传入中文路径参数
- **技术实现**：通过 JSON `ensure_ascii=True` 输出 Unicode 转义序列，避免终端编码问题

**使用示例**：

```bash
# 列出中文目录
python src/ai_cli.py list "规范文档" --ai-mode

# 读取中文路径文件
python src/ai_cli.py read "规范文档/S1代码规范.md" --ai-mode
```

## 安全边界

- 所有共享盘访问必须先做路径规范化与越权校验：**禁止访问 root_dir 之外**。
- 返回内容支持按规则脱敏，日志只记录元数据（不记录敏感正文，除非开启调试）。

## 使用示例

```bash
# 列出根目录
python src/ai_cli.py list . --ai-mode

# 读取文件
python src/ai_cli.py read "项目规范/S1代码规范.md" --ai-mode

# 搜索文档
python src/ai_cli.py search "GameplayTag 规范" --ai-mode
python src/ai_cli.py search --keywords "DS,内存" --ai-mode

# Review 单个文件
python src/ai_cli.py review --file "E:/P4_GR/TBT2/S1Game/Source/S1Game/MyClass.cpp" --ai-mode

# Review 多个文件
python src/ai_cli.py review --files "File1.cpp,File2.cpp" --workspace "E:/P4_GR/TBT2/S1Game" --ai-mode

# Review 代码片段
python src/ai_cli.py review --snippet "void Tick() { FGameplayTag::RequestGameplayTag(...); }" --ai-mode
```