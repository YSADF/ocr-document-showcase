# 样本来源与许可

[返回首页](README.md)

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

## 公开文档与工具

展示说明和独立样本准备脚本采用 [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/)，署名使用本仓库及其维护者。各第三方依赖继续遵循自身许可；本包不包含完整系统源码。

对外展示或衍生使用时，保留第三方来源、许可链接及修改说明。
