"""Unicode-exact engineering evaluation; review is not recognition credit."""
from collections import Counter
import math
import re


CRITICAL = set("Ø⌀∅Φφ±°×÷≤≥μµ²³′″−+-.")


def normalize(text):
    return " ".join(str(text or "").split())


def edit_counts(reference, prediction):
    """Return edit distance and errors at critical reference characters."""
    rows = [[(0, 0)] * (len(prediction)+1) for _ in range(len(reference)+1)]
    for i, char in enumerate(reference, 1):
        rows[i][0] = (i, rows[i-1][0][1] + int(char in CRITICAL))
    for j in range(1, len(prediction)+1):
        rows[0][j] = (j, 0)
    for i, char in enumerate(reference, 1):
        for j, other in enumerate(prediction, 1):
            prev = rows[i-1][j-1]
            substitution = (prev[0] + (char != other), prev[1] + int(char != other and char in CRITICAL))
            prev = rows[i-1][j]
            deletion = (prev[0]+1, prev[1]+int(char in CRITICAL))
            prev = rows[i][j-1]
            insertion = (prev[0]+1, prev[1])
            # Stable diagonal/deletion/insertion tie order; never choose an
            # alignment by whether it inflates the critical-character score.
            rows[i][j] = min((substitution, deletion, insertion), key=lambda p: p[0])
    return rows[-1][-1]


def intersection_over_union(a, b):
    intersection = max(0., min(a[2], b[2])-max(a[0], b[0])) * max(0., min(a[3], b[3])-max(a[1], b[1]))
    union = max(0., a[2]-a[0])*max(0., a[3]-a[1]) + max(0., b[2]-b[0])*max(0., b[3]-b[1])-intersection
    return intersection/union if union else 0.


def validate_manifest(manifest):
    drawings = {}
    ids = set()
    test_pages = set()
    for sample in manifest["samples"]:
        if not re.fullmatch(r"[A-Za-z0-9_-]+", sample["id"]):
            raise ValueError("Sample id must be a safe filename component")
        if sample["id"] in ids:
            raise ValueError("Duplicate sample id: " + sample["id"])
        ids.add(sample["id"])
        if sample["kind"] not in {"mechanical", "pid"} or sample["origin"] not in {"real", "synthetic"}:
            raise ValueError("Unknown drawing kind/origin")
        if sample["split"] not in {"dev", "test"}:
            raise ValueError("Unknown split")
        drawing = sample["drawing_id"]
        if drawing in drawings and drawings[drawing] != sample["split"]:
            raise ValueError("Drawing crosses development/test splits: " + drawing)
        drawings[drawing] = sample["split"]
        page_key = (drawing, sample.get("page_index", 0))
        if sample["split"] == "test":
            if page_key in test_pages:
                raise ValueError("Test annotations must be consolidated into one sample per drawing page")
            test_pages.add(page_key)
        if not sample.get("annotation_provenance"):
            raise ValueError("Annotations must declare their provenance")
        if min(sample["width"], sample["height"]) <= 0:
            raise ValueError("Invalid annotation coordinate dimensions")
        region_ids = set()
        for region in sample["regions"]:
            if region["id"] in region_ids or not normalize(region["text"]):
                raise ValueError("Duplicate region or empty reference text")
            region_ids.add(region["id"])
            box = region["bbox"]
            if (len(box) != 4 or not all(math.isfinite(float(x)) for x in box)
                    or not (0 <= box[0] < box[2] <= sample["width"] and 0 <= box[1] < box[3] <= sample["height"])):
                raise ValueError("Invalid reference box")
    return manifest


def corpus_coverage(manifest):
    tests = [s for s in manifest["samples"] if s["origin"] == "real" and s["split"] == "test"]
    pages = {kind: len({(s["drawing_id"], s.get("page_index", 0)) for s in tests if s["kind"] == kind})
             for kind in ("mechanical", "pid")}
    count = len({(s["drawing_id"], s.get("page_index", 0), r["id"]) for s in tests for r in s["regions"]})
    return {"real_test_pages": pages, "real_test_regions": count,
            "sample_origins": dict(Counter(s["origin"] for s in manifest["samples"])),
            "sufficient": all(n >= 10 for n in pages.values()) and count >= 200}


def predictions_for_page(response, sample):
    pages = response.get("pages") or []
    index = sample.get("page_index", 0)
    if index >= len(pages):
        return []
    page = pages[index]
    review = page.get("engineering_review") or {}
    page_blocked = bool(review.get("issues")) or (
        response.get("ocr_scene") == "engineering" and (not review or bool(response.get("errors"))))
    sx = sample["width"] / float(page.get("width") or sample["width"])
    sy = sample["height"] / float(page.get("height") or sample["height"])
    candidates = []
    seen = set()
    for block in page.get("regions", []):
        items = [(item, "line") for item in block.get("text_lines", []) + block.get("image_overlay_text", [])]
        items += [(item, "cell") for item in (block.get("table") or {}).get("cells", [])]
        for item, kind in items:
            box = item.get("bbox") or [item.get(k, 0) for k in ("x1", "y1", "x2", "y2")]
            box = [box[0]*sx, box[1]*sy, box[2]*sx, box[3]*sy]
            text = normalize(item.get("source_text") or item.get("text"))
            identity = (text, tuple(round(v, 1) for v in box), kind)
            if identity in seen:
                continue
            seen.add(identity)
            candidates.append({"text": text, "bbox": box, "kind": kind,
                               "needs_review": page_blocked or bool((item.get("engineering_review") or {}).get("needs_review"))})
    return candidates


def score_sample(sample, response):
    candidates = predictions_for_page(response, sample)
    used = set()
    rows = []
    for expected in sample["regions"]:
        eligible = [(intersection_over_union(expected["bbox"], item["bbox"]), i)
                    for i, item in enumerate(candidates) if i not in used
                    and item["kind"] == expected.get("kind", "line")]
        score, index = max(eligible, default=(0., -1))
        found = index >= 0 and score >= .2
        item = candidates[index] if found else {"text": "", "needs_review": False}
        if found:
            used.add(index)
        reference, prediction = normalize(expected["text"]), item["text"]
        edits, _ = edit_counts(reference, prediction)
        critical_errors, _ = edit_counts("".join(c for c in reference if c in CRITICAL),
                                        "".join(c for c in prediction if c in CRITICAL))
        rows.append({"id": expected["id"], "expected": reference, "predicted": prediction,
                     "exact": reference == prediction, "found": found, "edits": edits,
                     "reference_characters": len(reference), "critical_errors": critical_errors,
                     "critical_characters": sum(c in CRITICAL for c in reference),
                     "needs_review": item["needs_review"]})
    return {"sample_id": sample["id"], "kind": sample["kind"], "origin": sample["origin"],
            "split": sample["split"], "page_needs_review": bool(response.get("needs_review")), "regions": rows}


def aggregate(rows):
    total = len(rows)
    characters = sum(r["reference_characters"] for r in rows)
    critical = sum(r["critical_characters"] for r in rows)
    return {"regions": total, "cer": sum(r["edits"] for r in rows)/characters if characters else None,
            "annotation_accuracy": sum(r["exact"] and not r["needs_review"] for r in rows)/total if total else None,
            "critical_character_accuracy": max(0., 1-sum(
                max(r["critical_errors"], r["critical_characters"]) if r["needs_review"] else r["critical_errors"]
                for r in rows)/critical) if critical else None,
            "raw_annotation_accuracy": sum(r["exact"] for r in rows)/total if total else None,
            "raw_critical_character_accuracy": max(0., 1-sum(r["critical_errors"] for r in rows)/critical) if critical else None,
            "miss_rate": sum(not r["found"] for r in rows)/total if total else None,
            "review_rate": sum(r["needs_review"] for r in rows)/total if total else None,
            "reference_characters": characters, "critical_characters": critical}


def summarize(manifest, scores):
    groups = {}
    for kind in ("mechanical", "pid"):
        for origin in ("real", "synthetic"):
            for split in ("dev", "test"):
                rows = [r for score in scores if (score["kind"], score["origin"], score["split"]) == (kind, origin, split)
                        for r in score["regions"]]
                if rows:
                    groups[f"{kind}/{origin}/{split}"] = aggregate(rows)
    coverage = corpus_coverage(manifest)
    complete = {s["id"] for s in manifest["samples"]} == {s["sample_id"] for s in scores}
    passed = coverage["sufficient"] and complete and all(
        (groups.get(f"{kind}/real/test", {}).get("critical_character_accuracy") or 0) >= .99
        and (groups.get(f"{kind}/real/test", {}).get("annotation_accuracy") or 0) >= .95
        for kind in ("mechanical", "pid"))
    return {"groups": groups, "coverage": coverage, "complete": complete,
            "release_gate": "passed" if passed else "experimental",
            "review_is_recognition_credit": False,
            "critical_metric": "1 - engineering-symbol errors / reference symbols; includes insertions; reviewed regions get no correct-symbol credit",
            "raw_metrics": "transcription only; review remains a separate outcome and cannot satisfy the release gate",
            "normalization": "whitespace only; case and Unicode code points preserved"}
