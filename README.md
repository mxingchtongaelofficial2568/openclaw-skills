##Openclaw技能集合##

## Zotero Local Import Skill 功能总结

`zotero-local-import` 是一个面向 Zotero 本地库的命令行导入技能。
它通过 Zotero Local Connector（`127.0.0.1`）将本地 PDF 导入到 Zotero，适用于单篇导入、批量导入、定向导入到已有分类、分类查询和导入结果核查等场景。

### 核心能力

- 导入单个 PDF（`--pdf`）
- 导入多个 PDF（重复 `--pdf`）
- 导入整个文件夹（`--dir`，支持 `--recursive`）
- 仅导入文件夹内指定文件（`--pick`）
- 导入到已存在分类（`--collection`）
- 列出本地分类（`list-collections`）
- 校验最近导入附件（`check`，只读 `zotero.sqlite`）

### 设计边界（关键）

- **自然语言解析由 Agent 完成**（路径/文件名/端口/分类）
- **脚本只执行结构化参数**，不承担自然语言理解
- 不创建分类，仅允许导入到“我的文库”或“已存在分类”

### 使用前提

在 Zotero Desktop 中启用：

`设置 → 高级 → 允许此计算机中的其他应用程序与 Zotero 通讯`

并由用户提供 connector 端口（常见默认值：`23119`）。

### 标准执行流程

1. `doctor --auto-install-deps`（环境体检 + 缺失依赖自动安装）
2. `import ...`（执行实际导入）

### 跨平台支持

- Windows / macOS / Linux 均有代码路径支持
- URL 打开器适配：
- Windows: `os.startfile`
- macOS: `open`
- Linux: `xdg-open`
- 脚本包含 UTF-8 输出增强（改善 Windows 控制台中文显示）

> 当前实机验证结论：**Tested only on Windows (Windows 11 + Python 3.14).**

### 典型适用场景

- “把这个 PDF 导入 Zotero”
- “把这个文件夹里的 PDF 全部导入”
- “只导入这个目录下的 a.pdf、b.pdf、c.pdf”
- “导入到某个已有分类”
- “先列出分类让我选，再导入”
- “导入后检查最近是否成功入库”

### 常见失败与处理

- `collection not found`：目标分类不存在，需先在 Zotero 手动创建
- Connector 连接失败：确认 Zotero 已开启、已允许本机应用通信、端口正确
- 批量失败：先用单文件验证，再执行批量导入



---

如果你要，我下一条可以直接给你一版**完整 README.md 成稿**（含“快速开始 / 命令示例 / 故障排查 / 免责声明”四段结构），你直接复制即可。
