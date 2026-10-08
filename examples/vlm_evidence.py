"""Selected evidence/geometry contract only; no models, service, drawings, or automatic acceptance."""
from copy import deepcopy
from itertools import islice, product
import re
from examples.engineering_tolerances import NUMBER


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
