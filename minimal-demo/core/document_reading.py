"""Non-mutating, page-scoped reading views shared by OCR exports and diagnostics."""

from __future__ import annotations

from collections import defaultdict
from copy import copy
from dataclasses import dataclass
import math
from types import SimpleNamespace
import unicodedata


_ASCII_WIDTH_EQUIVALENTS = {code: code - 0xFEE0 for code in range(0xFF01, 0xFF5F)}


def overlap_ratio(left, right):
    """Intersection over the smaller rectangle, not intersection over union."""
    width = max(0, min(left[2], right[2]) - max(left[0], right[0]))
    height = max(0, min(left[3], right[3]) - max(left[1], right[1]))
    area = min(max(0, left[2] - left[0]) * max(0, left[3] - left[1]),
               max(0, right[2] - right[0]) * max(0, right[3] - right[1]))
    return width * height / area if area else 0.0


def _identity(line):
    # Detector copies may differ only in fullwidth ASCII (e.g. U+FF0D vs '-').
    # This is an equality key, never a rewrite of visible/source text. Avoid NFKC:
    # superscripts, circled numbers and other compatibility symbols stay distinct.
    text = str(getattr(line, "source_text", "") or line.text or "")
    return " ".join(text.translate(_ASCII_WIDTH_EQUIVALENTS).split())


def _is_rtl(blocks):
    return _lines_are_rtl(line for block in blocks
                          for line in ([line for line in _raw_lines(block) if _identity(line)]
                                       or [item[0] for item in _table_fallback_views(block)]))


def _lines_are_rtl(lines):
    directions = [unicodedata.bidirectional(char) for line in lines for char in _identity(line)]
    return sum(value in ("R", "AL") for value in directions) > directions.count("L")


def _raw_lines(block):
    image = getattr(block, "image", None)
    return list(block.text_lines or []) + list(getattr(image, "overlay_text", []) or [])


def _groups(items, axis, gap):
    groups = []
    edge = float("-inf")
    for item in sorted(items, key=lambda value: value.bbox[axis]):
        if not groups or item.bbox[axis] > edge + gap:
            groups.append([])
        groups[-1].append(item)
        edge = max(edge, item.bbox[axis + 2])
    return groups


def _geometric_order(items, rtl=False):
    if len(items) < 2:
        return list(items)
    extent = max(item.bbox[2] for item in items) - min(item.bbox[0] for item in items)
    columns = _groups(items, 0, max(12, extent * 0.025))
    if len(columns) > 1:
        # Vertically disjoint blocks are paragraphs, not side-by-side columns.
        spans = [(min(item.bbox[1] for item in group), max(item.bbox[3] for item in group))
                 for group in columns]
        shared_y = min(span[1] for span in spans) - max(span[0] for span in spans)
        if shared_y > 0:
            if rtl:
                columns.reverse()
            return [item for group in columns for item in _geometric_order(group, rtl)]
    bands = _groups(items, 1, 6)
    if len(bands) > 1:
        return [item for group in bands for item in _geometric_order(group, rtl)]
    return sorted(items, key=lambda item: (item.bbox[1], -item.bbox[2] if rtl else item.bbox[0]))


def ordered_blocks(blocks):
    """Preserve explicit order (including zero); otherwise apply conservative XY cuts."""
    blocks = list(blocks)

    def order_value(value):
        try:
            number = float(value)
            return number if math.isfinite(number) else None
        except (TypeError, ValueError):
            return None

    def raw_order(block):
        raw = getattr(block, "raw", {}) or {}
        for key in ("reading_order", "block_order", "parsing_order"):
            value = order_value(raw.get(key))
            if value is not None:
                return value
        return None

    explicit = [raw_order(block) for block in blocks]
    legacy = [order_value(getattr(block, "order", 0)) for block in blocks]
    if not any(value is not None for value in explicit) and any(value not in (None, 0) for value in legacy):
        # Legacy producers set .order on every block, but cannot distinguish an
        # intentionally assigned zero from the dataclass default.
        explicit = legacy
    else:
        explicit = [value if value is not None else (old if old not in (None, 0) else None)
                    for value, old in zip(explicit, legacy)]
    anchors = sorted((index for index, value in enumerate(explicit) if value is not None),
                     key=lambda index: explicit[index])
    geometric = _geometric_order(blocks, _is_rtl(blocks))
    if not anchors:
        return geometric
    if len(anchors) == len(blocks):
        return [blocks[index] for index in anchors]

    ranks = {id(block): rank for rank, block in enumerate(geometric)}
    anchor_ranks = [ranks[id(blocks[index])] for index in anchors]
    unmarked = {id(blocks[index]) for index, value in enumerate(explicit) if value is None}
    slots = [[] for _ in range(len(anchors) + 1)]
    previous_slot = 0
    for block in geometric:
        if id(block) not in unmarked:
            continue
        rank = ranks[id(block)]
        # Insert without ever reversing explicit anchors. Among valid boundaries,
        # minimize disagreements with geometry; preserve unmarked geometric order.
        cost = sum(value < rank for value in anchor_ranks)
        costs = [cost]
        for value in anchor_ranks:
            cost += 1 if value > rank else -1
            costs.append(cost)
        slot = min(range(previous_slot, len(slots)), key=lambda index: (costs[index], index))
        slots[slot].append(block)
        previous_slot = slot
    output = list(slots[0])
    for position, index in enumerate(anchors, start=1):
        output.extend([blocks[index], *slots[position]])
    return output


def _row_order(entries, box, rtl):
    """Read a visual baseline horizontally despite a few pixels of OCR jitter.

    Each band retains the common vertical intersection, so a tall box cannot
    transitively join successive rows. This only orders lines inside one region;
    explicit block order and page column ordering remain authoritative.
    """
    rows = []
    for entry in sorted(entries, key=lambda item: box(item)[1]):
        bounds = box(entry)
        height = max(1, bounds[3] - bounds[1])
        if rows:
            row, top, bottom, reference_height = rows[-1]
            overlap = min(bottom, bounds[3]) - max(top, bounds[1])
            if overlap >= 0.5 * min(height, reference_height):
                row.append(entry)
                rows[-1] = (row, max(top, bounds[1]), min(bottom, bounds[3]),
                            min(reference_height, height))
                continue
        rows.append(([entry], bounds[1], bounds[3], height))
    return [entry for row, *_ in rows for entry in sorted(
        row, key=lambda item: (-box(item)[2] if rtl else box(item)[0], box(item)[1])
    )]


def block_line_views(block, *, overlay=False):
    """Return page-coordinate lines without modifying shared OCR or rendering objects."""
    raw = getattr(block, "raw", {}) or {}
    image = getattr(block, "image", None)
    lines = list(getattr(image, "overlay_text", []) or []) if overlay else list(block.text_lines or [])
    key = "image_overlay_coordinate_space" if overlay else "text_line_coordinate_space"
    local = raw.get(key) == "crop_local"
    if not overlay and raw.get("image_table_lines_page_coords"):
        local = False
    if not local:
        return lines
    dx, dy = block.bbox[:2]
    views = []
    for line in lines:
        view = copy(line)
        x1, y1, x2, y2 = line.bbox
        view.bbox = (x1 + dx, y1 + dy, x2 + dx, y2 + dy)
        if getattr(line, "source_quad", ()):
            view.source_quad = tuple((x + dx, y + dy) for x, y in line.source_quad)
        if getattr(line, "baseline_y", None) is not None:
            view.baseline_y = line.baseline_y + dy
        if hasattr(line, "repair_audit"):
            from core.ocr_provenance import offset_source_audit
            view.repair_audit = {**offset_source_audit(line,(dx,dy)), "output_coordinate_space": "page"}
        views.append(view)
    return views


@dataclass
class _Entry:
    line: object
    owner: int
    cell: tuple | None


def _cell_page_box(block, cell):
    box = tuple(cell.bbox)
    if (getattr(cell, "raw", {}) or {}).get("coordinate_space") == "crop_local":
        dx, dy = block.bbox[:2]
        box = (box[0] + dx, box[1] + dy, box[2] + dx, box[3] + dy)
    return box


def document_orientation(metadata):
    """Read the same page diagnostic from direct or OCR layout metadata."""
    metadata = metadata if isinstance(metadata, dict) else {}
    report = metadata.get("document_orientation")
    if not isinstance(report, dict) or not report:
        layout = metadata.get("layout_engine")
        report = layout.get("document_orientation") if isinstance(layout, dict) else None
    return report if isinstance(report, dict) else {}


def _reading_box(box, page):
    """Project only a sorting key to upright space; keep all source objects intact."""
    metadata = getattr(page, "metadata", {}) or {}
    report = document_orientation(metadata)
    if (report.get("status") != "accepted" or not report.get("applied_to_reading")
            or report.get("coordinate_space") != "original_page"
            or (report.get("pixel_transform_applied") and not report.get("coordinates_restored_to_original"))):
        return box
    angle = report.get("source_clockwise_degrees")
    width, height = getattr(page, "width", 0), getattr(page, "height", 0)
    if width <= 0 or height <= 0:
        return box
    x1, y1, x2, y2 = box
    if angle == 90:
        return (y1, width - x2, y2, width - x1)
    if angle == 180:
        return (width - x2, height - y2, width - x1, height - y1)
    if angle == 270:
        return (height - y2, x1, height - y1, x2)
    return box


def _table_fallback_views(block):
    """Cell/HTML text is a last resort when the block has no direct/overlay text.

    Synthetic views carry cell or enclosing-table geometry, never invented word
    boxes. They are not attached to the source table or used for image rendering.
    """
    from models import TextLine
    from core.document_payload import original_ocr_text

    table = getattr(block, "table", None)
    if table is None:
        return []
    output = []
    for cell in table.cells or []:
        cell_lines = [line for line in (cell.text_lines or []) if _identity(line)]
        if cell_lines:
            owner = copy(block)
            owner.text_lines = cell_lines
            owner.raw = {**(getattr(block, "raw", {}) or {})}
            space = (cell.raw or {}).get("text_line_coordinate_space") or (table.raw or {}).get("text_line_coordinate_space")
            if space:
                owner.raw["text_line_coordinate_space"] = space
                owner.raw.pop("image_table_lines_page_coords", None)
            output.extend((line, (cell.row, cell.col)) for line in block_line_views(owner) if _identity(line))
            continue
        text = str(cell.text or cell.source_text or "")
        if not text.strip():
            continue
        box = _cell_page_box(block, cell)
        valid = box[2] > box[0] and box[3] > box[1]
        output.append((TextLine(text=text, source_text=original_ocr_text(cell),
                               bbox=box if valid else block.bbox, confidence=cell.confidence,
                               repair_audit={**{key: value for key, value in (cell.raw or {}).items()
                                               if key in {"engineering_review", "engineering_vlm_original_text", "confidence_source", "selected_confidence"}},
                                             "reading_view_source": "table_cell",
                                             "geometry_kind": "cell" if valid else "enclosing_table",
                                             "output_coordinate_space": "page"}), (cell.row, cell.col)))
    if output or not table.html:
        return output
    try:
        from render.word import _parse_html_table

        rows = _parse_html_table(table.html)
    except (TypeError, ValueError, IndexError):
        return []
    for r, row in enumerate(rows):
        for c, cell in enumerate(row):
            text = str(cell.get("text") or "")
            if cell.get("_skip") or not text.strip():
                continue
            output.append((TextLine(text=text, source_text=text, bbox=block.bbox, confidence=0.0,
                                   repair_audit={"reading_view_source": "table_html",
                                                 "geometry_kind": "enclosing_table",
                                                 "output_coordinate_space": "page"}), (r, c)))
    return output


def page_reading_groups(page):
    """Canonical visible lines, scoped to one page and ordered by region and cell."""
    blocks = list(page.blocks or [])
    cells = []
    source_cells = {}
    for index, block in enumerate(blocks):
        table = getattr(block, "table", None)
        for cell in getattr(table, "cells", []) or []:
            key = (index, cell.row, cell.col)
            box = _cell_page_box(block, cell)
            cells.append((key, box))
            for line in cell.text_lines:
                source_cells[id(line)] = key

    def cell_for(original, view):
        if id(original) in source_cells:
            return source_cells[id(original)]
        cx, cy = (view.bbox[0] + view.bbox[2]) / 2, (view.bbox[1] + view.bbox[3]) / 2
        matches = [(key, box) for key, box in cells
                   if box[0] <= cx < box[2] and box[1] <= cy < box[3]]
        return min(matches, key=lambda pair: (pair[1][2] - pair[1][0]) *
                   (pair[1][3] - pair[1][1]))[0] if matches else None

    entries = []
    by_text = defaultdict(list)

    def add_line(index, original, line, explicit_cell=None):
        text = _identity(line)
        if not text:
            return
        cell = explicit_cell if explicit_cell is not None else cell_for(original, line)
        # A confirmed table cell owns its reading position even if an overlapping
        # list/text detector supplied the first or highest-confidence observation.
        owner = cell[0] if cell is not None and getattr(blocks[cell[0]], "table", None) is not None else index
        duplicate = None
        for candidate in by_text[text]:
            if cell is not None and candidate.cell is not None and cell != candidate.cell:
                continue
            if candidate.owner != index and not overlap_ratio(blocks[index].bbox, blocks[candidate.owner].bbox):
                continue
            same_id = bool(getattr(line, "stable_id", "")) and line.stable_id == getattr(candidate.line, "stable_id", "")
            # A whole-table fallback box cannot prove two particular text
            # occurrences overlap; keep both until actual cell/line geometry exists.
            precise_geometry = all((getattr(item, "repair_audit", {}) or {}).get("geometry_kind") != "enclosing_table"
                                   for item in (line, candidate.line))
            if same_id or (precise_geometry and overlap_ratio(line.bbox, candidate.line.bbox) >= 0.45):
                duplicate = candidate
                break
        if duplicate is None:
            entry = _Entry(line, owner, cell)
            entries.append(entry)
            by_text[text].append(entry)
        elif (bool(getattr(line, "translated_text", "")), line.confidence) > (
            bool(getattr(duplicate.line, "translated_text", "")), duplicate.line.confidence
        ):
            duplicate.line = line
        if duplicate is not None and cell is not None:
            duplicate.owner = owner
            duplicate.cell = cell

    # Direct text owns ordinary regions; confirmed cells always use their table owner.
    for overlay in (False, True):
        for index, block in enumerate(blocks):
            originals = list(getattr(getattr(block, "image", None), "overlay_text", []) or []) if overlay else list(block.text_lines or [])
            for original, line in zip(originals, block_line_views(block, overlay=overlay)):
                add_line(index, original, line)
    for index, block in enumerate(blocks):
        if not any(_identity(line) for line in _raw_lines(block)):
            for line, cell in _table_fallback_views(block):
                add_line(index, line, line, (index, *cell))

    owners = defaultdict(list)
    for entry in entries:
        owners[entry.owner].append(entry)
    for index, block in enumerate(blocks):
        if getattr(getattr(block, "table", None), "html", ""):
            owners.setdefault(index, [])
    region_views = []
    view_indexes = {}
    for index, group in owners.items():
        view = copy(blocks[index])
        kind = str(getattr(getattr(view, "block_type", None), "value", ""))
        if group and kind in ("figure", "chart", "seal"):
            boxes = [entry.line.bbox for entry in group]
            view.bbox = (min(box[0] for box in boxes), min(box[1] for box in boxes),
                         max(box[2] for box in boxes), max(box[3] for box in boxes))
        view.bbox = _reading_box(view.bbox, page)
        region_views.append(view)
        view_indexes[id(view)] = index
    output = []
    for view in ordered_blocks(region_views):
        group = owners[view_indexes[id(view)]]
        rtl = _lines_are_rtl(entry.line for entry in group)
        def line_position(entry):
            box = _reading_box(entry.line.bbox, page)
            return box[1], -box[2] if rtl else box[0]
        if all(entry.cell is not None for entry in group):
            # Cell columns describe the physical left-to-right grid. Reading an
            # Arabic row starts at its right edge, without reversing its text.
            group.sort(key=lambda entry: (entry.cell[1], -entry.cell[2] if rtl else entry.cell[2],
                                          *line_position(entry)))
        else:
            # Text within a region is read by baseline; column grouping happens above.
            group = _row_order(group, lambda entry: _reading_box(entry.line.bbox, page), rtl)
        lines = []
        for entry in group:
            line = entry.line
            if entry.cell is not None:
                line = copy(line)
                line.repair_audit = {**(getattr(line, "repair_audit", {}) or {}), "reading_cell": entry.cell[1:]}
            lines.append(line)
        output.append((blocks[view_indexes[id(view)]], lines))
    return output


def page_reading_lines(page):
    return [line for _, lines in page_reading_groups(page) for line in lines]


def block_reading_lines(block):
    return page_reading_lines(SimpleNamespace(blocks=[block]))
