# 上传文件到 GitHub 仓库

此命令用于将指定文件上传到 https://github.com/1401213887/AiDoc.git

## 使用方法

```bash
# 上传单个文件
upload2git <文件路径>

# 上传多个文件
upload2git <文件1> <文件2> ...

# 示例：上传 AiDoc 目录下的文档
upload2git AiDoc/AiDoc_SkeletalMeshOnUnregisterDeallocateTransformDataConcurrentCrash_20260209.md
```

## 功能说明

- 自动克隆或更新目标仓库到本地临时目录 (`$HOME/.cursor_upload_repo/AiDoc`)
- 将指定文件复制到仓库根目录
- 自动提交并推送到远程仓库
- 使用时间戳作为提交信息
- **智能连接方式**：优先使用 SSH，失败时自动回退到 HTTPS
- **跨平台支持**：支持 macOS、Linux 和 Windows (Git Bash)

## 认证方式

脚本采用**智能回退机制**：

1. **优先使用 SSH**（无需密码）
   - SSH key 指纹: `SHA256:9W6WHBX4uEd/ZXxJmAAv/iWlUexEhTrH1XaaXvUUjCM`
   - 请确保该 SSH key 已添加到你的 GitHub 账户

2. **自动回退到 HTTPS**（当 SSH 失败时）
   - 使用配置的用户名和密码
   - 如果 HTTPS 也失败，会显示相应错误提示

## 平台支持

### macOS / Linux
- 直接运行，完全支持
- 支持颜色输出
- 支持所有标准 Unix 工具

### Windows
- 需要在 **Git Bash** 中运行（Git for Windows 自带）
- 支持颜色输出
- 自动处理 Windows 路径格式（反斜杠转正斜杠）
- 支持盘符路径（如 `C:/path/to/file`）

## 注意事项

- 如果文件已存在且内容相同，不会重复提交
- 首次运行会自动克隆仓库，后续运行会先更新仓库
- 脚本会自动选择最合适的连接方式（SSH 优先，HTTPS 备用）
- 如果 HTTPS 连接失败，可能需要使用 Personal Access Token (PAT) 替代密码
- Windows 用户请确保在 Git Bash 中运行，而不是 PowerShell 或 CMD
