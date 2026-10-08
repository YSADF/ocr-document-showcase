"""Recompute published derived scores, not OCR inference or label validation.

Run from any directory: python tools/score_real_drawings.py
Only the standard library and the selected scoring excerpt are required.
"""
import json
import math
from pathlib import Path
import statistics
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from examples.engineering_metrics import aggregate


def require(condition, message):
    if not condition:
        raise ValueError(message)


def score(root=ROOT):
    data = root / "artifacts/real-drawings-20261008"
    rows = [json.loads(line) for line in (data / "region-scores.jsonl").read_text(encoding="utf-8").splitlines()]
    cases = json.loads((data / "case-runs.json").read_text(encoding="utf-8"))
    sources = json.loads((data / "source-metadata.json").read_text(encoding="utf-8"))
    expected = json.loads((data / "summary.json").read_text(encoding="utf-8"))
    source_map = {s["id"]: s for s in sources}
    require(len(source_map) == len(sources) == 20, "Expected 20 distinct source pages")
    require(sum(s["selected_regions"] for s in sources) == 238, "Selected region count mismatch")
    require(len(rows) == 476 and len(cases) == 40, "Expected 238 regions and 20 requests per scene")
    require(len({(r["scene"], r["sample_id"], r["id"]) for r in rows}) == len(rows), "Duplicate region score")
    require(len({(c["scene"], c["sample_id"]) for c in cases}) == len(cases), "Duplicate request")

    result = {}
    for scene in ("general", "engineering"):
        scene_cases = [c for c in cases if c["scene"] == scene]
        require({c["sample_id"] for c in scene_cases} == set(source_map), "Source/request mismatch")
        for case in scene_cases:
            source = source_map[case["sample_id"]]
            case_rows = [r for r in rows if r["scene"] == scene and r["sample_id"] == case["sample_id"]]
            require(len(case_rows) == source["selected_regions"], "Per-page region count mismatch")
            require(case["input_sha256"] == source["image_sha256"], "Input hash mismatch")
            require(case["kind"] == source["kind"] and all(r["kind"] == source["kind"] for r in case_rows),
                    "Drawing category mismatch")
        groups, timing = {}, {}
        for kind in ("mechanical", "pid"):
            selected = [r for r in rows if r["scene"] == scene and r["kind"] == kind]
            group_key = f"{kind}/real/test"
            groups[group_key] = aggregate(selected)
            require(groups[group_key] == expected["scenes"][scene]["groups"][group_key], "Metric mismatch")
            runs = [c for c in scene_cases if c["kind"] == kind]
            durations = sorted(c["seconds"] for c in runs)
            require(len(durations) == 10 and all(math.isfinite(x) and x > 0 for x in durations),
                    "Invalid timing samples")
            timing[kind] = {
                "p50_seconds": statistics.median(durations),
                "p95_seconds": durations[math.ceil(.95 * len(durations)) - 1],
                "device_memory_max_mib": max(c["gpu_memory"]["max_device_used_mib"] for c in runs),
                "exact": sum(r["exact"] for r in selected),
                "missed": sum(not r["found"] for r in selected),
                "review_regions": sum(r["needs_review"] for r in selected),
            }
            require(timing[kind] == expected["scenes"][scene]["timing_by_kind"][kind], "Timing/count mismatch")
        page_review = sum(c["page_needs_review"] for c in scene_cases)
        require(page_review == expected["scenes"][scene]["page_needs_review_count"], "Page review mismatch")
        result[scene] = {"groups": groups, "timing_by_kind": timing, "page_needs_review_count": page_review}
    return {"verification": "Published aggregate metrics match derived records",
            "scope": "Does not verify private source images, annotations, geometry matching or OCR inference",
            "scenes": result}


if __name__ == "__main__":
    print(json.dumps(score(), ensure_ascii=False, indent=2))
