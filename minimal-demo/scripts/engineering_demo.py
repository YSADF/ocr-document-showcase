"""Portable line-OCR + regional VLM demo; no business service or reference input."""
import argparse
import hashlib
import html
import json
from pathlib import Path
import sys
import time
import importlib.metadata
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def read(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def save(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")


def render_result(value, output):
    response = value.get("response", value)
    rows = []
    for page in response.get("pages", []):
        report = page.get("engineering_review") or page.get("metadata", {}).get("engineering_review", {})
        for row in report.get("vlm_fallback", {}).get("regions", []):
            values = [row.get("rank"), row.get("source_text"), row.get("candidate_text"),
                      row.get("selected_text"), row.get("status"), row.get("elapsed_seconds")]
            rows.append("<tr>"+"".join("<td>"+html.escape(str(v if v is not None else "—"))+"</td>" for v in values)+"</tr>")
    image = ""
    if (output.parent/"input.png").exists():
        image = '<img src="input.png" alt="实际输入页面" style="max-width:100%;max-height:650px">'
    output.write_text('<!doctype html><html lang="zh-CN"><meta charset="utf-8"><title>OCR 与 VLM 对照</title>'
        '<style>body{font:16px system-ui;max-width:1100px;margin:36px auto;padding:20px;color:#173149}table{border-collapse:collapse;width:100%}td,th{padding:10px;border:1px solid #cbd6df}pre{white-space:pre-wrap}</style>'
        '<h1>OCR＋局部 VLM 结果对照</h1><p>原文、候选与机器选中值分别显示；机器选择仍待人工核查。</p>'
        +image+'<table><tr><th>排名</th><th>首次 OCR</th><th>候选</th><th>选中值</th><th>状态</th><th>追加秒数</th></tr>'
        +''.join(rows)+'</table><details><summary>完整运行记录</summary><pre>'
        +html.escape(json.dumps(value,ensure_ascii=False,indent=2))+'</pre></details></html>',encoding="utf-8")


def infer(args):
    import cv2
    import paddle
    from paddleocr import PaddleOCR
    from models import BlockType, DocumentResult, LayoutBlock, PageResult, TextLine
    from ocr_engine.vlm_region_runner import RegionVLMRunner
    from pipeline.engineering_review import review_engineering_page
    from pipeline.engineering_vlm_fallback import apply_engineering_vlm_fallback, EngineeringVLMConfig
    from services.document_results import serialize_page_results
    cfg = read(args.config)
    if not paddle.is_compiled_with_cuda() or paddle.device.cuda.device_count() < 1:
        raise RuntimeError("This measured demo requires a working GPU; no implicit CPU fallback")
    image = cv2.imread(str(args.image))
    if image is None:
        raise ValueError("Input must be a readable raster page")
    args.output.mkdir(parents=True, exist_ok=False)
    cv2.imwrite(str(args.output/"input.png"), image)
    total_started = time.perf_counter()
    pp = cfg["ppocr"]
    identities = {}
    for key in ("text_detection_model_dir", "text_recognition_model_dir"):
        directory = Path(pp[key])
        weights = [p for p in sorted(directory.rglob("*")) if p.suffix in {".pdiparams", ".pdparams", ".json", ".yml"} and p.is_file()]
        if not weights:
            raise ValueError("Missing local OCR weights: " + key)
        identities[key] = {str(p.relative_to(directory)): sha(p) for p in weights}
    started = time.perf_counter()
    engine = PaddleOCR(**pp, use_doc_orientation_classify=False, use_doc_unwarping=False,
                       use_textline_orientation=False)
    load_seconds = time.perf_counter()-started
    started = time.perf_counter()
    list(engine.predict(input=image))
    warmup_seconds = time.perf_counter()-started
    started = time.perf_counter()
    outputs = list(engine.predict(input=image))
    pp_seconds = time.perf_counter()-started
    if len(outputs) != 1:
        raise ValueError("Expected one OCR page")
    result = outputs[0].json
    if isinstance(result, str):
        result = json.loads(result)
    result = result.get("res", result)
    texts, scores, polygons = result["rec_texts"], result["rec_scores"], result["rec_polys"]
    if not len(texts) == len(scores) == len(polygons):
        raise ValueError("Paddle output arrays differ in length")
    lines = []
    for text, score, polygon in zip(texts, scores, polygons):
        points = [[float(x), float(y)] for x, y in polygon]
        box = (min(p[0] for p in points), min(p[1] for p in points), max(p[0] for p in points), max(p[1] for p in points))
        lines.append(TextLine(text=text, source_text=text, confidence=float(score), bbox=box, source_quad=points))
    height, width = image.shape[:2]
    page = PageResult(1, width, height, blocks=[LayoutBlock(BlockType.TEXT, (0, 0, width, height), text_lines=lines)])
    review_engineering_page(image, page, settings=SimpleNamespace(), reader=None)
    document = DocumentResult(source_path=args.image, pages=[page])
    baseline = {"ocr_scene": "engineering", "pages": serialize_page_results(document)}
    save(args.output/"baseline.json", baseline)
    selection = cfg.get("selection", {})
    EngineeringVLMConfig.from_value(selection)
    runner = RegionVLMRunner(cfg.get("runners", {}), log_dir=args.output/"logs", cache_size=0) if args.mode != "off" else None
    try:
        summary = apply_engineering_vlm_fallback(page, image, mode=args.mode, runner=runner, config=selection)
    finally:
        if runner is not None:
            runner.close()
    record = {"scope": "minimal line OCR pipeline; no business table recovery or full-page acceptance claim",
              "input_sha256": sha(args.image), "configuration_sha256": sha(args.config),
              "configuration": cfg, "runtime_packages": {},
              "ppocr_weights": identities, "pp_load_seconds": load_seconds, "pp_inference_seconds": pp_seconds,
              "pp_warmup_seconds": warmup_seconds, "pp_warmup_runs": 1,
              "pp_inference_executed": True, "reference_read_during_inference": False,
              "summary": summary, "response": {"ocr_scene": "engineering", "pages": serialize_page_results(document)}}
    record["total_seconds"] = time.perf_counter()-total_started
    for package in ("paddleocr", "paddlepaddle-gpu", "paddlex", "numpy", "opencv-python-headless"):
        try:
            record["runtime_packages"][package] = importlib.metadata.version(package)
        except importlib.metadata.PackageNotFoundError:
            record["runtime_packages"][package] = None
    root = Path(__file__).resolve().parents[1]
    record["code_hashes"] = {str(path.relative_to(root)).replace("\\", "/"): sha(path) for path in
        (Path(__file__), root/"pipeline/engineering_vlm_fallback.py", root/"ocr_engine/vlm_region_runner.py")}
    try:
        record["pp_gpu_peak_allocated_bytes"] = paddle.device.cuda.max_memory_allocated()
        record["pp_gpu_peak_reserved_bytes"] = paddle.device.cuda.max_memory_reserved()
    except (AttributeError, RuntimeError):
        record["pp_gpu_peak_allocated_bytes"] = None
    record["gpu_memory_scope"] = "Paddle process only; regional worker device memory requires experiment sampler"
    save(args.output/"result.json", record)
    render_result(record, args.output/"preview.html")


def replay(args):
    render_result(read(args.result), args.output)


def score(args):
    from evaluation.engineering_fallback import paired_sample
    from evaluation.engineering_collaboration import summarize_experiment
    manifest = read(args.manifest)
    scores, records = [], {}
    for sample in manifest["samples"]:
        baseline = read(args.baselines/(sample["id"]+".json"))
        path = args.results/(sample["id"]+".json")
        record = read(path) if path.exists() else {"response": {"pages": []}}
        measured = paired_sample(sample, baseline, record.get("response", record))
        scores.append({**measured, "result_present": path.exists()})
        if path.exists():
            records[sample["id"]] = record
    report = summarize_experiment(scores, manifest["samples"], profile=args.profile, records=records)
    report["scores"] = scores
    save(args.output, report)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    p = sub.add_parser("infer")
    for name in ("image", "config", "output"):
        p.add_argument("--"+name, type=Path, required=True)
    p.add_argument("--mode", choices=("off", "evidence", "conditional"), default="evidence")
    p.set_defaults(run=infer)
    p = sub.add_parser("replay")
    p.add_argument("--result", type=Path, required=True)
    p.add_argument("--output", type=Path, required=True)
    p.set_defaults(run=replay)
    p = sub.add_parser("score")
    for name in ("manifest", "baselines", "results", "output"):
        p.add_argument("--"+name, type=Path, required=True)
    p.add_argument("--profile", choices=("development", "holdout"), default="development")
    p.set_defaults(run=score)
    args = parser.parse_args()
    args.run(args)


if __name__ == "__main__":
    main()
