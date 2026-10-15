"""Regression checks using copies of the real, public frozen demo."""
import copy
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from tools import score_results
from tools.verify_demo import EXPECTED_SCORE, REQUIRED_METADATA_FILES, sha256, verify_demo

SOURCE = Path(__file__).resolve().parents[1]
RUN = Path("artifacts/gpu-20261007")


class VerifyDemoTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name) / "showcase"
        paths = set(REQUIRED_METADATA_FILES) | {
            "artifacts/case-metadata.json",
            (RUN / "benchmark.json").as_posix(),
            (RUN / "quality.json").as_posix(),
            (RUN / "merged-table-response.json").as_posix(),
            (RUN / "engineering-response.json").as_posix(),
            "tools/score_results.py", "tools/verify_demo.py",
        }
        for name in ("engineering", "merged-table"):
            paths.update({
                (RUN / f"{name}-output.docx").as_posix(),
                (RUN / f"{name}-render" / f"{name}-output.pdf").as_posix(),
                (RUN / f"{name}-render/page-1.png").as_posix(),
            })
        for relative in paths:
            destination = self.root / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(SOURCE / relative, destination)

    def load(self, relative):
        return json.loads((self.root / relative).read_text(encoding="utf-8"))

    def save(self, relative, data):
        (self.root / relative).write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")

    def snapshot(self):
        return {p.relative_to(self.root).as_posix(): (sha256(p), p.stat().st_mtime_ns)
                for p in self.root.rglob("*") if p.is_file()}

    def failed_ids(self, report):
        self.assertFalse(report["ok"])
        return {c["id"] for c in report["checks"] if not c["passed"]}

    def cli(self, tool="verify_demo.py", *args):
        # No -B: read-only defaults must prevent bytecode files themselves.
        result = subprocess.run(
            [sys.executable, "-S", str(self.root / "tools" / tool), *map(str, args)],
            cwd=self.root, capture_output=True, text=True, encoding="utf-8", check=False,
        )
        return result.returncode, json.loads(result.stdout)

    def test_real_baseline_and_historical_failures_are_preserved(self):
        before = self.snapshot()
        report = verify_demo(self.root)
        self.assertTrue(report["ok"], report["checks"])
        self.assertEqual({k: report["table"][k] for k in EXPECTED_SCORE}, EXPECTED_SCORE)
        self.assertAlmostEqual(report["table"]["cer"], 2 / 203)
        self.assertFalse(report["native_text_used_as_ocr"])
        for docx in report["docx"].values():
            self.assertTrue(docx["structure"]["package_and_xml_readable"])
            self.assertEqual(docx["historical_visual_review"]["visual_acceptance"], "failed")
            self.assertFalse(docx["visual_review_repeated"])
        self.assertEqual(self.snapshot(), before)

    def test_default_clis_are_stdlib_only_and_do_not_write(self):
        before = self.snapshot()
        for tool in ("verify_demo.py", "score_results.py"):
            with self.subTest(tool=tool):
                status, report = self.cli(tool)
                self.assertEqual(status, 0, report)
                self.assertTrue(report["ok"])
                self.assertFalse(report["ocr_executed"])
                self.assertFalse(report["renderer_executed"])
        self.assertEqual(self.snapshot(), before)

    def test_input_byte_tampering_fails_metadata_and_actual_input(self):
        path = self.root / "samples/merged-table-scan.pdf"
        path.write_bytes(path.read_bytes() + b"changed")
        ids = self.failed_ids(verify_demo(self.root))
        self.assertIn("metadata_hash:samples/merged-table-scan.pdf", ids)
        self.assertIn("actual_ocr_input:merged-table", ids)
        status, report = self.cli()
        self.assertEqual(status, 1)
        self.assertFalse(report["ok"])

    def test_rewriting_metadata_cannot_relabel_a_different_measured_input(self):
        relative = "samples/merged-table-scan.pdf"
        path = self.root / relative
        path.write_bytes(path.read_bytes() + b"changed")
        digest = sha256(path)
        metadata = self.load("artifacts/case-metadata.json")
        metadata["files"][relative] = {"sha256": digest, "bytes": path.stat().st_size}
        self.save("artifacts/case-metadata.json", metadata)
        benchmark = self.load(RUN / "benchmark.json")
        benchmark["cases"]["merged-table"]["sha256"] = digest
        self.save(RUN / "benchmark.json", benchmark)
        self.assertIn("actual_ocr_input:merged-table", self.failed_ids(verify_demo(self.root)))

    def test_missing_input_is_an_explicit_failure(self):
        (self.root / "samples/c03-source.pdf").unlink()
        self.assertIn("metadata_hash:samples/c03-source.pdf", self.failed_ids(verify_demo(self.root)))

    def test_native_text_cannot_replace_an_ocr_response(self):
        shutil.copy2(self.root / "artifacts/c03-native-text.json",
                     self.root / RUN / "engineering-response.json")
        self.assertIn("saved_ocr_response:engineering", self.failed_ids(verify_demo(self.root)))

    def test_reference_count_cannot_disagree_with_real_cells(self):
        reference = self.load("artifacts/merged-table-ground-truth.json")
        reference["physical_cell_count"] = 20
        self.save("artifacts/merged-table-ground-truth.json", reference)
        self.assertIn("recompute_table", self.failed_ids(verify_demo(self.root)))

    def test_duplicate_cell_is_not_hidden_by_dictionary_conversion(self):
        response = self.load(RUN / "merged-table-response.json")
        table = next(r["table"] for r in response["regions"] if r.get("table"))
        table["cells"].append(copy.deepcopy(table["cells"][0]))
        self.save(RUN / "merged-table-response.json", response)
        report = verify_demo(self.root)
        self.assertIn("recompute_table", self.failed_ids(report))
        check = next(c for c in report["checks"] if c["id"] == "recompute_table")
        self.assertIn("duplicate cell anchor", check["error"])

    def test_changed_prediction_recomputes_score_and_rejects_false_baseline(self):
        response = self.load(RUN / "merged-table-response.json")
        table = next(r["table"] for r in response["regions"] if r.get("table"))
        table["cells"][0]["text"] += "!"
        self.save(RUN / "merged-table-response.json", response)
        report = verify_demo(self.root)
        self.assertEqual(report["table"]["cell_exact"], 18)
        self.assertEqual(report["table"]["character_edits"], 3)
        self.assertIn("fixed_table_baseline", self.failed_ids(report))

    def test_removed_cell_changes_score_and_is_not_counted_correct(self):
        response = self.load(RUN / "merged-table-response.json")
        table = next(r["table"] for r in response["regions"] if r.get("table"))
        table["cells"].pop()
        self.save(RUN / "merged-table-response.json", response)
        report = verify_demo(self.root)
        self.assertEqual(report["table"]["predicted_cells"], 20)
        self.assertEqual(report["table"]["matching_cell_spans"], 20)
        self.assertEqual(report["table"]["merges"]["false_negative"], 1)
        self.assertIn("fixed_table_baseline", self.failed_ids(report))

    def test_false_historical_score_and_visual_pass_are_rejected(self):
        quality = self.load(RUN / "quality.json")
        quality["cell_exact"] = 21
        quality["docx"]["merged-table"]["visual_acceptance"] = "passed"
        self.save(RUN / "quality.json", quality)
        ids = self.failed_ids(verify_demo(self.root))
        self.assertIn("table_matches_historical_quality", ids)
        self.assertIn("historical_docx_review:merged-table", ids)

    def test_damaged_docx_and_missing_render_fail(self):
        (self.root / RUN / "engineering-output.docx").write_bytes(b"not a zip")
        (self.root / RUN / "merged-table-render/page-1.png").unlink()
        ids = self.failed_ids(verify_demo(self.root))
        self.assertIn("docx_readable:engineering", ids)
        self.assertIn("historical_render_exists:artifacts/gpu-20261007/merged-table-render/page-1.png", ids)

    def test_explicit_reports_cannot_overwrite_frozen_or_existing_files(self):
        before = self.snapshot()
        for tool in ("verify_demo.py", "score_results.py"):
            for relative in ("artifacts/gpu-20261007/quality.json", "artifacts/new.json",
                             "samples/new.json", "assets/new.json"):
                with self.subTest(tool=tool, relative=relative):
                    status, report = self.cli(tool, "--output", self.root / relative)
                    self.assertEqual(status, 1)
                    self.assertFalse(report["ok"])
        self.assertEqual(self.snapshot(), before)
        output = self.root / "results/check.json"
        status, report = self.cli("verify_demo.py", "--output", output)
        self.assertEqual(status, 0)
        self.assertEqual(json.loads(output.read_text(encoding="utf-8")), report)
        frozen = output.read_bytes()
        status, report = self.cli("score_results.py", "--output", output)
        self.assertEqual(status, 1)
        self.assertEqual(output.read_bytes(), frozen)

    def test_optional_release_manifest_checks_hashes_and_rejects_traversal(self):
        relative = "artifacts/gpu-20261007/engineering-response.json"
        path = self.root / relative
        manifest = self.root / "release.json"
        self.save("release.json", {"files": {relative: {"bytes": path.stat().st_size, "sha256": sha256(path)}}})
        self.assertTrue(verify_demo(self.root, manifest)["ok"])
        path.write_bytes(path.read_bytes() + b" ")
        self.assertIn("release_hash:" + relative, self.failed_ids(verify_demo(self.root, manifest)))
        self.save("release.json", {"files": {"../outside.txt": {"bytes": 0, "sha256": "0" * 64}}})
        self.assertIn("release_hash:../outside.txt", self.failed_ids(verify_demo(self.root, manifest)))

    def test_unicode_symbols_are_not_folded(self):
        self.assertEqual(score_results.normalize("  Ø\t 50  "), "Ø 50")
        self.assertEqual(score_results.distance("Ø", "∅"), 1)


if __name__ == "__main__":
    unittest.main()

