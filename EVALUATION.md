# 公开案例评测

[返回首页](README.md)

**第二轮机械优化：**零件表结构恢复后机械转写 74/118 → 83/118，17 个直径失败逐区域拦截。仍未通过发布门槛；方法、预算对照与失败诊断见[第二轮报告](cases/mechanical-ocr-round2.md)。

**后续真实图纸测试（2026-10-08）：**已完成 20 张图纸、238 个选定区域、40 次 GPU 对照推理，见[独立报告](cases/real-engineering-drawings.md)。工程模式仍未达标。本文继续保留 2026-10-07 两个固定案例的基线，不与新数据混合统计。

本轮于 2026-10-07 在实际服务上执行，所有数字对应公开输入和保存的响应，不使用简历中的历史百分比作为本轮结果。

## 环境与输入

- 单张 NVIDIA RTX 5090，32 GB；驱动 595.71.05；Python 3.11.17。
- PaddlePaddle GPU 3.3.1 / CUDA 12.9，PaddleOCR 3.7.0；GPU 就绪，未启用 CPU 回退。
- 实际识别模型 `PP-OCRv6_small_det`、`PP-OCRv6_small_rec`，版面模型 `PP-DocLayout-M`；表格来源字段为 `rapidtable`。构造参数与文件哈希见响应中的 `ocr_model`。
- 工程图使用 180 DPI、4210 × 2977 PNG，无 PDF 文字层。表格使用纯图像 PDF：真值为 180 DPI、2105 × 1489，服务输出坐标为 2573 × 1819，几何比较必须按实际宽高缩放。
- 输入哈希与每次请求耗时见 [benchmark.json](artifacts/gpu-20261007/benchmark.json)。

## 耗时口径

同机回环 HTTP，从发出请求到接收完整响应计时，不含之后的 JSON 解析。每例预热 2 次、测量 20 次、串行执行，NumPy 线性分位数。固定 `balanced / en / use_layout=true / conversion_mode=ocr`。

| 样本 | 成功 / 测量次数 | P50 | P95 | 最大值 | 独立 DOCX 请求 |
|---|---:|---:|---:|---:|---:|
| 工程图 | 20/20 | 4.164 s | 4.433 s | 4.583 s | 4.507 s |
| 合并表格 | 20/20 | 1.793 s | 1.919 s | 1.937 s | 1.692 s |

DOCX 每例只执行一次，不能给出稳定延迟分布。两个固定样本重复运行只衡量该输入的延迟波动，不能代替多样本准确率、并发吞吐或生产容量评估；20 次观测的 P95 不保证稳定尾延迟。

## 质量口径

使用第一个正式测量请求的 JSON 评分。

| 指标 | 结果 | 定义 |
|---|---|---|
| 表格文字完全匹配 | 19/21 | 按行列锚点对齐，只合并空白；保留大小写与 Unicode |
| 表格 CER | 2/203 = 0.985% | 逐单元格编辑距离求和；两处 `Ø → ∅` |
| 单元格位置与跨度 | 21/21 | `row, col, rowspan, colspan` 全部相等；预测也是 21 格 |
| 合并关系 | TP=5，FP=0，FN=0 | 精确匹配锚点与跨度 |
| 工程图全文 CER / 检测召回 | 未报告 | 原生提取不完整，尚无独立校订的全文真值 |
| DOCX 渲染 | 两例均未通过 | LibreOffice 转 PDF 后逐页检查 |

表格的系统状态为 `accepted`，Word 渲染仍失败，说明现有接受状态没有覆盖实际交付质量。工程图为 `review`，小字和长说明不完整。

DOCX XML 中工程图没有原生 `w:tbl`；表格有 1 个原生表格、4 个 `gridSpan`、2 个 `vMerge` 节点。节点存在只证明结构写入，不证明显示或编辑体验正确。Microsoft Word 尚未测试，不能断言所有客户端均有相同表现。

## 复算与产物

```bash
python tools/score_results.py
python -m unittest discover -s tests -v
```

[逐格评分](artifacts/gpu-20261007/quality.json) · [工程图 DOCX](artifacts/gpu-20261007/engineering-output.docx) · [表格 DOCX](artifacts/gpu-20261007/merged-table-output.docx) · [实际预览](artifacts/gpu-20261007/)

离线评分和关键代码可独立运行；端到端重跑仍需完整服务及模型。原生文字提取基线继续保留，与模型 OCR 分开标记。
