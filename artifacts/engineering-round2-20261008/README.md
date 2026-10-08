# 第二轮开发／回归实测

[完整报告](../../cases/mechanical-ocr-round2.md)。140 次有效正式请求、12 次有效预热，沿用 20 页 / 238 区域；另有 20 次误标 128 的实际 64 请求及 4 次预热，已排除消融对照。未把重复页当作新增图纸。

- `summary.json`：按模式／机械或 P&ID 分类的原文、候选、区域复核、跨页耗时及预算统计；发布门槛仍为试验状态。
- `region-scores.jsonl`：每行一个请求，`rows` 数组顺序由 `summary.json.region_fields` 定义，不包含原图或整页转写。
- `case-runs.json`：逐次耗时与整卡采样显存，重复页和跨页分别命名。
- `crop-summary.json`：236 次局部诊断的派生计数，不能作为独立图纸成绩。
- `audit.json`：数据／代码／证据哈希、模型环境及测试范围。

运行 `python tools/score_round2.py` 可复算聚合；这些派生记录不能独立证明未公开的原始匹配与人工标注正确。来源沿用[第一轮索引](../real-drawings-20261008/SOURCES.md)，公开可下载不代表允许再分发。
