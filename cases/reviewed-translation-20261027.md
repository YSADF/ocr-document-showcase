# 中文 DOCX 校对版（2026-10-27）

这两份文件由助手按用户要求，对保存的机器译文逐段校对，再调用原有 `faithful` 导出。**本次没有修改项目代码，也没有重新执行 OCR 或翻译模型。** 原始模型响应、OCR、未校对 DOCX 和评分全部保留在[原始实测](faithful-translation-20261027.md)中。

| 输入与问题 | 校对后产物 | 核查结果 |
|---|---|---|
| [PLOS 第 2 页](../samples/plos-best-practices-page-2.png)：编程术语误译、跨行续句及软件名／代码标识错误 | [中文 DOCX](../artifacts/reviewed-translation-20261027/plos/output.docx) · [译文 JSON](../artifacts/reviewed-translation-20261027/plos/reviewed.json) · [预览 PDF](../artifacts/reviewed-translation-20261027/plos/render/output.pdf) | 51 组译文逐组复核；一页双栏、蓝底及完整页脚；严格审计 0 违规 |
| [自制表格](../assets/merged-table-input.png)：Qty、ground truth、Valve body 误译及否定说明漏译 | [中文 DOCX](../artifacts/reviewed-translation-20261027/merged-table/output.docx) · [译文 JSON](../artifacts/reviewed-translation-20261027/merged-table/reviewed.json) · [预览 PDF](../artifacts/reviewed-translation-20261027/merged-table/render/output.pdf) | 3 组页外文字与 13 个格内译文核对；一页、表格可见、页脚两行；严格审计 0 违规 |

## 具体改了什么

- PLOS：修正“缺陷与测试用例”“符号调试器”“性能分析工具”“结对编程”等术语；补齐续句、否定意义；恢复 `Fortran`、`C++`、`Java`、`C#`、`Make`、变量名、引用编号和原网址。
- 表格：`齐哥 → 数量`、`地面真相 → 真值标注`、`阀门 → 阀体`；补回“并非 OCR 结果”。对照原图修正 `Ø 50 ± 0.10 mm`、`90° ± 0.5°`、`型号 P001 / 1 件`、`孔径 Ø 12 mm`。这些是校对后的输出，不是模型识别改善。
- 逐项保存[原文／旧译文／校对后文字](../artifacts/reviewed-translation-20261027/corrections.json)，没有覆盖原始 OCR。原图能直接确认的符号与数量另外标明；未将结构真值输入预测或导出。
- 表格 DOCX 页脚在导出后增加一处显式换行，使“目标：”另起一行。这是本份文件的格式编辑；没有修改渲染器。

## 实际预览

![PLOS 中文校对版的真实 DOCX 渲染，双栏及蓝底保留](../artifacts/reviewed-translation-20261027/plos/render/page-1.png)

![表格中文校对版的真实 DOCX 渲染，术语与说明已校对，底部两条说明分行](../artifacts/reviewed-translation-20261027/merged-table/render/page-1.png)

## 执行与复核范围

使用上轮冻结的识别／翻译数据，只替换校对文字，复用 `DocumentPipeline.render_result(..., 'docx', absolute_position=True)` 及相同静态 Noto 字体；两次最终导出和独立渲染均在禁网容器中执行。导出使用 4 CPU／6 GiB，渲染使用 2 CPU／4 GiB；没有调用模型或读取本地 `.env`。

独立环境的实际渲染命令为：

```bash
python /helper/render_docx.py /input/output.docx --output_dir /work/renders/plos --emit_pdf --dpi 144
python /helper/render_docx.py /input/output.docx --output_dir /work/renders/merged-table --emit_pdf --dpi 144
```

两条命令在各自容器中挂载对应 DOCX；`/helper` 为本地渲染工具，**不是公开包提供的入口**。完整私有导出器也不随此包发布。读者可以直接下载上述文件查看；公开包仍可按[快速开始](../README.md#快速开始)核验原始实测，另用 `python -S -X utf8 -B tools/check_publication.py` 检查包括校对版在内的显式文件清单与哈希。

LibreOffice 7.4.7.2／Poppler 22.12.0 以 144 DPI 渲染，两份均为一页。最终 PNG 全页目视检查未见重叠、裁切、溢出或中文缺字；原有严格审计均通过。PLOS 111 条来源记录覆盖、51 个定位文字区域；表格 23 条来源记录中 17 条写入、6 条保留，16 个定位文字区域。计数口径不同，不能把它们当成翻译准确率。[完整记录](../artifacts/reviewed-translation-20261027/run.json) · [逐页审阅](../artifacts/reviewed-translation-20261027/visual-review.json)

## 仍然保留的边界

这次是助手校对，不是独立人工认证或新模型成绩。应用源码快照 460 个文件、公开 Python 27 个文件与原 8 个精选算法哈希均未变；代码回归无需据此声称重新完成。旧 OCR 分数不因校对提升。

表格仍是原背景网格与原生定位文字，`w:tbl=0`。`PASS／REVIEW`、`DN` 标签、汇总状态和数量 `2／1` 保留为英文／数字背景，并非全文汉化或全表可编辑。PLOS 字体、局部字号与原文有差异；Microsoft Word 交互编辑尚未验证。页脚“可编辑文档结构”是原样本目标的翻译，不是本例已实现的承诺。

PLOS 内容来源：Wilson G 等（2014），*Best Practices for Scientific Computing*，PLOS Biology 12(1): e1001745，DOI `10.1371/journal.pbio.1001745`，CC BY 4.0。派生文件新增中文校对与文字排版；自制表格仍按 CC0 1.0。完整[来源、许可与字体说明](../CASE_SOURCES.md)继续适用。
