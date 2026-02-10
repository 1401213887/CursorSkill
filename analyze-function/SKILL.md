---
name: analyze-function
description: Analyzes the selected function's purpose, explains each parameter, and produces a flowchart. Use when the user asks to analyze a function, explain function parameters, get a function flowchart, or when they select a function and request analysis or documentation.
---

# 选中函数分析

当用户选中一段函数代码并请求分析时，按以下步骤执行，并统一用中文回复。

## 执行步骤

1. **定位函数**
   - 根据用户选中的代码或给出的文件:行号，读取完整函数定义（含签名与函数体）。
   - 若只给了声明或单行，在对应文件中找到该函数的完整实现。

2. **分析函数作用**
   - 用 2～4 句话概括函数在整体逻辑中的角色（做什么、在什么场景下被谁调用）。
   - 可结合调用处、类/模块职责简要说明。

3. **解释每个参数**
   - 按参数表顺序列出：参数名、类型、含义（用途、取值范围或约定、是否可选等）。
   - 使用表格形式，例如：

   | 参数 | 类型 | 含义 |
   |------|------|------|
   | xxx  | T    | ...  |

4. **绘制流程图**
   - 用 Mermaid 的 `flowchart` 描述主要逻辑（分支、循环、关键子步骤、出口）。
   - 不必画出每一行代码，突出：入口 → 主要分支/循环 → 关键处理 → 返回/结束。
   - 流程图放在独立的 Mermaid 代码块中，便于渲染。

## 输出结构模板

按以下结构组织回复（可据实际情况增删小节）：

```markdown
## 函数作用
[2～4 句话概括]

## 参数说明
| 参数 | 类型 | 含义 |
|------|------|------|
| ...  | ...  | ...  |

## 流程图
\`\`\`mermaid
flowchart TD
  A[入口] --> B{条件?}
  B -->|是| C[...]
  B -->|否| D[...]
  ...
\`\`\`

## 补充说明（可选）
[调用关系、注意事项、与其它函数的配合等]
```

## 注意事项

- 若函数体很长，先做“分段概括”，再在流程图中用子步骤表示，避免流程图过于细碎。
- 未在函数体内使用的参数也要在参数表中说明，并注明“当前实现中未使用”或可能用途（如预留、接口兼容）。
- 回复语言：中文。
