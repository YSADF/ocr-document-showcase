"""Check saved local-run evidence using only the standard library; never run OCR."""
import argparse
from datetime import date
import hashlib
import json
from pathlib import Path, PurePosixPath
import re
import sys

sys.dont_write_bytecode = True
if __package__:
    from .score_results import ROOT, TABLE_SCORE_KEYS, inspect_docx, read_json, score_table, write_new_report
else:
    from score_results import ROOT, TABLE_SCORE_KEYS, inspect_docx, read_json, score_table, write_new_report

RUN = "artifacts/local-20261026/run.json"
SCHEMA = "local-showcase-evidence-v1"
CASE_NAMES = {"plos", "merged-table"}
TABLE_REFERENCE = "artifacts/merged-table-ground-truth.json"


def local_path(root, relative):
    """Accept canonical package-relative file names, including no symlink hops."""
    if not isinstance(relative, str) or not relative or "\\" in relative or ":" in relative:
        raise ValueError("Expected a nonempty POSIX relative path")
    parts = PurePosixPath(relative)
    if parts.is_absolute() or ".." in parts.parts or parts.as_posix() != relative:
        raise ValueError("Evidence path must stay inside the package")
    root = Path(root).resolve()
    path = root.joinpath(*parts.parts)
    resolved = path.resolve()
    if resolved == root or root not in resolved.parents:
        raise ValueError("Evidence path escapes the package")
    parent = path
    while parent != root:
        if parent.is_symlink():
            raise ValueError("Evidence paths must not use symlinks")
        parent = parent.parent
    return resolved


def sha256(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def count_text_lines(payload):
    """Count the pipeline's block text lines, excluding overlays and cell copies."""
    pages = payload["pages"]
    if not isinstance(pages, list):
        raise ValueError("Pipeline pages must be a list")
    count = 0
    for page in pages:
        blocks = page["blocks"]
        if not isinstance(blocks, list):
            raise ValueError("Pipeline blocks must be a list")
        for block in blocks:
            lines = block["text_lines"]
            if not isinstance(lines, list) or any(
                not isinstance(line, dict) or not isinstance(line.get("text"), str)
                for line in lines
            ):
                raise ValueError("Pipeline text_lines must contain text objects")
            count += len(lines)
    return count


def verify_local(root=ROOT, record_path=RUN):
    """Verify one explicit package-relative record without changing older runs."""
    root = Path(root).resolve()
    report = {
        "schema_version": "local-showcase-verification-v1", "ok": False,
        "record": record_path, "status": "checked", "checks": [], "cases": {},
        "ocr_executed": False, "renderer_executed": False,
        "new_inference": False, "visual_review_repeated": False,
        "scope": "Saved local-run file integrity and structure, separate from the historical GPU baseline",
        "limitations": [
            "Hashes establish local consistency, not an external authenticity signature.",
            "Recorded execution and visual-review statements are preserved, not rerun or independently proven.",
            "DOCX ZIP/XML readability and render signatures do not establish editability or visual fidelity.",
            "Block text-line counts are not accuracy scores; overlays and table-cell copies are excluded.",
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
        if data["schema_version"] != SCHEMA:
            raise ValueError("Unsupported local-run schema")
        date.fromisoformat(data["run_date"])
        for field in ("environment", "models", "source"):
            if not data[field]:
                raise ValueError(f"Missing run provenance: {field}")
        if not isinstance(data["files"], dict) or not data["files"]:
            raise ValueError("Run requires a nonempty explicit files mapping")
        if not isinstance(data["cases"], dict) or set(data["cases"]) != CASE_NAMES:
            raise ValueError("Run must contain the plos and merged-table cases")
        return data

    record = check("read_local_run", record_shape)
    if record is not None:
        report["run_date"] = record["run_date"]

        def verify_file(relative, expected):
            path = local_path(root, relative)
            if not isinstance(expected, dict) or type(expected.get("bytes")) is not int:
                raise ValueError("Recorded byte count must be an integer")
            if expected["bytes"] < 0 or not isinstance(expected.get("sha256"), str):
                raise ValueError("Invalid file identity")
            if not re.fullmatch(r"[0-9a-f]{64}", expected["sha256"]):
                raise ValueError("Expected a lowercase SHA-256 digest")
            if not path.is_file():
                raise ValueError(f"Missing evidence file: {relative}")
            if path.stat().st_size != expected["bytes"] or sha256(path) != expected["sha256"]:
                raise ValueError(f"Recorded bytes/hash differ: {relative}")

        for relative, expected in record["files"].items():
            check(f"file_hash:{relative}", lambda p=relative, e=expected: verify_file(p, e))

        for name in sorted(CASE_NAMES):
            def case_shape(case=record["cases"][name]):
                for field in ("ocr_executed", "docx_generated"):
                    if type(case[field]) is not bool:
                        raise ValueError(f"{field} must be a boolean recorded statement")
                if type(case["text_line_count"]) is not int or case["text_line_count"] < 0:
                    raise ValueError("text_line_count must be a nonnegative integer")
                if not isinstance(case["visual_acceptance"], str) or not case["visual_acceptance"]:
                    raise ValueError("A recorded visual-review status is required")
                if not isinstance(case["observations"], list) or any(
                    not isinstance(item, str) for item in case["observations"]
                ):
                    raise ValueError("observations must be a list of strings")
                images = case["render_pngs"]
                if not isinstance(images, list) or not images:
                    raise ValueError("At least one saved render PNG is required")
                paths = [case[field] for field in ("input", "json", "docx", "render_pdf")] + images
                if "table_score" in case:
                    paths += [case["table_score"], TABLE_REFERENCE]
                for relative in paths:
                    local_path(root, relative)
                    if relative not in record["files"]:
                        raise ValueError(f"Case evidence is absent from files: {relative}")
                return case

            case = check(f"case_paths:{name}", case_shape)
            if case is None:
                continue
            result = report["cases"][name] = {
                "recorded_ocr_executed": case["ocr_executed"],
                "recorded_docx_generated": case["docx_generated"],
                "visual_acceptance": case["visual_acceptance"],
                "observations": case["observations"], "visual_review_repeated": False,
            }

            def verify_count(current=case):
                count = count_text_lines(read_json(local_path(root, current["json"])))
                if count != current["text_line_count"]:
                    raise ValueError(f"text_line_count: recorded {current['text_line_count']}, actual {count}")
                return count

            result["text_line_count"] = check(f"text_line_count:{name}", verify_count)
            result["docx_structure"] = check(
                f"docx_readable:{name}", lambda c=case: inspect_docx(local_path(root, c["docx"])))

            if "table_score" in case:
                def recompute_table(current=case):
                    saved = read_json(local_path(root, current["json"]))
                    response = {"success": not saved["errors"], "regions": [
                        block for page in saved["pages"] for block in page["blocks"]
                    ]}
                    score = score_table(read_json(local_path(root, TABLE_REFERENCE)), response)
                    recorded = read_json(local_path(root, current["table_score"]))
                    if {key: score[key] for key in TABLE_SCORE_KEYS} != {
                        key: recorded[key] for key in TABLE_SCORE_KEYS
                    }:
                        raise ValueError("Recomputed local table score differs from the saved score")
                    return score

                result["table_score"] = check(f"table_score:{name}", recompute_table)

            def verify_signature(relative, magic):
                with local_path(root, relative).open("rb") as stream:
                    if stream.read(len(magic)) != magic:
                        raise ValueError(f"Invalid saved render signature: {relative}")

            for relative, magic in [(case["render_pdf"], b"%PDF-")] + [
                (relative, b"\x89PNG\r\n\x1a\n") for relative in case["render_pngs"]
            ]:
                check(f"render_signature:{name}:{relative}",
                      lambda p=relative, m=magic: verify_signature(p, m))

    report["ok"] = all(entry["passed"] for entry in report["checks"])
    report["checks_passed"] = sum(entry["passed"] for entry in report["checks"])
    report["checks_failed"] = len(report["checks"]) - report["checks_passed"]
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--record", default=RUN, help="Explicit package-relative saved run JSON")
    parser.add_argument("--output", type=Path, help="New report outside the frozen evidence directories")
    args = parser.parse_args(argv)
    try:
        report = verify_local(args.root, args.record)
        if args.output:
            write_new_report(args.output, report, args.root)
    except Exception as error:
        report = {"ok": False, "error": f"{type(error).__name__}: {error}",
                  "ocr_executed": False, "renderer_executed": False, "new_inference": False}
    print(json.dumps(report, ensure_ascii=True, indent=2))
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
