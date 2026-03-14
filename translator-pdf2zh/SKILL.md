---
name: translator-pdf2zh-workflow
description: 用统一脚本执行 pdf2zh-next 。支持单/多PDF、单/多目录、目录内按条件筛选部分PDF；默认翻译服务SiliconFlowFree；可读取已有配置或写入自定义 provider；失败即停并回传错误。
---

# translator-pdf2zh-workflow

## 1) 运行前检查
1. Python 可用。
2. pdf2zh 主程序按优先级检测：
   - uv/CLI 入口（`pdf2zh_next` / `pdf2zh-next` / `pdf2zh`）.这个是通过uv或者pip安装的。
   - 用户给定 `--exe-path`（Windows 常见）
   - 都没有再回退 Python API。
3. 配置文件：
   - Linux/macOS：`~/.config/pdf2zh/config.v3.toml`
   - Windows：`C:\Users\<用户名>\.config\pdf2zh\config.v3.toml`
   - 若未找到：不要盲猜；要求用户提供配置文件路径并使用 `--config-path`。

## 2) 输入场景覆盖
脚本：`scripts/run_pdf2zh_pipeline.py`

- 单个 PDF：`--input-file` 1 次
- 多个 PDF：`--input-file` 多次
- 单个目录全部 PDF：`--input-dir` 1 次
- 单个目录部分 PDF：`--input-dir` + `--include-glob`（可多次）
- 多个目录全部 PDF：`--input-dir` 多次
- 多个目录部分 PDF：`--input-dir` 多次 + `--include-glob`（可多次）

## 3) 命令模板（使用用户给定路径）
```bash
python skills/translator-pdf2zh-workflow/scripts/run_pdf2zh_pipeline.py \
  --input-file "{用户给定PDF绝对路径，可重复}" \
  --input-dir "{用户给定输入目录绝对路径，可重复}" \
  --include-glob "{可选: 目录内筛选模式，如 *A*.pdf，可重复}" \
  --output-dir "{用户给定输出目录绝对路径}" \
  --exe-path "{可选: 用户给定pdf2zh.exe绝对路径}" \
  --stream
```

## 4) Provider 规则
- 默认：`siliconflowfree`。
- 若用户本次明确指定 provider/base_url/api_key：
  - **由 agent 直接写入 `config.v3.toml`**；
  - 在配置中启用该 provider；
  - 同时将 `siliconflowfree = false`。
- 若用户说“使用当前 agent 所使用的大模型”：
  - **由 agent 读取并解析 `openclaw.json`**；
  - agent 智能判断模型类别（OpenAI/Anthropic 兼容）；
  - agent 直接把转换后的 provider/base_url/api_key 写入 `config.v3.toml`。
- 脚本不负责 provider 智能判断，不负责写入 provider 凭据；脚本只读取现有配置并执行翻译。
- **优先级规则（必须遵守）**：用户在本次运行命令里明确追加的参数，权重大于配置文件；执行时一律以“运行时参数”优先。
- **缺省参数规则（必须遵守）**：如果本次运行未显式追加某参数，而该参数在 `config.v3.toml` 中存在，则使用 `config.v3.toml` 中的该参数值。


## 5) 帮助文档入口
- Advanced（中文，含参数说明），如果遇到问题，agent可访问该链接读取最新的参数说明和使用指南：  
   - https://pdf2zh-next.com/zh/advanced/advanced.html


## 6) OpenClaw 需要开启的工具权限（需告知用户）
最小可运行权限：
- `exec`（必需）：运行翻译脚本与 `pdf2zh` 主程序
- `read`（必需）：读取输入/配置/日志文件
- `write`（必需）：写入输出 PDF、`config.v3.toml`
- `edit`（建议）：自动修补脚本与 skill 文档


## 7) 参数不确定时的强制流程
- 若 agent 不能从用户描述直接确定参数组合：
  1. 先运行主程序帮助命令获取最新参数说明（`-h` 或 `--help`）。
  2. 读取帮助输出后，再选择并拼装本次所需参数。
  3. 如果还是不行，则阅读6) 帮助文档入口中提供的链接，获取更详细的参数说明和使用指南。
  3. 再执行正式翻译命令。
- 推荐帮助命令：
  - `pdf2zh_next -h`
  - 或 `"{用户给定pdf2zh.exe绝对路径}" -h`

## 8) 稳定性约束
- 默认单线程（`--threads 1`）。
- 默认禁用术语表自动提取：优先使用 `--no-auto-extract-glossary`（若当前 CLI 支持），并保持 `save_auto_extracted_glossary=false`。
- 任一文件失败即停，并回传：文件名 + 错误摘要 + 关键日志, agent阅读错误日志并自动解决问题。
- 全部成功后必须验证输出目录存在对应译文 PDF。