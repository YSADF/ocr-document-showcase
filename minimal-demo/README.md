# 最小 OCR＋VLM 协同推理

这是独立的文本行识别示例，复用业务项目的区域路由、候选采用与评分代码。
它不包含完整业务服务、表格恢复或工程分块；其成绩不能代替业务流水线成绩。

## 运行

Python 3.11；回放和评分无需 GPU。实时推理要求 GPU、已验证的 PaddleOCR/Paddle GPU 环境、
本地 PP-OCRv6 权重，以及隔离的 GLM/MinerU worker 环境。当前导出包本身不代表 GPU 验证已完成。
安装 requirements.txt 后按实际路径修改 config.example.json。模型版本沿用项目锁定的配置，
不要把示例路径当成已安装环境。权重不随源码分发。

```bash
python scripts/engineering_demo.py infer --image sample.png --config config.json --output run-001 --mode evidence
python scripts/engineering_demo.py replay --result run-001/result.json --output run-001/replay.html
python scripts/engineering_demo.py score --manifest labels.json --baselines baselines --results results --output score.json
```

评分目录按清单 sample ID 存为 `<id>.json`。baseline 为 baseline.json 的内容，result 为 result.json 的内容。
推理不接受答案文件。回放只展示已保存结果，不执行模型。默认只保留候选；conditional 需显式选择，仍标记待核查。
SOURCE_MANIFEST.json 列出与业务实现逐字节一致的源码摘要。
