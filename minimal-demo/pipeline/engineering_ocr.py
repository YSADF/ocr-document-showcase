"""Bounded original-resolution OCR tiles with reversible geometry and provenance."""
from copy import deepcopy
import math
import time

from core.document_reading import block_line_views, overlap_ratio
from core.document_payload import table_payload
from models import BlockType, LayoutBlock


def tile_boxes(width, height, size=1536, overlap=192):
    if size < 64 or overlap < 0 or overlap >= size:
        raise ValueError("Invalid engineering tile size/overlap")

    def starts(length):
        points = list(range(0, max(1, length - size + 1), size - overlap))
        end = max(0, length - size)
        if points[-1] != end:
            points.append(end)
        return points

    for y in starts(height):
        for x in starts(width):
            yield x, y, min(width, x + size), min(height, y + size)


def positioned_lines(blocks):
    return [line for block in blocks for overlay in (False, True)
            for line in block_line_views(block, overlay=overlay) if line.text.strip()]


def same_region(left, right):
    """Require comparable extents; a superscript inside a dimension is not a copy."""
    def area(box):
        return max(1, box[2] - box[0]) * max(1, box[3] - box[1])
    ratio = area(left) / area(right)
    return .55 <= ratio <= 1.8 and overlap_ratio(left, right) >= .75


def _move_line(line, dx, dy):
    line = deepcopy(line)
    a, b, c, d = line.bbox
    line.bbox = (a + dx, b + dy, c + dx, d + dy)
    if line.source_quad:
        line.source_quad = tuple((x + dx, y + dy) for x, y in line.source_quad)
    if line.baseline_y is not None:
        line.baseline_y += dy
    for observation in line.character_observations:
        a, b, c, d = observation.bbox
        observation.bbox = (a + dx, b + dy, c + dx, d + dy)
        if observation.quad:
            observation.quad = tuple((x + dx, y + dy) for x, y in observation.quad)
        if observation.baseline_y is not None:
            observation.baseline_y += dy
    return line


def augment_engineering_tiles(image, blocks, *, recognize, settings, clock=time.perf_counter):
    started = clock()
    size = int(getattr(settings, "OCR_ENGINEERING_TILE_SIZE", 1536))
    overlap = int(getattr(settings, "OCR_ENGINEERING_TILE_OVERLAP", 192))
    maximum = max(1, int(getattr(settings, "OCR_ENGINEERING_MAX_TILES", 64)))
    seconds = max(1., float(getattr(settings, "OCR_ENGINEERING_TILE_SECONDS", 90)))
    height, width = image.shape[:2]
    boxes = list(tile_boxes(width, height, size, overlap))
    existing = positioned_lines(blocks)
    cells = [cell for block in blocks for cell in (table_payload(block) or {}).get("cells", [])]
    report = {"status": "checked", "tile_size": size, "overlap": overlap,
              "coordinate_space": "page", "tile_count": len(boxes), "completed_tiles": 0,
              "added_lines": 0, "conflicts": [], "issues": [], "model_receipts": [],
              "budget_type": "cooperative_between_native_calls", "needs_review": False}
    report.update(resolved_duplicate_count=0, clipped_candidate_count=0)
    additions = []
    # Even a small page gets one original-resolution pass: the ordinary path
    # may have selected native layout or resized the recognizer input.
    for index, (x1, y1, x2, y2) in enumerate(boxes):
        if index >= maximum or clock() - started >= seconds:
            report["issues"].append("tile_budget_exhausted")
            break
        try:
            result = recognize(image[y1:y2, x1:x2], False)
            tile_blocks = result[0]
            metadata = result[2] if len(result) > 2 else {}
            receipt = metadata.get("ocr_configuration") or {}
            if receipt and receipt not in report["model_receipts"]:
                report["model_receipts"].append(receipt)
            for candidate in positioned_lines(tile_blocks):
                if not math.isfinite(float(candidate.confidence)):
                    report["issues"].append("invalid_tile_confidence")
                    continue
                a, b, c, d = candidate.bbox
                if not (0 <= a < c <= x2-x1 and 0 <= b < d <= y2-y1):
                    report["issues"].append("invalid_tile_geometry")
                    continue
                # Do not accept clipped edge words as independent source text.
                if ((x1 and a < 3) or (y1 and b < 3)
                        or (x2 < width and c > x2-x1-3) or (y2 < height and d > y2-y1-3)):
                    report["clipped_candidate_count"] += 1
                    continue
                candidate = _move_line(candidate, x1, y1)
                matches = [line for line in existing if same_region(line.bbox, candidate.bbox)]
                key = " ".join(candidate.text.split())
                if any(" ".join(line.text.split()) == key for line in matches):
                    report["resolved_duplicate_count"] += 1
                    continue
                # Independent table OCR may have cells without text_lines. Keep
                # their text in the table and retain tile discrepancies as evidence.
                a, b, c, d = candidate.bbox
                cell_matches = [cell for cell in cells if
                    max(0, min(c, cell["bbox"][2])-max(a, cell["bbox"][0])) *
                    max(0, min(d, cell["bbox"][3])-max(b, cell["bbox"][1])) / ((c-a)*(d-b)) >= .9]
                if cell_matches:
                    if not any(" ".join(str(cell["source_text"]).split()) == key for cell in cell_matches):
                        report["conflicts"].append({"bbox": list(candidate.bbox),
                            "source_text": cell_matches[0]["source_text"], "candidate_text": candidate.text,
                            "confidence": float(candidate.confidence), "tile": index,
                            "geometry_kind": "cell", "model": receipt})
                    continue
                if matches:
                    report["conflicts"].append({"bbox": list(candidate.bbox),
                        "source_text": matches[0].text, "candidate_text": candidate.text,
                        "confidence": float(candidate.confidence), "tile": index, "model": receipt})
                    # A conflict is evidence for review, never an automatic overwrite.
                    continue
                candidate.repair_audit["engineering_tile"] = {
                    "tile": index, "tile_bbox": [x1, y1, x2, y2],
                    "initial_text": candidate.text, "coordinate_space": "page",
                    "confidence": float(candidate.confidence), "model": receipt}
                additions.append(LayoutBlock(BlockType.TEXT, candidate.bbox,
                    text_lines=[candidate], raw={"text_line_coordinate_space": "page",
                                               "engineering_tile": True}))
                existing.append(candidate)
                report["added_lines"] += 1
            report["completed_tiles"] += 1
        except Exception as error:
            report["issues"].append("tile_inference_failed:" + type(error).__name__)
    report["issues"] = list(dict.fromkeys(report["issues"]))
    report["needs_review"] = bool(report["issues"] or report["conflicts"])
    report["status"] = "needs_review" if report["needs_review"] else "checked"
    report["elapsed_seconds"] = round(clock()-started, 4)
    return [*blocks, *additions], report
