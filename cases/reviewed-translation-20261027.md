# 中文 Word 案例（2026-10-27）

对照英文原页，查看双栏论文和合并表格的最终中文文档。原始 OCR、模型响应和历史评分单独保存在[模型实测](faithful-translation-20261027.md)中；PLOS 的生成参数与内容版本见[导出记录](../artifacts/reviewed-translation-20261027/run.json)。表格已补入四处检测状态，见[本次记录](../artifacts/status-translation-20261027/run.json)和[逐区域内容检查](../artifacts/status-translation-20261027/semantic-coverage.json)。

| 输入与场景 | 中文产物 | 核查结果 |
|---|---|---|
| [PLOS 第 2 页](../samples/plos-best-practices-page-2.png)：双栏科学计算论文，包含编号摘要框、软件名与引用 | [中文 DOCX](../artifacts/reviewed-translation-20261027/plos/output.docx) · [译文 JSON](../artifacts/reviewed-translation-20261027/plos/reviewed.json) · [预览 PDF](../artifacts/reviewed-translation-20261027/plos/render/output.pdf) | 一页双栏、蓝底及完整页脚；严格审计 0 违规 |
| [自制表格](../assets/merged-table-input.png)：工程检查记录，包含跨行／跨列合并、数量与公差 | [中文 DOCX](../artifacts/status-translation-20261027/merged-table/output.docx) · [译文 JSON](../artifacts/status-translation-20261027/merged-table/reviewed.json) · [预览 PDF](../artifacts/status-translation-20261027/merged-table/render/output.pdf) | 一页、21 个物理格与 5 处合并边界；合格／待复核与汇总均显示中文；严格审计 0 违规 |

下载原文：[PLOS 完整论文 PDF](../samples/plos-best-practices-source.pdf) · [表格扫描 PDF](../samples/merged-table-scan.pdf)。

## 实际预览

![PLOS 中文 DOCX 的真实渲染，双栏及蓝底保留](../artifacts/reviewed-translation-20261027/plos/render/page-1.png)

![表格中文 DOCX 的真实渲染，检测状态及汇总已译为中文，底部两条说明分行](../artifacts/status-translation-20261027/merged-table/render/page-1.png)

## 执行与复核范围

使用已保存的文档数据，复用 `DocumentPipeline.render_result(..., 'docx', absolute_position=True)` 及静态 Noto 字体。最终导出和独立渲染均在禁网容器中执行：导出使用 4 CPU／6 GiB，渲染使用 2 CPU／4 GiB；这一步没有重新运行 OCR／翻译模型或读取本地 `.env`。

随后只编辑表格 DOCX，补上先前漏译的两处 `PASS`、一处 `REVIEW` 及 `3 PASS / 1 REVIEW` 汇总。它们之前被技术标识／算式保护规则保留在背景中，不能当作完成翻译。本次复用既有擦字、定位文字和字体嵌入方法，分别写成“合格”“待复核”“合格”“3 合格 / 1 待复核”；文档编辑容器使用 4 CPU／10 GiB，独立渲染仍为 2 CPU／4 GiB，均禁网。只清除四处原字形，字形掩码外像素变化为 0；没有修改应用代码或原始模型结果。[四项变更与坐标](../artifacts/status-translation-20261027/merged-table/corrections.json) · [执行记录](../artifacts/status-translation-20261027/merged-table/execution.json)

独立环境的实际渲染命令为：

```bash
python /helper/render_docx.py /input/output.docx --output_dir /work/renders/plos --emit_pdf --dpi 144
python /helper/render_docx.py /input/output.docx --output_dir /work/renders/merged-table --emit_pdf --dpi 144
```

两条命令在各自容器中挂载对应 DOCX；`/helper` 为本地渲染工具，**不是公开包提供的入口**。完整私有导出器也不随此包发布。读者可以直接下载上述文件查看；公开包仍可按[快速开始](../README.md#快速开始)核验原始实测，另用 `python -S -X utf8 -B tools/check_publication.py` 检查最终文档的显式文件清单与哈希。

LibreOffice 7.4.7.2／Poppler 22.12.0 以 144 DPI 渲染，两份均为一页。PLOS 文件不变，仍为 111 条来源记录、51 个定位文字区域。新表格 DOCX 有 20 个原生定位文字区域，四处新增中文在 DOCX 和实际 PDF 中均可匹配；全页目视未见英文状态残影、重叠、裁切或溢出，表格线与合并边界完整。[实际审计](../artifacts/status-translation-20261027/merged-table/audit/delivery-audit.json)通过、0 违规；其 17 条写入／6 条保留仍沿用原始文字保护分类，不代表当前中文覆盖数量。

另对 21 个物理格与 3 个页外区域逐一检查：19 个需要翻译的区域均有对应中文，5 个区域保留规格、量值或单位；其中 DN 标签与数量共 4 格仍在背景中。这是固定样本的内容复核，不能换算成模型准确率。[逐区域记录](../artifacts/status-translation-20261027/semantic-coverage.json) · [视觉记录](../artifacts/status-translation-20261027/merged-table/visual-review.json) · [旧表格版本](../artifacts/reviewed-translation-20261027/merged-table/output.docx)

## 仍然保留的边界

这些页面用于检查文档呈现，不构成模型准确率、独立人工认证或通用版式保证。原始 OCR 分数与模型输出继续保留。公开包只提供原有 8 个精选算法，不包含完整翻译或排版服务。

表格仍是原背景网格与原生定位文字，`w:tbl=0`。`DN 50／DN 80` 与数量 `2／1` 为背景文字；数量对应的原始 OCR 格仍为空，不能据此声称已识别或全表可编辑。PLOS 的软件名、代码标识与 URL 保留原文；两例字体、局部字号与原文有差异，Microsoft Word 交互编辑尚未验证。页脚“可编辑文档结构”是原样本目标的翻译，不是本例已实现的承诺。

PLOS 内容来源：Wilson G 等（2014），*Best Practices for Scientific Computing*，PLOS Biology 12(1): e1001745，DOI `10.1371/journal.pbio.1001745`，CC BY 4.0。派生文件包含中文译文与文字排版；自制表格仍按 CC0 1.0。完整[来源、许可与字体说明](../CASE_SOURCES.md)继续适用。
