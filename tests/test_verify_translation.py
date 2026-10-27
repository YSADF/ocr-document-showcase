"""Synthetic integrity fixtures only; no OCR, translation model, or renderer runs."""
import io
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
import zipfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from tools.verify_translation import RUN, SCHEMA, FAITHFUL_SCHEMA, PATH_FIELDS, verify_translation
from tools.verify_local import sha256

SOURCE = Path(__file__).resolve().parents[1]


def docx_bytes(table=True, chinese=True):
    text = "测试译文" if chinese else "Fixture source"
    cell = f"<w:tbl><w:tr><w:tc><w:p><w:r><w:t>{text}</w:t></w:r></w:p></w:tc></w:tr></w:tbl>" if table else ""
    xml = (f'<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
           f'<w:body><w:p><w:r><w:t>{text}</w:t></w:r></w:p>{cell}</w:body></w:document>')
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as package:
        package.writestr("word/document.xml", xml.encode("utf8"))
    return buffer.getvalue()


class VerifyTranslationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name) / "showcase"
        self.root.mkdir()
        self.record = {
            "schema_version": SCHEMA, "run_date": "2026-10-26",
            "environment": {"purpose": "synthetic fixture"},
            "models": {"purpose": "no model executed"}, "source": {"purpose": "fixture"},
            "files": {}, "cases": {},
        }
        for name in ("plos", "merged-table"):
            prefix = f"artifacts/local-translation-20261026/{name}"
            case = {field: f"{prefix}/{field}.json" for field in PATH_FIELDS}
            case.update(input=f"samples/{name}.png", docx=f"{prefix}/output.docx",
                        render_pdf=f"{prefix}/render/output.pdf",
                        render_pngs=[f"{prefix}/render/page-1.png"],
                        translation_executed=True, docx_generated=True,
                        visual_acceptance="failed", observations=["Synthetic recorded overlap"])
            self.record["cases"][name] = case
            source = {"pages": [{"blocks": [{"text_lines": [{"text": "Fixture source", "translated_text": ""}]}]}]}
            translated = json.loads(json.dumps(source))
            translated["pages"][0]["blocks"][0]["text_lines"][0]["translated_text"] = "测试译文"
            responses = {"model": "fixture/no-model", "revision": "fixture", "generation": {"fixture": True},
                         "requests": [{"request": {"q": ["Fixture source", "A-01"], "source": "en", "target": "zh"},
                                       "response": {"translatedText": ["测试译文", "A-01"]}}]}
            self.write(case["input"], b"synthetic input")
            self.write_json(case["source_json"], source)
            self.write_json(case["translated_json"], translated)
            self.write_json(case["model_responses"], responses)
            self.write_json(case["execution"], {"translation_executed": True, "docx_generated": True,
                            "translation_parameters": {"source_lang": "en", "target_lang": "zh"}})
            self.write_json(case["render_audit"], {"fixture": "no rendering performed"})
            self.write(case["docx"], docx_bytes())
            self.write(case["render_pdf"], b"%PDF-synthetic signature fixture")
            self.write(case["render_pngs"][0], b"\x89PNG\r\n\x1a\nsynthetic signature fixture")
        self.save_record()

    def write(self, relative, content):
        path = self.root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)
        self.record["files"][relative] = {"bytes": len(content), "sha256": sha256(path)}

    def write_json(self, relative, value):
        self.write(relative, json.dumps(value, ensure_ascii=False).encode("utf8"))

    def read_json(self, field, case="plos"):
        return json.loads((self.root / self.record["cases"][case][field]).read_text(encoding="utf8"))

    def save_record(self):
        path = self.root / RUN
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(self.record), encoding="utf8")

    def failures(self):
        self.save_record()
        report = verify_translation(self.root)
        self.assertFalse(report["ok"], report)
        return {check["id"] for check in report["checks"] if not check["passed"]}

    def test_integrity_does_not_upgrade_failed_visual_review_or_rerun_models(self):
        before = {p: (sha256(p), p.stat().st_mtime_ns) for p in self.root.rglob("*") if p.is_file()}
        report = verify_translation(self.root)
        self.assertTrue(report["ok"], report)
        for field in ("ocr_executed", "translation_executed", "renderer_executed", "new_inference", "visual_review_repeated"):
            self.assertFalse(report[field])
        self.assertEqual(report["cases"]["plos"]["visual_acceptance"], "failed")
        self.assertEqual(report["cases"]["plos"]["model_responses"]["response_entries_with_chinese"], 1)
        self.assertEqual(before, {p: (sha256(p), p.stat().st_mtime_ns) for p in self.root.rglob("*") if p.is_file()})

    def test_same_size_tampering_is_detected(self):
        relative = self.record["cases"]["plos"]["input"]
        path = self.root / relative
        path.write_bytes(b"X" + path.read_bytes()[1:])
        self.assertIn(f"file_hash:{relative}", self.failures())

    def test_rehashed_missing_translation_cannot_hide_in_metadata(self):
        payload = self.read_json("translated_json")
        payload["pages"][0]["blocks"][0]["text_lines"][0]["translated_text"] = ""
        payload["metadata"] = {"translated_text": "这不是正文译文"}
        self.write_json(self.record["cases"]["plos"]["translated_json"], payload)
        self.assertIn("translated_text:plos", self.failures())

    def test_table_raw_translation_provenance_is_supported(self):
        payload = {"pages": [{"blocks": [{"text_lines": [], "table": {"cells": [
            {"text": "测试译文", "source_text": "Fixture source", "raw": {"translated_text": "测试译文"}}]}}]}]}
        self.write_json(self.record["cases"]["merged-table"]["translated_json"], payload)
        self.save_record()
        self.assertTrue(verify_translation(self.root)["ok"])

    def test_rehashed_source_echo_is_not_translation_evidence(self):
        payload = self.read_json("model_responses")
        payload["requests"][0]["response"]["translatedText"] = ["Fixture source", "A-01"]
        self.write_json(self.record["cases"]["plos"]["model_responses"], payload)
        self.assertIn("model_responses:plos", self.failures())

    def test_wrong_direction_and_response_count_fail(self):
        relative = self.record["cases"]["plos"]["model_responses"]
        original = self.read_json("model_responses")
        for mutation in ("direction", "length"):
            with self.subTest(mutation=mutation):
                payload = json.loads(json.dumps(original))
                if mutation == "direction":
                    payload["requests"][0]["request"]["target"] = "en"
                else:
                    payload["requests"][0]["response"]["translatedText"].pop()
                self.write_json(relative, payload)
                self.assertIn("model_responses:plos", self.failures())

    def test_chinese_paragraph_does_not_replace_missing_native_table(self):
        self.write(self.record["cases"]["merged-table"]["docx"], docx_bytes(table=False))
        self.assertIn("docx_chinese:merged-table", self.failures())

    def test_docx_without_chinese_text_fails_even_if_rehashed(self):
        self.write(self.record["cases"]["plos"]["docx"], docx_bytes(chinese=False))
        self.assertIn("docx_chinese:plos", self.failures())

    def test_rehashed_invalid_render_signature_fails(self):
        relative = self.record["cases"]["plos"]["render_pngs"][0]
        self.write(relative, b"not an image")
        self.assertIn(f"render_signature:plos:{relative}", self.failures())

    def test_case_paths_must_be_listed_and_cannot_escape(self):
        self.record["cases"]["plos"]["docx"] = "../private.docx"
        self.record["files"]["../private.docx"] = {"bytes": 0, "sha256": "0" * 64}
        self.assertIn("case_paths:plos", self.failures())
        self.assertIn("file_hash:../private.docx", self.failures())
        self.record["cases"]["plos"]["docx"] = "unlisted.docx"
        self.assertIn("case_paths:plos", self.failures())

    def test_execution_statement_must_agree_with_case(self):
        execution = self.read_json("execution")
        execution["translation_executed"] = False
        self.write_json(self.record["cases"]["plos"]["execution"], execution)
        self.assertIn("execution_record:plos", self.failures())

    def test_cli_runs_with_standard_library_only(self):
        tool_dir = self.root / "tools"
        tool_dir.mkdir()
        for name in ("verify_translation.py", "verify_local.py", "score_results.py"):
            shutil.copyfile(SOURCE / "tools" / name, tool_dir / name)
        result = subprocess.run([sys.executable, "-S", "-X", "utf8", "-B", str(tool_dir / "verify_translation.py")],
                                cwd=self.root, capture_output=True, text=True, encoding="utf8")
        self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
        report = json.loads(result.stdout)
        self.assertTrue(report["ok"])
        self.assertFalse(report["translation_executed"])
        self.assertFalse(list(self.root.rglob("__pycache__")))

    def test_demo_hook_preserves_separate_translation_and_visual_status(self):
        from tools.verify_demo import verify_demo
        report = verify_demo(self.root)  # Historical evidence is intentionally absent.
        self.assertFalse(report["ok"])
        self.assertTrue(report["local_translation"]["ok"], report["local_translation"])
        self.assertEqual(report["local_translation"]["cases"]["plos"]["visual_acceptance"], "failed")
        self.assertEqual(report["local_run"]["status"], "not_present")
        self.assertEqual(report["local_docx_fix"]["status"], "not_present")
        self.assertFalse(report["translation_executed"])
        relative = self.record["cases"]["plos"]["docx"]
        self.write(relative, docx_bytes(chinese=False))
        self.save_record()
        report = verify_demo(self.root)
        self.assertFalse(report["local_translation"]["ok"])
        failures = {entry["id"] for entry in report["checks"] if not entry["passed"]}
        self.assertIn("local_translation_evidence", failures)

    def test_demo_hook_leaves_missing_translation_record_optional(self):
        from tools.verify_demo import verify_demo
        (self.root / RUN).unlink()
        report = verify_demo(self.root)
        self.assertEqual(report["local_translation"]["status"], "not_present")
        self.assertNotIn("local_translation_evidence", {entry["id"] for entry in report["checks"]})

    def faithful_fixture(self):
        self.record["schema_version"] = FAITHFUL_SCHEMA
        for case in self.record["cases"].values():
            buffer = io.BytesIO()
            with zipfile.ZipFile(buffer, "w") as package:
                package.writestr("word/document.xml", '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:body><w:p><w:pPr><w:framePr/></w:pPr><w:r><w:t>测试译文</w:t></w:r></w:p></w:body></w:document>')
                package.writestr("word/fonts/fixture.odttf", b"synthetic font fixture; not an actual font")
            self.write(case["docx"], buffer.getvalue())
            self.write_json(case["execution"], {
                "translation_executed": True, "docx_generated": True,
                "renderer_confirmed": "FaithfulWordBuilder",
                "translation_parameters": {"source_lang": "en", "target_lang": "zh",
                    "runtime_options": {"_faithful_layout": True, "_preserve_block_boundaries": True}}})
            self.write_json(case["render_audit"], {
                "docx_sha256": sha256(self.root / case["docx"]),
                "visual_review": {"acceptance": "failed"}, "report": {"passed": False},
                "layout": {"failed_region_count": 1, "page_plans": [{"failed_erase_regions": ["lost"]}],
                           "font_embedding": {"status": "success"}}})
        self.save_record()

    def test_faithful_frames_do_not_claim_native_table_or_success(self):
        self.faithful_fixture()
        report = verify_translation(self.root)
        self.assertTrue(report["ok"], report)
        case = report["cases"]["merged-table"]
        self.assertFalse(case["faithful_evidence"]["recorded_delivery_passed"])
        self.assertEqual(case["faithful_evidence"]["representation"], "source_background_and_native_text_frames")

    def test_source_table_score_requires_explicit_evaluation_evidence(self):
        self.faithful_fixture()
        self.record["cases"]["merged-table"]["source_table_score"] = "unlisted-table-score.json"
        self.assertIn("source_table_score:merged-table", self.failures())

    def test_faithful_failed_regions_cannot_claim_visual_pass(self):
        self.faithful_fixture()
        case = self.record["cases"]["plos"]
        case["visual_acceptance"] = "passed_for_page_layout"
        audit = self.read_json("render_audit")
        audit["visual_review"] = {"acceptance": "passed_for_page_layout", "overlap_seen": False,
            "clipping_seen": False, "page_overflow_seen": False, "source_pages": 1, "rendered_pages": 1}
        self.write_json(case["render_audit"], audit)
        self.assertIn("faithful_evidence:plos", self.failures())

    def test_faithful_missing_runtime_option_fails(self):
        self.faithful_fixture()
        execution = self.read_json("execution")
        execution["translation_parameters"]["runtime_options"].pop("_faithful_layout")
        self.write_json(self.record["cases"]["plos"]["execution"], execution)
        self.assertIn("faithful_evidence:plos", self.failures())

    def test_faithful_clean_layout_cannot_hide_delivery_failure_or_ghosts(self):
        self.faithful_fixture()
        case = self.record["cases"]["plos"]
        case["visual_acceptance"] = "passed_for_page_layout"
        audit = self.read_json("render_audit")
        audit["layout"].update(failed_region_count=0, page_plans=[{"failed_erase_regions": []}])
        audit["visual_review"] = {"acceptance": "passed_for_page_layout", "overlap_seen": False,
            "clipping_seen": False, "page_overflow_seen": False, "source_text_ghosts_seen": False,
            "source_pages": 1, "rendered_pages": 1}
        self.write_json(case["render_audit"], audit)
        self.assertIn("faithful_evidence:plos", self.failures())
        audit["report"] = {"passed": True, "violations": []}
        audit["visual_review"]["source_text_ghosts_seen"] = True
        self.write_json(case["render_audit"], audit)
        self.assertIn("faithful_evidence:plos", self.failures())
        audit["visual_review"]["source_text_ghosts_seen"] = False
        self.write_json(case["render_audit"], audit)
        self.save_record()
        self.assertTrue(verify_translation(self.root)["ok"])

    def test_faithful_audit_cannot_reference_another_docx(self):
        self.faithful_fixture()
        audit = self.read_json("render_audit")
        audit["docx_sha256"] = "0" * 64
        self.write_json(self.record["cases"]["plos"]["render_audit"], audit)
        self.assertIn("faithful_evidence:plos", self.failures())

    def test_faithful_missing_font_fails_after_rehash(self):
        self.faithful_fixture()
        case = self.record["cases"]["plos"]
        data = io.BytesIO()
        with zipfile.ZipFile(self.root / case["docx"]) as original, zipfile.ZipFile(data, "w") as target:
            target.writestr("word/document.xml", original.read("word/document.xml"))
        self.write(case["docx"], data.getvalue())
        audit = self.read_json("render_audit")
        audit["docx_sha256"] = sha256(self.root / case["docx"])
        self.write_json(case["render_audit"], audit)
        self.assertIn("faithful_evidence:plos", self.failures())


if __name__ == "__main__":
    unittest.main()
