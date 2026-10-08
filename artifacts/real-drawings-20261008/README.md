# 真实图纸派生评分（2026-10-08）

20 张真实项目图纸、238 个选定区域、两种模式各一次整页推理。标注由助手目视核对并在推理前冻结，尚待独立人工复核。

| 文件 | 内容 |
|---|---|
| [SOURCES.md](SOURCES.md) | 官方来源链接、图号、页码；未打包第三方图纸 |
| [source-metadata.json](source-metadata.json) | 20 个输入的来源/图像哈希、尺寸和区域数量 |
| [case-runs.json](case-runs.json) | 40 次请求的耗时、整卡采样显存、页级复核状态与原始响应哈希 |
| [region-scores.jsonl](region-scores.jsonl) | 476 条派生记录：238 区域 × 2 模式；只含标识及评分，不含完整原文或预测 |
| [summary.json](summary.json) | 四组成绩、环境、审计数量、事后诊断和证据包哈希 |

每条区域记录中，`exact` 是转写完全匹配，`found` 是类型及位置匹配成功，`edits` 是字符编辑距离，`critical_errors` 是关键符号子序列编辑距离。`needs_review` 保留工程评测器的区域复核口径；普通模式另有页级质量检查，行级标记为假不能表示页面可交付。未命中项以空预测计错，但不会被算作已找到的待复核区域。

```bash
python tools/score_real_drawings.py
```

复算脚本检查主指标、计数和时间汇总。`summary.json` 中取消表格类型限制的诊断、直径错误分类和审计原因来自本地原始响应核查，不由这个精简脚本重新推导。输入与响应哈希用于标识本地证据；**公开派生评分不足以独立验证标注和模型推理**。原始 PDF、图像、完整标注、完整响应和服务源码未包含在本次发布中。

[完整方法与失败分析](../../cases/real-engineering-drawings.md)
