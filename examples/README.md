# 8 个可独立检查的算法片段

[返回首页](../README.md) · [快速开始](../docs/GETTING_STARTED.md) · [代码来源](../CODE_PROVENANCE.json)

本目录从完整项目中选取小范围算法并做独立运行适配，不包含 OCR 服务端、模型加载、完整页面处理或部署系统。来源哈希用于追溯，不使未公开源码变成可复现源码。

| 文件 | 输入 → 输出 | 使用边界 |
|---|---|---|
| [pdf_routing.py](pdf_routing.py) | PDF 文字统计 → 转换路由与扫描页风险 | 检查真实 PDF 需 PyMuPDF；文字层存在不代表内容正确 |
| [copy_fit.py](copy_fit.py) | 文本、框尺寸和字号 → 有界布局候选及 `fits` | 默认估算不能替代真实字体和 Word 渲染 |
| [literal_guard.py](literal_guard.py) | 文本、调用方确认的片段 → 受保护文本与恢复校验 | 不包含工程符号分类，不能纠正上游 OCR 错字 |
| [engineering_metrics.py](engineering_metrics.py) | 参考文字、预测及复核状态 → 编辑距离与聚合分数 | 保留 Unicode；不含检测、坐标匹配和整页放行 |
| [engineering_tolerances.py](engineering_tolerances.py) | 文字片段、位置、方向及表格边界 → 公差关联候选 | 仅组合已观测片段，不推断缺失符号 |
| [vlm_evidence.py](vlm_evidence.py) | 首次识别与模型候选 → 可追溯证据 | 保留原文和疑点，不凭一致性放行 |
| [vlm_geometry.py](vlm_geometry.py) | 模型 JSON、图像尺寸 → 坐标与表格几何检查 | 拒绝无效结构；合法框仍需验证内容 |
| [vlm_fallback_policy.py](vlm_fallback_policy.py) | 风险、输出状态、模型身份 → 优先级和检查结论 | 不含推理、完整调度、自动写回 |

## 从根目录运行

```bash
python -X utf8 -m unittest discover -s tests -v
python -X utf8 examples/literal_guard.py
```

独立测试和字符保护演示仅使用标准库，不需要 GPU、模型或 API 密钥。Windows 使用 `-X utf8`，让 Python 以 UTF-8 处理文本流，避免输出工程字符时出现默认编码错误。

## PDF 路由和 Copy-fit

只有实际读取 PDF 的路由调用需要安装可选依赖：

```bash
python -X utf8 -m pip install -r requirements-pdf.txt
```

在仓库根目录运行 Python，或将下面代码保存为根目录的临时脚本：

```python
from pathlib import Path
from examples.pdf_routing import should_auto_route_pdf_to_direct
from examples.copy_fit import _solve_copy_fit

decision = should_auto_route_pdf_to_direct(Path("samples/merged-table-source.pdf"))
print(decision.to_dict())
print(_solve_copy_fit("DN 50", 100, 20, 12).to_dict())
```

Copy-fit 按候选行数搜索字号、字距与横向比例，受到最小字号等约束。返回 `fits=False` 时应保留失败信息，不能为提高通过率删除文字；`fits=True` 也不能排除完整 DOCX 的叠字或缺失。

## 工程字符、公差与 VLM

工程评分不把 `Ø` 与 `∅` 当成同一字符，待复核也不能算验收正确。公差函数保留片段及位置，不能根据“尺寸通常应该如此”补写符号。

VLM 三个片段分别展示证据保存、几何检查和局部调用策略。它们可以研究和测试，不会启动 VLM。模型自报置信度、多个候选一致、LaTeX 语法合法，都不能单独证明工程转写正确。

完整业务调度与独立示例的边界见[架构说明](../docs/ARCHITECTURE.md)。历史分数见[案例目录](../README.md#历史测量的范围)，当前文件的测试结果不能替代当时的模型推理或人工验收。

## 许可

本目录和独立测试采用 [MIT](../CODE_LICENSE.txt)。样本、文档和第三方材料分别遵循[展示许可](../LICENSE.md)及[来源清单](../CASE_SOURCES.md)，未公开业务源码不在授权范围内。
