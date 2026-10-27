# 运行指南

[首页](../README.md) · [算法说明](../examples/README.md) · [架构与范围](ARCHITECTURE.md) · [验证记录](VALIDATION.md)

本仓库的最小可运行内容是独立算法、测试和保存结果的离线核验。它不包含完整 OCR 服务端；运行 Quickstart 不需要 GPU、模型、API 密钥或第三方 Python 包。

## 1. 获取源码并核验公开案例

准备 Git 和 Python 3.11+。第一次获取源码需要联网；此步骤不安装依赖、不下载模型，之后可离线运行：

```bash
git clone https://github.com/YSADF/ocr-document-showcase.git
cd ocr-document-showcase
python -S -X utf8 -B tools/verify_demo.py
python -S -X utf8 -B examples/literal_guard.py
python -S -X utf8 -B -m unittest discover -s tests -v
```

目录中应能看到 `examples/`、`tests/` 和 `tools/`。若你在完整项目中操作，先进入 `showcase/`，无需再次克隆。`-S` 关闭第三方包加载，`-B` 禁止生成字节码缓存。实际运行环境和检查范围见[验证记录](VALIDATION.md)；CI 配置存在不代表远端测试已经通过。

先用 `python --version` 确认可用解释器。Windows 的应用执行别名可能存在但未安装 Python；此时需要安装 Python 3.11+，或将命令中的 `python` 替换为已安装解释器的路径。

Windows 上将 `-X utf8` 放在脚本路径或 `-m` 之前。它启用 Python UTF-8 模式，避免默认编码无法输出 `Ø、∅、±` 等工程字符；仅更改源文件编码不能解决输出流的编码问题。

三个命令分别完成以下工作：

| 命令 | 检查内容 | 没有执行的工作 |
|---|---|---|
| `verify_demo.py` | 分别核验各轮本地实测与历史 GPU 证据：输入/产物哈希、OCR 文字行、逐格分数、DOCX 内部结构及渲染文件 | 不加载模型，不重新 OCR，不重新渲染 DOCX |
| `unittest discover` | 公开算法及工具的独立行为与反例 | 不测试未公开的完整服务 |
| `literal_guard.py` | 保护与恢复调用方已确认的字符片段 | 不自动判断上游识别是否正确 |

核验成功表示公开证据相互一致。`local_run` 保留首次 CPU 失败记录，`local_docx_fix` 检查原文导出修复，`local_translation` 检查 2026-10-26 历史单栏英译中结果，`local_faithful` 检查 2026-10-27 原页版式路径的保存证据。翻译核验不调用模型，不代表译文正确。2026-10-26 源表格 OCR 文字 **13/21**、位置及跨度 **16/21**、5 个合并关系漏检属于旧记录；历史 GPU 样本的文字 **19/21**、结构 **21/21** 和 DOCX 视觉失败也继续保留，不被新实验覆盖。

单独核验原页版式结果或对照历史单栏结果：

```bash
python -S -X utf8 -B tools/verify_translation.py --record artifacts/local-faithful-20261027/run.json
python -S -X utf8 -B tools/verify_translation.py --record artifacts/local-translation-20261026/run.json
```

命令读取仓库中已经保存的记录，不启动翻译服务或重新渲染。`local_faithful` 的具体检查数量、页面结论和待复核项见[本轮案例](../cases/faithful-translation-20261027.md)及[运行记录](../artifacts/local-faithful-20261027/run.json)。

默认结果输出到终端，不写入产物：核验报告中 `ok=true` 代表证据一致，`ocr_executed=false` 和 `renderer_executed=false` 说明没有执行新推理或渲染。字符保护脚本只对内置文字示例执行保护与恢复。需要保存新核验报告时使用尚不存在的文件：

```bash
python -S -X utf8 -B tools/verify_demo.py --output generated/demo-verification.json
```

## 2. 对照输入、JSON 与文档

**2026-10-27 原页版式英译中：**

从[案例入口](../cases/faithful-translation-20261027.md)按“原输入 → OCR JSON → 模型响应与译后 JSON → DOCX → 实际渲染”对照两例。此次复用完整项目现有 `faithful`，翻译阶段与导出阶段均显式选定该模式及 `strict` 质量策略；源码、模型和适配器不在精选公开包中，以上核验命令不能代替完整推理。

本轮传递实际 DPI 与页尺寸，按文字中心／基线及同栏关系分组，从局部规则线证据恢复表格合并；区分蓝底面板和线条，测量、嵌入及渲染使用同一静态 TTF。详细设计见[架构说明](ARCHITECTURE.md#2026-10-27-原页版式路径)。表格背景与定位文字不等于原生 Word 表格，`PASS`／`REVIEW` 等部分内容继续按策略保留原图。数量 `2`、`1` 在背景可见但对应 OCR 格为空；`Qty → 齐哥`、`ground truth → 地面真相` 等实际误译没有人工改写。显示、识别、翻译及编辑边界见[限制说明](LIMITATIONS.md)。

**2026-10-26 本地 CPU 历史实测：**

| 案例 | 实际输入 | 保存结果 |
|---|---|---|
| PLOS 论文正文与分级条目 | [第 2 页 PNG](../samples/plos-best-practices-page-2.png) | [JSON](../artifacts/local-20261026/plos/output.json) · [识别文字](../artifacts/local-20261026/plos/recognized.txt) · [DOCX](../artifacts/local-20261026/plos/output.docx) · [失败预览](../artifacts/local-20261026/plos/render/page-1.png) · [执行记录](../artifacts/local-20261026/plos/execution.json) |
| 自制合并表格 | [扫描 PDF](../samples/merged-table-scan.pdf) | [JSON](../artifacts/local-20261026/merged-table/output.json) · [逐格评分](../artifacts/local-20261026/merged-table/table-score.json) · [DOCX](../artifacts/local-20261026/merged-table/output.docx) · [失败预览](../artifacts/local-20261026/merged-table/render/page-1.png) · [执行记录](../artifacts/local-20261026/merged-table/execution.json) |

运行条件为断网 Docker、4 CPU / 8 GiB、Python 3.11.16、RapidOCR 3.0.0 / ONNX Runtime 1.19.2。实际使用 PP-OCRv3 检测与英文 PP-OCRv4 识别模型，版面与表格使用几何/OpenCV 路径，未启用 RapidTable 或 VLM；模型文件与哈希见执行记录的 `models`。JSON 中通用 Paddle 模型审计的 `not_found` 项不是这次实际使用的模型。

PLOS 保存 103 条块内文字行，没有独立人工校对的全文准确率。表格对照 21 格真值预测出 30 格，文字匹配 13/21、位置及跨度匹配 16/21，5 个合并关系全部漏检。两例没有记录运行时错误，不等于文档质量通过。公开包不含此次运行的完整处理系统，默认命令复核保存证据；新推理需要另行提供该系统、依赖与对应模型。

上表保留首次失败输出。随后在同样的输入和 OCR 配置下修复并重新运行，原文 DOCX 通过限定的叠字／缺失检查。[原文修复结果](../cases/docx-export-fix-20261026.md)另存；同日的[单栏英译中历史结果](../cases/english-to-chinese-20261026.md)为 PLOS 三页、表格一页，通过当时限定的显示检查，但放弃原版布局且仍有误译和漏译。2026-10-27 原页版式结果另立记录，历史产物保持不变。Microsoft Word 编辑行为未验证。

单独核验新结果：

```bash
python -S -X utf8 -B tools/verify_local.py --record artifacts/local-docx-fix-20261026/run.json
```

**2026-10-07 历史 GPU 基线：**

| 案例 | 实际输入 | 历史输出 |
|---|---|---|
| DEXPI C03 工程图 | [PNG](../samples/c03-raster.png)；[来源 PDF](../samples/c03-source.pdf) | [OCR JSON](../artifacts/gpu-20261007/engineering-response.json) · [DOCX](../artifacts/gpu-20261007/engineering-output.docx) · [渲染预览](../artifacts/gpu-20261007/engineering-render/page-1.png) |
| 自制合并表格 | [扫描 PDF](../samples/merged-table-scan.pdf)；[原生 PDF](../samples/merged-table-source.pdf) | [OCR JSON](../artifacts/gpu-20261007/merged-table-response.json) · [DOCX](../artifacts/gpu-20261007/merged-table-output.docx) · [渲染预览](../artifacts/gpu-20261007/merged-table-render/page-1.png) |

历史 OCR 请求实际使用工程图 PNG 和表格扫描 PDF；来源 PDF 的原生文字提取不是 OCR 输出。2026-10-07 的 DOCX 经 LibreOffice 渲染存在叠字、缺字或边框问题，Microsoft Word 未参与该次验证。新旧实验后端、模型与配置不同，不合并分数，也不直接推导性能或质量变化。

公开输入包含 PNG、原生 PDF 和扫描 PDF。JSON 可以检查和编辑已识别的文字、坐标及表格结构；DOCX 的可编辑范围以实际生成的文字和原生表格为限，图像背景与工程图元不能作为 CAD 对象编辑。保存的渲染 PDF/PNG 是显示预览，不能据此宣称已经提供或验收可搜索 PDF。

阅读顺序尚未经过独立的整页标注验收，不能宣称完整还原原文档的顺序或版面。

## 3. 可选：检查 PDF 路由

只有读取真实 PDF 时需要 PyMuPDF。建议为以下可选步骤创建独立环境；安装需要联网或预先准备好的依赖包。Windows PowerShell：

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
```

如果 PowerShell 禁止运行激活脚本，可跳过激活，将后续命令的 `python` 换成 `.venv\Scripts\python.exe`；无需修改系统执行策略。

Linux/macOS：

```bash
python3 -m venv .venv
source .venv/bin/activate
```

在已激活环境中运行。此处需要加载第三方包，因此不使用 `-S`：

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
