# translator-pdf2zh-workflow

## 免费大模型推荐
1. 火山引擎协作奖励计划：每天使用量会影响次日赠送量，单日最高 `200w` token，当日满额后次日可达 `400w` token。  
   链接：https://console.volcengine.com/ark/region:ark+cn-beijing/openManagement/rewardPlan?
2. 美团 Longcat：可申请 token 扩容，`Longcat-flash-lite` 每日使用量 5000w token。 `LongCat-Flash-Chat`、`LongCat-Flash-Thinking-2601`、`LongCat-Flash-Omni-2603` 模型申请扩容后每日使用量 `500w` token
   链接：https://longcat.chat/platform/usage

---

## 1. 官方文档入口

- Advanced（中文）：https://pdf2zh-next.com/zh/advanced/advanced.html  
- SiliconFlow（中文）：https://pdf2zh-next.com/zh/advanced/TranslationServices/SiliconFlow.html  
- Python API（中文）：https://pdf2zh-next.com/zh/advanced/API/python.html  
- PyPI：https://pypi.org/project/pdf2zh-next/

---

## 2. 这个 Skill 能做什么

支持 6 类输入：
1. 单个 PDF
2. 多个 PDF
3. 单个文件夹全部 PDF
4. 单个文件夹部分 PDF
5. 多个文件夹全部 PDF
6. 多个文件夹部分 PDF

输出目录始终由用户指定。

---

## 3. 先记住这 4 条规则

1. **路径必须是绝对路径**。  
2. **运行时参数优先于 config.v3.toml**。  
3. **没在命令里写的参数，如果 config.v3.toml 里有，就用配置文件的值**。  
4. 默认走 **SiliconFlowFree**，并尽量禁用自动术语表提取。

---

## 4. 环境要求

### 4.1 通用
- Python（建议 3.10~3.13）
- 能运行 `python --version`
- 网络可访问翻译服务

### 4.2 Windows
- 可用 uv/CLI（`pdf2zh_next`）或 exe
- 你提供的 exe 路径示例：`D:\pdf2zh\pdf2zh.exe`
- exe 不能运行时先装 VC 运行库：
  https://aka.ms/vs/17/release/vc_redist.x64.exe

---

## 5. OpenClaw 需要的工具权限（要告知用户）

### 必需
- `exec`
- `read`
- `write`

### 建议
- `edit`
- `process`

---

## 6. 配置文件位置

- Linux/macOS：`~/.config/pdf2zh/config.v3.toml`
- Windows：`C:\Users\<用户名>\.config\pdf2zh\config.v3.toml`

找不到配置时：
1) 不要自动猜测或创建；
2) 直接要求用户提供配置文件路径；
3) 用 `--config-path` 指定。

常见默认位置：
- Linux/macOS：`~/.config/pdf2zh/config.v3.toml`
- Windows：`C:\Users\<用户名>\.config\pdf2zh\config.v3.toml`

---

## 7. 命令模板（直接改路径就能用）

脚本：`skills/translator-pdf2zh-workflow/scripts/run_pdf2zh_pipeline.py`

### 7.1 单个 PDF
```bash
python skills/translator-pdf2zh-workflow/scripts/run_pdf2zh_pipeline.py \
  --input-file "{PDF绝对路径}" \
  --output-dir "{输出目录绝对路径}" \
  --stream
```

### 7.2 多个 PDF
```bash
python skills/translator-pdf2zh-workflow/scripts/run_pdf2zh_pipeline.py \
  --input-file "{PDF1绝对路径}" \
  --input-file "{PDF2绝对路径}" \
  --output-dir "{输出目录绝对路径}" \
  --stream
```

### 7.3 单目录全部 PDF
```bash
python skills/translator-pdf2zh-workflow/scripts/run_pdf2zh_pipeline.py \
  --input-dir "{输入目录绝对路径}" \
  --output-dir "{输出目录绝对路径}" \
  --stream
```

### 7.4 单目录部分 PDF
```bash
python skills/translator-pdf2zh-workflow/scripts/run_pdf2zh_pipeline.py \
  --input-dir "{输入目录绝对路径}" \
  --include-glob "*A*.pdf" \
  --include-glob "*2024*.pdf" \
  --output-dir "{输出目录绝对路径}" \
  --stream
```

### 7.5 多目录全部 PDF
```bash
python skills/translator-pdf2zh-workflow/scripts/run_pdf2zh_pipeline.py \
  --input-dir "{目录1绝对路径}" \
  --input-dir "{目录2绝对路径}" \
  --output-dir "{输出目录绝对路径}" \
  --stream
```

### 7.6 多目录部分 PDF
```bash
python skills/translator-pdf2zh-workflow/scripts/run_pdf2zh_pipeline.py \
  --input-dir "{目录1绝对路径}" \
  --input-dir "{目录2绝对路径}" \
  --include-glob "*keyword*.pdf" \
  --output-dir "{输出目录绝对路径}" \
  --stream
```

### 7.7 指定 exe（Windows）
```bash
python skills/translator-pdf2zh-workflow/scripts/run_pdf2zh_pipeline.py \
  --input-file "C:\Users\tiandoufayale\Desktop\1.pdf" \
  --output-dir "C:\Users\tiandoufayale\Desktop" \
  --exe-path "D:\pdf2zh\pdf2zh.exe" \
  --stream
```

---

## 8. Provider 用法

- 默认：若用户未指定提供商，agent 将确保配置使用 `siliconflowfree`。
- 若用户本次明确指定 provider/base_url/api_key：
  - 由 **agent 直接写入 `config.v3.toml`**；
  - 启用该 provider；
  - 将 `siliconflowfree = false`；
  - 下次运行可不再指定 provider（读取配置文件）。
- 若用户说“使用当前 agent 所用大模型”：
  - 由 **agent 读取 openclaw.json 并完成模型类别判断**；
  - agent 直接把转换结果写入 `config.v3.toml`（仅 anthropic/openaicompatible 等受支持配置）。
- 脚本不读取 openclaw.json，不负责 provider 智能判断，不负责写入 provider 凭据。

---

## 9. 参数不确定时（强制流程）

先看帮助再跑：
- `pdf2zh_next -h`
- 或 `"{exe绝对路径}" -h`

---

## 10. 成功/失败判定

### 成功（必须全满足）
1. 退出码 0
2. 日志有 `[ok] all translations finished successfully`
3. 输出目录有译文 PDF

### 失败
任一文件报错即停；agent看最后 50~100 行日志定位问题。

---

## 11. 常见问题

- 参数不识别：先 `-h`
- 服务不支持：切兼容参数或切主程序入口
- 配置找不到：用 `--config-path`
- 包安装失败：检查 Python 版本
- 限流：降并发/降 qps

---

## 12. 技术原理与实现细节

1. CLI 兼容探测：脚本先读取 `-h`，自动判断用 `--siliconflowfree` 或 `--service siliconflowfree`。  
2. 参数优先级：运行时参数覆盖 config；未显式传参则回落 config。  
3. 术语表策略：优先追加 `--no-auto-extract-glossary`，并保持配置里关闭自动保存。  
4. 失败策略：任一文件失败即停，输出文件名 + 错误摘要 + 关键日志。  
5. 输出验收：以日志 `[ok]` + 输出目录译文 PDF 双重确认。
