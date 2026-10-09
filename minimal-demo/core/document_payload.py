"""Public table structure without image bytes or mutable internal OCR objects."""

from __future__ import annotations


def original_ocr_text(owner):
    """Retain even an empty first transcription after optional VLM selection."""
    audit = getattr(owner, "repair_audit", None) or getattr(owner, "raw", None) or {}
    if "engineering_vlm_original_text" in audit:
        return audit["engineering_vlm_original_text"]
    return getattr(owner, "source_text", None) or owner.text


def text_confidence_source(owner):
    audit = getattr(owner, "repair_audit", None) or getattr(owner, "raw", None) or {}
    return str(audit.get("confidence_source") or "original_ocr")


def table_payload(block):
    table = getattr(block, "table", None)
    if table is None:
        return None
    dx, dy = block.bbox[:2]
    table_local = (getattr(table, "raw", {}) or {}).get("coordinate_space") == "crop_local"
    raw = getattr(block, "raw", {}) or {}
    cells = []
    for cell in table.cells:
        local = (getattr(cell, "raw", {}) or {}).get("coordinate_space", "crop_local" if table_local else "page") == "crop_local"
        ox, oy = (dx, dy) if local else (0, 0)
        x1, y1, x2, y2 = cell.bbox
        cells.append({
            "row": cell.row, "col": cell.col, "rowspan": cell.rowspan, "colspan": cell.colspan,
            "text": cell.text, "source_text": original_ocr_text(cell),
            "bbox": [x1 + ox, y1 + oy, x2 + ox, y2 + oy],
            "polygon": [[x + ox, y + oy] for x, y in cell.polygon],
            "is_header": cell.is_header, "confidence": float(cell.confidence), "source": cell.source,
            "confidence_source": text_confidence_source(cell),
            "engineering_review": (cell.raw or {}).get("engineering_review", {}),
        })
    return {
        "html": table.html, "rows": table.rows, "cols": table.cols, "cells": cells,
        "coordinate_space": "page",
        "x_edges": [x + (dx if table_local else 0) for x in table.x_edges],
        "y_edges": [y + (dy if table_local else 0) for y in table.y_edges],
        "rapidtable_polygons": [[[x + (dx if table_local else 0), y + (dy if table_local else 0)]
                                  for x, y in polygon] for polygon in table.rapidtable_polygons],
        "topology_confidence": float(table.topology_confidence),
        "topology_valid": bool(table.topology_valid), "topology_error": table.topology_error,
        "analysis_schema_version": table.analysis_schema_version,
        "render_mode": raw.get("table_render_mode"),
        "quality_score": raw.get("table_quality_score"),
        "source": raw.get("table_source"),
        "needs_verification": bool(raw.get("table_needs_verification", False)),
        "decision_reasons": list(raw.get("table_decision_reasons") or []),
        "candidates": list(raw.get("table_candidates") or []),
    }
