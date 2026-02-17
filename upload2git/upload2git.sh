#!/bin/bash

# 配置信息
GIT_REPO_SSH="git@github.com:1401213887/AiDoc.git"
GIT_REPO_HTTPS="https://github.com/1401213887/AiDoc.git"
GIT_USERNAME="1401213887"
GIT_PASSWORD="Chenglide1949"

# 检测操作系统
detect_os() {
    case "$(uname -s)" in
        Linux*)     echo "Linux";;
        Darwin*)    echo "macOS";;
        CYGWIN*)    echo "Windows";;
        MINGW*)     echo "Windows";;
        MSYS*)      echo "Windows";;
        *)          echo "Unknown";;
    esac
}

OS_TYPE=$(detect_os)

# 检测是否支持颜色输出（Windows Git Bash 通常支持）
if [ -t 1 ] && [ "$TERM" != "dumb" ]; then
    RED='\033[0;31m'
    GREEN='\033[0;32m'
    YELLOW='\033[1;33m'
    NC='\033[0m' # No Color
else
    RED=''
    GREEN=''
    YELLOW=''
    NC=''
fi

# 创建临时文件的跨平台函数
create_temp_file() {
    if command -v mktemp >/dev/null 2>&1; then
        mktemp
    elif [ "$OS_TYPE" = "Windows" ]; then
        # Windows 备用方案
        echo "${TMP:-/tmp}/upload2git_$$_$(date +%s).tmp"
    else
        echo "/tmp/upload2git_$$_$(date +%s).tmp"
    fi
}

# 规范化路径（跨平台）
normalize_path() {
    local path="$1"
    # 在 Windows Git Bash 中，路径可能包含反斜杠，转换为正斜杠
    if [ "$OS_TYPE" = "Windows" ]; then
        path=$(echo "$path" | sed 's|\\|/|g')
    fi
    echo "$path"
}

# 判断是否为绝对路径（跨平台）
is_absolute_path() {
    local path="$1"
    # Unix/Linux/macOS: 以 / 开头
    # Windows: 以盘符开头 (C:, D: 等) 或 / 开头（Git Bash）
    if [[ "$path" == /* ]] || [[ "$path" == [A-Za-z]:* ]] || [[ "$path" == [A-Za-z]:/* ]]; then
        return 0
    else
        return 1
    fi
}

# 使用工作区内的临时目录（优先使用 $HOME，如果失败则使用当前目录）
if [ -w "$HOME" ] 2>/dev/null; then
    REPO_DIR="$HOME/.cursor_upload_repo/AiDoc"
else
    # 如果无法写入 $HOME，使用当前工作目录
    REPO_DIR="$(pwd)/.cursor_upload_repo/AiDoc"
fi

# 当前使用的连接方式（SSH 或 HTTPS）
USE_SSH=true

# 检查参数
if [ $# -eq 0 ]; then
    echo -e "${RED}错误: 请指定要上传的文件路径${NC}"
    echo "用法: $0 <文件路径1> [文件路径2] ..."
    exit 1
fi

# 保存原始工作目录
ORIGINAL_DIR="$(pwd)"

# 创建临时仓库目录
mkdir -p "$(dirname "$REPO_DIR")"

# 克隆或更新仓库
if [ ! -d "$REPO_DIR/.git" ]; then
    # 尝试使用 SSH 克隆
    echo -e "${YELLOW}正在克隆仓库 (尝试 SSH)...${NC}"
    if git clone "$GIT_REPO_SSH" "$REPO_DIR" 2>/dev/null; then
        echo -e "${GREEN}✓ 使用 SSH 克隆成功${NC}"
        USE_SSH=true
    else
        # SSH 失败，回退到 HTTPS
        echo -e "${YELLOW}SSH 连接失败，切换到 HTTPS...${NC}"
        GIT_URL_WITH_CREDENTIALS="https://${GIT_USERNAME}:${GIT_PASSWORD}@github.com/1401213887/AiDoc.git"
        if git clone "$GIT_URL_WITH_CREDENTIALS" "$REPO_DIR" 2>&1 | sed "s/${GIT_PASSWORD}/***/g"; then
            echo -e "${GREEN}✓ 使用 HTTPS 克隆成功${NC}"
            USE_SSH=false
        else
            echo -e "${RED}错误: 无法克隆仓库（SSH 和 HTTPS 都失败）${NC}"
            exit 1
        fi
    fi
else
    # 更新现有仓库
    cd "$REPO_DIR"
    CURRENT_REMOTE=$(git remote get-url origin 2>/dev/null || echo "")
    
    # 判断当前使用的连接方式
    if [[ "$CURRENT_REMOTE" == "git@github.com:"* ]] || [[ "$CURRENT_REMOTE" == *"@github.com:"* ]]; then
        USE_SSH=true
        echo -e "${YELLOW}正在更新仓库 (使用 SSH)...${NC}"
        if ! git pull 2>/dev/null; then
            echo -e "${YELLOW}SSH 更新失败，切换到 HTTPS...${NC}"
            USE_SSH=false
            GIT_URL_WITH_CREDENTIALS="https://${GIT_USERNAME}:${GIT_PASSWORD}@github.com/1401213887/AiDoc.git"
            git remote set-url origin "$GIT_URL_WITH_CREDENTIALS"
            git pull 2>&1 | sed "s/${GIT_PASSWORD}/***/g"
        fi
    else
        USE_SSH=false
        echo -e "${YELLOW}正在更新仓库 (使用 HTTPS)...${NC}"
        git pull 2>&1 | sed "s/${GIT_PASSWORD}/***/g"
    fi
fi

cd "$REPO_DIR"

# 根据当前连接方式设置远程仓库 URL
CURRENT_REMOTE=$(git remote get-url origin 2>/dev/null || echo "")
if [ "$USE_SSH" = true ]; then
    # 确保使用 SSH 格式
    if [[ "$CURRENT_REMOTE" != "git@github.com:"* ]] && [[ "$CURRENT_REMOTE" != *"@github.com:"* ]]; then
        echo -e "${YELLOW}正在设置远程仓库为 SSH 格式...${NC}"
        git remote set-url origin "$GIT_REPO_SSH"
    fi
else
    # 确保使用 HTTPS 格式
    if [[ "$CURRENT_REMOTE" != "https://"* ]]; then
        echo -e "${YELLOW}正在设置远程仓库为 HTTPS 格式...${NC}"
        GIT_URL_WITH_CREDENTIALS="https://${GIT_USERNAME}:${GIT_PASSWORD}@github.com/1401213887/AiDoc.git"
        git remote set-url origin "$GIT_URL_WITH_CREDENTIALS"
    fi
fi

# 复制文件到仓库
echo -e "${YELLOW}正在复制文件...${NC}"
for file_path in "$@"; do
    # 规范化路径（处理 Windows 反斜杠等）
    file_path=$(normalize_path "$file_path")
    
    # 处理相对路径：如果不是绝对路径，则基于原始工作目录转换为绝对路径
    if ! is_absolute_path "$file_path"; then
        # 相对路径，基于原始工作目录转换为绝对路径
        # 规范化路径（处理 .. 和 .）
        if [ -f "$ORIGINAL_DIR/$file_path" ]; then
            # 获取目录部分和文件名
            file_dir=$(dirname "$file_path" 2>/dev/null || echo ".")
            file_name=$(basename "$file_path" 2>/dev/null || echo "$file_path")
            # 转换为绝对路径
            if [ "$file_dir" = "." ] || [ "$file_dir" = "./" ]; then
                abs_file_path="$ORIGINAL_DIR/$file_name"
            else
                abs_file_path="$(cd "$ORIGINAL_DIR" && cd "$file_dir" 2>/dev/null && pwd)/$file_name"
            fi
            file_path="$abs_file_path"
        else
            # 如果文件不存在，尝试直接使用原始路径
            file_path="$ORIGINAL_DIR/$file_path"
        fi
    fi
    
    # 再次规范化路径
    file_path=$(normalize_path "$file_path")
    
    if [ ! -f "$file_path" ]; then
        echo -e "${RED}警告: 文件不存在: $file_path${NC}"
        continue
    fi
    
    # 获取文件名（跨平台兼容）
    filename=$(basename "$file_path" 2>/dev/null || echo "$file_path" | sed 's|.*[/\\]||')
    
    # 复制文件到仓库根目录
    if cp "$file_path" "$REPO_DIR/$filename" 2>/dev/null; then
        echo -e "${GREEN}已复制: $filename${NC}"
    else
        echo -e "${RED}错误: 无法复制文件 $filename${NC}"
        continue
    fi
done

# 添加文件到 git
echo -e "${YELLOW}正在添加文件到 git...${NC}"
git add .

# 检查是否有更改
if git diff --staged --quiet; then
    echo -e "${YELLOW}没有需要提交的更改${NC}"
    exit 0
fi

# 提交更改
echo -e "${YELLOW}正在提交更改...${NC}"
# 跨平台的日期格式
if date --version >/dev/null 2>&1; then
    # GNU date (Linux)
    COMMIT_MSG="Upload files: $(date '+%Y-%m-%d %H:%M:%S')"
else
    # BSD date (macOS) 或其他
    COMMIT_MSG="Upload files: $(date '+%Y-%m-%d %H:%M:%S')"
fi
git commit -m "$COMMIT_MSG"

# 推送到远程仓库
if [ "$USE_SSH" = true ]; then
    echo -e "${YELLOW}正在推送到远程仓库 (使用 SSH)...${NC}"
    if git push origin main 2>/dev/null; then
        echo -e "${GREEN}✓ 文件上传成功! (SSH)${NC}"
    else
        # SSH 推送失败，切换到 HTTPS
        echo -e "${YELLOW}SSH 推送失败，切换到 HTTPS...${NC}"
        GIT_URL_WITH_CREDENTIALS="https://${GIT_USERNAME}:${GIT_PASSWORD}@github.com/1401213887/AiDoc.git"
        git remote set-url origin "$GIT_URL_WITH_CREDENTIALS"
        TEMP_OUTPUT=$(create_temp_file)
        if git push origin main > "$TEMP_OUTPUT" 2>&1; then
            sed "s/${GIT_PASSWORD}/***/g" "$TEMP_OUTPUT"
            rm -f "$TEMP_OUTPUT" 2>/dev/null
            echo -e "${GREEN}✓ 文件上传成功! (HTTPS)${NC}"
        else
            sed "s/${GIT_PASSWORD}/***/g" "$TEMP_OUTPUT"
            rm -f "$TEMP_OUTPUT" 2>/dev/null
            echo -e "${RED}✗ 文件上传失败（SSH 和 HTTPS 都失败）${NC}"
            echo -e "${YELLOW}提示: 请检查网络连接或 GitHub 认证${NC}"
            exit 1
        fi
    fi
else
    # 使用 HTTPS 推送
    echo -e "${YELLOW}正在推送到远程仓库 (使用 HTTPS)...${NC}"
    TEMP_OUTPUT=$(create_temp_file)
    if git push origin main > "$TEMP_OUTPUT" 2>&1; then
        sed "s/${GIT_PASSWORD}/***/g" "$TEMP_OUTPUT"
        rm -f "$TEMP_OUTPUT" 2>/dev/null
        echo -e "${GREEN}✓ 文件上传成功! (HTTPS)${NC}"
    else
        sed "s/${GIT_PASSWORD}/***/g" "$TEMP_OUTPUT"
        rm -f "$TEMP_OUTPUT" 2>/dev/null
        echo -e "${RED}✗ 文件上传失败${NC}"
        echo -e "${YELLOW}提示: GitHub 可能不再支持密码认证，请使用 Personal Access Token (PAT)${NC}"
        echo -e "${YELLOW}获取 PAT: https://github.com/settings/tokens${NC}"
        exit 1
    fi
fi
