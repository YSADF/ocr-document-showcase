# 案例二：合并单元格表格重建

[返回项目首页](../README.md) · [样本来源与许可](../CASE_SOURCES.md) · [评测方法](../EVALUATION.md)

使用自行制作的英文 Inspection Record 表格样本，验证行列结构、跨行跨列关系、单元格文字与可编辑 Word 输出。样本逻辑网格为 6 行 × 5 列，包含 21 个物理单元格，其中 5 个合并单元格；文字包含 `Ø、±、°`。当前已提供输入和生成时记录的结构真值；OCR、表格识别及 DOCX 重建结果待实测。

## 输入难点

- 跨行与跨列会改变网格边界，按文字位置直接排序容易把合并单元格拆成多个普通格。
- 表格线和相邻文字容易造成错列或重复文字，需要同时检查结构与内容。
- Word 输出既要保留合并关系，也要保留可编辑的单元格；仅把表格截图嵌入 Word 无法验证重建能力。

![自行制作的合并单元格表格输入](../assets/merged-table-input.png)

样本提供两种输入：[原生 PDF](../samples/merged-table-source.pdf)和[纯图像 PDF](../samples/merged-table-scan.pdf)。后者用于 OCR 评测，避免原生文字层影响结论；PNG 是同一输入的页面预览。

## 处理方法

1. 生成表格 PDF 时同时保存真实行列位置、单元格文字和 `rowspan` / `colspan`，建立可重复的自制样本。
2. 原生 PDF 和纯图像输入分别执行结构提取，不混合报告两条路径的结果。
3. 表格结构以网格、单元格跨度和文字记录，后续 DOCX 输出按跨度恢复 Word 合并单元格。
4. 用真值逐格比对文字和合并范围，再打开 Word 检查编辑能力、边框与排版。

现有系统的数据模型能表达 `rowspan` / `colspan`，表格处理包含合并格几何回填，Word 输出包含合并单元格映射。这些是已有实现依据；本样本是否正确还需实际运行验证。

## 当前结果

| 产物 | 状态与含义 |
|---|---|
| 自制 PDF、纯图像 PDF 与 PNG | 已提供，内容不含客户或实际业务数据 |
| [merged-table-ground-truth.json](../artifacts/merged-table-ground-truth.json) | 已提供；生成样本时记录的预期结构，不是识别结果 |
| 表格 OCR 与结构 JSON | 待实测 |
| 可编辑 DOCX 与 Word 页面预览 | 待实测 |
| 单元格文字及合并关系正确率 | 待实测，不填示意分数 |

真值文件可用于核对行列、跨度和文字。它说明“输入应当怎样被还原”，不证明模型已经识别出同样结果；当前不会把真值或样本生成文件放入识别结果栏。

## 待验证

- 基础行列数是否正确；跨行、跨列范围是否与真值一致，是否出现重复格或漏格。
- 数字、单位、`Ø、±、°` 及英文文字是否正确；同时报告单元格完全匹配率和文字 CER，避免结构正确掩盖内容错误。
- DOCX 中的表格是否可直接编辑，横向与纵向合并是否正确，长文字是否溢出，页面边框是否异常。
- 原生 PDF 与扫描路径分别保存请求、响应、环境及耗时；只有本样本完成验证后才发布对应效果图。

## 复现参数

在展示包根目录执行 `python tools/prepare_examples.py` 可重建自制样本和真值，扫描页面默认 180 DPI。生成环境、页面尺寸和文件校验值见[评测文档](../EVALUATION.md)与[来源清单](../CASE_SOURCES.md)。自制样本和真值可独立复现；完整 OCR、表格识别和 Word 重建需要已部署的项目服务及模型，本展示包不包含完整系统实现。

以下为本地项目服务的 **Bash** 请求示例，在展示包根目录执行。示例尚未针对本样本运行；服务地址和认证应使用自己的本地环境。

本样本尚未覆盖空白单元格、断线、倾斜和低清扫描，这些情况需要另建测试组。

```bash
mkdir -p results/merged-table
curl --fail --show-error \
  http://127.0.0.1:8089/api/v1/ocr/file/sync \
  -F 'file=@samples/merged-table-scan.pdf' \
  -F 'output_format=json' \
  -F 'use_layout=true' \
  -F 'ocr_lang=en' \
  -F 'ocr_mode=balanced' \
  -F 'conversion_mode=ocr' \
  -o results/merged-table/ocr-response.json

curl --fail --show-error \
  http://127.0.0.1:8089/api/v1/ocr/file/sync \
  -F 'file=@samples/merged-table-scan.pdf' \
  -F 'output_format=docx' \
  -F 'direct_download=true' \
  -F 'use_layout=true' \
  -F 'ocr_lang=en' \
  -F 'ocr_mode=balanced' \
  -F 'conversion_mode=ocr' \
  -o results/merged-table/ocr-output.docx
```

JSON 中的 `regions` / `pages` 用于检查表格与单元格信息，DOCX 请求直接保存文件。两个请求分别执行任务，比较产物时应保留各自配置与任务信息；接口成功返回后仍需逐格检查与 Word 视觉检查。

原生 PDF 对照时改用 `samples/merged-table-source.pdf`，另存响应并检查 `conversion`、质量与页面元数据，确认实际使用的路径。原生内容提取和图像 OCR 的结构结果分别报告。

## 来源

样本、生成时记录的真值及输入图由本展示包自行制作，使用虚构内容，供公开测试。可用方式与生成说明见[来源清单](../CASE_SOURCES.md)。对外报告中保留“自制输入 / 真值 / 实测输出”的标记，便于读者判断每份文件提供的证据。
