---
name: paper-review-generator
description: 将论文 PDF 批处理为中文精读总结报告的工作流技能。适用于“PaddleOCR 或 pdfplumber 抽取 + 大模型总结论文”场景。使用时仅读取 skill 目录下 config.json 与 prompt.md，并运行 scripts 中所需脚本。
---

# paper-review-generator

## 1) 配置文件约束
- 仅使用当前 skill 目录下两个文件：
  - `config.json`：包含运行所需全部信息（是否 OCR、OCR 参数、总结模型 base_url/model/api_key、可见窗口开关、线程数）
  - `prompt.md`：总结提示词模板
- 不读取系统环境变量中的私密值，不读取其他目录 secret。
- 不在日志和异常信息中回显任何 api_key。

## 2) 执行入口
- **必须先切换到本 skill 根目录再运行脚本**（即 `.../paper-review-generator`），否则相对路径的 `config.json` / `prompt.md` 会找不到。
- 必须由用户明确传入输入与输出路径：
  - `--pdf`（可重复，支持多个文件）
  - `--dir`（可重复，支持多个文件夹）
  - `--output-dir`（可选；不传时默认输出到每个输入 PDF 同目录下的 `总结` 文件夹）
- 示例（路径由 agent 按用户需求填入）：
  - 单文件：`python scripts/run_pipeline.py --pdf "{pdf_path}" --output-dir "{output_dir}"`
  - 多文件：`python scripts/run_pipeline.py --pdf "{pdf_path_1}" --pdf "{pdf_path_2}" --output-dir "{output_dir}"`
  - 单文件夹：`python scripts/run_pipeline.py --dir "{pdf_dir}" --output-dir "{output_dir}"`
  - 多文件夹：`python scripts/run_pipeline.py --dir "{pdf_dir_1}" --dir "{pdf_dir_2}" --output-dir "{output_dir}"`

## 3) 分流逻辑
- 读取 `config.json.use_paddleocr`：
  - `true`：调用 `extract_paddleocr.py` 抽取文本（JSON 行输出，不落盘）。
  - `false`：调用 `extract_pdfplumber.py` 抽取文本（JSON 行输出，不落盘）。
- 然后调用 `summarize_reports.py`：读取 `prompt.md` 与管道传递的抽取文本，调用 `summarizer.provider` 指定的模型配置生成 `*_研读报告.md`。

## 4) 环境检查与安全规范
- 执行前先检查 Python 是否可用（建议 3.10+）：
  - 若用户电脑未安装 Python，必须先明确提示用户安装 Python，再继续后续步骤。
- 执行前检查依赖：
  - 若缺少依赖包，agent 应在 skill 根目录按 `scripts/requirements.txt` 执行安装：
    - `pip install -r scripts/requirements.txt`
- 仅向用户配置的 OCR/LLM 端点发请求。
- 若配置缺失（如 api_key/token/model/base_url），直接报错并提示补齐字段。
- 不在日志和异常信息中回显任何 api_key。
