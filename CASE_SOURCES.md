# 样本来源与许可

[返回首页](README.md)

## 2026-10-26 英译中派生产物

`artifacts/local-translation-20261026/` 使用下文同一份 PLOS 公开论文页和自制 CC0 表格。PLOS 中文译文是本项目调用机器翻译模型生成的派生内容，沿用原文章的来源和许可要求；不是原作者提供、认可或校对的译本。译文存在误译与遗漏，正文版式已重排。表格的机器译文与原预测结构也原样保留。

翻译权重来自 [Argos 官方模型索引](https://raw.githubusercontent.com/argosopentech/argospm-index/main/index.json) 的 `translate-en_zh` 1.9。下载日期、包及展开文件 SHA-256 记录在[模型来源](artifacts/local-translation-20261026/model-provenance.json)。公开包不再分发模型权重、Stanza 数据或模型 README；这里只保存来源、哈希、项目请求响应及本项目导出物，不把第三方翻译模型称为自主训练成果。

修复前后使用相同模型重新执行，`before-reflow/` 保留真实旧布局；原文 OCR 记录和此前失败产物未被覆盖。[本轮案例与限制](cases/english-to-chinese-20261026.md)

## DEXPI C03

- 来源项目：[DEXPI / Public Example PIDs](https://gitlab.com/dexpi/TrainingTestCases)。
- 原始路径：`dexpi 1.2/example pids/C03 DEXPI Example Tank Displ Pump Pipe with Tee/C03V01-SAG.EX01.pdf`。
- [原始 PDF](https://gitlab.com/dexpi/TrainingTestCases/-/raw/master/dexpi%201.2/example%20pids/C03%20DEXPI%20Example%20Tank%20Displ%20Pump%20Pipe%20with%20Tee/C03V01-SAG.EX01.pdf)。
- 仓库声明：[Creative Commons Attribution 4.0 International](https://gitlab.com/dexpi/TrainingTestCases/-/blob/master/LICENSE)。本包保留[许可证原文](samples/DEXPI-LICENSE.txt)。
- 归属：DEXPI 测试案例及图纸署名信息以原图、上游仓库为准。
- 修改：`c03-source.pdf` 保留原始文件；PNG 为 180 DPI 页面渲染，预览进一步缩小；蓝框图叠加了从原生文字层提取的位置；JSON 为文字层数据提取结果。
- 原图图框仍有模板版权文字，保留原貌；来源与授权记录使用上游公开仓库的许可声明。
- 文件字节数和 SHA-256 见[案例元数据](artifacts/case-metadata.json)。

文字层结果是标注辅助，不是人工校订真值，也不是 OCR 模型预测。

## 自制合并单元格表格

- 作者：本展示项目。
- 来源：`tools/prepare_examples.py` 中人工定义的表格内容与网格，仅使用自行制作的公开测试材料。
- 内容：英文工程检查表，6 行 × 5 列，包含跨行/跨列合并、`Ø、±、°`、设备编号与说明。
- 文件：原生 PDF、纯图像扫描 PDF、PNG 输入预览、人工结构真值。
- 许可：[CC0 1.0 Universal](https://creativecommons.org/publicdomain/zero/1.0/)。
- 真值由样本定义生成，不是结构识别模型的结果。

## PLOS 正文与层级条目样本（2026-10-26）

- 作品：Wilson G, Aruliah DA, Brown CT, Chue Hong NP, Davis M, Guy RT, et al. (2014). *Best Practices for Scientific Computing*. PLOS Biology 12(1): e1001745。DOI：`10.1371/journal.pbio.1001745`。
- 官方来源：[文章与版权声明](https://journals.plos.org/plosbiology/article?id=10.1371/journal.pbio.1001745) · [完整原始 PDF](https://journals.plos.org/plosbiology/article/file?id=10.1371/journal.pbio.1001745&type=printable)。下载日期为 2026-10-26。
- 许可：文章 Copyright 段直接链接到 [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/)，明确允许在保留作者与来源署名的条件下使用、分发和复制。原始 PDF 第 1 页也保留许可声明；另见 [PLOS 许可政策](https://journals.plos.org/plosbiology/s/licenses-and-copyright)。此处许可依据是文章本身，不是软件仓库许可证。
- 原始文件：[完整 7 页 PDF](samples/plos-best-practices-source.pdf)，183,769 字节，保持下载原貌。SHA-256：`8e85cf1b7bc9738f152e16709105b8951cecbe8621b55933d17ecdf63f75ea47`。
- 本次输入：[第 2 页 PNG](samples/plos-best-practices-page-2.png)，由 Poppler `pdftoppm 26.07.0` 以 200 DPI 整页渲染，1701 × 2197 像素、RGB、无透明通道，883,883 字节。未裁剪、修字、重排或替换页面内容。
- 内容与用途：公开论文正文、章节标题、强调文字及带层级编号的摘要框，用于检查文字识别、阅读顺序和导出结果。摘要框不是有行列定义的表格，不能据此声称表格结构识别通过。
- [原生文字参考](samples/plos-best-practices-page-2-reference.txt)由 `pypdf 6.10.0` 提取，仅供排查；它不是 OCR 输出，也不是独立人工校对的金标准，文字顺序、连字及断词可能与目视阅读不同。OCR 使用上述 PNG，避免原 PDF 的文字层被误作模型识别结果。
- 制备步骤没有调用 OCR 或生成 DOCX。样本可读不等于识别、翻译或 Word 交付通过；这些结论必须由后续运行结果单独支持。
- [来源与制备元数据](samples/plos-best-practices-source.json)记录署名、许可依据、页码、渲染参数、文件大小和 SHA-256。发布方 PDF 元数据及 PNG 元数据已检查，未添加本地用户名、文件系统路径、客户资料或密钥。

复现 PNG（从本展示仓库根目录执行，需要另行安装相同版本的 Poppler）：

```bash
pdftoppm -f 2 -l 2 -singlefile -r 200 -png samples/plos-best-practices-source.pdf generated/plos-best-practices-page-2
```

先创建输出目录 `generated/`；制备工具及其版本记录仅用于复现输入，不属于标准库快速开始的必需依赖。再分发原图、OCR 输出或 DOCX 派生产物时保留上述作者、标题、DOI、许可链接，并说明所做的修改。

## 公开文档与工具

展示说明和独立样本准备脚本采用 [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/)，署名使用本仓库及其维护者。各第三方依赖继续遵循自身许可；本包不包含完整系统源码。

对外展示或衍生使用时，保留第三方来源、许可链接及修改说明。

## 2026-10-08 真实项目图纸

新增评测来自 LIGO 机械图、Hanford 工程公开档案和 Johannesburg Water 政府招标图册，共 20 个不同图号。详细来源、页码与图号见[来源清单](artifacts/real-drawings-20261008/SOURCES.md)。

原图用于本地测试；本仓库只公开来源链接、文件哈希、派生评分和少量说明性错误示例，没有发布这批 PDF、整页图像、完整转写或标注裁剪。尚未确认第三方图纸的再分发许可，它们不适用上文的 CC BY 4.0 或自制样本 CC0 声明。

标注由助手目视核对并在推理前冻结，尚未完成独立人工复核。派生数据的统计复算不等于完整 OCR 推理复现。

## 2026-10-26 DOCX 导出修复产物

`artifacts/local-docx-fix-20261026/` 使用同样的 PLOS 输入及 CC0 自制表格重新运行，来源和许可沿用上文；不引入新样本。新 DOCX 和预览是项目修复导出器后产生的真实文件，原始输入、首次失败记录及 OCR 文字没有为展示而改写。[修复案例](cases/docx-export-fix-20261026.md)分别说明导出改善与仍存在的识别、版式限制。

## 2026-10-27 原页版式中文产物与字体

`artifacts/local-faithful-20261027/` 复用上述输入，重新 OCR、英译中并调用既有 `faithful` 导出器。PLOS 派生文件包括机器翻译、文字替换、字体及段落排版变化；文章署名与 CC BY 4.0 保持有效。表格结构真值仅在运行结束后评测使用，不参与预测或导出。旧单栏版本继续保留，详见[本轮案例](cases/faithful-translation-20261027.md)。

DOCX 内嵌 Noto 字体子集；推理与独立渲染使用同一批已准备的静态 TTF，未另创字体嵌入算法。上游为 [notofonts/noto-cjk](https://github.com/notofonts/noto-cjk/tree/985fa52c81c1d6692ccdd82bc3656e8fb932fd89)，固定提交 `985fa52c81c1d6692ccdd82bc3656e8fb932fd89`。保存的[字体来源与 SHA-256](artifacts/local-faithful-20261027/font-provenance.json)记录上游文件、静态实例及权重；[Sans OFL](artifacts/local-faithful-20261027/OFL-NotoSansCJK.txt)与[Serif OFL](artifacts/local-faithful-20261027/OFL-NotoSerifCJK.txt)随产物提供。完整字体文件和模型权重不单独纳入公开包。

## 2026-10-27 原生 Word 表格产物

`artifacts/native-table-20261027/` 继续使用同一自制 CC0 表格与已有中文内容，生成真正的 Word 单元格、边框及合并关系。原图中的数量 `2／1` 补录为文档文字，原始 OCR 记录保持空值；[逐格数据](artifacts/native-table-20261027/targets.json)与[执行记录](artifacts/native-table-20261027/execution.json)说明变化。这是助手对保存文档的格式与内容修订，不是模型新输出。输入沿用 CC0 1.0，嵌入字体沿用上述 Noto OFL；未引入新资料，旧产物不覆盖。

## 2026-10-27 表格状态补译产物

`artifacts/status-translation-20261027/` 是上述自制 CC0 表格的文档派生版本，补入四处中文状态并重新嵌入同源 Noto 字体、独立渲染。源图与原始模型结果不变，没有新增资料或模型推理。输入继续适用 CC0 1.0，字体继续适用前述 OFL；[逐项内容变化](artifacts/status-translation-20261027/merged-table/corrections.json)与[区域复核](artifacts/status-translation-20261027/semantic-coverage.json)记录助手对保存产物的修改，不作为模型输出。

## 2026-10-27 中文校对版

`artifacts/reviewed-translation-20261027/` 是上述机器输出的助手校对派生版本，不是重新推理的结果。修改包括中文术语、漏句、软件名／引用、从原图核对的符号与数量，以及表格 DOCX 页脚一处换行。PLOS 作者、文章与 CC BY 4.0 署名继续适用；自制表格沿用 CC0 1.0，内嵌字体沿用上述来源与 OFL。原始输入、OCR、模型响应、DOCX 及评分不覆盖。[逐项修改及验收范围](cases/reviewed-translation-20261027.md)
