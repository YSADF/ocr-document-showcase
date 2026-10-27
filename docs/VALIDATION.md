# 验证记录

## 2026-10-27：只校对译文与文档

按用户要求，校对保存的机器译文，不修改项目代码。PLOS 的 51 组及表格的 3 组页外文字／13 个格内译文已对照原文复核；另记录直接目视确认的符号、数量修正。没有重跑 OCR 或翻译模型，原始结果、历史分数全部冻结。详见[校对案例](../cases/reviewed-translation-20261027.md)及[逐项修改](../artifacts/reviewed-translation-20261027/corrections.json)。

| 本次实际检查 | 结果与边界 |
|---|---|
| 现有导出与独立渲染 | 禁网容器复用 `faithful` 与同批静态 Noto 字体；LibreOffice 7.4.7.2／Poppler 22.12.0／144 DPI，两份均一页；表格 DOCX 导出后仅增加一处页脚显式换行 |
| 最终文件严格审计 | 两份 `passed=true`，0 违规；审计中的 DOCX 哈希与交付文件一致 |
| 校对文字完整性 | PLOS 51 组、表格 16 组校对目标在 DOCX XML 与渲染 PDF 均可匹配；仅忽略空白，不以此证明翻译准确率 |
| 全页视觉复核 | 最终两张原尺寸 PNG 对照原图，双栏／蓝底／表格边界保留，未见叠字、裁切、溢出、缺失中文；表格两条页脚说明已分行。助手复核，不是独立人工认证 |
| 代码与历史文件 | 应用快照 460 个文件、公开 Python 27 个文件（含原 8 个算法）哈希未变；166 个原有样本、证据、示例及 Python 文件哈希未变 |
| 标准库测试 | Windows 执行 `python -S -X utf8 -B -m unittest discover -s tests -v`：78 通过、1 项符号链接权限跳过；本轮未重跑私有代码回归 |
| 原始证据核验 | `python -S -X utf8 -B tools/verify_demo.py`：顶层 35 项、旧 CPU 33、原文修复 36、历史翻译 55、原页版式 42 项均通过；此工具仍核验原始模型记录，不验证校对译文 |
| 公开清单 | `python -S -X utf8 -B tools/check_publication.py` 及导出检查通过，显式清单 213 个文件；仅增加校对产物和说明，公开代码范围不扩大 |
| Markdown 与预览 | 29 份 Markdown 相对链接、锚点、围栏无错误；本地桌面浅色／深色首页图片可加载、无横向溢出、快速开始锚点有效、Mermaid 正常；未验证 GitHub 托管页面或移动端 |
| 元数据与敏感信息 | 扫描 155 个公开文本文件、新 DOCX XML、PDF／PNG 元数据；无凭据或私网地址命中，4 个已有路径模式命中均为公开政府下载 URL 及其说明；DOCX 无外部关系，PDF／PNG 元数据无真实本机路径 |

以上结果只对应[校对版记录](../artifacts/reviewed-translation-20261027/run.json)。表格仍无原生 `w:tbl`，部分数字／状态保留为背景文字，局部字号与原文仍有差异；Microsoft Word 交互编辑未验收。下节为之前完整模型实测，不能把两轮操作或质量结论混为一谈。

## 2026-10-27：既有 faithful 路径的中文原页版式

两例以固定源码快照重新执行 `DocumentPipeline.process()` → 英译中 → `render_result()`，没有复用旧单栏结果冒充新运行。翻译与导出均显式 `faithful`、严格策略；既有静态字体在推理与独立 LibreOffice 环境一致。源码、输入、模型和字体只读，推理与渲染禁网，未读取本地 `.env`。

| 实际检查 | 最终结果及边界 |
|---|---|
| 完整新 OCR／英译中／DOCX | 两例完成，无运行时错误；同一 Argos 1.9 CPU int8；保存原始响应和源码／模型摘要 |
| 现有完整严格交付审计 | 两例均 `passed=true`、0 违规；字体嵌入、容量、源文字擦除、内容覆盖、真实渲染字形与碰撞检查通过 |
| 独立真实渲染 | LibreOffice 7.4.7.2 / Poppler 22.12.0 / 144 DPI；各 1 页；导出 DOCX 未做后处理 |
| 原尺寸逐页视觉复核 | 两个助手分别对照输入；PLOS 双栏／蓝底／标题／完整页脚、表格位置／底色／合并边界保留，未见叠字、裁切、溢出或源字残影；不是独立人工验收 |
| PLOS 来源覆盖 | 111/111 条来源记录；51 个原生定位文字区域，不将来源行数当作译文段落数或准确率 |
| 表格来源与结构 | 23 条来源中 16 条写入、7 条保留；21 物理格、5 合并；21/21 结构匹配，文字 14/21，字符编辑 14/203；真值仅后验评测 |
| 私有相关回归 | 隔离禁网容器 `python -m pytest -q -p no:cacheprovider ...`：336 项及另行保留的 11 项单栏重排回归，共 347 项通过；覆盖既有导出、DPI、旋转、多帧、重叠行、物理行数、颜色／线条、合并、混排页脚和禁止静默回退；不是全部项目测试 |
| 公开标准库测试 | `python -S -X utf8 -B -m unittest discover -s tests -v`：禁网 Linux 79/79；Windows 78 通过、1 项符号链接权限跳过 |
| 离线证据核验 | `verify_demo.py` 顶层 35 项；`local_faithful` 42 项；旧 CPU 33、原文修复 36、历史翻译 55 项均通过；不执行模型或渲染 |

新增回归还确认：缺失 DPI 时 semantic_layout 继续沿用 200、faithful 沿用 300；真实 X/Y DPI 才写入物理尺寸。EXIF 旋转与多帧解码均测试，但 strict 多帧导出仍明确拒绝；非等轴 DPI 的完整物理尺寸消费只验证 faithful。没有把所有渲染模式默认为 200，也没有放宽严格审计以获得通过结果。

开发中的日期裁切和右栏异常小字曾被实际 PNG／审计发现；修正后使用新快照完整重跑。保存的 [运行记录](../artifacts/local-faithful-20261027/run.json)及[视觉审查](../artifacts/local-faithful-20261027/visual-review.json)只对应最终文件；失败诊断保留本地。旧三页单栏、首次 CPU 失败及更早 GPU 产物不覆盖。

本轮 `passed_for_page_layout` 只确认两个单页的限定版式表现。机器误译、遗漏、工程字符错误、字体与局部字号差异仍在；表格是原背景加定位文字，不是原生 `w:tbl`。数量 `2`／`1` 漏识别，部分状态词和数字保留栅格；不宣称完整汉化、全表可编辑或 Microsoft Word 交互编辑通过。详见[完整案例](../cases/faithful-translation-20261027.md)。

本地桌面首页浅色／深色预览中，两张图片正常加载，无横向溢出，快速开始锚点可跳转，Mermaid 成功渲染；这是本地 Markdown 预览，不是 GitHub 托管页或移动端验收。28 份 Markdown 的相对链接、锚点和围栏检查无错误；显式发布清单为 197 个文件，原 8 个算法及 122 份已冻结输入／证据／示例摘要未变。敏感信息和二进制元数据检查范围见[审阅记录](../SANITIZATION.md#2026-10-27-faithful-chinese-layout-evidence)。

## 2026-10-26：英译中与中文导出重跑

两例分别在相同 Argos 模型下执行旧布局基线及修复后完整流程：`DocumentPipeline.process()` → `TranslationPipeline.translate_document(..., en, zh)` → `render_result(..., docx)`。模型通过项目已有 HTTP 翻译后端调用，推理、翻译与导出均在禁网容器内；依赖和模型的下载准备阶段联网。

| 实际检查 | 结果与边界 |
|---|---|
| OCR、英译中、中文 DOCX | 两例完成，运行时错误列表为空；Argos `translate-en_zh` 1.9、CTranslate2 4.5.0 int8，实际请求响应另存 |
| 同模型修复前后对照 | OCR 文字／几何、译后文字／几何、模型请求和响应均一致；不比较含时间元数据的完整 JSON 哈希 |
| 独立 DOCX 渲染 | LibreOffice 7.4.7.2、Poppler 22.12.0、144 DPI；PLOS 3 页、表格 1 页，原始 DOCX 未做导出后修改 |
| 全部四页视觉检查 | 两个助手分别查看原尺寸 PNG，未见叠字、裁切、页外溢出或表格缺失；不是独立人工校对 |
| 字面保留检查 | DOCX 和 PDF 均找到 PLOS 111/111 显示行、表格 4/4 非表格行及 19/19 非空预测格；只去空白，不证明翻译正确 |
| 几何和结构 | PDF 可测文字框均在页面内；DOCX 表格 6×5，PLOS 图内 8 行转为原生文字，两例无嵌入图片 |
| 私有相关回归 | 禁网最终镜像内 `python -m pytest -p no:cacheprovider ... -q`：88 项通过，包含 11 项译文重排测试；不是全项目测试通过 |
| 公开包标准库测试 | `python -S -X utf8 -B -m unittest discover -s tests -v`：禁网 Linux 72/72；Windows 71 通过、1 项符号链接权限跳过 |
| 离线证据核验 | `verify_demo.py` 顶层 34 项；旧 CPU 33 项、原文 DOCX 修复 36 项、英译中 55 项分别通过；核验不执行模型或渲染 |
| 发布与文档检查 | 显式清单 174 个文件；27 份 Markdown 的相对链接及锚点无错误；原 8 个算法及此前证据哈希未变 |
| 桌面本地预览 | 首页浅色／深色、案例四张图片及 Mermaid 图正常；不是 GitHub 托管页或移动端检查 |

译文空间不足时，本轮改为 10.5 pt 单栏原生段落与自然分页；表格保留预测的原生结构。**`passed_for_translation_export_targets` 仅表示上述显示修复通过，翻译质量仍为 `needs_review_known_mistranslations`。** `Qty → 齐哥`、`ground truth → 地面真相`、术语误译及部分说明遗漏均原样保留。原双栏、蓝底、原页数和正确合并结构没有因此恢复，Microsoft Word 交互编辑未验收。

当前 PyMuPDF 对这些中文 PDF 的 `get_text("dict")` 返回空块，审计显式退回非空的 word boxes 后检查边界；不会用空检测结果宣称没有越界。字号依据 DOCX XML，逐页 PNG 是视觉检查依据。详情见[完整案例](../cases/english-to-chinese-20261026.md)、[运行记录](../artifacts/local-translation-20261026/run.json)和[视觉记录](../artifacts/local-translation-20261026/visual-review.json)。

新增公开文件与 DOCX/PDF/PNG 元数据检查未发现密钥、私网地址或需要移除的宿主机路径。DOCX 作者为通用 `python-docx`，外部关系为空；PNG 仅 DPI 元数据。公开执行记录仅去掉私有工作区路径清单，原始记录留在本地。完整模型、HTTP 适配器、运行脚本和业务修复继续排除在发布范围之外。

## 2026-10-26：DOCX 导出修复后重新运行

本轮修复完整项目的 `semantic_layout` 导出器，以同样的输入、OCR 模型和参数重新调用 `DocumentPipeline.process()`，再调用 `render_result()`。新结果另存，首次 CPU 失败记录及更早历史证据保持原样。

| 实际检查 | 结果与范围 |
|---|---|
| 两例新推理、DOCX 导出及独立渲染 | 禁网 CPU 容器完成；无运行时错误；LibreOffice 7.4.7.2、144 DPI，各 1 页 |
| PLOS 逐页视觉检查 | 正文不再重叠；上方 2 条及下方 6 条图像覆盖文字均可见；通过本轮叠字／遮字修复目标 |
| 表格逐页视觉检查 | 6×5 原生网格和预测内容可见；副标题及两条页脚没有重叠；通过本轮缺失修复目标 |
| DOCX 与渲染 PDF 文字核查 | PLOS 103/103 条块内行；表格 23/23 条行、19/19 个非空预测单元格；均无页外文字区域 |
| OCR 前后对照 | 明确的文字及几何字段投影相同；排除时间、置信度和审计元数据；不把 JSON 哈希不同解释为识别变化 |
| 私有完整项目回归 | `python -m pytest -p no:cacheprovider ... -q`：77 项通过，含新增源行拟合、文本框定义、背景层级和浮动表格尾段回归 |
| 公开包标准库测试 | `python -S -X utf8 -B -m unittest discover -s tests -v`：Windows 57 通过、1 项符号链接权限跳过；禁网 Linux 58/58 通过 |
| `tools/verify_demo.py` | 33 项顶层检查通过；旧 `local_run` 33 项、新 `local_docx_fix` 36 项分别通过，旧失败状态不变 |
| `tools/verify_local.py --record artifacts/local-docx-fix-20261026/run.json` | 36 项通过；校验保存的证据，不进行推理或渲染 |
| 显式发布清单与文档 | 134 个审核文件通过清单检查；26 份 Markdown 的相对链接和锚点无缺失；8 个算法和原始失败产物的哈希未变 |
| 本地首页预览 | 桌面浅色／深色检查，两例真实图片正常加载，Mermaid 已渲染；不是 GitHub 托管页或移动端验收 |

私有回归覆盖 `test_semantic_source_line_fit.py`、`test_semantic_layout_floating_table_anchor.py`、`test_docx_locked_geometry.py`、`test_docx_shaped_layout.py`、`test_table_rendering.py`、`test_docx_mode_routing.py`、`test_semantic_layout_word.py`、`test_semantic_word.py`、`test_pipeline_architecture.py`。这些私有测试和业务渲染器均未加入公开包。测试依赖单独准备，运行时工作目录隔离；没有把当前项目的全部测试说成通过。

开发过程中保留过尚未通过的中间渲染：第一版仍有换行，后一次背景清理暴露出首个图像遮挡文字的问题。最终运行在修复文本框类型、背景层级后重新执行，不将中间产物当作最终通过证据。最终原始 DOCX 没有再做手工 OOXML 修改；公开预览来自该 DOCX 的独立只读渲染。

视觉检查由两个助手分别对照原输入查看全部页面，不是独立人工验收。结论为 `passed_for_export_targets`：只覆盖本轮重叠和缺失问题。PLOS 仍有最小约 5 pt 的小字、字号／间距差异和局部蓝底；表格的文字 13/21、位置及跨度 16/21、5 个合并关系漏检均未改善。Microsoft Word 编辑、完整原版还原、翻译、可搜索 PDF 和总体准确率均不在本轮通过范围内。

[修复案例与实际调用](../cases/docx-export-fix-20261026.md) · [新运行记录](../artifacts/local-docx-fix-20261026/run.json) · [PLOS 内容核查](../artifacts/local-docx-fix-20261026/plos/render-audit.json) · [表格内容核查](../artifacts/local-docx-fix-20261026/merged-table/render-audit.json)

## 2026-10-26：新增公开资料的本地实测

本轮新增 PLOS 正文页与自制合并表格的实际 CPU 推理、DOCX 导出和页面渲染。日期使用 Asia/Shanghai；与下方 2026-10-15 整理检查及更早的 GPU 实验分别记录。

| 实际检查 | 结果与范围 |
|---|---|
| 构建 `onnx-only`，模型 profile 为 `ch,en` | 成功；项目依赖安装后 `pip check` 无冲突，四个准备模型通过锁定摘要检查 |
| 两例完整项目推理与 DOCX 导出 | 成功生成文件，`runtime_errors=[]`；使用 `--network none --cpus=4 --memory=8g`，没有运行翻译或 VLM |
| 新表格评分 | 文字 13/21、位置及跨度 16/21；24/203 个字符编辑；预测 30 格；5 个合并关系全部漏检 |
| DOCX 实际渲染与逐页检查 | 两份各 1 页，均视觉失败：PLOS 正文大量叠行；表格主体未显示、页脚重叠 |
| `python -S -X utf8 -B tools/verify_local.py` | 33 项核验通过；从保存的流水线 JSON 重新计算新表格分数，不执行新推理或渲染 |
| `python -S -X utf8 -B tools/verify_demo.py` | 32 项顶层检查通过；新记录的 33 项子检查独立保存在 `local_run`，历史分数保持不变 |
| `python -S -X utf8 -B -m unittest discover -s tests -v` | 54 项：53 通过，1 项因 Windows 缺少创建符号链接权限跳过 |
| 同一测试集在本地 Linux 容器执行 | Python 3.11.16、只读挂载公开包、禁网；54/54 通过，包含符号链接拒绝测试 |
| 历史派生评分工具 | `score_real_drawings.py`、`score_round2.py`、`score_round3.py` 均执行；不重新推理、不扩大历史验收范围 |
| 本地 README 预览 | 浅色与深色截图检查完成，图片正常加载、无页面横向溢出；快速开始锚点可跳转，Mermaid 成功渲染 |

标准库检查使用 Windows 上的 Python 3.12.14；模型推理使用 Docker 内 Python 3.11.16、RapidOCR 3.0.0、ONNX Runtime 1.19.2。实际模型是 PP-OCRv3 多语检测和 PP-OCRv4 英文识别，不能将旧 PP-OCRv6 GPU 成绩套用到本次 CPU 路径。

宿主没有 LibreOffice，首次直接运行 `render_docx.py` 因缺少 `soffice.exe` 失败。随后在独立本地镜像中安装 LibreOffice 7.4.7.2、Poppler 22.12.0、pdf2image 1.17.0，以原样 `render_docx.py` 和 144 DPI 完成两份渲染；没有修改原始 DOCX 来美化结果。

详细输入、输出、环境、实际命令和取舍见[本次案例](../cases/local-cpu-20261026.md)及[运行记录](../artifacts/local-20261026/run.json)。保存的 `execution.json` 截止于推理和导出阶段，单独的渲染及视觉结论记录在 `run.json`。

新输入、JSON、DOCX、渲染 PDF/PNG 均纳入显式发布清单；8 个业务算法的内容摘要与此前相同。未运行 Microsoft Word、翻译、VLM 或可搜索 PDF 验收，未发布远端 CI 状态或新的性能基准。

Markdown 视觉检查使用本地 `markdown-it 15.0.3` 与 `mermaid 12.2.0` 预览，覆盖桌面浅色／深色、图片和快速开始导航；相对文件链接、中文锚点与代码围栏另作静态检查。这不是 GitHub 托管页面的实际渲染，也不代表已验证移动端或远端 CI。

## 2026-10-15：历史整理检查

日期：**2026-10-15（Asia/Shanghai）**。本记录描述公开包的整理检查，与 2026-10-07 / 08 / 09 的模型实测分开。

### 已实际运行

本地环境为 Windows、Python 3.12.14。核心检查加 `-S` 关闭第三方 site-packages，证明标准库入口不依赖完整业务项目或 OCR 模型。

| 检查 | 结果 | 说明 |
|---|---|---|
| `python -S -X utf8 -B -m unittest discover -s tests -v` | 40 项通过 | 包括 20 项既有算法测试，以及发布边界、导出期间变更、只读核验、输入篡改、重复单元格和冻结文件保护 |
| `python -S -X utf8 -B tools/verify_demo.py` | 31 项核验通过 | 表格 19/21、字符错误 2/203、位置与跨度 21/21；保留历史 DOCX 视觉失败 |
| 三组历史派生评分复算 | 通过 | `score_real_drawings.py`、`score_round2.py`、`score_round3.py`；不重新推理、不验证未公开图纸标签 |
| 字符保护独立示例 | 通过 | 原样保留 `Ø`、`±`；Windows UTF-8 输出正常 |
| 真实 PDF 路由 | 通过 | 原生表格 350 个非空白字符，选择 `direct`；扫描表格 0 个文字层字符，选择 `ocr` |
| 输入再生成 | 通过 | 输出独立写入 `generated/demo`，明确 `ocr_executed=false`；不覆盖历史输入 |
| 可选服务客户端参数帮助 | 通过 | 支持 `--runs`、`--warmup` 和新的独立输出目录 |

可选 PDF 路由使用 PyMuPDF 1.25.3。输入生成使用 `requirements-demo.txt` 中的版本；生成环境与冻结历史输入的环境并非完全相同，再生成不承诺逐字节一致。

### 素材与发布检查

- 两个实际 OCR 输入与历史 benchmark 的 SHA-256 一致。扫描表格采用原件，修复后续发布副本与实测输入不一致的问题；没有改动历史分数。
- 人工查看了公开表格输入和既有 Word 渲染预览，确认文字缺失、重叠及边框问题与历史失败描述一致。
- 精选算法共 8 个文件，来源说明区分历史原模块摘要和实际公开片段摘要。
- 发布检查核对显式清单、文件哈希、相对链接、来源摘要和敏感模式；未知文件不自动纳入。
- `generated/`、缓存及虚拟环境不参与发布。清单和导出检查的实际结果以运行 `tools/check_publication.py` 的输出为准。

### 尚未验证的范围

本次没有重新执行 GPU OCR/VLM、翻译、远程服务调用或 Word/LibreOffice 渲染。历史预览仍是历史结果。GitHub 的 Linux/Windows、Python 3.11/3.12 CI 已配置，远端运行状态需推送后查看；不能将本地 Windows 检查当作全平台验证。

公开包不包含完整 OCR 服务，因此没有“从这个仓库启动全部业务系统”的验收结果。许可和敏感信息检查范围见 [审阅记录](../SANITIZATION.md)，发布步骤见 [PUBLISHING.md](PUBLISHING.md)。
