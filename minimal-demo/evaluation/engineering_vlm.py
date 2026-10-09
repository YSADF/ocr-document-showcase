"""Strict, evidence-preserving adapters for engineering VLM experiments."""
from collections import Counter
import hashlib
import json
import math
import re

from evaluation.engineering_metrics import CRITICAL, edit_counts, normalize


LOCAL_PROMPT = (
    "Transcribe all visible text in this image exactly. Preserve case, symbols, decimal points "
    "and signs. For stacked text, use nominal value, upper deviation, lower deviation order, "
    "separated by spaces. Do not infer or correct missing characters. Return only the transcription."
)
PAGE_PROMPT = (
    "Transcribe every visible text region exactly, including rotated text. Preserve all symbols "
    "and signs; do not infer missing characters. Return one JSON object, no markdown. "
    "Coordinates are [left,top,right,bottom] in the range 0..1000 relative to this image. "
    'Schema: {"regions":[{"text":"literal text","bbox":[0,0,1,1]}],'
    '"tables":[{"bbox":[0,0,1,1],"rows":1,"cols":1,"cells":'
    '[{"row":0,"col":0,"rowspan":1,"colspan":1,"text":"literal text","bbox":[0,0,1,1]}]}]}. '
    "Use zero-based row/col. Do not duplicate table cells in regions. Preserve separate visual "
    "lines and neighboring independent dimensions. Omit unreadable text rather than guessing."
)


def digest(value):
    raw = value if isinstance(value, bytes) else json.dumps(value, sort_keys=True, ensure_ascii=False).encode()
    return hashlib.sha256(raw).hexdigest()


def box_valid(box, width, height):
    return (isinstance(box, (list, tuple)) and len(box) == 4
            and all(isinstance(v, (int, float)) and math.isfinite(v) for v in box)
            and 0 <= box[0] < box[2] <= width and 0 <= box[1] < box[3] <= height)


def unwrap_json(text):
    text = text.strip()
    # Permit a single presentation fence, never salvage arbitrary embedded fragments.
    if text.startswith("```json\n") and text.endswith("```"):
        text = text[8:-3].strip()
    value = json.loads(text)
    if not isinstance(value, dict):
        raise ValueError("Expected a JSON object")
    return value


def table_geometry(table, width, height):
    """Validate complete cell occupancy and shared row/column boundaries."""
    if not isinstance(table, dict):
        return False
    rows, cols = table.get("rows"), table.get("cols")
    if (type(rows) is not int or type(cols) is not int or not 1 <= rows <= 200
            or not 1 <= cols <= 100 or not box_valid(table.get("bbox"), width, height)):
        return False
    cells = table.get("cells", [])
    if not isinstance(cells, list):
        return False
    occupied, xs, ys = set(), {}, {}
    a, b, c, d = table["bbox"]
    for cell in cells:
        if not isinstance(cell, dict):
            return False
        indexes = [cell.get(k) for k in ("row", "col", "rowspan", "colspan")]
        if any(type(v) is not int for v in indexes) or not box_valid(cell.get("bbox"), width, height):
            return False
        row, col, rs, cs = indexes
        x1, y1, x2, y2 = cell["bbox"]
        if not (0 <= row < row+rs <= rows and 0 <= col < col+cs <= cols
                and a <= x1 < x2 <= c and b <= y1 < y2 <= d):
            return False
        for r in range(row, row+rs):
            for q in range(col, col+cs):
                if (r, q) in occupied:
                    return False
                occupied.add((r, q))
        for values, index, coordinate, tolerance in (
                (xs, col, x1, (c-a)*.02), (xs, col+cs, x2, (c-a)*.02),
                (ys, row, y1, (d-b)*.02), (ys, row+rs, y2, (d-b)*.02)):
            if index in values and abs(values[index]-coordinate) > tolerance:
                return False
            values[index] = coordinate
    return (len(occupied) == rows*cols and len(xs) == cols+1 and len(ys) == rows+1
            and all(xs[i] < xs[i+1] for i in range(cols))
            and all(ys[i] < ys[i+1] for i in range(rows)))


def qwen_page(text, width, height):
    data = unwrap_json(text)
    if not isinstance(data.get("regions"), list) or not isinstance(data.get("tables"), list):
        raise ValueError("Missing regions/tables arrays")
    output = {"lines": [], "tables": [], "issues": []}
    def scale(box):
        if not box_valid(box, 1000, 1000):
            raise ValueError("Invalid normalized geometry")
        return [box[0]*width/1000, box[1]*height/1000, box[2]*width/1000, box[3]*height/1000]
    for region in data["regions"]:
        if not isinstance(region, dict) or not isinstance(region.get("text"), str):
            raise ValueError("Invalid region text")
        output["lines"].append({"text": region["text"], "bbox": scale(region["bbox"]),
                                "geometry_source": "model_predicted"})
    for table in data["tables"]:
        if not isinstance(table, dict) or not isinstance(table.get("cells"), list):
            raise ValueError("Invalid table schema")
        valid = table_geometry(table, 1000, 1000)
        converted = {**table, "bbox": scale(table["bbox"]), "cells": [],
                     "topology_valid": valid, "geometry_source": "model_predicted"}
        for cell in table.get("cells", []):
            if not isinstance(cell, dict) or not isinstance(cell.get("text"), str):
                raise ValueError("Invalid cell text")
            converted["cells"].append({**cell, "bbox": scale(cell["bbox"]),
                                       "geometry_source": "model_predicted"})
        if not valid:
            output["issues"].append("table_geometry_invalid")
        output["tables"].append(converted)
    return output


def paddle_page(raw, width, height):
    """Keep PP-DocLayout block geometry; never divide it into synthetic lines."""
    output = {"lines": [], "tables": [], "issues": []}
    for payload in raw:
        data = payload.get("res", payload)
        for block in data.get("parsing_res_list", []):
            box = block.get("block_bbox", block.get("bbox"))
            text = block.get("block_content", block.get("text", ""))
            kind = block.get("block_label", block.get("label", "text"))
            if not box_valid(box, width, height):
                output["issues"].append("native_block_geometry_unavailable")
                continue
            if kind == "table":
                # HTML alone has no cell positions. Keep it for separate structure review.
                output["tables"].append({"bbox": box, "raw_html": text, "cells": [],
                    "topology_valid": False, "geometry_source": "detector_aligned",
                    "geometry_model": "PP-DocLayoutV3", "geometry_granularity": "block"})
                output["issues"].append("native_table_cell_geometry_unavailable")
            elif text:
                output["lines"].append({"text": str(text), "bbox": box,
                    "geometry_source": "detector_aligned", "geometry_granularity": "block",
                    "geometry_model": "PP-DocLayoutV3"})
    return output


def adapted_response(output, width, height):
    """Only measured/predicted geometry participates in strict region scoring."""
    regions = []
    for line in output.get("lines", []):
        if line.get("geometry_source") not in {"model_predicted", "detector_aligned"}:
            continue
        regions.append({"text_lines": [{**line, "source_text": line["text"],
            "engineering_review": {"needs_review": True}}]})
    for table in output.get("tables", []):
        if table.get("topology_valid") and table.get("geometry_source") != "synthetic":
            regions.append({"table": {**table, "cells": [
                {**cell, "source_text": cell["text"], "engineering_review": {"needs_review": True}}
                for cell in table["cells"]]}})
    return {"ocr_scene": "engineering", "needs_review": True, "disposition": "review",
            "pages": [{"width": width, "height": height, "regions": regions,
                       "engineering_review": {"needs_review": True, "experimental": True,
                                               "issues": output.get("issues", [])}}]}


def literal_score(reference, predicted):
    reference, predicted = normalize(reference), normalize(predicted)
    edits, _ = edit_counts(reference, predicted)
    critical_errors, _ = edit_counts("".join(c for c in reference if c in CRITICAL),
                                    "".join(c for c in predicted if c in CRITICAL))
    expected, actual = Counter(c for c in reference if c in CRITICAL), Counter(c for c in predicted if c in CRITICAL)
    return {"exact": reference == predicted, "edits": edits, "reference_characters": len(reference),
            "critical_errors": critical_errors, "critical_characters": sum(expected.values()),
            "inserted_critical": dict(actual-expected), "missing_critical": dict(expected-actual)}


def plain_paddle_text(raw):
    return " ".join(str(block.get("block_content", "")) for payload in raw
                    for block in payload.get("res", payload).get("parsing_res_list", []))


def safe_id(value):
    if not re.fullmatch(r"[A-Za-z0-9_.-]+", value) or value in {".", ".."}:
        raise ValueError("Unsafe sample identifier")
    return value
