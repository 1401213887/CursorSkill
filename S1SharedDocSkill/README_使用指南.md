# 📚 S1SharedDocSkill 使用指南

## 这是什么？

这是一个 **AI 助手 Skill**，可以帮助你：
1. **访问共享盘文档** - 浏览、读取 `W:\S1UnrealSharedDoc` 共享盘上的资料
2. **上传文档** - 把本地文档上传到共享盘
3. **智能检索** - 用自然语言搜索你需要的文档
4. **代码 Review** - 根据共享盘中的《项目规范》自动检查你的代码

---

## 🚀 如何使用

### 方式一：在 AI 对话中直接使用（推荐）

在 CodeBuddy/Cursor 中与 AI 对话时，直接用自然语言描述你的需求即可：

| 你想做什么 | 直接这样说 |
|-----------|-----------|
| 查看共享盘有什么资料 | "帮我看看共享盘根目录下有哪些文件" |
| 找某个文档 | "帮我找一下关于 GameplayTag 的文档" |
| 读取文档内容 | "读取共享盘里的 S1代码规范.md" |
| Review 代码 | "用项目规范帮我 review 一下这个文件：xxx.cpp" |
| 上传文档 | "把我这个文件上传到共享盘的 xxx 目录" |

### 方式二：命令行调用

如果你需要在脚本中使用，可以直接调用 CLI：

```bash
# 进入 Skill 目录
cd E:\P4_GR\TBT2\S1Game\.codebuddy\skills\S1SharedDocSkill

# 列目录
python src/ai_cli.py list .

# 读取文件
python src/ai_cli.py read "项目规范/S1代码规范.md"

# 搜索文档
python src/ai_cli.py search "GameplayTag"

# Review 代码文件
python src/ai_cli.py review --file "E:/P4_GR/TBT2/S1Game/Source/xxx.cpp"
```

---

## 📁 共享盘目录结构

共享盘根目录：`W:\S1UnrealSharedDoc`

```
W:\S1UnrealSharedDoc\
├── 项目规范\              ← Review 功能会自动读取这里的规范文档
│   ├── S1代码规范.md
│   └── ...
├── 技术文档\
├── 设计文档\
└── ...
```

> **注意**：Review 功能只会参考 `项目规范` 目录下的文档来检查代码。

---

## ⭐ 核心功能详解

### 1. 文档检索

支持两种搜索方式：
- **自然语言搜索**：直接描述你想找什么，例如 "关于内存优化的文档"
- **关键词搜索**：精确匹配关键词，例如 "DS,内存,GC"

搜索范围包括：
- 文件名匹配
- 目录名匹配  
- 文件内容匹配（会返回相关片段）

### 2. 代码 Review

这是最实用的功能！它会：
1. 自动读取共享盘 `项目规范` 目录下的所有规范文档
2. 从规范中提取检查规则
3. 用这些规则检查你的代码
4. 给出具体的问题描述和修改建议

**支持的输入方式：**
- 单个文件：`--file xxx.cpp`
- 多个文件：`--files a.cpp,b.cpp,c.h`
- 代码片段：`--snippet "void Tick() { ... }"`
- Git diff：`--diff-file changes.diff`

**当前规范示例（S1代码规范.md）：**
- ❌ 禁止在 Tick 中创建 GameplayTag（性能开销）
- ❌ DS 服务器禁止开启 DS（防止内存爆炸）

---

## 💡 使用场景举例

### 场景 1：提交代码前自检

```
你：帮我用项目规范 review 一下我改的这个文件 E:/P4_GR/TBT2/S1Game/Source/S1Game/Combat/CombatManager.cpp
```

AI 会返回类似：
```
检测到以下问题：

⚠️ 第 156 行：在 Tick 函数中调用了 FGameplayTag::RequestGameplayTag()
   规范要求：禁止在 Tick 中创建 GameplayTag
   建议：将 GameplayTag 提取为成员变量，在构造函数或 BeginPlay 中初始化
```

### 场景 2：查找技术方案

```
你：帮我找一下共享盘里有没有关于布娃娃系统的文档
```

### 场景 3：上传新文档

```
你：帮我把 E:/我的文档/新功能设计.md 上传到共享盘的 设计文档 目录下
```

---

## ⚠️ 注意事项

1. **共享盘访问**：确保你的电脑可以访问 `W:\S1UnrealSharedDoc` 网络路径
2. **规范文档位置**：Review 功能只读取 `项目规范` 目录下的文档
3. **文件大小限制**：单次上传限制 50MB，读取超大文件会自动截断
4. **安全边界**：只能访问共享盘根目录内的文件，无法越权访问

---

## 🔧 常见问题

**Q: 为什么 Review 没有检测到问题？**  
A: 检查 `W:\S1UnrealSharedDoc\项目规范\` 目录下是否有相关的规范文档。

**Q: 如何添加新的检查规则？**  
A: 在 `W:\S1UnrealSharedDoc\项目规范\` 目录下添加或修改 `.md` 文档，按照规范格式编写即可。

**Q: 搜索找不到我要的文档？**  
A: 尝试换几个关键词搜索，或者使用 `list` 命令手动浏览目录。

---

## 📞 联系方式

如有问题或建议，请联系 Skill 维护者。

---

*最后更新：2026-01-21*
