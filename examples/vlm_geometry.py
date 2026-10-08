"""Selected evidence/geometry contract only; no models, service, drawings, or automatic acceptance."""
import math
import json


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
