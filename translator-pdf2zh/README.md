# translator-pdf2zh（小白版）

这个 skill 用来批量调用 `pdf2zh-next` 做 PDF 翻译。

## 致谢与来源声明
- 本 skill 依赖并使用了 **PDFMathTranslate-next / pdf2zh-next** 项目的成果：
  - https://github.com/PDFMathTranslate-next/PDFMathTranslate-next
- 本仓库仅提供安全包装与流程化调用，不包含对上游项目的替代。

## 安全边界（审计可见）
- 只允许读取：`skills/translator-pdf2zh/config.toml`（相对路径，跨电脑可识别）。
- 禁止读取 `openclaw.json`。
- 禁止读写全局 `~/.config/pdf2zh/config.v3.toml`。
- 不做运行时 `pip install`。

## 审计前置声明（避免“隐式下载”误判）
- 本脚本本身不内置外部下载逻辑。
- 但 `pdf2zh-next / babeldoc` 在首次运行时可能自动下载模型/字体/cmap 资产（上游程序行为，不是本 skill 私自下载）。
- 这些缓存会写入 skill 目录下的 `.cache/`、`.config/`（已与全局配置隔离）。

---

## 1) 环境要求

### Python
- **Python 3.11+（必须）**
  - 原因：脚本使用 `tomllib`（3.11 开始内置）

### pdf2zh-next CLI
满足任一：
- 命令可运行：`pdf2zh_next -h`
- 或你有可执行文件路径：`--exe-path`

---

## 2) 三端兼容性（Windows / Linux / macOS）

### 已支持（脚本层面）
- Windows ✅
- Linux ✅
- macOS ✅

### 说明
- CLI 探测兼容三端（`pdf2zh_next` / `pdf2zh-next` / `pdf2zh`，并含常见 Windows 路径）。
- 配置路径固定为相对路径 `skills/translator-pdf2zh/config.toml`，不依赖用户主目录。
- `--visible-monitor`：
  - Windows：使用 Python 原生新控制台窗口（`CREATE_NEW_CONSOLE`）。
  - Linux/macOS：无“新窗口”保证，改为当前终端实时日志流（需在交互终端运行）。

---

## 3) 配置文件
只用这个文件：
- `skills/translator-pdf2zh/config.toml`

如果你传了别的 `--config-path`，脚本会直接拒绝执行。

---

## 4) provider 规则
- 不传 `--provider`：完全按 `config.toml` 生效。
- 传 `--provider xxx`：必须同时满足：
  1) `config.toml` 顶层存在同名布尔开关；
  2) `pdf2zh_next -h` 里存在官方 `--<Services>` 参数。

例如：
- `--provider openai` → `--openai`
- `--provider deepseek` → `--deepseek`
- `--provider siliconflow` → `--siliconflow`

---

## 5) 调用示例

### 单文件（按 config.toml）
```bash
python skills/translator-pdf2zh/scripts/run_pdf2zh_pipeline.py \
  --input-file "C:/path/to/1.pdf" \
  --output-dir "C:/path/to/out" \
  --workers 1
```

### 实时监控
```bash
python skills/translator-pdf2zh/scripts/run_pdf2zh_pipeline.py \
  --input-file "C:/path/to/1.pdf" \
  --output-dir "C:/path/to/out" \
  --visible-monitor \
  --workers 1
```

### 并行多文件
```bash
python skills/translator-pdf2zh/scripts/run_pdf2zh_pipeline.py \
  --input-dir "C:/path/to/pdfs" \
  --output-dir "C:/path/to/out" \
  --workers 3
```

### 指定 provider（官方 --<Services>）
```bash
python skills/translator-pdf2zh/scripts/run_pdf2zh_pipeline.py \
  --input-file "C:/path/to/1.pdf" \
  --output-dir "C:/path/to/out" \
  --provider "openaicompatible" \
  --workers 1
```

---

## 6) 常见问题

### Q1: 看不到可见窗口
- 在 OpenClaw 后台会话中可能看不到桌面窗口。
- 请在你本机交互终端直接运行命令。

### Q2: 提示 provider 不存在
- 检查 `config.toml` 顶层布尔开关是否有该 key。
- 检查 `pdf2zh_next -h` 是否有对应 `--<Services>` 参数。

### Q3: 首次运行很慢
- 可能在下载上游资产（模型/字体/cmap），属于预期行为。
