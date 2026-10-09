"""Evidence-preserving review of engineering text, including independent table OCR.

Recognition consensus is not proof of an ambiguous glyph's Unicode identity.
This module never substitutes diameter signs or converts text into dimensions.
"""
import math
import re
import time

import cv2
import numpy as np

from core.document_reading import block_line_views
from core.document_payload import table_payload
from pipeline.engineering_geometry import (annotation_groups, deduplicate_targets,
    expanded_box, ink_evidence, line_suppressed_view, numeric_annotation)
from pipeline.engineering_candidates import compose_reviewed_annotations, fragment_crop_box


ENGINEERING_CHARACTERS = "Ø⌀∅Φφ±°×÷≤≥μµ²³′″−"
_DIAMETER = re.compile(r"[Ø⌀∅Φφ]\s*[0-9OIl]")
_MEASUREMENT = re.compile(
    r"(?:\d\s*(?:mm|cm|µm|μm|MPa|kPa|kN|bar|°)\b|"
    r"\b(?:DN|PN|[MR])\s*\d|\d\s*[±×]\s*[\dOIl]|[+-]\s*\d+[.,]\d+|"
    r"[尺寸径角公差螺纹]|\b(?:bore|diameter|tolerance|thread|angle)\b)", re.I)
_TAG = re.compile(r"\b[A-Z]{1,6}[-/]?[0-9OIl]{2,}[A-Z]?\b")


def attach_engineering_review(image, page, *, settings, reader=None):
    """A review failure must never turn into an accepted page."""
    try:
        return review_engineering_page(image, page, settings=settings, reader=reader)
    except Exception as error:
        report = {"version": 1, "status": "needs_review", "needs_review": True,
                  "experimental": True, "issues": ["engineering_review_failed"],
                  "error_type": type(error).__name__, "regions": []}
        page.metadata["engineering_review"] = report
        return report


def engineering_risks(text, confidence=1.):
    standalone = bool(re.fullmatch(r"[+-]?\d+(?:[.,]\d+)?|[Ø⌀∅Φφ±°×µμ²³]+", text.strip()))
    context = bool(standalone or numeric_annotation(text) or _DIAMETER.search(text)
                   or _MEASUREMENT.search(text) or _TAG.search(text))
    if not context:
        return []
    risks = []
    if _DIAMETER.search(text) or text.strip() in "Ø⌀∅Φφ":
        risks.append("diameter_glyph_ambiguous")
    if re.search(r"(?:\d[OIl]|[OIl]\d|[OIl][.,]\d|\d[.,][OIl])", text):
        risks.append("letter_digit_confusable")
    if re.search(r"\+\s*\d", text):
        risks.append("tolerance_sign_ambiguous")
    if re.search(r"\d\s*x\s*\d", text):
        risks.append("multiplication_glyph_ambiguous")
    if any(c in text for c in "±+−-.,×°²³≤≥") or any(c.isdigit() for c in text):
        risks.append("critical_engineering_annotation")
    if not math.isfinite(float(confidence)) or confidence < .95:
        risks.append("low_confidence")
    return risks


def loaded_character_coverage(engine):
    """Inspect the loaded decoder, never infer coverage from a version/name."""
    from ocr_engine.numeric_character_support import model_characters

    handle = getattr(engine, "_ocr_handle", None)
    native = getattr(handle, "engine", None) or getattr(engine, "_ocr", None)
    chars = model_characters(native)
    config = getattr(handle, "model_config", None)
    name = getattr(config, "recognition_model", "")
    missing = [char for char in ENGINEERING_CHARACTERS if char not in chars]
    return {"status": ("available" if not missing else "incomplete") if chars else "unavailable",
            "model": name, "dictionary_size": len(chars),
            "required_characters": ENGINEERING_CHARACTERS,
            "missing_characters": missing if chars else [], "source": "loaded_decoder"}


def _targets(page):
    """Yield mutable owners paired with non-mutating page-coordinate geometry."""
    for bi, block in enumerate(page.blocks):
        for overlay in (False, True):
            raw = (block.image.overlay_text if block.image is not None else []) if overlay else block.text_lines
            for li, (owner, view) in enumerate(zip(raw or [], block_line_views(block, overlay=overlay))):
                yield f"block:{bi}:{'overlay' if overlay else 'line'}:{li}", owner, view.bbox, view.source_quad, "line"
        table = table_payload(block)
        if table:
            for ci, (owner, view) in enumerate(zip(block.table.cells, table["cells"])):
                yield f"block:{bi}:cell:{ci}", owner, view["bbox"], (), "cell"


def _crop(image, bbox, quad, margin=3):
    height, width = image.shape[:2]
    if len(bbox) != 4 or not all(math.isfinite(float(v)) for v in bbox):
        return None
    a, b, c, d = map(float, bbox)
    if not (0 <= a < c <= width and 0 <= b < d <= height):
        return None
    if len(quad) == 4:
        points = np.asarray(quad, dtype=np.float32)
        if (not np.isfinite(points).all() or (points < 0).any()
                or (points[:, 0] > width).any() or (points[:, 1] > height).any()):
            return None
        w = round(max(np.linalg.norm(points[1]-points[0]), np.linalg.norm(points[2]-points[3])))
        h = round(max(np.linalg.norm(points[3]-points[0]), np.linalg.norm(points[2]-points[1])))
        if min(w, h) >= 3 and max(w, h) <= 8192 and w*h <= 1_000_000:
            destination = np.float32([[0, 0], [w-1, 0], [w-1, h-1], [0, h-1]])
            transform = cv2.getPerspectiveTransform(points, destination)
            return cv2.warpPerspective(image, transform, (w, h), borderValue=(255, 255, 255))
    return image[max(0, int(b)-margin):min(height, math.ceil(d)+margin),
                 max(0, int(a)-margin):min(width, math.ceil(c)+margin)]


def review_engineering_page(image, page, *, settings, reader=None, coverage=None, clock=time.perf_counter):
    started = clock()
    layout = page.metadata.get("layout_engine") or {}
    tiles = layout.get("engineering_tiles") or {}
    coverage = coverage or layout.get("engineering_character_coverage") or {"status": "unavailable"}
    report = {"version": 2, "status": "checked", "experimental": True,
              "coordinate_space": "page", "regions": [], "issues": [],
              "character_coverage": coverage, "tiles": tiles, "needs_review": False,
              "budget_type": "cooperative_between_native_calls"}
    if coverage.get("status") != "available":
        report["issues"].append("engineering_character_coverage_" + coverage.get("status", "unavailable"))
    if tiles.get("needs_review"):
        report["issues"].append("engineering_tiles_unresolved")
    max_regions = max(1, int(getattr(settings, "OCR_ENGINEERING_REVIEW_MAX_REGIONS", 128)))
    max_seconds = max(1., float(getattr(settings, "OCR_ENGINEERING_REVIEW_SECONDS", 45)))
    report["configured_limits"] = {"max_unique_regions": max_regions, "max_seconds": max_seconds}
    checked = 0
    targets = list(_targets(page))
    groups = deduplicate_targets(targets)
    cells = [bbox for _, _, bbox, _, kind in targets if kind == "cell"]
    report["annotation_groups"] = annotation_groups(groups, cells)
    grouped = {part["region_id"] for group in report["annotation_groups"] for part in group["parts"]}
    fragment_boxes = {part["region_id"]: fragment_crop_box(group, part, image.shape, cells)
                      for group in report["annotation_groups"] for part in group["parts"]} if image is not None else {}
    work = []
    for group in groups:
        _, owner, bbox, _, _ = group["targets"][0]
        text = str(owner.source_text or owner.text or "")
        risks = list(dict.fromkeys(r for _, member, _, _, _ in group["targets"]
                    for r in engineering_risks(str(member.source_text or member.text), member.confidence)))
        if not risks:
            continue
        dimension = any(numeric_annotation(t) for t in group["texts"])
        pixels = ink_evidence(image, bbox) if dimension else {"status": "not_requested", "issues": []}
        if dimension:
            risks.append("dimension_symbol_completeness_unverified")
        if len(group["texts"]) > 1:
            risks.append("positioned_candidate_conflict")
        if group["id"] in grouped:
            risks.append("stacked_tolerance_fragment")
        risks.extend(pixels["issues"])
        group.update(risks=risks, image_evidence=pixels, dimension=dimension)
        # Deterministic risk order; duplicate owners never spend additional slots.
        group["priority"] = (0 if dimension and pixels["issues"] else
                             1 if any("ambiguous" in r for r in risks) else
                             2 if group["id"] in grouped else 3 if len(group["texts"]) > 1 else 4)
        work.append(group)
    work.sort(key=lambda g: (g["priority"], g["bbox"][1], g["bbox"][0], g["id"]))
    report["unique_regions"] = []
    for group in work:
        identity, owner, bbox, quad, kind = group["targets"][0]
        text = str(owner.source_text or owner.text or "")
        risks = group["risks"]
        evidence = {"source_text": text, "bbox": list(bbox), "source_quad": list(quad),
                    "source_confidence": float(owner.confidence) if math.isfinite(float(owner.confidence)) else None,
                    "source_model": coverage.get("model", ""),
                    "text_angle": float(getattr(owner, "text_angle", 0)),
                    "baseline_y": getattr(owner, "baseline_y", None),
                    "geometry_kind": kind, "risks": risks, "candidates": [],
                    "unique_region_id": group["id"], "member_ids": group["members"],
                    "positioned_texts": group["texts"], "priority": group["priority"],
                    "image_evidence": group["image_evidence"],
                    "needs_review": True, "resolution": "unverified"}
        crop = _crop(image, bbox, quad) if image is not None else None
        if reader is None:
            evidence["resolution"] = "review_recognizer_unavailable"
        elif crop is None or not crop.size:
            evidence["resolution"] = "original_geometry_unavailable"
        elif crop.shape[0]*crop.shape[1] > 1_000_000:
            evidence["resolution"] = "crop_pixel_budget_exhausted"
        elif checked >= max_regions or clock()-started >= max_seconds:
            evidence["resolution"] = "review_budget_exhausted"
        elif kind == "cell" and crop.shape[0] > crop.shape[1]*.6:
            evidence["resolution"] = "cell_requires_line_geometry"
        else:
            checked += 1
            variants = [("original", crop), ("padded", cv2.copyMakeBorder(
                crop, 6, 6, 6, 6, cv2.BORDER_CONSTANT, value=(255, 255, 255)))]
            if crop.shape[0] > crop.shape[1]*1.3:
                variants = [("rotate_90", cv2.rotate(crop, cv2.ROTATE_90_CLOCKWISE)),
                            ("rotate_270", cv2.rotate(crop, cv2.ROTATE_90_COUNTERCLOCKWISE))]
            elif owner.confidence < .95 or abs(float(getattr(owner, "text_angle", 0))) > 90:
                variants.append(("rotate_180", cv2.rotate(crop, cv2.ROTATE_180)))
            if group["dimension"]:
                expanded_bbox = fragment_boxes.get(group["id"], expanded_box(bbox, image.shape))
                expanded = _crop(image, expanded_bbox, (), margin=0)
                if expanded is not None and expanded.size and expanded.shape[0]*expanded.shape[1] <= 1_000_000:
                    variants.append(("expanded", expanded))
                suppressed = line_suppressed_view(crop)
                if suppressed is not None:
                    variants.append(("line_suppressed_candidate_only", suppressed))
            for variant, pixels in variants:
                if clock()-started >= max_seconds:
                    evidence["resolution"] = "review_budget_exhausted"
                    break
                try:
                    candidate, score, model = reader(pixels)
                    model = dict(model)
                    alternates = model.pop("alternate_observations", [])
                    observations = [{"text": candidate, "confidence": score, "model": model}, *alternates]
                    for observation in observations:
                        score = float(observation["confidence"])
                        if not math.isfinite(score):
                            evidence["resolution"] = "invalid_recognition_score"
                            break
                        evidence["candidates"].append({**observation, "confidence": score, "view": variant,
                            "crop_bbox": list(expanded_bbox if variant == "expanded" else bbox),
                            "source": "text_recognition", "status": "ok"})
                        if observation["model"].get("reason") or not observation["text"]:
                            evidence["resolution"] = "review_candidate_unavailable"
                    if evidence["resolution"] != "unverified":
                        break
                except Exception as error:
                    evidence["resolution"] = "review_inference_failed:" + type(error).__name__
                    break
            observations = evidence["candidates"]
            agreeing = len(observations) >= 2 and all(
                item["text"] == text and item["confidence"] >= .9 for item in observations)
            ambiguous = any(risk.endswith("ambiguous") or risk == "letter_digit_confusable" for risk in risks)
            if evidence["resolution"] == "unverified":
                if ambiguous:
                    evidence["resolution"] = "ambiguous_symbol"
                elif group["dimension"]:
                    evidence["resolution"] = "symbol_completeness_unverified"
                elif agreeing and len(group["texts"]) == 1:
                    evidence.update(resolution="consistent_recognition", needs_review=False)
                else:
                    evidence["resolution"] = "recognition_disagreement"
        report["unique_regions"].append(evidence)
        for member_id, member, member_bbox, member_quad, member_kind in group["targets"]:
            row = {**evidence, "id": member_id, "source_text": str(member.source_text or member.text or ""),
                   "bbox": list(member_bbox), "source_quad": list(member_quad), "geometry_kind": member_kind}
            report["regions"].append(row)
            if member_kind == "line":
                member.repair_audit["engineering_review"] = row
            else:
                member.raw["engineering_review"] = row
    report["annotation_groups"] = compose_reviewed_annotations(
        report["annotation_groups"], report["unique_regions"])
    report["unique_target_regions"] = len(work)
    report["shared_review_owners"] = len(report["regions"])-len(work)
    report["unique_budget_exhausted"] = sum(r["resolution"] == "review_budget_exhausted"
                                             for r in report["unique_regions"])
    report["checked_regions"] = checked
    report["needs_review"] = bool(report["issues"] or any(r["needs_review"] for r in report["regions"]))
    report["status"] = "needs_review" if report["needs_review"] else "checked"
    report["elapsed_seconds"] = round(clock()-started, 4)
    page.metadata["engineering_review"] = report
    timing = page.metadata.setdefault("timing", {})
    timing["engineering_review"] = report["elapsed_seconds"]
    timing["total"] = round(float(timing.get("total", 0)) + report["elapsed_seconds"], 4)
    return report
