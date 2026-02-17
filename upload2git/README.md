# upload2git - Cursor Skill

一个用于将文件上传到 GitHub 仓库的 Cursor skill，支持智能连接回退和跨平台运行。

## 安装

将 `upload2git` 目录复制到 `.cursor/skills/` 目录下即可。

## 功能特性

- ✅ **智能连接回退**：优先使用 SSH，失败时自动切换到 HTTPS
- ✅ **跨平台支持**：支持 macOS、Linux 和 Windows (Git Bash)
- ✅ **自动仓库管理**：自动克隆或更新目标仓库
- ✅ **路径处理**：支持相对路径和绝对路径
- ✅ **安全输出**：自动隐藏密码信息

## 使用方法

### 在 Cursor 中使用

```bash
# 上传单个文件
upload2git <文件路径>

# 上传多个文件
upload2git <文件1> <文件2> ...

# 示例：上传 AiDoc 目录下的文档
upload2git AiDoc/AiDoc_SkeletalMeshOnUnregisterDeallocateTransformDataConcurrentCrash_20260209.md
```

### 直接运行脚本

```bash
.cursor/skills/upload2git/upload2git.sh <文件路径>
```

## 配置

脚本中的配置信息位于 `upload2git.sh` 文件开头：

```bash
GIT_REPO_SSH="git@github.com:1401213887/AiDoc.git"
GIT_REPO_HTTPS="https://github.com/1401213887/AiDoc.git"
GIT_USERNAME="1401213887"
GIT_PASSWORD="Chenglide1949"
```

可以根据需要修改这些配置。

## 认证方式

### SSH 认证（推荐）

1. 确保 SSH key 已添加到 GitHub 账户
2. SSH key 指纹: `SHA256:9W6WHBX4uEd/ZXxJmAAv/iWlUexEhTrH1XaaXvUUjCM`
3. 脚本会自动优先使用 SSH 连接

### HTTPS 认证（备用）

- 当 SSH 连接失败时，自动切换到 HTTPS
- 使用配置的用户名和密码
- 注意：GitHub 可能不再支持密码认证，建议使用 Personal Access Token (PAT)

## 平台支持

### macOS / Linux
- 直接运行，完全支持
- 支持颜色输出
- 支持所有标准 Unix 工具

### Windows
- 需要在 **Git Bash** 中运行（Git for Windows 自带）
- 支持颜色输出
- 自动处理 Windows 路径格式
- 支持盘符路径（如 `C:/path/to/file`）

## 工作流程

1. **检查参数**：验证是否提供了文件路径
2. **仓库管理**：
   - 如果仓库不存在，尝试克隆（SSH 优先，失败则 HTTPS）
   - 如果仓库存在，更新到最新版本
3. **文件处理**：
   - 规范化文件路径（处理相对路径、Windows 路径等）
   - 复制文件到仓库根目录
4. **Git 操作**：
   - 添加文件到暂存区
   - 提交更改（带时间戳）
   - 推送到远程仓库（SSH 优先，失败则 HTTPS）

## 故障排除

### SSH 连接失败
- 检查 SSH key 是否已添加到 GitHub
- 测试连接：`ssh -T git@github.com`
- 确保 SSH agent 正在运行

### HTTPS 连接失败
- GitHub 可能不再支持密码认证
- 建议使用 Personal Access Token (PAT)
- 获取 PAT: https://github.com/settings/tokens

### Windows 相关问题
- 确保在 Git Bash 中运行，而不是 PowerShell 或 CMD
- 检查 Git for Windows 是否正确安装

## 文件结构

```
upload2git/
├── manifest.json      # Skill 配置文件
├── upload2git.sh      # 主脚本文件
└── README.md          # 本文件
```

## 版本历史

- **v1.0.0** (2026-02-17)
  - 初始版本
  - 支持 SSH 和 HTTPS 智能回退
  - 跨平台支持

## 许可证

本 skill 为内部使用工具。

## 贡献

如有问题或建议，请提交 Issue 或 Pull Request。
