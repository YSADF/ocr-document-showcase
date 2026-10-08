# 可独立运行的关键代码

公开裁剪后的算法与少量适配，不包含完整业务引擎。[来源说明与原模块哈希](../CODE_PROVENANCE.json)记录裁剪范围，哈希不能让未公开源码变成可复现源码。

| 文件 | 运行与边界 |
|---|---|
| [pdf_routing.py](pdf_routing.py) | 原生文字密度决定自动 DOCX 路由；真实 PDF 需 `pip install PyMuPDF`，不能判断文字层内容是否正确 |
| [copy_fit.py](copy_fit.py) | 有界搜索并输出 `fits`；可注入字体测量器，默认估算不能替代 Word 渲染 |
| [literal_guard.py](literal_guard.py) | 保护调用方已确认的片段，不包含生产场景的公式分类、区域检测 |

```python
from pathlib import Path
from examples.pdf_routing import should_auto_route_pdf_to_direct
from examples.copy_fit import _solve_copy_fit

print(should_auto_route_pdf_to_direct(Path("samples/merged-table-source.pdf")).to_dict())
print(_solve_copy_fit("DN 50", 100, 20, 12).to_dict())
```

```bash
python -m unittest discover -s tests -v
python examples/literal_guard.py
```

Copy-fit 对每个候选行数依次尝试字号、字距及横向比例，最小字号受限，放不下时明确失败。本片段不包含完整文字框生成逻辑，其单元测试不能排除本轮 Word 渲染问题。

## 工程图评分片段

[engineering_metrics.py](engineering_metrics.py) 选取字符编辑距离与聚合逻辑，保留原始 Unicode，并分别给出原文转写和复核折减后的成绩。它不含模型、坐标匹配或整页放行逻辑；普通模式的行级复核标记不覆盖原有页级质量检查。

```bash
python tools/score_real_drawings.py
```

该脚本复算 20 张真实图纸的公开派生评分，不能仅凭评分验证未公开的图像、标注和匹配是否正确。详见[测试报告](../cases/real-engineering-drawings.md)。
