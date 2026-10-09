"""Identical sanitized behavior fixtures for business and exported implementations."""
from types import SimpleNamespace
import numpy as np
import pytest
from models import BlockType, DocumentResult, LayoutBlock, PageResult, TextLine
from pipeline.engineering_review import review_engineering_page
from pipeline.engineering_vlm_fallback import apply_engineering_vlm_fallback, order_regions
from services.document_results import serialize_page_results
from evaluation.engineering_collaboration import paired_character_analysis


@pytest.mark.parametrize("scenario,selected", [("agree", True), ("same_weights", False), ("disagree", False), ("timeout", False)])
def test_public_selection_preserves_source_and_machine_review(scenario, selected):
    image = np.full((200, 300, 3), 255, dtype=np.uint8)
    line = TextLine("20", (40, 60, 100, 85), source_text="20", confidence=.99)
    page = PageResult(1, 300, 200, blocks=[LayoutBlock(BlockType.TEXT, (0, 0, 300, 200), text_lines=[line])])
    review_engineering_page(image, page, settings=SimpleNamespace(), reader=None)
    for row in page.metadata["engineering_review"]["unique_regions"]:
        row["risks"] = ["leading_glyph_requires_verification"]
    def runner(pixels, *, model, task, max_new_tokens, timeout_seconds):
        assert timeout_seconds <= 15 and task == "text"
        if scenario == "timeout":
            raise TimeoutError()
        return {"status": "ok", "text": "Ø20" if scenario != "disagree" or model == "glm-ocr" else "Ø21",
                "model": {"id": model, "weight_identity": "alias" if scenario == "same_weights" else model},
                "elapsed_seconds": .001}
    summary = apply_engineering_vlm_fallback(page, image, mode="conditional", runner=runner)
    assert summary["selected_regions"] == int(selected)
    result = serialize_page_results(DocumentResult(source_path="fixture.png", pages=[page]))[0]
    output = result["regions"][0]["text_lines"][0]
    assert output["text"] == ("Ø20" if selected else "20")
    assert output["source_text"] == "20"
    assert result["engineering_review"]["needs_review"]


def test_public_routing_is_label_independent():
    rows = [{"id": str(i), "bbox": [0, i, 10, i+1], "priority": 0,
             "routing_evidence": {"evidence_rank": i//3}, "reference": "ignored"} for i in range(6)]
    assert [r["id"] for r in order_regions(rows, "stratified")] == ["0", "3", "1", "4", "2", "5"]
    for row in rows:
        row["reference"] = "different hidden label"
    assert [r["id"] for r in order_regions(rows, "stratified")] == ["0", "3", "1", "4", "2", "5"]


def test_public_scoring_detects_wrong_inserted_digit():
    assert paired_character_analysis("Ø20", "20", "Ø201")["new_sensitive_errors"]
    assert not paired_character_analysis("Ø20", "20", "Ø20")["new_sensitive_errors"]
