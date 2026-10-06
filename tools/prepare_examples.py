"""Prepare public inputs and native-PDF baselines; this script never runs OCR."""

from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import io
import json
import platform
import sys
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pdfplumber
import pypdfium2 as pdfium
from PIL import Image, ImageDraw
from reportlab.lib import colors
from reportlab.lib.pagesizes import landscape, A4
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas


C03_URL = (
    "https://gitlab.com/dexpi/TrainingTestCases/-/raw/master/"
    "dexpi%201.2/example%20pids/"
    "C03%20DEXPI%20Example%20Tank%20Displ%20Pump%20Pipe%20with%20Tee/"
    "C03V01-SAG.EX01.pdf"
)
LICENSE_URL = "https://gitlab.com/dexpi/TrainingTestCases/-/raw/master/LICENSE"
DEFAULT_ROOT = Path(__file__).resolve().parents[1]


def save_json(path, payload):
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def fetch(url):
    request = urllib.request.Request(url, headers={"User-Agent": "Public-OCR-Showcase/1.0"})
    with urllib.request.urlopen(request, timeout=45) as response:
        return response.read()


def rasterize(path, dpi):
    document = pdfium.PdfDocument(str(path))
    try:
        page = document[0]
        try:
            bitmap = page.render(scale=dpi / 72.0)
            try:
                return bitmap.to_pil().convert("RGB").copy()
            finally:
                bitmap.close()
        finally:
            page.close()
    finally:
        document.close()


def make_preview(image, path, width=1600):
    preview = image.copy()
    preview.thumbnail((width, width))
    preview.save(path)


def native_baseline(root, dpi):
    source = root / "samples/c03-source.pdf"
    if not source.exists():
        source.write_bytes(fetch(C03_URL))
    if not source.read_bytes().startswith(b"%PDF-"):
        raise ValueError("The C03 download is not a PDF")
    license_path = root / "samples/DEXPI-LICENSE.txt"
    if not license_path.exists():
        license_path.write_bytes(fetch(LICENSE_URL))

    image = rasterize(source, dpi)
    image.save(root / "samples/c03-raster.png", dpi=(dpi, dpi))
    make_preview(image, root / "assets/engineering-input.png")
    with pdfplumber.open(source) as document:
        page = document.pages[0]
        sx, sy = image.width / page.width, image.height / page.height
        words = []
        for word in page.extract_words():
            box = [word["x0"], word["top"], word["x1"], word["bottom"]]
            pixel_box = [round(box[0] * sx), round(box[1] * sy),
                         round(box[2] * sx), round(box[3] * sy)]
            words.append({"text": word["text"], "bbox_pdf_points": box,
                          "bbox_pixels": pixel_box})
        payload = {
            "status": "native_pdf_baseline_only",
            "method": "pdfplumber.extract_words",
            "ocr_executed": False,
            "source": "samples/c03-source.pdf",
            "source_url": C03_URL,
            "coordinate_origin": "top_left",
            "page_number": 1,
            "page_size_points": [page.width, page.height],
            "raster_dpi": dpi,
            "raster_size_pixels": [image.width, image.height],
            "words": words,
        }
    save_json(root / "artifacts/c03-native-text.json", payload)
    boxed = image.copy()
    drawing = ImageDraw.Draw(boxed)
    for word in words:
        drawing.rectangle(word["bbox_pixels"], outline="#2563eb", width=3)
    make_preview(boxed, root / "assets/engineering-native-boxes.png")
    return {"page_count": 1, "native_word_count": len(words),
            "raster_dpi": dpi, "raster_size_pixels": [image.width, image.height],
            "ocr_status": "pending", "docx_status": "pending"}


def find_font(explicit):
    candidates = [Path(explicit)] if explicit else []
    candidates += [Path("C:/Windows/Fonts/arial.ttf"),
                   Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"),
                   Path("/Library/Fonts/Arial.ttf")]
    for candidate in candidates:
        if candidate.is_file():
            pdfmetrics.registerFont(TTFont("ShowcaseSans", str(candidate)))
            return "ShowcaseSans"
    raise RuntimeError("Pass --font /path/to/a/Unicode-font.ttf (Arial or DejaVu Sans)")


def table_cells():
    specs = [
        (0, 0, 1, 5, "Engineering inspection record"),
        (1, 0, 1, 1, "Item"), (1, 1, 1, 1, "Specification"),
        (1, 2, 1, 1, "Qty"), (1, 3, 1, 1, "Result"), (1, 4, 1, 1, "Note"),
        (2, 0, 2, 1, "Valve body"), (2, 1, 1, 1, "DN 50"),
        (2, 2, 1, 1, "2"), (2, 3, 1, 1, "PASS"),
        (2, 4, 1, 1, "Ø 50 ± 0.10 mm"),
        (3, 1, 1, 1, "DN 80"), (3, 2, 1, 1, "1"),
        (3, 3, 1, 1, "REVIEW"), (3, 4, 1, 1, "Angle 90° ± 0.5°"),
        (4, 0, 1, 1, "Pump"), (4, 1, 1, 2, "Model P001 / 1 unit"),
        (4, 3, 1, 1, "PASS"), (4, 4, 1, 1, "Bore Ø 12 mm"),
        (5, 0, 1, 3, "Summary: 4 inspected units"),
        (5, 3, 1, 2, "3 PASS / 1 REVIEW"),
    ]
    return [dict(row=r, col=c, rowspan=rs, colspan=cs, text=text)
            for r, c, rs, cs, text in specs]


def make_table(root, dpi, font):
    path = root / "samples/merged-table-source.pdf"
    page_width, page_height = landscape(A4)
    pdf = canvas.Canvas(str(path), pagesize=(page_width, page_height))
    pdf.setTitle("Public merged-cell table fixture")
    pdf.setAuthor("OCR showcase - self-created fixture")
    pdf.setFont(font, 20)
    pdf.drawString(48, page_height - 65, "Merged-cell table input")
    pdf.setFont(font, 10)
    pdf.setFillColor(colors.HexColor("#475569"))
    pdf.drawString(48, page_height - 85, "Self-created input and ground truth | Not an OCR result")
    column_edges = [48, 174, 353, 413, 509, page_width - 48]
    row_edges = [155, 197, 233, 288, 343, 398, 440]
    cells = table_cells()
    for cell in cells:
        r, c = cell["row"], cell["col"]
        rs, cs = cell["rowspan"], cell["colspan"]
        left, right = column_edges[c], column_edges[c + cs]
        top, bottom = row_edges[r], row_edges[r + rs]
        pdf.setFillColor(colors.HexColor("#e2e8f0") if r <= 1 else colors.white)
        pdf.setStrokeColor(colors.HexColor("#334155"))
        pdf.setLineWidth(0.7)
        pdf.rect(left, page_height - bottom, right - left, bottom - top, fill=1, stroke=1)
        pdf.setFillColor(colors.HexColor("#0f172a"))
        pdf.setFont(font, 13 if r == 0 else 10)
        pdf.drawString(left + 10, page_height - (top + bottom) / 2 - 3, cell["text"])
        cell["bbox_pdf_points"] = [left, top, right, bottom]
    pdf.setFont(font, 9)
    pdf.setFillColor(colors.HexColor("#475569"))
    pdf.drawString(48, 92, "6 logical rows x 5 columns | rowspan and colspan | CC0 1.0")
    pdf.drawString(48, 74, "Target: preserve text, merged cells and editable document structure.")
    pdf.showPage()
    pdf.save()

    image = rasterize(path, dpi)
    make_preview(image, root / "assets/merged-table-input.png")
    # Embed only the raster; this scan fixture has no searchable text layer.
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    from reportlab.lib.utils import ImageReader
    scanned = canvas.Canvas(str(root / "samples/merged-table-scan.pdf"),
                            pagesize=(page_width, page_height))
    scanned.setTitle("Raster-only merged-cell table input")
    scanned.drawImage(ImageReader(buffer), 0, 0, width=page_width, height=page_height)
    scanned.showPage()
    scanned.save()
    sx, sy = image.width / page_width, image.height / page_height
    for cell in cells:
        x0, y0, x1, y1 = cell["bbox_pdf_points"]
        cell["bbox_pixels"] = [round(x0 * sx), round(y0 * sy), round(x1 * sx), round(y1 * sy)]
    payload = {"status": "manually_authored_ground_truth", "ocr_executed": False,
               "coordinate_origin": "top_left", "indices": "zero_based",
               "rows": 6, "cols": 5, "physical_cell_count": len(cells),
               "merged_cell_count": sum(c["rowspan"] > 1 or c["colspan"] > 1 for c in cells),
               "raster_dpi": dpi, "raster_size_pixels": [image.width, image.height],
               "cells": cells, "license": "CC0-1.0"}
    save_json(root / "artifacts/merged-table-ground-truth.json", payload)
    return {"rows": 6, "cols": 5, "physical_cell_count": len(cells),
            "merged_cell_count": payload["merged_cell_count"], "raster_dpi": dpi,
            "raster_size_pixels": [image.width, image.height],
            "ocr_status": "pending", "docx_status": "pending"}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=DEFAULT_ROOT)
    parser.add_argument("--dpi", type=int, default=180)
    parser.add_argument("--font", default="", help="Unicode TTF for the self-created table")
    args = parser.parse_args()
    if not 72 <= args.dpi <= 300:
        parser.error("--dpi must be between 72 and 300")
    root = args.root.resolve()
    for folder in ["assets", "samples", "artifacts"]:
        (root / folder).mkdir(parents=True, exist_ok=True)
    engineering = native_baseline(root, args.dpi)
    table = make_table(root, args.dpi, find_font(args.font))
    files = {}
    for folder in ["assets", "samples", "artifacts"]:
        for path in sorted((root / folder).iterdir()):
            if path.is_file() and path.name != "case-metadata.json":
                files[path.relative_to(root).as_posix()] = {
                    "bytes": path.stat().st_size,
                    "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                }
    metadata = {
        "prepared_at": datetime.now(timezone.utc).astimezone(
            timezone(timedelta(hours=8))).isoformat(timespec="seconds"),
        "environment": {"python": platform.python_version(), "os": platform.system(),
                        "architecture": platform.machine(),
                        "packages": {name: importlib.metadata.version(name)
                                     for name in ["pdfplumber", "pypdfium2", "reportlab", "Pillow"]}},
        "company_service_called": False, "ocr_executed": False,
        "engineering": engineering, "merged_table": table, "files": files,
    }
    save_json(root / "artifacts/case-metadata.json", metadata)
    print(json.dumps({"engineering": engineering, "merged_table": table,
                      "ocr_executed": False}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
