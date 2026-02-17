# upload2git Skill 安装指南

## 安装步骤

### 方法 1: 直接使用（已安装）

如果 skill 已经在 `.cursor/skills/upload2git/` 目录下，可以直接使用：

```bash
# 直接运行脚本
.cursor/skills/upload2git/upload2git.sh <文件路径>

# 或者添加到 PATH（可选）
export PATH="$PATH:$(pwd)/.cursor/skills/upload2git"
upload2git.sh <文件路径>
```

### 方法 2: 创建符号链接（推荐）

在系统 PATH 中创建一个符号链接，方便全局使用：

```bash
# macOS/Linux
sudo ln -s $(pwd)/.cursor/skills/upload2git/upload2git.sh /usr/local/bin/upload2git

# 或者用户级别（不需要 sudo）
mkdir -p ~/bin
ln -s $(pwd)/.cursor/skills/upload2git/upload2git.sh ~/bin/upload2git
export PATH="$PATH:$HOME/bin"  # 添加到 ~/.bashrc 或 ~/.zshrc
```

### 方法 3: 在 Cursor 中注册为命令

如果 Cursor 支持自定义命令注册，可以在 Cursor 设置中配置：

1. 打开 Cursor 设置
2. 找到 "Commands" 或 "Skills" 设置
3. 添加新命令：
   - 名称: `upload2git`
   - 路径: `.cursor/skills/upload2git/upload2git.sh`
   - 参数: `$1 $2 $3 ...`

## 验证安装

运行以下命令验证安装：

```bash
# 检查脚本是否存在
ls -l .cursor/skills/upload2git/upload2git.sh

# 检查脚本权限
chmod +x .cursor/skills/upload2git/upload2git.sh

# 测试运行（应该显示帮助信息）
.cursor/skills/upload2git/upload2git.sh
```

## 使用示例

```bash
# 上传单个文件
upload2git AiDoc/document.md

# 上传多个文件
upload2git file1.txt file2.txt file3.txt

# 使用相对路径
upload2git ../other-project/file.txt

# 使用绝对路径
upload2git /path/to/file.txt
```

## 配置说明

### 修改目标仓库

编辑 `upload2git.sh` 文件，修改以下配置：

```bash
GIT_REPO_SSH="git@github.com:1401213887/AiDoc.git"
GIT_REPO_HTTPS="https://github.com/1401213887/AiDoc.git"
GIT_USERNAME="1401213887"
GIT_PASSWORD="Chenglide1949"
```

### 配置 SSH Key

1. 生成 SSH key（如果还没有）:
   ```bash
   ssh-keygen -t ed25519 -C "your_email@example.com"
   ```

2. 将 SSH key 添加到 GitHub:
   - 复制公钥: `cat ~/.ssh/id_ed25519.pub`
   - 在 GitHub 设置中添加 SSH key

3. 测试连接:
   ```bash
   ssh -T git@github.com
   ```

### 配置 Personal Access Token (PAT)

如果使用 HTTPS 且密码认证失败：

1. 访问 https://github.com/settings/tokens
2. 创建新的 Personal Access Token
3. 将 Token 替换脚本中的 `GIT_PASSWORD`

## 卸载

如果需要卸载：

```bash
# 删除符号链接（如果创建了）
rm /usr/local/bin/upload2git  # 或
rm ~/bin/upload2git

# 删除 skill 目录（可选）
rm -rf .cursor/skills/upload2git
```

## 故障排除

### 权限问题
```bash
chmod +x .cursor/skills/upload2git/upload2git.sh
```

### 找不到命令
确保脚本路径正确，或使用完整路径运行。

### Git 相关问题
确保已安装 Git 并配置正确：
```bash
git --version
git config --global user.name "Your Name"
git config --global user.email "your.email@example.com"
```

### SSH 连接问题
```bash
# 测试 SSH 连接
ssh -T git@github.com

# 检查 SSH agent
eval "$(ssh-agent -s)"
ssh-add ~/.ssh/id_ed25519
```

### HTTPS 认证问题
- GitHub 已不再支持密码认证
- 必须使用 Personal Access Token (PAT)
- 在脚本中将 `GIT_PASSWORD` 替换为 PAT

## 系统要求

- **Git**: >= 2.0.0
- **Bash**: >= 3.0 (macOS/Linux) 或 Git Bash (Windows)
- **网络连接**: 用于访问 GitHub

## 支持的操作系统

- ✅ macOS
- ✅ Linux
- ✅ Windows (需要 Git Bash)
