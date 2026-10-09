"""Literal post-recognition tolerance candidates; no inferred signs or rewrites."""
from copy import deepcopy
from itertools import islice, product
import re

from pipeline.engineering_geometry import NUMBER, expanded_box


def fragment_crop_box(group, part, shape, cell_boxes=()):
    """Expand a fragment while keeping upper/lower rows and cells separate."""
    box = expanded_box(part["bbox"], shape)
    parts = {p["role"]: p for p in group["parts"]}
    upper, lower = parts["upper"]["bbox"], parts["lower"]["bbox"]
    boundary = (upper[3] + lower[1]) / 2
    if part["role"] == "upper":
        box[3] = min(box[3], int(boundary))
    elif part["role"] == "lower":
        box[1] = max(box[1], int(boundary))
    else:
        box[2] = min(box[2], int(min(upper[0], lower[0])))
    a, b, c, d = part["bbox"]
    cells = [cell for cell in cell_boxes
             if cell[0] <= (a+c)/2 <= cell[2] and cell[1] <= (b+d)/2 <= cell[3]]
    if cells:
        cell = min(cells, key=lambda r: (r[2]-r[0])*(r[3]-r[1]))
        box = [max(box[0], int(cell[0])), max(box[1], int(cell[1])),
               min(box[2], int(cell[2])), min(box[3], int(cell[3]))]
    return box if box[2] > box[0] and box[3] > box[1] else list(part["bbox"])


def compose_reviewed_annotations(annotations, regions, *, limit=8):
    """Reference actual candidate evidence after review, preserving the original group."""
    by_id = {r["unique_region_id"]: r for r in regions}
    result = deepcopy(annotations)
    for group in result:
        choices = []
        missing = []
        for part in group["parts"]:
            region = by_id.get(part["region_id"], {})
            options = []
            seen = set()
            for index, candidate in enumerate(region.get("candidates", [])):
                text = str(candidate.get("text", "")).strip()
                if (not text or candidate.get("status", "ok") != "ok"
                        or (candidate.get("model") or {}).get("reason")
                        or re.search(r"\d\s+\d", text)
                        or not NUMBER.fullmatch(text.replace(" ", "")) or text in seen):
                    continue
                seen.add(text)
                options.append({"text": text, "region_id": part["region_id"],
                                "candidate_index": index, "source": "recognition", "role": part["role"]})
            if not options:
                missing.append(part["region_id"])
            # Original observations remain alternatives, never inserted characters.
            for text in part.get("observed_alternatives", [part["text"]]):
                if text not in seen:
                    seen.add(text)
                    options.append({"text": text, "region_id": part["region_id"],
                                    "source": "positioned_observation", "role": part["role"]})
            choices.append(options)
        group["reviewed_candidates"] = [
            {"text": " ".join(p["text"] for p in combination), "parts": list(combination),
             "needs_review": True, "status": "candidate_only"}
            for combination in islice(product(*choices), max(0, limit))]
        group["unreviewed_part_ids"] = missing
        group["needs_review"] = True
        group["review_status"] = "partial" if missing else "candidates_available"
    return result


def attach_vlm_evidence(report, observations):
    """Merge addressed VLM evidence into an existing review, never into source text.

    Callers must map crops to unique_region_id using geometry, not text similarity.
    Even successful VLM output keeps every affected region pending review.
    """
    result = deepcopy(report)
    by_id = {r["unique_region_id"]: r for r in result.get("unique_regions", [])}
    rejected = []
    for observation in observations:
        identity = observation.get("unique_region_id")
        region = by_id.get(identity)
        if region is None:
            rejected.append({"unique_region_id": identity, "reason": "unknown_region"})
            continue
        candidate = deepcopy(observation)
        candidate["confidence"] = None  # A VLM self-rating is not calibrated OCR probability.
        candidate["source"] = "vlm"
        existing = region.setdefault("candidates", [])
        if candidate not in existing:
            existing.append(candidate)
        region["needs_review"] = True
        region["resolution"] = "vlm_candidate_requires_review"
    for owner in result.get("regions", []):
        region = by_id.get(owner.get("unique_region_id"))
        if region:
            for key in ("candidates", "needs_review", "resolution"):
                owner[key] = deepcopy(region[key])
    result["annotation_groups"] = compose_reviewed_annotations(
        result.get("annotation_groups", []), list(by_id.values()))
    result["vlm_rejected_evidence"] = rejected
    if observations:
        result.update(needs_review=True, status="needs_review")
    return result


def attach_vlm_to_response(response, observations):
    """Enrich a single-page API/export payload and all of its owner aliases."""
    result = deepcopy(response)
    if len(result.get("pages", [])) != 1:
        raise ValueError("VLM evidence attachment requires a single-page response")
    page = result["pages"][0]
    # API/task responses use the page field; file exports retain page metadata.
    holder = page if "engineering_review" in page else page.setdefault("metadata", {})
    report = attach_vlm_evidence(holder.get("engineering_review") or {}, observations)
    holder["engineering_review"] = report
    if holder is page and "engineering_review" in page.get("metadata", {}):
        page["metadata"]["engineering_review"] = deepcopy(report)
    by_id = {row["id"]: row for row in report.get("regions", [])}

    def replace_audit(value):
        if isinstance(value, dict):
            audit = value.get("engineering_review")
            if isinstance(audit, dict) and audit.get("id") in by_id:
                value["engineering_review"] = deepcopy(by_id[audit["id"]])
            for key, child in value.items():
                if key != "engineering_review":
                    replace_audit(child)
        elif isinstance(value, list):
            for child in value:
                replace_audit(child)

    replace_audit(page.get("regions", []))
    replace_audit(page.get("blocks", []))
    replace_audit(result.get("regions", []))
    if report.get("needs_review"):
        result.update(needs_review=True, disposition="review")
    return result
