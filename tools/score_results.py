"""Recompute saved table scores; no OCR, rendering, or writes by default."""
import argparse
import json
import re
import zipfile
from pathlib import Path
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
RUN = Path("artifacts/gpu-20261007")
SPAN_KEYS = ("row", "col", "rowspan", "colspan")
TABLE_SCORE_KEYS = (
    "cell_exact", "cell_total", "reference_characters", "character_edits",
    "cer", "matching_cell_spans", "predicted_cells", "merges", "cells",
)


def normalize(value):
    if not isinstance(value, str):
        raise ValueError("Cell text must be a string")
    return re.sub(r"\s+", " ", value).strip()


def distance(a, b):
    row = list(range(len(b) + 1))
    for i, x in enumerate(a, 1):
        nxt = [i]
        for j, y in enumerate(b, 1):
            nxt.append(min(row[j] + 1, nxt[-1] + 1, row[j - 1] + (x != y)))
        row = nxt
    return row[-1]


def read_json(path):
    with Path(path).open(encoding="utf-8") as stream:
        return json.load(stream)


def _validated_cells(table, label):
    """Reject duplicate anchors and invalid spans, rather than hide them."""
    rows, cols = table["rows"], table["cols"]
    if any(type(n) is not int or n <= 0 for n in (rows, cols)):
        raise ValueError(f"{label}: positive integer row/column counts required")
    cells = table["cells"]
    if not isinstance(cells, list) or not cells:
        raise ValueError(f"{label}: nonempty cells required")
    indexed, occupied = {}, set()
    for cell in cells:
        values = tuple(cell[k] for k in SPAN_KEYS)
        if any(type(n) is not int for n in values):
            raise ValueError(f"{label}: integer cell positions/spans required")
        r, c, rs, cs = values
        if r < 0 or c < 0 or rs < 1 or cs < 1 or r + rs > rows or c + cs > cols:
            raise ValueError(f"{label}: cell span outside table")
        if (r, c) in indexed:
            raise ValueError(f"{label}: duplicate cell anchor {(r, c)}")
        slots = {(rr, cc) for rr in range(r, r + rs) for cc in range(c, c + cs)}
        if occupied & slots:
            raise ValueError(f"{label}: overlapping cell spans")
        occupied.update(slots)
        normalize(cell["text"])
        indexed[r, c] = cell
    if label == "reference":
        if table["physical_cell_count"] != len(cells):
            raise ValueError("reference: physical_cell_count does not match cells")
        merges = sum(c["rowspan"] > 1 or c["colspan"] > 1 for c in cells)
        if table["merged_cell_count"] != merges:
            raise ValueError("reference: merged_cell_count does not match cells")
        if len(occupied) != rows * cols:
            raise ValueError("reference: incomplete table grid")
    return indexed


def score_table(ground_truth, response):
    """Score OCR cells; normalize whitespace, never diameter symbols."""
    if response.get("success") is not True:
        raise ValueError("Saved OCR response is not successful")
    tables = [r["table"] for r in response["regions"] if r.get("table")]
    if len(tables) != 1:
        raise ValueError(f"Expected exactly one OCR table, found {len(tables)}")
    _validated_cells(ground_truth, "reference")
    prediction = tables[0]
    cells = _validated_cells(prediction, "prediction")
    if (prediction["rows"], prediction["cols"]) != (ground_truth["rows"], ground_truth["cols"]):
        raise ValueError("Predicted row/column counts differ from the reference")
    rows = []
    errors = chars = exact = structure = 0
    for cell in ground_truth["cells"]:
        value = cells.get((cell["row"], cell["col"]), {})
        expected, actual = normalize(cell["text"]), normalize(value.get("text", ""))
        edits = distance(expected, actual)
        errors += edits
        chars += len(expected)
        exact += expected == actual
        same = all(cell[k] == value.get(k) for k in SPAN_KEYS)
        structure += same
        rows.append({"row": cell["row"], "col": cell["col"], "expected": expected,
                     "predicted": actual, "edit_distance": edits, "span_matches": same})
    key = lambda c: tuple(c[k] for k in SPAN_KEYS)
    expected_merges = {key(c) for c in ground_truth["cells"] if c["rowspan"] > 1 or c["colspan"] > 1}
    actual_merges = {key(c) for c in prediction["cells"] if c["rowspan"] > 1 or c["colspan"] > 1}
    return {
        "scope": "one self-created table, 21 cells; saved OCR JSON only",
        "normalization": "collapse whitespace only; preserve case and Unicode code points",
        "cell_exact": exact, "cell_total": len(rows), "reference_characters": chars,
        "character_edits": errors, "cer": errors / chars if chars else None,
        "matching_cell_spans": structure, "predicted_cells": len(prediction["cells"]),
        "merges": {"true_positive": len(expected_merges & actual_merges),
                   "false_positive": len(actual_merges - expected_merges),
                   "false_negative": len(expected_merges - actual_merges)},
        "cells": rows,
    }


def inspect_docx(path):
    """Check package/XML readability, not visual correctness or editability."""
    with zipfile.ZipFile(path) as package:
        damaged = package.testzip()
        if damaged:
            raise ValueError(f"DOCX has a damaged member: {damaged}")
        tree = ET.fromstring(package.read("word/document.xml"))
    namespace = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
    if tree.tag != f"{{{namespace}}}document" or tree.find(f"{{{namespace}}}body") is None:
        raise ValueError("DOCX does not contain a Word document body")
    ns = {"w": namespace}
    return {
        "package_and_xml_readable": True,
        "native_table_count": len(tree.findall(".//w:tbl", ns)),
        "grid_span_xml_nodes": len(tree.findall(".//w:gridSpan", ns)),
        "vertical_merge_xml_nodes": len(tree.findall(".//w:vMerge", ns)),
    }


def score_saved_outputs(root=ROOT):
    root = Path(root)
    result = score_table(read_json(root / "artifacts/merged-table-ground-truth.json"),
                         read_json(root / RUN / "merged-table-response.json"))
    historical = read_json(root / RUN / "quality.json")
    result.update({"ocr_executed": False, "renderer_executed": False, "docx": {}})
    for name in ("engineering", "merged-table"):
        result["docx"][name] = {
            **inspect_docx(root / RUN / f"{name}-output.docx"),
            "historical_visual_review": historical["docx"][name],
            "review_source": (RUN / "quality.json").as_posix(),
            "scope_note": "Historical review is copied, not revalidated; XML readability is not visual acceptance.",
        }
    return result


def write_new_report(path, result, root=ROOT):
    """Write only to an explicit new path outside immutable evidence."""
    target, root = Path(path).resolve(), Path(root).resolve()
    for directory in ("artifacts", "samples", "assets"):
        protected = (root / directory).resolve()
        if target == protected or protected in target.parents:
            raise ValueError(f"Report output is inside protected {directory}/")
    if target.exists():
        raise FileExistsError("Report output already exists; choose a new path")
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("x", encoding="utf-8", newline="\n") as stream:
        json.dump(result, stream, ensure_ascii=True, indent=2)
        stream.write("\n")


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--output", type=Path, help="New JSON report; frozen directories are forbidden")
    args = parser.parse_args(argv)
    try:
        result = score_saved_outputs(args.root)
        result["ok"] = True
        if args.output:
            write_new_report(args.output, result, args.root)
    except Exception as error:
        result = {"ok": False, "error": f"{type(error).__name__}: {error}",
                  "ocr_executed": False, "renderer_executed": False}
    print(json.dumps(result, ensure_ascii=True, indent=2))
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())

