# 运行指南

[首页](../README.md) · [算法说明](../examples/README.md) · [架构与范围](ARCHITECTURE.md) · [验证记录](VALIDATION.md)

本仓库的最小可运行内容是独立算法、测试和保存结果的离线核验。它不包含完整 OCR 服务端；运行 Quickstart 不需要 GPU、模型、API 密钥或第三方 Python 包。

## 1. 核验公开案例

在本仓库根目录运行，目录中应能看到 `examples/`、`tests/` 和 `tools/`：

```bash
python -X utf8 tools/verify_demo.py
python -X utf8 -m unittest discover -s tests -v
python -X utf8 examples/literal_guard.py
```

代码以 Python 3.11+ 为设计目标，本次整理实际使用 Python 3.12.14。具体运行环境和检查范围见[验证记录](VALIDATION.md)；CI 配置存在不代表远端测试已经通过。

Windows 上将 `-X utf8` 放在脚本路径或 `-m` 之前。它启用 Python UTF-8 模式，避免默认编码无法输出 `Ø、∅、±` 等工程字符；仅更改源文件编码不能解决输出流的编码问题。

三个命令分别完成以下工作：

| 命令 | 检查内容 | 没有执行的工作 |
|---|---|---|
| `verify_demo.py` | 输入哈希、保存的 OCR 响应、逐格分数、DOCX 内部结构与历史失败记录 | 不加载模型，不重新 OCR，不重新渲染 DOCX |
| `unittest discover` | 公开算法及工具的独立行为与反例 | 不测试未公开的完整服务 |
| `literal_guard.py` | 保护与恢复调用方已确认的字符片段 | 不自动判断上游识别是否正确 |

核验成功表示公开证据相互一致。它会保留表格文字 **19/21**、结构 **21/21** 和两份 DOCX 的历史视觉失败，不会把这些已知错误改记为成功。

默认结果输出到终端，不覆盖冻结证据。需要保存新核验报告时使用尚不存在的文件：

```bash
python -X utf8 tools/verify_demo.py --output generated/demo-verification.json
```

## 2. 对照输入、JSON 与文档

| 案例 | 实际输入 | 历史输出 |
|---|---|---|
| DEXPI C03 工程图 | [PNG](../samples/c03-raster.png)；[来源 PDF](../samples/c03-source.pdf) | [OCR JSON](../artifacts/gpu-20261007/engineering-response.json) · [DOCX](../artifacts/gpu-20261007/engineering-output.docx) · [渲染预览](../artifacts/gpu-20261007/engineering-render/page-1.png) |
| 自制合并表格 | [扫描 PDF](../samples/merged-table-scan.pdf)；[原生 PDF](../samples/merged-table-source.pdf) | [OCR JSON](../artifacts/gpu-20261007/merged-table-response.json) · [DOCX](../artifacts/gpu-20261007/merged-table-output.docx) · [渲染预览](../artifacts/gpu-20261007/merged-table-render/page-1.png) |

OCR 请求实际使用工程图 PNG 和表格扫描 PDF；来源 PDF 的原生文字提取不是 OCR 输出。2026-10-07 的 DOCX 经 LibreOffice 渲染存在叠字、缺字或边框问题，Microsoft Word 未参与该次验证。

公开输入包含 PNG、原生 PDF 和扫描 PDF。JSON 可以检查和编辑已识别的文字、坐标及表格结构；DOCX 的可编辑范围以实际生成的文字和原生表格为限，图像背景与工程图元不能作为 CAD 对象编辑。保存的渲染 PDF/PNG 是显示预览，两例 DOCX 仍保留视觉失败结论。

阅读顺序尚未经过独立的整页标注验收，不能宣称完整还原原文档的顺序或版面。

## 3. 可选：检查 PDF 路由

只有读取真实 PDF 时需要 PyMuPDF：

```bash
python -X utf8 -m pip install -r requirements-pdf.txt
python -X utf8 -c "from pathlib import Path; from examples.pdf_routing import should_auto_route_pdf_to_direct as route; print(route(Path('samples/merged-table-source.pdf')).to_dict()); print(route(Path('samples/merged-table-scan.pdf')).to_dict())"
```

本次本地检查中，原生表格得到 `direct / text_pdf`，扫描表格得到 `ocr / low_text_density`。这是路由判定，不会执行转换或识别；存在文字层也不等于内容正确。

## 4. 可选：重新生成演示样本

样本准备需要 PDF、绘图和图像依赖：

```bash
python -X utf8 -m pip install -r requirements-demo.txt
python -X utf8 tools/prepare_examples.py --out-dir generated/demo --dpi 180
```

输出目录必须尚不存在；重复运行请使用另一个目录名。工具生成自制表格、工程图预览和元数据，不调用 OCR。字体、依赖版本或渲染器变化可能改变图像和哈希，新生成文件不能直接冒充历史测量所用输入。

依赖版本见 [requirements-demo.txt](../requirements-demo.txt)，素材归属见[来源说明](../CASE_SOURCES.md)。

## 5. 可选：连接已有兼容服务

仓库只提供 HTTP 测试客户端。服务端、模型及部署环境需要另行提供，不能从本仓库启动。客户端向 `/api/v1/ocr/file/sync` 上传两个公开案例，分别请求 JSON 和 DOCX。

```bash
python -X utf8 -m pip install -r requirements-client.txt
python -X utf8 tools/benchmark_service.py --base-url http://127.0.0.1:8089 --output-dir generated/benchmark --runs 1 --warmup 0
```

将 `--base-url` 改为已有服务地址。服务需要认证时，通过当前进程环境变量 `PPOCR_API_KEY` 提供密钥；客户端不会自动读取 `.env` 文件，不要把真实密钥写入公开文件。

`generated/benchmark` 必须尚不存在，防止覆盖历史结果或先前测试。一次请求适合检查连通性和输出，不能形成稳定的 P50/P95 结论。历史性能记录使用每例 2 次预热、20 次串行测量，完整口径见[评测说明](../EVALUATION.md)。

## 常见问题

| 现象 | 检查方式 |
|---|---|
| 找不到 `tools/verify_demo.py` | 切换到包含本 README 的公开仓库根目录 |
| `UnicodeEncodeError` 或工程字符无法输出 | 使用完整的 `python -X utf8 ...` 命令；确认终端字体支持该字符 |
| 调用 PDF 路由提示缺少 `fitz` | 在同一个 Python 环境安装 `requirements-pdf.txt` |
| 输出目录已存在 | 改用新目录，保留之前的报告 |
| HTTP 连接失败或返回 401 | 确认已有服务地址及其认证配置；本仓库不会启动服务 |
| 离线核验通过，但 Word 显示有问题 | 核验只确认保存证据；历史 DOCX 的视觉失败仍然成立 |

提交变更前请阅读[贡献方式](../CONTRIBUTING.md)。发布目录的清单核验和独立导出步骤见[发布说明](PUBLISHING.md)。
