# OCR 与文档结构化系统

把 PDF、扫描页和工程图转换为带坐标、表格跨度及质量信息的结构化结果。我负责文档处理流程、模型集成、版式适配、服务部署与评测，关注识别结果如何继续用于编辑、检索和业务处理。

**Python · PaddleOCR · OpenCV · PyMuPDF · FastAPI · DOCX**

[公开实测](EVALUATION.md) · [工程图案例](cases/engineering-pdf.md) · [合并表格案例](cases/merged-table.md) · [关键代码](examples/README.md) · [Agent / RAG 项目](https://github.com/YSADF/agent-rag-showcase)

## 公开实测：2026-10-07

在单张 RTX 5090 32 GB 上调用实际项目服务，每例预热 2 次，再串行测量 20 次。语言 `en`、模式 `balanced`，启用版面分析。项目目录沿用 PP-V5 命名，**本轮实际 OCR 后端为 PP-OCRv6 small**，模型文件哈希随响应公开。

| 样本 | JSON 请求成功 | P50 / P95 | 质量核查 |
|---|---:|---:|---|
| DEXPI C03 工程图 PNG | 20/20 | 4.164 / 4.433 秒 | 可识别主要设备编号；小字和长说明有漏字、截断 |
| 自制合并表格扫描 PDF | 20/20 | 1.793 / 1.919 秒 | 单元格文字完全匹配 19/21；5 个合并关系全部匹配 |

表格的 203 个参考字符中有 2 个替换错误，CER **0.985%**：两处 `Ø` 被识别成 `∅`。21 个单元格的行列位置与跨度全部匹配。这只覆盖一张自制表，不能推断复杂表格的总体准确率。

**Word 导出仍有问题：** 两个 DOCX 均已生成，但 LibreOffice 渲染核查未通过，分别出现文字重叠、表格文字缺失及边框不完整。保留[原始输出、预览与逐项评分](artifacts/gpu-20261007/)，接口成功率与页面还原质量分别报告。

## 案例与证据

| 工程图：小字、旋转标签、线条干扰 | 表格：跨行跨列、工程字符 |
|---|---|
| ![工程图输入](assets/engineering-input.png) | ![表格输入](assets/merged-table-input.png) |
| [实际 OCR 响应](artifacts/gpu-20261007/engineering-response.json) · [案例分析](cases/engineering-pdf.md) | [实际 OCR 响应](artifacts/gpu-20261007/merged-table-response.json) · [逐格评分](artifacts/gpu-20261007/quality.json) |

## 重难点与我的实现

| 工程问题 | 处理方法与取舍 | 可检查的证据 |
|---|---|---|
| 原生、扫描 PDF 走错链路会损失文字或重复识别 | 结合文字页比例与每页文字量选择 DOCX 路径；保留强制模式和探测失败回退 | [PDF 路由](examples/pdf_routing.py) |
| 译文变长，覆盖图线与相邻标签 | 有界搜索换行、字号、字距及横向比例，返回明确的 `fits` 状态；估算通过仍需渲染验证 | [Copy-fit 搜索](examples/copy_fit.py) |
| 编号、尺寸、符号被翻译或归一化改写 | 保存已确认片段的原始 Unicode，校验占位符数量、顺序与摘要，异常时返回原文 | [字符保护](examples/literal_guard.py) |
| 合并单元格同时包含文字与结构 | 统一 `row / col / rowspan / colspan`，分别检查文字、网格与输出效果 | [21 单元格结果](artifacts/gpu-20261007/quality.json) |
| PDF 点坐标与图像像素混用 | 按实际页面和栅格尺寸换算，保存坐标系和尺度 | [样本准备脚本](tools/prepare_examples.py) |

字符保护只能保留上游已经给出的字符，不能自动把 OCR 的 `∅` 判断为 `Ø`。结构化表格正确也不足以证明 Word 显示正确，需要独立的渲染质量检查。

```mermaid
flowchart LR
    A[PDF / 图片] --> B[页面分类与路由]
    B --> C[原生提取或 OCR]
    C --> D[版面与表格结构]
    D --> E[坐标统一与质量检查]
    E --> F[JSON]
    E --> G[DOCX]
    G --> H[渲染核查与人工复核]
```

检测、识别及版面模型来自开源项目；我的工作集中在流程设计、组件集成、字符与版式适配、异常处理和部署交付。符号语义分类、P&ID 管线连通性和模型微调不作为本轮已验证能力。

## 运行公开代码

独立示例与离线评分只需 Python 3.11+，无需完整业务源码或 GPU：

```bash
python -m unittest discover -s tests -v
python examples/literal_guard.py
python tools/score_results.py
```

6 项独立示例测试通过。重新生成公开输入：

```bash
python -m pip install -r requirements-demo.txt
python tools/prepare_examples.py --dpi 180
```

对已部署的项目服务复测：

```bash
python -m pip install httpx numpy
python tools/benchmark_service.py --base-url http://127.0.0.1:8089 --runs 20
```

认证通过环境变量 `PPOCR_API_KEY` 设置。此仓库公开选取的算法、测试客户端、输入和实测产物；完整业务服务未开源，不能仅凭展示包重建全部系统。

## 下一步

- 修复 Word 文本与背景重复叠加、表格显示异常，再用相同输入复测。
- 扩展小字、旋转标注、断线和倾斜表格的独立标注集。
- 增加 Word 与 LibreOffice 双渲染器检查，将页面交付质量纳入门禁。

[样本来源与许可](CASE_SOURCES.md) · [代码来源](CODE_PROVENANCE.json) · [展示许可](LICENSE.md)
