"""Verify frozen public evidence with the standard library; read-only by default."""
import argparse
import hashlib
import json
from pathlib import Path, PurePosixPath
import sys

# Avoid creating __pycache__ even when the CLI is invoked without Python -B.
sys.dont_write_bytecode = True
if __package__:
    from .score_results import ROOT, RUN, TABLE_SCORE_KEYS, inspect_docx, read_json, score_table, write_new_report
else:
    from score_results import ROOT, RUN, TABLE_SCORE_KEYS, inspect_docx, read_json, score_table, write_new_report

EXPECTED_SCORE = {
    "cell_exact": 19, "cell_total": 21, "reference_characters": 203,
    "character_edits": 2, "matching_cell_spans": 21, "predicted_cells": 21,
    "merges": {"true_positive": 5, "false_positive": 0, "false_negative": 0},
}
EXPECTED_INPUTS = {
    "engineering": ("samples/c03-raster.png", "fb9feef4294f6f67ca5f26886eed879a05b739f15a4129b687e1ac4a370a69f6"),
    "merged-table": ("samples/merged-table-scan.pdf", "df9a44b94571a7baa3d27818378d0f61db1f7250f0a58b7a12bf96adb7cfaed7"),
}
REQUIRED_METADATA_FILES = {
    "assets/engineering-input.png", "assets/engineering-native-boxes.png",
    "assets/merged-table-input.png", "samples/c03-raster.png", "samples/c03-source.pdf",
    "samples/DEXPI-LICENSE.txt", "samples/merged-table-scan.pdf",
    "samples/merged-table-source.pdf", "artifacts/c03-native-text.json",
    "artifacts/merged-table-ground-truth.json",
}


def sha256(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def local_path(root, relative):
    """Manifest paths must resolve inside this public package."""
    if not isinstance(relative, str) or not relative or "\\" in relative or ":" in relative:
        raise ValueError("Expected a nonempty POSIX relative path")
    parts = PurePosixPath(relative)
    if parts.is_absolute() or ".." in parts.parts:
        raise ValueError("Evidence path escapes the showcase root")
    target, root = (Path(root) / relative).resolve(), Path(root).resolve()
    if target == root or root not in target.parents:
        raise ValueError("Evidence path escapes the showcase root")
    return target


def verify_demo(root=ROOT, manifest=None):
    root = Path(root).resolve()
    report = {
        "schema_version": "public-demo-verification-v1", "ok": False,
        "scope": "Frozen 2026-10-07 outputs; not new inference or current production acceptance",
        "ocr_executed": False, "translation_executed": False,
        "renderer_executed": False, "native_text_used_as_ocr": False,
        "checks": [], "table": None, "docx": {},
        "limitations": [
            "DEXPI native text and native boxes are source-layer extraction, not OCR output or proofread truth.",
            "Historical DOCX visual reviews failed. ZIP/XML readability does not overturn them.",
            "This table has two diameter-symbol errors; verified evidence does not mean perfect recognition.",
            "Hashes establish local evidence consistency, not an external authenticity signature.",
        ],
    }

    def check(identifier, operation, include_detail=True):
        try:
            detail = operation()
            entry = {"id": identifier, "passed": True}
            if detail is not None and include_detail:
                entry["details"] = detail
            report["checks"].append(entry)
            return detail
        except Exception as error:
            report["checks"].append({"id": identifier, "passed": False,
                                     "error": f"{type(error).__name__}: {error}"})
            return None

    def equal(actual, expected, label):
        if actual != expected:
            raise ValueError(f"{label}: expected {expected!r}, got {actual!r}")
        return actual

    def verify_file(relative, recorded):
        path = local_path(root, relative)
        actual = {"bytes": path.stat().st_size, "sha256": sha256(path)}
        if type(recorded.get("bytes")) is not int:
            raise ValueError("Manifest byte count must be an integer")
        for field in ("bytes", "sha256"):
            equal(actual[field], recorded[field], f"{relative} {field}")
        return {"path": relative, **actual}

    metadata = check("read_case_metadata", lambda: read_json(root / "artifacts/case-metadata.json"), False)
    benchmark = check("read_benchmark", lambda: read_json(root / RUN / "benchmark.json"), False)
    historical = check("read_historical_quality", lambda: read_json(root / RUN / "quality.json"), False)
    if metadata is not None:
        entries = check("metadata_required_files", lambda: (
            equal(set(metadata["files"]), REQUIRED_METADATA_FILES, "metadata paths"), metadata["files"])[1], False)
        check("preparation_is_not_inference", lambda: equal(
            (metadata["ocr_executed"], metadata["company_service_called"]), (False, False), "preparation scope"))
        if isinstance(entries, dict):
            for relative, recorded in entries.items():
                check(f"metadata_hash:{relative}", lambda p=relative, r=recorded: verify_file(p, r))
    if benchmark is not None:
        check("benchmark_cases", lambda: equal(set(benchmark["cases"]), set(EXPECTED_INPUTS), "benchmark cases"), False)
        for name, (relative, expected_hash) in EXPECTED_INPUTS.items():
            def verify_input(case=name, path=relative, digest=expected_hash):
                entry = benchmark["cases"][case]
                equal(entry["input"], PurePosixPath(path).name, "benchmark input filename")
                equal(entry["sha256"], digest, "frozen benchmark input identity")
                equal(sha256(local_path(root, path)), digest, "actual OCR input SHA256")
                if metadata is None:
                    raise ValueError("Cannot cross-check missing preparation metadata")
                equal(metadata["files"][path]["sha256"], digest, "metadata/benchmark input identity")
                return {"path": path, "sha256": digest}
            check(f"actual_ocr_input:{name}", verify_input)

    for name in EXPECTED_INPUTS:
        def verify_response(case=name):
            saved = read_json(root / RUN / f"{case}-response.json")
            equal(saved["success"], True, "saved OCR request success")
            if not isinstance(saved["regions"], list) or not saved["regions"]:
                raise ValueError("Saved OCR response has no regions")
            model = saved["ocr_model"]
            equal(model["ocr_version"], "PP-OCRv6", "historical OCR version")
            equal(model["detection_model"], "PP-OCRv6_small_det", "historical detector")
            equal(model["recognition_model"], "PP-OCRv6_small_rec", "historical recognizer")
            return {"path": (RUN / f"{case}-response.json").as_posix(),
                    "region_count": len(saved["regions"]),
                    "saved_model": model["recognition_model"], "model_loaded_now": False}
        check(f"saved_ocr_response:{name}", verify_response)

    def recompute():
        ground_truth = read_json(root / "artifacts/merged-table-ground-truth.json")
        equal(ground_truth["status"], "manually_authored_ground_truth", "reference provenance")
        equal(ground_truth["ocr_executed"], False, "reference is not OCR")
        equal(ground_truth["license"], "CC0-1.0", "reference license")
        return score_table(ground_truth, read_json(root / RUN / "merged-table-response.json"))

    score = check("recompute_table", recompute, False)
    if score is not None:
        report["table"] = score
        check("fixed_table_baseline", lambda: equal(
            {key: score[key] for key in EXPECTED_SCORE}, EXPECTED_SCORE, "historical table baseline"))
        if historical is not None:
            check("table_matches_historical_quality", lambda: equal(
                {key: score[key] for key in TABLE_SCORE_KEYS},
                {key: historical[key] for key in TABLE_SCORE_KEYS}, "recomputed versus historical table"), False)

    for name in ("engineering", "merged-table"):
        current = check(f"docx_readable:{name}", lambda n=name: inspect_docx(root / RUN / f"{n}-output.docx"))
        report["docx"][name] = {"structure": current, "visual_review_repeated": False}
        if historical is not None:
            def review_docx(case=name, structure=current):
                review = historical["docx"][case]
                equal(review["visual_acceptance"], "failed", "historical visual acceptance")
                equal(review["review_renderer"], "LibreOffice -> PDF -> PNG", "historical renderer")
                if not review.get("observations"):
                    raise ValueError("Historical visual failure observations are missing")
                if structure is None:
                    raise ValueError("DOCX could not be read")
                for key in ("native_table_count", "grid_span_xml_nodes", "vertical_merge_xml_nodes"):
                    equal(structure[key], review[key], f"DOCX {key}")
                return review
            review = check(f"historical_docx_review:{name}", review_docx, False)
            report["docx"][name]["historical_visual_review"] = review
        for extension, magic in (("pdf", b"%PDF-"), ("png", b"\x89PNG\r\n\x1a\n")):
            relative = (RUN / f"{name}-render" / (f"{name}-output.pdf" if extension == "pdf" else "page-1.png")).as_posix()
            def render_exists(path=relative, signature=magic):
                with local_path(root, path).open("rb") as stream:
                    equal(stream.read(len(signature)), signature, "historical render signature")
                return {"path": path, "rendered_now": False}
            check(f"historical_render_exists:{relative}", render_exists)

    # A caller-supplied release manifest checks distribution integrity; it is
    # distinct from historic run metadata and is never generated here.
    if manifest is not None:
        release = check("read_release_manifest", lambda: read_json(manifest), False)
        if release is not None:
            def manifest_entries():
                entries = release["files"]
                if not isinstance(entries, dict) or not entries:
                    raise ValueError("Manifest requires a nonempty files mapping")
                return entries
            entries = check("release_manifest_entries", manifest_entries, False)
            if entries is not None:
                for relative, recorded in entries.items():
                    check(f"release_hash:{relative}", lambda p=relative, r=recorded: verify_file(p, r))
    for field, relative in (
        ("local_run", "artifacts/local-20261026/run.json"),
        ("local_docx_fix", "artifacts/local-docx-fix-20261026/run.json"),
    ):
        local_record = root / relative
        report[field] = {"status": "not_present", "new_inference": False,
                         "visual_review_repeated": False}
        if local_record.exists() or local_record.is_symlink():
            def verify_local_record(record_path=relative, report_field=field):
                # Delay the import so copies of the historical fixture remain usable.
                if __package__:
                    from .verify_local import verify_local
                else:
                    from verify_local import verify_local
                local_report = verify_local(root, record_path)
                report[report_field] = local_report
                if not local_report["ok"]:
                    raise ValueError(f"Local-run evidence checks failed; see {report_field}.checks")
            check(f"{field}_evidence", verify_local_record, False)
    translation_record = "artifacts/local-translation-20261026/run.json"
    report["local_translation"] = {
        "status": "not_present", "translation_executed": False,
        "new_inference": False, "visual_review_repeated": False,
    }
    translation_path = root / translation_record
    if translation_path.exists() or translation_path.is_symlink():
        def verify_translation_record():
            # Keep the translation dependency optional for older public fixtures.
            if __package__:
                from .verify_translation import verify_translation
            else:
                from verify_translation import verify_translation
            translated = verify_translation(root, translation_record)
            report["local_translation"] = translated
            if not translated["ok"]:
                raise ValueError("Translation evidence checks failed; see local_translation.checks")
        check("local_translation_evidence", verify_translation_record, False)
    faithful_record = "artifacts/local-faithful-20261027/run.json"
    report["local_faithful"] = {"status": "not_present", "new_inference": False,
                                "visual_review_repeated": False}
    if (root / faithful_record).exists() or (root / faithful_record).is_symlink():
        def verify_faithful_record():
            if __package__:
                from .verify_translation import verify_translation
            else:
                from verify_translation import verify_translation
            faithful = verify_translation(root, faithful_record)
            report["local_faithful"] = faithful
            if not faithful["ok"]:
                raise ValueError("Faithful evidence checks failed; see local_faithful.checks")
        check("local_faithful_evidence", verify_faithful_record, False)
    report["ok"] = all(entry["passed"] for entry in report["checks"])
    report["checks_passed"] = sum(entry["passed"] for entry in report["checks"])
    report["checks_failed"] = len(report["checks"]) - report["checks_passed"]
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--manifest", type=Path, help="Release files mapping: relative paths to sha256 and bytes")
    parser.add_argument("--output", type=Path, help="New JSON report outside frozen evidence")
    args = parser.parse_args(argv)
    try:
        report = verify_demo(args.root, args.manifest)
        if args.output:
            write_new_report(args.output, report, args.root)
    except Exception as error:
        report = {"ok": False, "error": f"{type(error).__name__}: {error}",
                  "ocr_executed": False, "renderer_executed": False}
    print(json.dumps(report, ensure_ascii=True, indent=2))
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())

