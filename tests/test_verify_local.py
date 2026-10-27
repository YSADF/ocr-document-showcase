"""Integrity regressions for tiny synthetic records, without OCR or renderers."""
import base64
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
import zipfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from tools.score_results import score_table
from tools.verify_local import RUN, SCHEMA, TABLE_REFERENCE, local_path, sha256, verify_local

SOURCE = Path(__file__).resolve().parents[1]
FIX_RUN = "artifacts/local-docx-fix-20261026/run.json"
PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+aWQAAAABJRU5ErkJggg==")
WORD_XML = b'''<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
<w:body><w:p><w:r><w:t>Fixture only</w:t></w:r></w:p><w:tbl><w:tr><w:tc>
<w:tcPr><w:gridSpan w:val="2"/></w:tcPr><w:p/></w:tc></w:tr></w:tbl></w:body></w:document>'''


class VerifyLocalTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name) / "showcase"
        self.root.mkdir()
        self.record = {
            "schema_version": SCHEMA, "run_date": "2026-10-26",
            "environment": {"purpose": "synthetic test fixture"},
            "models": {"purpose": "no models used by these tests"},
            "source": {"purpose": "standard-library fixture"}, "files": {}, "cases": {},
        }
        for name, suffix in (("plos", ".png"), ("merged-table", ".pdf")):
            prefix = f"artifacts/local-20261026/{name}"
            case = {
                "input": f"samples/{name}{suffix}", "json": f"{prefix}/result.json",
                "docx": f"{prefix}/result.docx", "render_pdf": f"{prefix}/render.pdf",
                "render_pngs": [f"{prefix}/page-1.png"], "text_line_count": 2,
                "ocr_executed": True, "docx_generated": True,
                "visual_acceptance": "failed", "observations": ["Synthetic recorded visual failure"],
            }
            self.record["cases"][name] = case
            self.write(case["input"], PNG if suffix == ".png" else b"%PDF-1.4\nfixture input\n")
            payload = {"pages": [{"input_kind": "unrestricted-test-kind", "blocks": [
                {"text_lines": [{"text": "first"}, {"text": "second"}],
                 "image_overlay_text": [{"text": "excluded overlay"}],
                 "table": {"cells": [{"text_lines": [{"text": "excluded cell copy"}]}]}},
                {"text_lines": []},
            ]}]}
            self.write(case["json"], json.dumps(payload).encode())
            destination = self.root / case["docx"]
            with zipfile.ZipFile(destination, "w") as package:
                package.writestr("word/document.xml", WORD_XML)
            self.write(case["render_pdf"], b"%PDF-1.4\nfixture render signature only\n")
            self.write(case["render_pngs"][0], PNG)
            for relative in [case[k] for k in ("input", "json", "docx", "render_pdf")] + case["render_pngs"]:
                self.record_file(relative)
        self.save_record()

    def write(self, relative, data):
        path = self.root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)

    def record_file(self, relative):
        path = self.root / relative
        self.record["files"][relative] = {"bytes": path.stat().st_size, "sha256": sha256(path)}

    def save_record(self):
        self.write(RUN, json.dumps(self.record).encode())

    def failed_ids(self):
        report = verify_local(self.root)
        self.assertFalse(report["ok"], report)
        return {entry["id"] for entry in report["checks"] if not entry["passed"]}

    def snapshot(self):
        return {p.relative_to(self.root).as_posix(): (sha256(p), p.stat().st_mtime_ns)
                for p in self.root.rglob("*") if p.is_file()}

    def test_visual_failures_remain_visible_and_do_not_fail_integrity(self):
        before = self.snapshot()
        report = verify_local(self.root)
        self.assertTrue(report["ok"], report)
        for result in report["cases"].values():
            self.assertEqual(result["text_line_count"], 2)
            self.assertEqual(result["visual_acceptance"], "failed")
            self.assertEqual(result["observations"], ["Synthetic recorded visual failure"])
            self.assertEqual(result["docx_structure"]["native_table_count"], 1)
            self.assertFalse(result["visual_review_repeated"])
        for field in ("ocr_executed", "renderer_executed", "new_inference", "visual_review_repeated"):
            self.assertFalse(report[field])
        self.assertEqual(self.snapshot(), before)

    def test_same_size_input_tampering_fails_hash(self):
        relative = self.record["cases"]["plos"]["input"]
        data = bytearray((self.root / relative).read_bytes())
        data[-1] ^= 1
        self.write(relative, data)
        self.assertIn(f"file_hash:{relative}", self.failed_ids())

    def test_escape_and_noncanonical_paths_are_rejected(self):
        for relative in ("../outside.txt", "/outside.txt", "C:/outside.txt", "samples\\x.png",
                         "samples/../outside.txt", "samples//x.png", "./samples/x.png", "."):
            with self.subTest(relative=relative):
                with self.assertRaises(ValueError):
                    local_path(self.root, relative)
        self.record["files"]["../outside.txt"] = {"bytes": 0, "sha256": "0" * 64}
        self.save_record()
        self.assertIn("file_hash:../outside.txt", self.failed_ids())

    def test_symlink_escape_is_rejected_when_platform_allows_it(self):
        outside = Path(self.temp.name) / "outside.txt"
        outside.write_text("private fixture")
        link = self.root / "linked.txt"
        try:
            link.symlink_to(outside)
        except OSError as error:
            self.skipTest(f"Symlink creation unavailable: {error}")
        with self.assertRaises(ValueError):
            local_path(self.root, "linked.txt")

    def test_missing_render_is_an_explicit_failure(self):
        relative = self.record["cases"]["plos"]["render_pngs"][0]
        (self.root / relative).unlink()
        failures = self.failed_ids()
        self.assertIn(f"file_hash:{relative}", failures)
        self.assertIn(f"render_signature:plos:{relative}", failures)

    def test_false_text_line_count_is_recomputed(self):
        self.record["cases"]["plos"]["text_line_count"] = 3
        self.save_record()
        self.assertIn("text_line_count:plos", self.failed_ids())

    def test_boolean_cannot_be_used_as_a_recorded_line_count(self):
        self.record["cases"]["plos"]["text_line_count"] = True
        self.save_record()
        self.assertIn("case_paths:plos", self.failed_ids())

    def test_case_outputs_must_be_listed_in_files(self):
        relative = self.record["cases"]["merged-table"]["json"]
        del self.record["files"][relative]
        self.save_record()
        self.assertIn("case_paths:merged-table", self.failed_ids())

    def test_rehashed_invalid_render_or_docx_still_fails(self):
        for field, prefix in (("render_pdf", "render_signature:plos:"), ("docx", "docx_readable:")):
            with self.subTest(field=field):
                case = self.record["cases"]["plos"]
                relative = case[field]
                original = (self.root / relative).read_bytes()
                self.write(relative, b"not the claimed format")
                self.record_file(relative)
                self.save_record()
                expected = prefix + (relative if field == "render_pdf" else "plos")
                self.assertIn(expected, self.failed_ids())
                self.write(relative, original)
                self.record_file(relative)
                self.save_record()

    def test_wrong_json_shape_cannot_pass_as_pipeline_output(self):
        relative = self.record["cases"]["plos"]["json"]
        self.write(relative, b'{"native_text": "source reference, not OCR"}')
        self.record_file(relative)
        self.save_record()
        self.assertIn("text_line_count:plos", self.failed_ids())

    def test_absent_record_is_an_explicit_standalone_failure(self):
        (self.root / RUN).unlink()
        self.assertIn("read_local_run", self.failed_ids())

    def test_optional_table_score_is_recomputed_and_requires_listed_reference(self):
        case = self.record["cases"]["merged-table"]
        reference = {"rows": 1, "cols": 2, "physical_cell_count": 2, "merged_cell_count": 0,
                     "cells": [{"row": 0, "col": c, "rowspan": 1, "colspan": 1, "text": text}
                               for c, text in enumerate(("A", "B"))]}
        prediction = json.loads(json.dumps(reference))
        prediction["cells"][1]["text"] = "C"
        payload = json.loads((self.root / case["json"]).read_text())
        payload["errors"] = []
        payload["pages"][0]["blocks"][0]["table"] = prediction
        self.write(case["json"], json.dumps(payload).encode())
        self.write(TABLE_REFERENCE, json.dumps(reference).encode())
        case["table_score"] = "artifacts/local-20261026/merged-table/table-score.json"
        score = score_table(reference, {"success": True, "regions": payload["pages"][0]["blocks"]})
        self.write(case["table_score"], json.dumps(score).encode())
        for relative in (case["json"], TABLE_REFERENCE, case["table_score"]):
            self.record_file(relative)
        self.save_record()
        report = verify_local(self.root)
        self.assertTrue(report["ok"], report)
        self.assertEqual(report["cases"]["merged-table"]["table_score"]["cell_exact"], 1)
        self.assertEqual(report["cases"]["merged-table"]["table_score"]["character_edits"], 1)
        score["cell_exact"] = 2  # A rehashed false score must still be rejected.
        self.write(case["table_score"], json.dumps(score).encode())
        self.record_file(case["table_score"])
        self.save_record()
        self.assertIn("table_score:merged-table", self.failed_ids())
        del self.record["files"][TABLE_REFERENCE]
        self.save_record()
        self.assertIn("case_paths:merged-table", self.failed_ids())

    def test_cli_is_stdlib_only_and_read_only(self):
        for name in ("verify_local.py", "score_results.py"):
            path = self.root / "tools" / name
            path.parent.mkdir(exist_ok=True)
            shutil.copy2(SOURCE / "tools" / name, path)
        before = self.snapshot()
        result = subprocess.run(
            [sys.executable, "-S", str(self.root / "tools/verify_local.py")],
            cwd=self.root, capture_output=True, text=True, encoding="utf-8", check=False,
        )
        report = json.loads(result.stdout)
        self.assertEqual(result.returncode, 0, result.stderr or report)
        self.assertTrue(report["ok"], report)
        self.assertEqual(self.snapshot(), before)

    def test_demo_hook_keeps_local_results_separate(self):
        from tools.verify_demo import verify_demo
        report = verify_demo(self.root)  # This fixture intentionally has no historical evidence.
        self.assertFalse(report["ok"])
        self.assertTrue(report["local_run"]["ok"], report["local_run"])
        self.assertIsNone(report["table"])
        (self.root / RUN).unlink()
        self.assertEqual(verify_demo(self.root)["local_run"]["status"], "not_present")
        self.assertEqual(report["local_docx_fix"]["status"], "not_present")

    def test_explicit_record_preserves_the_original_failure(self):
        corrected = json.loads(json.dumps(self.record))
        corrected["cases"]["plos"]["visual_acceptance"] = "passed_for_recorded_scope"
        self.write(FIX_RUN, json.dumps(corrected).encode())
        before = self.snapshot()
        fixed = verify_local(self.root, FIX_RUN)
        original = verify_local(self.root)
        self.assertTrue(fixed["ok"], fixed)
        self.assertEqual(fixed["record"], FIX_RUN)
        self.assertEqual(fixed["cases"]["plos"]["visual_acceptance"], "passed_for_recorded_scope")
        self.assertEqual(original["record"], RUN)
        self.assertEqual(original["cases"]["plos"]["visual_acceptance"], "failed")
        self.assertEqual(self.snapshot(), before)

    def test_invalid_or_missing_explicit_record_never_falls_back(self):
        for relative in (FIX_RUN, "../private.json", "/outside.json", "C:/outside.json"):
            with self.subTest(relative=relative):
                report = verify_local(self.root, relative)
                self.assertFalse(report["ok"], report)
                self.assertEqual(report["record"], relative)
                self.assertEqual(report["checks"][0]["id"], "read_local_run")
                self.assertFalse(report["checks"][0]["passed"])
                self.assertEqual(report["cases"], {})

    def test_cli_can_select_a_new_record_without_the_original(self):
        self.write(FIX_RUN, json.dumps(self.record).encode())
        (self.root / RUN).unlink()
        before = self.snapshot()
        result = subprocess.run(
            [sys.executable, "-S", "-B", str(SOURCE / "tools/verify_local.py"),
             "--root", str(self.root), "--record", FIX_RUN],
            cwd=self.root, capture_output=True, text=True, encoding="utf-8", check=False,
        )
        report = json.loads(result.stdout)
        self.assertEqual(result.returncode, 0, result.stderr or report)
        self.assertTrue(report["ok"], report)
        self.assertEqual(report["record"], FIX_RUN)
        self.assertEqual(self.snapshot(), before)

    def test_demo_fix_hook_keeps_failures_separate_from_original_integrity(self):
        from tools.verify_demo import verify_demo
        self.write(FIX_RUN, json.dumps(self.record).encode())
        report = verify_demo(self.root)
        self.assertTrue(report["local_run"]["ok"], report["local_run"])
        self.assertTrue(report["local_docx_fix"]["ok"], report["local_docx_fix"])
        self.assertEqual(report["local_docx_fix"]["record"], FIX_RUN)
        corrected = json.loads(json.dumps(self.record))
        corrected["cases"]["plos"]["text_line_count"] = 999
        self.write(FIX_RUN, json.dumps(corrected).encode())
        report = verify_demo(self.root)
        self.assertTrue(report["local_run"]["ok"], report["local_run"])
        self.assertFalse(report["local_docx_fix"]["ok"], report["local_docx_fix"])
        failures = {entry["id"] for entry in report["checks"] if not entry["passed"]}
        self.assertIn("local_docx_fix_evidence", failures)
        self.assertNotIn("local_run_evidence", failures)


if __name__ == "__main__":
    unittest.main()
