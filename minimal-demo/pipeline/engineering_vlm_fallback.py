"""Bounded, evidence-preserving local VLM fallback for engineering OCR.

The runner receives pixels and task parameters only, never OCR text or answers.
Production runners must enforce the requested inference timeout in a killable
worker; a Python caller cannot safely interrupt a running CUDA operation.
Consensus supports a machine choice, not a claim of verified transcription.
"""
from __future__ import annotations

from copy import deepcopy
from collections import defaultdict, deque
from dataclasses import dataclass, fields
import hashlib
import math
import re
import time
from types import SimpleNamespace

import cv2

from models import BlockType
from pipeline.engineering_candidates import compose_reviewed_annotations, fragment_crop_box
from pipeline.engineering_geometry import NUMBER, deduplicate_targets, expanded_box
from pipeline.engineering_ocr import same_region
from pipeline.engineering_review import _crop, _targets, engineering_risks


@dataclass(frozen=True)
class EngineeringVLMConfig:
    max_regions: int = 16
    seconds: float = 90.
    request_seconds: float = 15.
    text_max_tokens: int = 256
    formula_max_tokens: int = 1024
    primary_model: str = "glm-ocr"
    verifier_model: str = "mineru"
    max_crop_pixels: int = 1_000_000
    routing_order: str = "position"
    shared_candidate_pool: bool = False

    @classmethod
    def from_value(cls, value=None):
        values = {}
        for field in fields(cls):
            setting = "OCR_ENGINEERING_VLM_" + field.name.upper()
            if isinstance(value, dict):
                values[field.name] = value.get(field.name, value.get(setting, field.default))
            else:
                values[field.name] = getattr(value, setting, field.default)
        config = value if isinstance(value, cls) else cls(**values)
        routing_policy_version(config.routing_order)
        for name in ("max_regions", "seconds", "request_seconds", "text_max_tokens",
                     "formula_max_tokens", "max_crop_pixels"):
            number = float(getattr(config, name))
            if not math.isfinite(number) or number <= 0:
                raise ValueError("Engineering VLM limits must be finite and positive")
            if name in {"max_regions", "text_max_tokens", "formula_max_tokens", "max_crop_pixels"} and (
                    not isinstance(getattr(config, name), int) or isinstance(getattr(config, name), bool)):
                raise ValueError("Engineering VLM count limits must be integers")
        return config


_CRITICAL = re.compile(r"[0-9Ø⌀∅Φφ±+\-−.,×x°²³⁰¹⁴⁵⁶⁷⁸⁹⁺⁻]")
_HIGH_RISKS = {"unexplained_neighbor_ink", "leading_glyph_requires_verification",
               "positioned_candidate_conflict", "stacked_tolerance_fragment",
               "diameter_glyph_ambiguous", "tolerance_sign_ambiguous",
               "letter_digit_confusable", "multiplication_glyph_ambiguous",
               "critical_candidate_conflict"}
ROUTING_POLICY_VERSION = "engineering-position-priority-v1"
ROUTING_EVIDENCE_POLICY_VERSION = "engineering-evidence-priority-v2"
ROUTING_STRATIFIED_POLICY_VERSION = "engineering-stratified-priority-v1"


def routing_policy_version(order="position"):
    versions = {"position": ROUTING_POLICY_VERSION, "evidence": ROUTING_EVIDENCE_POLICY_VERSION,
                "stratified": ROUTING_STRATIFIED_POLICY_VERSION}
    if order not in versions:
        raise ValueError("routing_order must be position, evidence or stratified")
    return versions[order]


def order_regions(work, order):
    """Order an identical candidate pool; never add candidates based on policy."""
    routing_policy_version(order)
    position = lambda g: (g["bbox"][1], g["bbox"][0], g["id"])
    if order != "stratified":
        return sorted(work, key=lambda g: (g["priority"],
            g["routing_evidence"]["evidence_rank"] if order == "evidence" else 0, *position(g)))
    buckets = defaultdict(lambda: defaultdict(deque))
    for group in sorted(work, key=position):
        buckets[group["priority"]][group["routing_evidence"]["evidence_rank"]].append(group)
    result = []
    for priority in sorted(buckets):
        queues = [buckets[priority][rank] for rank in sorted(buckets[priority])]
        while any(queues):
            for queue in queues:
                if queue:
                    result.append(queue.popleft())
    return result


def _source(owner):
    audit = getattr(owner, "repair_audit", getattr(owner, "raw", {})) or {}
    if "engineering_vlm_original_text" in audit:
        return str(audit["engineering_vlm_original_text"])
    return str(getattr(owner, "source_text", "") or getattr(owner, "text", "") or "")


def _safe_box(box, image):
    if image is None or not isinstance(box, (list, tuple)) or len(box) != 4:
        return False
    try:
        a, b, c, d = map(float, box)
        return (all(math.isfinite(x) for x in (a, b, c, d))
                and 0 <= a < c <= image.shape[1] and 0 <= b < d <= image.shape[0])
    except (TypeError, ValueError):
        return False


def _risk_priority(region):
    risks = set(region.get("risks", []))
    if risks & _HIGH_RISKS:
        return 0
    if risks & {"detected_empty_region", "direction_recognition_failed", "formula_unverified"}:
        return 1
    if "low_confidence" in risks and "critical_engineering_annotation" in risks:
        return 1
    if "dimension_symbol_completeness_unverified" in risks:
        return 2  # Only the remaining bounded regional budget after error evidence.
    # Page-level needs_review by itself is never a trigger.
    return None


def _routing_evidence(region, annotations):
    """Order actual image/recognizer evidence without reference labels.

    A leading component also occurs in correctly read numbers, so it is weaker
    than disagreeing observed critical glyphs or ink outside the detection box.
    Candidate confidence filters obvious garbage here; it never validates text.
    """
    source = " ".join(str(region.get("source_text", "")).split())
    observations = [source, *(" ".join(str(value).split()) for value in region.get("positioned_texts", []))]
    for candidate in region.get("candidates", []):
        try:
            confidence = float(candidate.get("confidence", 0.))
        except (TypeError, ValueError):
            continue
        model = candidate.get("model") or {}
        if not isinstance(model, dict):
            continue
        if (candidate.get("source") == "text_recognition" and candidate.get("status", "ok") == "ok"
                and candidate.get("view") in {"original", "padded", "expanded"}
                and confidence >= .9 and math.isfinite(confidence)
                and not candidate.get("truncated") and candidate.get("finish_reason") not in {"length", "max_tokens"}
                and not model.get("reason") and not model.get("error") and not model.get("identity_error")
                and model.get("identity_verified") is not False
                and model.get("status") not in {"error", "failed", "unavailable", "truncated"}
                and str(candidate.get("text", "")).strip()):
            observations.append(" ".join(str(candidate["text"]).split()))
    critical_conflict = len({tuple(_CRITICAL.findall(text)) for text in observations}) > 1
    missing_tolerance_sign = any(
        any(part.get("region_id") == region.get("unique_region_id") for part in group.get("parts", []))
        and any(part.get("role") in {"upper", "lower"}
                and not str(part.get("text", "")).lstrip().startswith(("+", "-", "−"))
                and str(part.get("text", "")).strip() != "0" for part in group.get("parts", []))
        for group in annotations)
    risks = set(region.get("risks", []))
    if critical_conflict:
        rank, reason = 0, "observed_critical_candidate_conflict"
    elif missing_tolerance_sign:
        rank, reason = 1, "stacked_tolerance_sign_completeness_unverified"
    elif risks & {"stacked_tolerance_fragment", "diameter_glyph_ambiguous", "tolerance_sign_ambiguous"}:
        rank, reason = 2, "explicit_engineering_symbol_or_tolerance_ambiguity"
    elif "unexplained_neighbor_ink" in risks:
        rank, reason = 3, "ink_outside_detection"
    elif risks & {"positioned_candidate_conflict", "letter_digit_confusable", "multiplication_glyph_ambiguous"}:
        rank, reason = 4, "positioned_text_or_glyph_conflict"
    elif "leading_glyph_requires_verification" in risks:
        rank, reason = 5, "leading_inside_detection_only"
    else:
        rank, reason = 6, "secondary_or_completeness_risk"
    return {"evidence_policy_version": ROUTING_EVIDENCE_POLICY_VERSION, "evidence_rank": rank,
            "reason": reason, "critical_candidate_conflict": critical_conflict,
            "tolerance_sign_completeness_unverified": missing_tolerance_sign}


def _collect(page, report, image, *, routing_order="position", shared_candidate_pool=False):
    policy = routing_policy_version(routing_order)
    targets = list(_targets(page))
    groups = deduplicate_targets(targets)
    by_id = {r["unique_region_id"]: r for r in report.get("unique_regions", [])}
    by_member = {member: r for r in by_id.values() for member in r.get("member_ids", [])}
    used = set(by_id)
    work = []
    for group in groups:
        existing = by_id.get(group["id"]) or next(
            (by_member[m] for m in group["members"] if m in by_member), None)
        if existing:
            group["id"] = existing["unique_region_id"]
            region = existing
        else:
            owner = group["targets"][0][1]
            risks = engineering_risks(_source(owner), getattr(owner, "confidence", 1.))
            if not _source(owner).strip():
                risks.append("detected_empty_region")
            region = {"unique_region_id": group["id"], "member_ids": group["members"],
                      "source_text": _source(owner), "bbox": group["bbox"],
                      "source_confidence": getattr(owner, "confidence", None),
                      "risks": risks, "candidates": [], "needs_review": True,
                      "geometry_kind": group["targets"][0][4]}
        if len(group["texts"]) > 1:
            region["risks"] = list(dict.fromkeys([*region.get("risks", []), "positioned_candidate_conflict"]))
        region["positioned_texts"] = list(group["texts"])
        if "direction" in str(region.get("resolution", "")) or "rotation" in str(region.get("resolution", "")):
            region["risks"] = list(dict.fromkeys([*region.get("risks", []), "direction_recognition_failed"]))
        group["routing_evidence"] = _routing_evidence(region, report.get("annotation_groups", []))
        if (shared_candidate_pool or routing_order == "evidence") and group["routing_evidence"]["critical_candidate_conflict"]:
            region["risks"] = list(dict.fromkeys([*region.get("risks", []), "critical_candidate_conflict"]))
        group.update(region=region, task="text", formula_block=None)
        group["priority"] = _risk_priority(region)
        if group["priority"] is not None:
            if region["unique_region_id"] not in used:
                report.setdefault("unique_regions", []).append(region)
                used.add(region["unique_region_id"])
            work.append(group)

    # Equations have real layout geometry but are excluded from ordinary text OCR.
    for index, block in enumerate(page.blocks):
        if block.block_type != BlockType.EQUATION:
            continue
        raw = block.raw or {}
        previous = raw.get("engineering_review") or {}
        if block.formula_latex and block.confidence >= .95 and not (
                raw.get("needs_review") or previous.get("needs_review")):
            continue
        identity = f"engineering-formula:{index}"
        region = by_id.get(identity) or {
            "unique_region_id": identity, "member_ids": [f"block:{index}:formula"],
            "source_text": raw.get("source_formula_latex", block.formula_latex),
            "source_confidence": block.confidence, "bbox": list(block.bbox),
            "geometry_kind": "formula", "risks": ["formula_unverified"],
            "candidates": [], "needs_review": True}
        proxy = SimpleNamespace(text=block.formula_latex, source_text=region["source_text"],
                                text_angle=0, confidence=block.confidence)
        group = {"id": identity, "bbox": list(block.bbox), "angle": 0.,
                 "members": region["member_ids"], "texts": [region["source_text"]],
                 "targets": [(region["member_ids"][0], proxy, block.bbox, (), "formula")],
                 "region": region, "priority": 1, "task": "formula", "formula_block": block}
        if identity not in used:
            report.setdefault("unique_regions", []).append(region)
            used.add(identity)
        work.append(group)

    # Located omissions are useful candidates; without a mutable owner they must
    # remain candidates, not fabricated positioned text lines.
    for row in (page.metadata.get("source_region_review") or {}).get("unresolved_regions", []):
        box = row.get("bbox")
        if not _safe_box(box, image) or any(same_region(box, g["bbox"]) for g in groups + work):
            continue
        if row.get("failure_stage") not in {"ocr_recognition", "ocr_assignment"}:
            continue
        identity = "engineering-missing:" + str(row.get("id", len(work)))
        region = {"unique_region_id": identity, "member_ids": [], "bbox": list(box),
                  "source_text": row.get("source_text", ""), "geometry_kind": "detected_region",
                  "risks": ["detected_empty_region"], "candidates": [], "needs_review": True}
        report.setdefault("unique_regions", []).append(region)
        work.append({"id": identity, "bbox": list(box), "angle": 0., "members": [],
                     "texts": [region["source_text"]], "targets": [], "region": region,
                     "priority": 1, "task": "text", "formula_block": None})
    for group in work:
        group.setdefault("routing_evidence", _routing_evidence(group["region"], report.get("annotation_groups", [])))
        group["routing_evidence"].update(policy_version=policy, routing_order=routing_order,
                                          evidence_sort_enabled=routing_order == "evidence")
    work = order_regions(work, routing_order)
    return work, groups


def _views(group, image, annotations, cell_boxes):
    box = group["bbox"]
    quad = group["targets"][0][3] if group["targets"] else ()
    original = _crop(image, box, quad, margin=0)
    extended = expanded_box(box, image.shape)
    for annotation in annotations:
        for part in annotation.get("parts", []):
            if part.get("region_id") == group["id"]:
                extended = fragment_crop_box(annotation, part, image.shape, cell_boxes)
    expanded = _crop(image, extended, (), margin=0)
    views = [("original", original, box), ("expanded", expanded, extended)]
    # Rotate only when measured direction supplies an unambiguous correction.
    owner = group["targets"][0][1] if group["targets"] else None
    angle = float(getattr(owner, "text_angle", 0)) % 360
    for name, crop, crop_box in views:
        rotation = 0 if quad and name == "original" else (round(angle / 90) * 90) % 360
        if crop is not None and rotation:
            code = {90: cv2.ROTATE_90_COUNTERCLOCKWISE, 180: cv2.ROTATE_180,
                    270: cv2.ROTATE_90_CLOCKWISE}[rotation]
            crop = cv2.rotate(crop, code)
        yield name, crop, crop_box, rotation


def _valid_output(observation, task):
    if observation.get("status") != "ok":
        return str(observation.get("status") or "invalid_response")
    if observation.get("truncated") or observation.get("finish_reason") in {"length", "max_tokens"}:
        return "truncated"
    text = observation.get("text")
    if not isinstance(text, str) or not text.strip():
        return "empty_output"
    if "```" in text or "\x00" in text or re.match(
            r"\s*(?:the (?:image|text|formula)|here (?:is|are)|识别结果[：:]|转写结果[：:])", text, re.I):
        return "nonliteral_output"
    if task == "text" and ("\n" in text.strip() or "\r" in text.strip()):
        return "multiple_annotation_output"
    if task == "formula":
        depth = 0
        for char in re.sub(r"\\[{}]", "", text):
            depth += (char == "{") - (char == "}")
            if depth < 0:
                return "invalid_formula_structure"
        if depth:
            return "invalid_formula_structure"
    return "ok"


def _weight(observation):
    model = observation.get("model") or {}
    if not isinstance(model, dict):
        return None
    identity = model.get("weight_identity") or model.get("weights_sha256") or model.get("weight_sha256")
    if identity:
        return str(identity)
    # A model label/path alone is not proof that different weights were loaded.
    revision = model.get("revision") or model.get("commit_hash")
    model_id = model.get("id") or model.get("model_id")
    return f"{model_id}@{revision}" if model_id and revision else None


def _critical_change(old, new, task):
    return task == "formula" or _CRITICAL.findall(old) != _CRITICAL.findall(new)


def _html_updates(page, owners, text):
    """Address HTML by validated row/column/span, never by global text replace."""
    updates = []
    owner_ids = {id(owner) for owner in owners}
    for block in page.blocks:
        table = block.table
        if table is None:
            continue
        selected = [cell for cell in table.cells if id(cell) in owner_ids]
        if not selected or not table.html:
            continue
        try:
            from bs4 import BeautifulSoup
            soup = BeautifulSoup(table.html, "html.parser")
            mapped, occupied = {}, set()
            for row, tr in enumerate(soup.find_all("tr")):
                col = 0
                for node in tr.find_all(["td", "th"], recursive=False):
                    while (row, col) in occupied:
                        col += 1
                    rowspan, colspan = int(node.get("rowspan", 1)), int(node.get("colspan", 1))
                    if min(rowspan, colspan) <= 0:
                        return None
                    mapped[(row, col)] = (node, rowspan, colspan)
                    occupied.update((r, c) for r in range(row, row+rowspan) for c in range(col, col+colspan))
                    col += colspan
            for cell in selected:
                item = mapped.get((cell.row, cell.col))
                if not item or item[1:] != (cell.rowspan, cell.colspan):
                    return None
                node = item[0]
                if node.get_text().strip() != cell.text.strip():
                    return None
                node.clear()
                node.append(text)
            updates.append((table, str(soup)))
        except (ImportError, TypeError, ValueError):
            return None
    return updates


def _apply_choice(page, group, text):
    if group["formula_block"] is not None:
        block = group["formula_block"]
        block.raw.setdefault("source_formula_latex", block.formula_latex)
        block.formula_latex = text
        return "selected"
    owners = [target[1] for target in group["targets"]]
    if not owners:
        return "no_mutable_positioned_owner"
    if len({_source(owner) for owner in owners}) != 1:
        return "positioned_owner_conflict"
    if any("\n" in _source(owner).strip() or "\r" in _source(owner).strip() for owner in owners):
        return "multiple_annotation_owner"
    if any(kind == "cell" and (box[3]-box[1]) > (box[2]-box[0])*.6
           and not getattr(owner, "text_lines", []) for _, owner, box, _, kind in group["targets"]):
        return "cell_requires_line_geometry"
    # Cell line aliases are safe only when the cell is one complete annotation.
    for owner in list(owners):
        nested = getattr(owner, "text_lines", [])
        if nested:
            if len(nested) != 1 or _source(nested[0]) != _source(owner):
                return "cell_requires_line_geometry"
            if all(id(nested[0]) != id(existing) for existing in owners):
                owners.append(nested[0])
    if any(getattr(owner, "translated_text", "") for owner in owners):
        return "already_translated_owner"
    updates = _html_updates(page, owners, text)
    if updates is None:
        return "table_html_mapping_ambiguous"
    for owner in owners:
        audit = owner.repair_audit if hasattr(owner, "repair_audit") else owner.raw
        audit.setdefault("engineering_vlm_original_text", _source(owner))
        audit.update(confidence_source="ppocr", selected_confidence=None)
        if not owner.source_text:
            owner.source_text = owner.text
        owner.text = text
    for table, html in updates:
        table.html = html
    return "selected"


def _publish_group(report, group):
    region = group["region"]
    rows = {r.get("id"): r for r in report.setdefault("regions", [])}
    for identity, owner, box, quad, kind in group["targets"]:
        row = {**deepcopy(region), "id": identity, "bbox": list(box), "source_quad": list(quad),
               "geometry_kind": kind, "source_text": _source(owner)}
        if identity in rows:
            rows[identity].update(row)
            row = rows[identity]
        else:
            report["regions"].append(row)
        if kind == "formula":
            group["formula_block"].raw["engineering_review"] = deepcopy(row)
        elif hasattr(owner, "repair_audit"):
            owner.repair_audit["engineering_review"] = deepcopy(row)
        else:
            owner.raw["engineering_review"] = deepcopy(row)
            for line in getattr(owner, "text_lines", []):
                if _source(line) == _source(owner):
                    line.repair_audit["engineering_review"] = deepcopy(row)


def _apply_engineering_vlm_fallback(page, image, *, mode="off", runner=None, config=None):
    """Enrich engineering review and optionally select unverified local readings.

    ``runner(crop, *, model, task, max_new_tokens, timeout_seconds)`` returns a
    dict containing status, text, raw_output, model identity and timings. The
    runner must enforce a hard per-request timeout. All routing is answer blind.
    ``config`` accepts EngineeringVLMConfig, settings attributes, or a dict.
    """
    if mode not in {"off", "evidence", "conditional"}:
        raise ValueError("vlm_fallback must be off, evidence or conditional")
    if mode == "off":
        return {"mode": "off", "status": "disabled", "checked_regions": 0}
    cfg = EngineeringVLMConfig.from_value(config)
    clock = config.get("clock", time.perf_counter) if isinstance(config, dict) else time.perf_counter
    started = clock()
    report = page.metadata.setdefault("engineering_review", {
        "version": 2, "regions": [], "unique_regions": [], "issues": [], "needs_review": False})
    summary = {"version": 1, "mode": mode, "status": "completed", "experimental": True,
               "routing_policy_version": routing_policy_version(cfg.routing_order),
               "routing_order": cfg.routing_order,
               "validation_status": "machine_selected_unverified", "checked_regions": 0,
               "selected_regions": 0, "request_count": 0, "generation_count": 0,
               "cache_hits": 0, "runner_cache_hits": 0,
               "skipped_after_model_failure_requests": 0, "model_failures": {},
               "budget_exhausted_regions": 0, "load_seconds": 0., "regions": [],
               "configured_limits": {field.name: getattr(cfg, field.name) for field in fields(cfg)},
               "budget_type": "hard_worker_request_timeout_warm_page_budget"}
    report["vlm_fallback"] = summary
    work, all_groups = _collect(page, report, image, routing_order=cfg.routing_order,
                               shared_candidate_pool=cfg.shared_candidate_pool)
    if runner is None and work:
        try:
            from ocr_engine.vlm_region_runner import build_region_vlm_runner
            runner = build_region_vlm_runner(config)
        except Exception as error:
            summary["runner_initialization_error"] = type(error).__name__
    summary["eligible_regions"] = len(work)
    summary["completeness_only_regions"] = sum(group["priority"] == 2 for group in work)
    summary["skipped_stable_regions"] = len(all_groups) - sum(g["formula_block"] is None and bool(g["targets"]) for g in work)
    cells = [target[2] for group in all_groups for target in group["targets"] if target[4] == "cell"]
    cache = {}  # Request-local: no page, model or tenant can inherit stale evidence.
    disabled_models = {}  # A failed native worker must not reload for each region.
    spent = 0.

    def remaining():
        return cfg.seconds - max(spent, clock()-started-summary["load_seconds"])

    def observe(group, model, view):
        nonlocal spent
        name, pixels, box, rotation = view
        payload = {"source": "vlm", "view": name, "crop_bbox": list(box),
                   "rotation_degrees": rotation, "unique_region_id": group["id"],
                   "task": group["task"], "requested_model": model, "confidence": None,
                   "selected_confidence": None, "status": "invalid_crop"}
        if pixels is None or not pixels.size:
            return payload
        if pixels.shape[0]*pixels.shape[1] > cfg.max_crop_pixels:
            return {**payload, "status": "crop_pixel_budget_exhausted"}
        tokens = cfg.formula_max_tokens if group["task"] == "formula" else cfg.text_max_tokens
        digest = hashlib.sha256(pixels.tobytes()).hexdigest()
        key = (model, group["task"], tokens, digest, pixels.shape)
        payload["image_sha256"] = digest
        payload["pixel_shape"] = list(pixels.shape)
        if model in disabled_models:
            summary["skipped_after_model_failure_requests"] += 1
            failed = disabled_models[model]
            return {**payload, "status": "skipped_after_model_failure",
                    "inference_executed": False, "failure_status": failed["status"],
                    "failure_reason": failed.get("error", failed["status"]),
                    "model": deepcopy(failed.get("model", {})),
                    "failure_region_id": failed.get("unique_region_id"),
                    "failure_view": failed.get("view")}
        if key in cache:
            summary["cache_hits"] += 1
            return {**deepcopy(cache[key]), **payload, "status": cache[key]["status"], "cache_hit": True,
                    "cached_generation_seconds": cache[key].get("elapsed_seconds"),
                    "elapsed_seconds": 0., "load_seconds": 0., "inference_executed": False}
        available = remaining()
        if available <= 0:
            return {**payload, "status": "page_budget_exhausted"}
        if runner is None:
            return {**payload, "status": "runner_unavailable"}
        timeout = min(cfg.request_seconds, available)
        before = clock()
        summary["request_count"] += 1
        try:
            result = runner(pixels, model=model, task=group["task"],
                            max_new_tokens=tokens, timeout_seconds=timeout)
            if not isinstance(result, dict):
                result = {"status": "invalid_response"}
            result = deepcopy(result)
            if result.get("cache_hit"):
                summary["runner_cache_hits"] += 1
                summary["cache_hits"] += 1
            elif result.get("inference_executed", True):
                summary["generation_count"] += 1
        except TimeoutError:
            result = {"status": "timeout"}
        except Exception as error:
            result = {"status": "error", "error_type": type(error).__name__}
        wall = max(0., clock()-before)
        load = max(0., min(wall, float(result.get("load_seconds", 0.) or 0.)))
        if result.get("cache_hit"):
            result["cached_generation_seconds"] = result.get("cached_generation_seconds", result.get("elapsed_seconds"))
            result["inference_executed"] = False
        elapsed = max(wall-load, 0. if result.get("cache_hit") else float(result.get("elapsed_seconds", 0.) or 0.))
        summary["load_seconds"] += load
        spent += elapsed
        result.update(payload, status=_valid_output(result, group["task"]),
                      elapsed_seconds=elapsed, load_seconds=load)
        if elapsed > timeout + .05 and result["status"] == "ok":
            result["status"] = "timeout"
        if result["status"] in {"error", "timeout"} and result.get("error") not in {
                "empty_output", "invalid_output", "invalid_crop"}:
            disabled_models[model] = deepcopy(result)
            summary["model_failures"][model] = {
                key: deepcopy(result[key]) for key in (
                    "status", "error", "error_type", "model", "unique_region_id", "view") if key in result}
        if result["status"] == "ok":
            result["text"] = result["text"].strip()
        cache[key] = deepcopy(result)
        return result

    for rank, group in enumerate(work, 1):
        region = group["region"]
        prior_calls, prior_spent = summary["request_count"], spent
        prior_candidates = len(region.get("candidates", []))
        selection = {"unique_region_id": group["id"], "trigger_reasons": list(region.get("risks", [])),
                     "rank": rank, "within_region_budget": rank <= cfg.max_regions,
                     "bbox": list(group["bbox"]),
                     "geometry_kinds": sorted({target[4] for target in group.get("targets", [])}) or ["detected_region"],
                     "routing_evidence": deepcopy(group["routing_evidence"]),
                     "priority": group["priority"], "status": "candidate_only", "needs_review": True,
                     "source_text": region.get("source_text", ""), "selected_text": None,
                     "selected_confidence": None, "confidence_owner": "original_pp_ocr",
                     "validation_status": "machine_selected_unverified"}
        region["vlm_fallback"] = selection
        region["needs_review"] = True
        summary["regions"].append(selection)
        if rank > cfg.max_regions or remaining() <= 0:
            selection["status"] = "region_budget_exhausted" if rank > cfg.max_regions else "page_budget_exhausted"
            summary["budget_exhausted_regions"] += 1
        elif not _safe_box(group["bbox"], image):
            selection["status"] = "original_geometry_unavailable"
        else:
            summary["checked_regions"] += 1
            views = list(_views(group, image, report.get("annotation_groups", []), cells))
            observations = [observe(group, cfg.primary_model, view) for view in views]
            region.setdefault("candidates", []).extend(observations)
            failure = next((o["status"] for o in observations if o["status"] != "ok"), None)
            if failure:
                selection["status"] = failure
            elif observations[0]["text"] != observations[1]["text"]:
                selection["status"] = "view_disagreement"
            else:
                proposed = observations[0]["text"]
                selection["candidate_text"] = proposed
                source = str(region.get("source_text", ""))
                identities = [_weight(o) for o in observations]
                distinct_views = ((observations[0].get("image_sha256"), observations[0].get("pixel_shape"))
                                  != (observations[1].get("image_sha256"), observations[1].get("pixel_shape")))
                selection["distinct_source_views"] = distinct_views
                fragment = any(part.get("region_id") == group["id"]
                               for annotation in report.get("annotation_groups", [])
                               for part in annotation.get("parts", []))
                if fragment and (not NUMBER.fullmatch(proposed.replace(" ", ""))
                                 or re.search(r"\d\s+\d", proposed)):
                    selection["status"] = "multiple_annotation_output"
                elif not identities[0] or identities[0] != identities[1]:
                    selection["status"] = "weight_identity_unverified"
                elif proposed == source:
                    selection["status"] = "unchanged_unverified"
                elif not distinct_views:
                    selection["status"] = "insufficient_distinct_views"
                else:
                    critical = _critical_change(source, proposed, group["task"])
                    selection["critical_change"] = critical
                    if critical:
                        checks = [observe(group, cfg.verifier_model, view) for view in views]
                        region["candidates"].extend(checks)
                        if any(o["status"] != "ok" for o in checks):
                            selection["status"] = next(o["status"] for o in checks if o["status"] != "ok")
                        elif any(o["text"] != proposed for o in checks):
                            selection["status"] = "independent_model_disagreement"
                        elif not _weight(checks[0]) or _weight(checks[0]) != _weight(checks[1]) or _weight(checks[0]) == identities[0]:
                            selection["status"] = "independent_weight_identity_unverified"
                        else:
                            selection["status"] = "eligible_unverified"
                    else:
                        selection["status"] = "eligible_unverified"
                    if selection["status"] == "eligible_unverified" and mode == "conditional":
                        # An expanded view containing another independent region
                        # cannot uniquely attribute all returned glyphs.
                        box = views[1][2]
                        neighbors = [other for other in all_groups if other["id"] != group["id"]
                                     and box[0] <= (other["bbox"][0]+other["bbox"][2])/2 <= box[2]
                                     and box[1] <= (other["bbox"][1]+other["bbox"][3])/2 <= box[3]]
                        outcome = "expanded_crop_contains_neighbor" if neighbors else _apply_choice(page, group, proposed)
                        selection["status"] = outcome
                        if outcome == "selected":
                            selection.update(selected_text=proposed, selected_source="vlm",
                                             selection_reason="independent_views_and_weights" if critical else "independent_views")
                            summary["selected_regions"] += 1
        observations = region.get("candidates", [])[prior_candidates:]
        selection.update(request_count=summary["request_count"]-prior_calls,
                         elapsed_seconds=max(0., spent-prior_spent),
                         invocation_completed=bool(observations) and all(
                             o.get("status") == "ok" for o in observations) and any(
                             o.get("inference_executed", True) and not o.get("cache_hit") for o in observations),
                         budget_skip_reason=selection["status"] if "budget_exhausted" in selection["status"] else None)
        region["resolution"] = "vlm_" + selection["status"]
        _publish_group(report, group)

    report["annotation_groups"] = compose_reviewed_annotations(
        report.get("annotation_groups", []), report.get("unique_regions", []))
    if work:
        report.update(needs_review=True, status="needs_review", experimental=True)
    summary["elapsed_seconds"] = round(max(spent, clock()-started-summary["load_seconds"]), 4)
    summary["wall_seconds"] = round(clock()-started, 4)
    timing = page.metadata.setdefault("timing", {})
    timing["engineering_vlm_fallback"] = summary["wall_seconds"]
    timing["total"] = round(float(timing.get("total", 0.)) + summary["wall_seconds"], 4)
    return summary


def apply_engineering_vlm_fallback(page, image, *, mode="off", runner=None, config=None):
    """Fail closed around optional VLM work without dropping the PP OCR page."""
    if mode not in {"off", "evidence", "conditional"}:
        raise ValueError("vlm_fallback must be off, evidence or conditional")
    try:
        return _apply_engineering_vlm_fallback(page, image, mode=mode, runner=runner, config=config)
    except Exception as error:
        report = page.metadata.setdefault("engineering_review", {})
        report.update(needs_review=True, status="needs_review", experimental=True)
        report["issues"] = list(dict.fromkeys([*report.get("issues", []), "vlm_fallback_failed"]))
        summary = report.setdefault("vlm_fallback", {})
        summary.update(mode=mode, status="failed", needs_review=True, error_type=type(error).__name__)
        return summary
