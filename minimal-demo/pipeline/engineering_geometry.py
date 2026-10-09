"""Image and spatial evidence for engineering review; never infer missing text."""
import math
import re
from itertools import islice, product

import cv2
import numpy as np

from pipeline.engineering_ocr import same_region


NUMBER = re.compile(r"^[Ø⌀∅Φφ]?[+\-−]?(?:\d+(?:[.,]\d*)?|[.,]\d+)$")


def normalized(text):
    return " ".join(str(text or "").split())


def numeric_annotation(text):
    text = normalized(text)
    return bool(NUMBER.fullmatch(text.replace(" ", "")) or re.search(
        r"[Ø⌀∅Φφ±°]|(?:\d|[.,]\d)\s*(?:mm|cm|µm|μm)\b|\b(?:REAM|BORE|THRU|REF|RAD|HOLES?)\b", text, re.I))


def deduplicate_targets(targets):
    """Share one review for compatible geometry, retaining every mutable owner.

    Text conflicts remain in the group. Containment alone is insufficient: a
    tolerance inside a larger dimension/cell must remain a separate target.
    """
    groups = []
    for target in targets:
        identity, owner, bbox, quad, kind = target
        text = normalized(owner.source_text or owner.text)
        angle = float(getattr(owner, "text_angle", 0)) % 180
        match = next((g for g in groups if same_region(g["bbox"], bbox)
                      and min(abs(g["angle"]-angle), 180-abs(g["angle"]-angle)) <= 10), None)
        if match is None:
            match = {"id": f"engineering-region:{len(groups)}", "bbox": list(bbox),
                     "angle": angle, "members": [], "texts": [], "targets": []}
            groups.append(match)
        match["targets"].append(target)
        match["members"].append(identity)
        if text not in match["texts"]:
            match["texts"].append(text)
        for alternative in (getattr(owner, "raw", {}) or {}).get("engineering_alternatives", []):
            value = normalized(alternative.get("candidate_text"))
            if value and value not in match["texts"]:
                match["texts"].append(value)
    return groups


def expanded_box(bbox, shape):
    height, width = shape[:2]
    a, b, c, d = map(float, bbox)
    h = max(1., min(d-b, c-a))
    return [max(0, math.floor(a-h*.65)), max(0, math.floor(b-h*.55)),
            min(width, math.ceil(c+h*.35)), min(height, math.ceil(d+h*.55))]


def ink_evidence(image, bbox):
    """Find unexplained ink near a detected number, not a Unicode classifier.

    Both in-box leading components and outside-box components are retained;
    an OCR box can include the diameter glyph while its decoder drops it.
    """
    result = {"status": "unavailable", "components": [], "issues": [],
              "semantic_classification": False}
    if image is None or len(bbox) != 4 or not all(math.isfinite(float(x)) for x in bbox):
        return result
    h, w = image.shape[:2]
    a, b, c, d = map(float, bbox)
    if not (0 <= a < c <= w and 0 <= b < d <= h):
        return result
    expanded = expanded_box(bbox, image.shape)
    x1, y1, x2, y2 = expanded
    result["expanded_bbox"] = expanded
    if (x2-x1)*(y2-y1) > 1_000_000:
        result["status"] = "pixel_budget_exhausted"
        return result
    crop = image[y1:y2, x1:x2]
    gray = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY) if crop.ndim == 3 else crop
    ink = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)[1]
    if np.count_nonzero(ink) < 3 or np.mean(ink > 0) > .65:
        result["status"] = "insufficient_ink"
        return result
    count, _, stats, _ = cv2.connectedComponentsWithStats(ink, 8)
    line_height = max(3., min(d-b, c-a))
    for x, y, cw, ch, area in stats[1:]:
        if area < max(2, line_height*.025) or cw > line_height*2 or ch > line_height*1.7:
            continue  # Long drawing rules are not isolated character evidence.
        box = [int(x+x1), int(y+y1), int(x+x1+cw), int(y+y1+ch)]
        cx, cy = (box[0]+box[2])/2, (box[1]+box[3])/2
        outside = cx < a or cy < b or cy > d or cx > c
        leading = cx < a+line_height*.85 and b-line_height*.15 <= cy <= d+line_height*.15
        if not (outside or leading):
            continue
        result["components"].append({"bbox": box, "pixels": int(area),
                                      "location": "outside_detection" if outside else "leading_inside_detection"})
    result["status"] = "observed"
    if any(c["location"] == "outside_detection" for c in result["components"]):
        result["issues"].append("unexplained_neighbor_ink")
    if any(c["location"] == "leading_inside_detection" for c in result["components"]):
        result["issues"].append("leading_glyph_requires_verification")
    return result


def line_suppressed_view(crop):
    """Additional candidate only; never replace the original source pixels."""
    gray = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY) if crop.ndim == 3 else crop
    ink = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)[1]
    h, w = gray.shape
    mask = cv2.morphologyEx(ink, cv2.MORPH_OPEN, np.ones((1, max(24, int(w*.8))), np.uint8))
    # Do not suppress a line occupying a substantial part of a tiny symbol crop.
    fraction = np.count_nonzero(mask)/max(1, np.count_nonzero(ink))
    if not .01 < fraction < .25:
        return None
    result = crop.copy()
    result[mask > 0] = 255
    return result


def annotation_groups(groups, cell_boxes=()):
    """Associate nominal/upper/lower fragments; preserve literal signs and boxes."""
    result, used = [], set()

    def cell_id(box):
        x, y = (box[0]+box[2])/2, (box[1]+box[3])/2
        hits = [(i, b) for i, b in enumerate(cell_boxes) if b[0] <= x <= b[2] and b[1] <= y <= b[3]]
        return min(hits, key=lambda ib: (ib[1][2]-ib[1][0])*(ib[1][3]-ib[1][1]))[0] if hits else None

    for nominal in groups:
        value = nominal["texts"][0].replace(" ", "")
        if not NUMBER.fullmatch(value) or value.startswith(("+", "-", "−")) or nominal["id"] in used:
            continue
        a, b, c, d = nominal["bbox"]
        height = d-b
        if c-a < height*.8 or min(nominal["angle"], 180-nominal["angle"]) > 10:
            continue  # Only calibrated horizontal association in this revision.
        neighbors = []
        for candidate in groups:
            if candidate is nominal or candidate["id"] in used:
                continue
            if (not all(NUMBER.fullmatch(t.replace(" ", "")) for t in candidate["texts"])
                    # A single 0 can have a tall box and a spurious 90-degree
                    # angle. Its direction is ambiguous, not evidence of rotation.
                    or (len(candidate["texts"][0].replace(" ", "")) > 1
                        and min(abs(candidate["angle"]-nominal["angle"]),
                                180-abs(candidate["angle"]-nominal["angle"])) > 10)
                    or cell_id(candidate["bbox"]) != cell_id(nominal["bbox"])):
                continue
            x1, y1, x2, y2 = candidate["bbox"]
            if (.2*height <= y2-y1 <= 1.1*height and -.5*height <= x1-c <= 1.1*height
                    and b-.8*height <= (y1+y2)/2 <= d+.8*height):
                neighbors.append(candidate)
        if len(neighbors) != 2:
            continue
        upper, lower = sorted(neighbors, key=lambda g: g["bbox"][1])
        if (upper["bbox"][3] > lower["bbox"][1]+height*.45
                or (upper["bbox"][1]+upper["bbox"][3])/2 >= (b+d)/2-height*.1
                or (lower["bbox"][1]+lower["bbox"][3])/2 <= (b+d)/2+height*.1
                or abs(upper["bbox"][0]-lower["bbox"][0]) > height*.6
                or not any(g["texts"][0].lstrip().startswith(("+", "-", "−")) for g in neighbors)):
            continue
        parts = [{"region_id": g["id"], "role": role, "text": g["texts"][0], "bbox": g["bbox"],
                  "observed_alternatives": list(g["texts"])}
                 for g, role in ((nominal, "nominal"), (upper, "upper"), (lower, "lower"))]
        boxes = [p["bbox"] for p in parts]
        candidates = [" ".join(values) for values in islice(
            product(*(p["observed_alternatives"] for p in parts)), 8)]
        result.append({"id": f"engineering-annotation:{len(result)}", "kind": "stacked_tolerance",
                       "bbox": [min(x[0] for x in boxes), min(x[1] for x in boxes),
                                max(x[2] for x in boxes), max(x[3] for x in boxes)],
                       "parts": parts, "candidate_text": " ".join(p["text"] for p in parts),
                       "observed_candidates": candidates,
                       "needs_review": True, "reason": "spatial_association_only_no_inferred_signs"})
        used.update(g["id"] for g in (nominal, upper, lower))
    return result
