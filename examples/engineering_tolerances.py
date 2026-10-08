"""Selected production geometry only: associate literal tolerance fragments.

This example does not load OCR models, classify glyphs, repair signs, or decide
whether a drawing is acceptable. Input groups contain observed OCR text/boxes.
"""
import re
from itertools import islice, product

NUMBER = re.compile(r"^[Ø⌀∅Φφ]?[+\-−]?(?:\d+(?:[.,]\d*)?|[.,]\d+)$")


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
