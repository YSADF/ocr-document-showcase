# 第三轮派生证据

20 页开发／回归材料，参考尚无独立人工验收。这里不公开第三方原图、完整 OCR 转写、模型权重或业务服务。

- [summary.json](summary.json)：局部、整页、反例、公差组合、配对增减和失败清单。
- [region-scores.jsonl](region-scores.jsonl)：数值逐区域评分；每条记录自带字段名。
- [case-runs.json](case-runs.json)：100 次同机 OCR 与 794 次正式 VLM 任务的状态、耗时、整卡显存采样。
- [input-transforms.jsonl](input-transforms.jsonl)：原尺寸、实际传入尺寸、内部图像网格和截断检查。
- [audit.json](audit.json)：模型／输入摘要、配置、清单去重映射及证据归档摘要。

```bash
python tools/score_round3.py
```

此命令验证公开派生计数、CER 和目标单元格命中，不执行推理，也不能独立证明私有原图的标注与匹配正确。[完整方法和限制](../../cases/engineering-vlm-round3.md)。
