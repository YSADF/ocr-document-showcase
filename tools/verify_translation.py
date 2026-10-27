"""Check saved English-to-Chinese evidence with the standard library, read-only."""
import argparse
from datetime import date
import json
from pathlib import Path
import re
import sys
import xml.etree.ElementTree as ET
import zipfile

sys.dont_write_bytecode = True
if __package__:
    from .score_results import ROOT, TABLE_SCORE_KEYS, read_json, score_table, write_new_report
    from .verify_local import local_path, sha256
else:
    from score_results import ROOT, TABLE_SCORE_KEYS, read_json, score_table, write_new_report
    from verify_local import local_path, sha256

RUN = "artifacts/local-translation-20261026/run.json"
SCHEMA = "translation-showcase-evidence-v1"
FAITHFUL_SCHEMA = "faithful-translation-showcase-evidence-v1"
CASE_NAMES = {"plos", "merged-table"}
PATH_FIELDS = ("input", "source_json", "translated_json", "docx", "model_responses",
               "execution", "render_audit", "render_pdf")
CJK = re.compile(r"[\u3400-\u4dbf\u4e00-\u9fff]")
W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"


def pipeline_text_evidence(payload):
    """Inspect text-bearing fields only; metadata cannot stand in for translated text."""
    pages = payload["pages"]
    if not isinstance(pages, list) or not pages:
        raise ValueError("Expected nonempty pipeline pages")
    translations, current_cells = [], []
    for page in pages:
        if not isinstance(page["blocks"], list):
            raise ValueError("Pipeline blocks must be a list")
        for block in page["blocks"]:
            for key in ("text_lines", "image_overlay_text"):
                lines = block.get(key, [])
                if not isinstance(lines, list):
                    raise ValueError(f"{key} must be a list")
                for line in lines:
                    if not isinstance(line, dict) or not isinstance(line.get("text"), str):
                        raise ValueError("Text entries require a text string")
                    value = line.get("translated_text")
                    if value is not None and not isinstance(value, str):
                        raise ValueError("translated_text must be a string or null")
                    if value and value.strip():
                        translations.append(value)
            if block.get("table"):
                for cell in block["table"]["cells"]:
                    if not isinstance(cell.get("text"), str):
                        raise ValueError("Table cells require text strings")
                    current_cells.append(cell["text"])
                    # TableCell stores current text plus raw translation provenance.
                    values = [cell.get("translated_text"), (cell.get("raw") or {}).get("translated_text")]
                    for value in values:
                        if value is not None and not isinstance(value, str):
                            raise ValueError("Cell translated_text must be a string or null")
                        if value and value.strip():
                            translations.append(value)
    return {
        "page_count": len(pages), "nonempty_translated_entries": len(translations),
        "translated_entries_with_chinese": sum(bool(CJK.search(text)) for text in translations),
        "current_cells_with_chinese": sum(bool(CJK.search(text)) for text in current_cells),
    }


def inspect_chinese_docx(path, require_table=False):
    with zipfile.ZipFile(path) as package:
        if package.testzip() is not None:
            raise ValueError("Damaged DOCX ZIP member")
        document = ET.fromstring(package.read("word/document.xml"))
    all_text = "".join(node.text or "" for node in document.iter(W + "t"))
    tables = list(document.iter(W + "tbl"))
    table_text = "".join(node.text or "" for table in tables for node in table.iter(W + "t"))
    count = len(CJK.findall(all_text))
    table_count = len(CJK.findall(table_text))
    if not count:
        raise ValueError("DOCX has no native Chinese text nodes")
    if require_table and (not tables or not table_count):
        raise ValueError("Table case needs a native table containing Chinese text")
    return {"native_chinese_characters": count, "native_table_count": len(tables),
            "native_table_chinese_characters": table_count}


def inspect_responses(payload):
    for key in ("model", "revision"):
        if not isinstance(payload[key], str) or not payload[key]:
            raise ValueError(f"Missing model provenance: {key}")
    if not isinstance(payload["generation"], dict) or not payload["generation"]:
        raise ValueError("Missing generation parameters")
    requests = payload["requests"]
    if not isinstance(requests, list) or not requests:
        raise ValueError("No captured model requests")
    entries = chinese = 0
    for item in requests:
        request, response = item["request"], item["response"]
        if (request["source"], request["target"]) != ("en", "zh"):
            raise ValueError("Captured request is not English to Chinese")
        source, translated = request["q"], response["translatedText"]
        if isinstance(source, str):
            source = [source]
        if isinstance(translated, str):
            translated = [translated]
        if (not isinstance(source, list) or not source or not isinstance(translated, list)
                or len(source) != len(translated)
                or any(not isinstance(value, str) or not value.strip() for value in source + translated)):
            raise ValueError("Captured response must provide one nonempty string per input")
        entries += len(source)
        chinese += sum(bool(CJK.search(text)) for text in translated)
    if not chinese:
        raise ValueError("Captured model responses contain no Chinese translation")
    return {"request_count": len(requests), "response_entries": entries,
            "response_entries_with_chinese": chinese, "model": payload["model"],
            "revision": payload["revision"]}


def verify_translation(root=ROOT, record_path=RUN):
    root = Path(root).resolve()
    report = {
        "schema_version": "translation-showcase-verification-v1", "ok": False,
        "record": record_path, "checks": [], "cases": {},
        "ocr_executed": False, "translation_executed": False, "renderer_executed": False,
        "new_inference": False, "visual_review_repeated": False,
        "scope": "Saved English-to-Chinese request, output and file consistency only",
        "limitations": [
            "Hashes establish local consistency, not independent authenticity or model execution.",
            "Chinese text and captured responses do not establish translation correctness or completeness.",
            "DOCX text/table XML and PDF/PNG signatures do not establish visual fidelity or Word editability.",
            "Recorded visual outcomes are preserved; this command does not repeat visual review.",
        ],
    }

    def check(identifier, operation):
        try:
            value = operation()
            report["checks"].append({"id": identifier, "passed": True})
            return value
        except Exception as error:
            report["checks"].append({"id": identifier, "passed": False,
                                     "error": f"{type(error).__name__}: {error}"})
            return None

    def record_shape():
        data = read_json(local_path(root, record_path))
        if data["schema_version"] not in {SCHEMA, FAITHFUL_SCHEMA}:
            raise ValueError("Unsupported translation evidence schema")
        date.fromisoformat(data["run_date"])
        for key in ("environment", "models", "source"):
            if not data[key]:
                raise ValueError(f"Missing provenance: {key}")
        if not isinstance(data["files"], dict) or not data["files"]:
            raise ValueError("An explicit nonempty files mapping is required")
        if not isinstance(data["cases"], dict) or set(data["cases"]) != CASE_NAMES:
            raise ValueError("Expected plos and merged-table cases")
        return data

    record = check("read_translation_run", record_shape)
    if record is not None:
        report["run_date"] = record["run_date"]

        def verify_file(relative, expected):
            path = local_path(root, relative)
            if (not isinstance(expected, dict) or type(expected.get("bytes")) is not int
                    or expected["bytes"] < 0 or not isinstance(expected.get("sha256"), str)
                    or not re.fullmatch(r"[0-9a-f]{64}", expected["sha256"])):
                raise ValueError("Expected a byte count and lowercase SHA-256 digest")
            if not path.is_file() or path.stat().st_size != expected["bytes"] or sha256(path) != expected["sha256"]:
                raise ValueError(f"Missing or changed evidence: {relative}")

        for relative, identity in record["files"].items():
            check(f"file_hash:{relative}", lambda p=relative, e=identity: verify_file(p, e))

        for name in sorted(CASE_NAMES):
            def case_shape(current=record["cases"][name]):
                for key in ("translation_executed", "docx_generated"):
                    if type(current[key]) is not bool:
                        raise ValueError(f"{key} must be a recorded boolean")
                if not isinstance(current["visual_acceptance"], str) or not current["visual_acceptance"]:
                    raise ValueError("Recorded visual acceptance is required")
                if not isinstance(current["observations"], list) or any(
                        not isinstance(value, str) for value in current["observations"]):
                    raise ValueError("Observations must be strings")
                if not isinstance(current["render_pngs"], list) or not current["render_pngs"]:
                    raise ValueError("At least one saved page PNG is required")
                for relative in [current[key] for key in PATH_FIELDS] + current["render_pngs"]:
                    local_path(root, relative)
                    if relative not in record["files"]:
                        raise ValueError(f"Case file absent from explicit mapping: {relative}")
                return current

            case = check(f"case_paths:{name}", case_shape)
            if case is None:
                continue
            detail = report["cases"][name] = {
                "recorded_translation_executed": case["translation_executed"],
                "recorded_docx_generated": case["docx_generated"],
                "visual_acceptance": case["visual_acceptance"], "observations": case["observations"],
            }

            def text_evidence(current=case):
                source = pipeline_text_evidence(read_json(local_path(root, current["source_json"])))
                translated = pipeline_text_evidence(read_json(local_path(root, current["translated_json"])))
                if source["page_count"] != translated["page_count"]:
                    raise ValueError("Translation pipeline page count differs from OCR source")
                if not translated["translated_entries_with_chinese"]:
                    raise ValueError("Pipeline output has no Chinese translated_text fields")
                return translated

            detail["text_evidence"] = check(f"translated_text:{name}", text_evidence)
            detail["model_responses"] = check(f"model_responses:{name}", lambda c=case:
                inspect_responses(read_json(local_path(root, c["model_responses"]))))
            detail["docx_structure"] = check(f"docx_chinese:{name}", lambda c=case, n=name:
                inspect_chinese_docx(local_path(root, c["docx"]),
                    require_table=n == "merged-table" and record["schema_version"] == SCHEMA))

            def execution_evidence(current=case):
                execution = read_json(local_path(root, current["execution"]))
                for key in ("translation_executed", "docx_generated"):
                    if type(execution[key]) is not bool or execution[key] != current[key]:
                        raise ValueError(f"Case/execution statements differ: {key}")
                parameters = execution["translation_parameters"]
                if (parameters["source_lang"], parameters["target_lang"]) != ("en", "zh"):
                    raise ValueError("Execution parameters are not English to Chinese")
                audit = read_json(local_path(root, current["render_audit"]))
                if not isinstance(audit, dict) or not audit:
                    raise ValueError("Saved render audit must be a nonempty object")

            check(f"execution_record:{name}", execution_evidence)

            if "source_table_score" in case:
                def table_evidence(current=case):
                    truth_path = "artifacts/merged-table-ground-truth.json"
                    for relative in (truth_path, current["source_table_score"]):
                        if relative not in record["files"]:
                            raise ValueError("Table evaluation input/output absent from explicit mapping")
                    source = read_json(local_path(root, current["source_json"]))
                    regions = [block for page in source["pages"] for block in page["blocks"]]
                    actual = score_table(read_json(local_path(root, truth_path)),
                                         {"success": True, "regions": regions})
                    saved = read_json(local_path(root, current["source_table_score"]))
                    if any(actual[key] != saved[key] for key in TABLE_SCORE_KEYS):
                        raise ValueError("Saved source table score differs from recomputed OCR evidence")
                    return actual
                detail["source_table_score"] = check(f"source_table_score:{name}", table_evidence)

            if record["schema_version"] == FAITHFUL_SCHEMA:
                def faithful_evidence(current=case):
                    execution = read_json(local_path(root, current["execution"]))
                    if execution["renderer_confirmed"] != "FaithfulWordBuilder":
                        raise ValueError("The faithful renderer was not confirmed")
                    options = execution["translation_parameters"]["runtime_options"]
                    if options.get("_faithful_layout") is not True or options.get("_preserve_block_boundaries") is not True:
                        raise ValueError("Translation did not use faithful grouping")
                    audit = read_json(local_path(root, current["render_audit"]))
                    if audit["docx_sha256"] != sha256(local_path(root, current["docx"])):
                        raise ValueError("Audit belongs to a different DOCX")
                    review = audit["visual_review"]
                    if review["acceptance"] != current["visual_acceptance"]:
                        raise ValueError("Case and visual review disagree")
                    with zipfile.ZipFile(local_path(root, current["docx"])) as package:
                        xml = ET.fromstring(package.read("word/document.xml"))
                        frames = xml.findall(".//" + W + "framePr")
                        fonts = [name for name in package.namelist() if name.startswith("word/fonts/") and name.endswith(".odttf")]
                        if not frames or not fonts:
                            raise ValueError("Faithful DOCX needs native frames and embedded fonts")
                    if audit["layout"]["font_embedding"]["status"] != "success":
                        raise ValueError("Font embedding is not verified")
                    if review["acceptance"] == "passed_for_page_layout":
                        if audit["report"].get("passed") is not True or audit["report"].get("violations"):
                            raise ValueError("Accepted layout requires a passing saved delivery audit")
                        if audit["layout"]["failed_region_count"] or any(
                                p["failed_erase_regions"] for p in audit["layout"]["page_plans"]):
                            raise ValueError("Failed layout regions cannot be presented as accepted")
                        if any(review.get(key) is not False for key in ("overlap_seen", "clipping_seen", "page_overflow_seen", "source_text_ghosts_seen")):
                            raise ValueError("Accepted layout requires an explicit clean visual review")
                        if review["rendered_pages"] != review["source_pages"]:
                            raise ValueError("Accepted faithful layout changed the page count")
                    return {"representation": "source_background_and_native_text_frames",
                            "native_frames": len(frames), "embedded_fonts": len(fonts),
                            "recorded_delivery_passed": audit["report"]["passed"],
                            "recorded_visual_acceptance": review["acceptance"]}
                detail["faithful_evidence"] = check(f"faithful_evidence:{name}", faithful_evidence)

            def signature(relative, magic):
                with local_path(root, relative).open("rb") as stream:
                    if stream.read(len(magic)) != magic:
                        raise ValueError(f"Invalid saved render signature: {relative}")

            for relative, magic in [(case["render_pdf"], b"%PDF-")] + [
                    (path, b"\x89PNG\r\n\x1a\n") for path in case["render_pngs"]]:
                check(f"render_signature:{name}:{relative}", lambda p=relative, m=magic: signature(p, m))

    report["ok"] = all(entry["passed"] for entry in report["checks"])
    report["checks_passed"] = sum(entry["passed"] for entry in report["checks"])
    report["checks_failed"] = len(report["checks"]) - report["checks_passed"]
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--record", default=RUN, help="Explicit package-relative saved run JSON")
    parser.add_argument("--output", type=Path, help="New report outside frozen evidence")
    args = parser.parse_args(argv)
    try:
        report = verify_translation(args.root, args.record)
        if args.output:
            write_new_report(args.output, report, args.root)
    except Exception as error:
        report = {"ok": False, "error": f"{type(error).__name__}: {error}",
                  "ocr_executed": False, "translation_executed": False,
                  "renderer_executed": False, "new_inference": False}
    print(json.dumps(report, ensure_ascii=True, indent=2))
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
