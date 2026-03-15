# paper-review-generator

这个工具做一件事：
**把你给的 PDF 论文，自动生成中文研读报告（`*_研读报告.md`）**。

---

## 0. 你需要先准备什么（前置要求）

1. 你电脑有 Python（建议 3.10+）
2. 安装依赖（在本目录执行）：
   ```bash
   pip install -r scripts/requirements.txt
   ```
3. 在 `config.json` 填好密钥：
   - `paddleocr.api_key`（如果你要开 OCR）
   - `summarizer.providers.你选的provider.api_key`

---

## 1. 最常用配置（先看这个）

### `config.json` 每一项怎么填（建议按这个顺序）

#### 顶层
- `use_paddleocr`（必填）
  - `true`：走 OCR（适合扫描版 PDF、图片论文）
  - `false`：不走 OCR，直接 pdfplumber 抽文本（适合文字层清晰的 PDF，速度更快）

#### `paddleocr`（仅当 `use_paddleocr=true` 时生效）
- `job_url`：PaddleOCR 服务接口地址。默认即可。
- `model`：OCR 模型名。默认 `PaddleOCR-VL-1.5`。
- `api_key`（必填）：你的 API 密钥。
- `show_window`：`true/false`，是否显示执行窗口。
- `threads`：并发线程数（建议`1`起步）。
- `poll_seconds`：轮询 OCR 任务状态的间隔秒数（常用 3~8）。
- `timeout_seconds`：单个 OCR 任务超时秒数（长文档可设大一些，如 1800）。
- `optional_payload`：OCR 可选开关。
  - `useDocOrientationClassify`：页面方向自动纠正
  - `useDocUnwarping`：页面形变矫正
  - `useChartRecognition`：图表识别
  - 不确定就先都 `false`，需要时再打开。

#### `summarizer`
- `provider`（必填）：当前使用的提供商名称，必须和 `providers` 里的键名一致。
  - 当前可选：`modelscope` / `siliconflow` / `openai-compatible`
- `show_window`：`true/false`，是否显示总结执行窗口。
- `threads`：总结并发数（建议 1~2，过高可能触发限流）。
- `max_input_chars`：每篇输入给模型的最大字符数。
  - `0` = 不截断（默认）
  - >0 = 超出就截断（用于控 token / 降成本）
- `sleep_seconds`：每次调用模型之间的等待秒数（用于降低 429 风险）。

#### `summarizer.providers`（给每个 provider 填连接信息）
每个 provider 都是同样 3 项：
- `base_url`：API 基地址
- `api_key`：密钥
- `model`：模型名
- 默认使用siliconflow的免费模型，需要siliconflow的API_KEY
实际生效的是 `summarizer.provider` 指向的那一组。示例：
- 如果 `"provider": "siliconflow"`，就只会使用 `providers.siliconflow` 里的 `base_url/api_key/model`。

### 最小可运行填写清单
- 必填：
  - `use_paddleocr`(True/False)
  - `summarizer.provider`
  - `summarizer.providers.<你选的provider>.api_key`
  - `summarizer.providers.<你选的provider>.model`
- 若 `use_paddleocr=true` 还必须填：
  - `paddleocr.api_key`

---

## 2. 怎么运行（复制就能用）

先进入目录（由 agent 根据用户环境填写）：
```bash
cd {skill_root_dir}
```

### A) 总结 1 个 PDF
```bash
python scripts/run_pipeline.py --pdf "{pdf_path}" --output-dir "{output_dir}"
```

### B) 总结多个 PDF
```bash
python scripts/run_pipeline.py --pdf "{pdf_path_1}" --pdf "{pdf_path_2}" --output-dir "{output_dir}"
```

### C) 总结 1 个文件夹里的全部 PDF
```bash
python scripts/run_pipeline.py --dir "{pdf_dir}" --output-dir "{output_dir}"
```

### D) 总结多个文件夹里的全部 PDF
```bash
python scripts/run_pipeline.py --dir "{pdf_dir_1}" --dir "{pdf_dir_2}" --output-dir "{output_dir}"
```

### E) 不指定输出目录（可选）
```bash
python scripts/run_pipeline.py --pdf "{pdf_path}"
```

> 不指定 `--output-dir` 时：
> **默认保存到每个输入 PDF 同目录下的 `总结` 文件夹**。

---

## 3. 常见问题

### Q1: 为什么没出报告？
- 先看终端报错。
- 常见原因：
  - API key 没填对
  - OCR 服务临时 500
  - 模型名写错

### Q2: 怎么关可见窗口？
- 在 `config.json` 把：
  - `paddleocr.show_window` 设为 `false`
  - `summarizer.show_window` 设为 `false`

### Q3: 抽取文本会不会单独保存成文件？
- 不会。当前是管道传递，不落盘。

---

## 4. 技术原理

流程是：

1. `run_pipeline.py` 收集用户给的 PDF 路径（支持单文件/多文件/单目录/多目录）
2. 根据 `use_paddleocr`：
   - `true`：`extract_paddleocr.py`
   - `false`：`extract_pdfplumber.py`
3. 抽取结果以 JSON 行通过 stdin 传给 `summarize_reports.py`
4. `summarize_reports.py` 调用你在 `config.json` 里指定的 provider+model
5. 生成 `*_研读报告.md`
