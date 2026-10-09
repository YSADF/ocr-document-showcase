"""Download published sources, verify frozen hashes, and rasterize selected pages.

No OCR runs and no labels are generated. Third-party files remain local.
"""
import argparse
import hashlib
import json
from pathlib import Path
import urllib.request


def sha(data):
    return hashlib.sha256(data).hexdigest()


def prepare(selection, output):
    import fitz
    if fitz.VersionBind != "1.25.3":
        raise ValueError("Frozen rasters require PyMuPDF==1.25.3; use a separate environment")
    manifest = json.loads(selection.read_text(encoding="utf-8"))
    output.mkdir(parents=True, exist_ok=False)
    (output/"sources").mkdir()
    (output/"pages").mkdir()
    sources = {}
    for sample in manifest["samples"]:
        identity = sample["source_pdf_sha256"]
        if identity not in sources:
            request = urllib.request.Request(sample["source_url"], headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(request, timeout=60) as response:
                data = response.read()
            if sha(data) != identity:
                raise ValueError("Source changed: " + sample["source_url"])
            sources[identity] = output/"sources"/(identity+".pdf")
            sources[identity].write_bytes(data)
        name = sample["id"]
        if Path(name).name != name or "/" in name or "\\" in name or name in {".", ".."}:
            raise ValueError("Unsafe sample ID")
        path = output/"pages"/(name+".png")
        with fitz.open(sources[identity]) as document:
            document[sample["source_page"]-1].get_pixmap(matrix=fitz.Matrix(2.5, 2.5), alpha=False).save(path)
        if sha(path.read_bytes()) != sample["image_sha256"]:
            raise ValueError("Raster differs from frozen image: " + name)
        sample["image"] = "pages/"+path.name
    (output/"selection.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Prepared {len(manifest['samples'])} pages; human labels remain pending")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--selection", type=Path, default=Path(__file__).resolve().parents[1]/"artifacts/collaboration-20261009/holdout-selection.json")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    prepare(args.selection, args.output)
