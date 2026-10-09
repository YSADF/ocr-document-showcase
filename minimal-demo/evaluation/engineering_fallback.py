"""Post-inference scoring for actual fallback choices, separate from routing.

Importing this module is not required by any inference worker or selector.
References may be assistant-generated development references, never training gold.
"""
from collections import Counter
import copy
from difflib import SequenceMatcher

from evaluation.engineering_metrics import CRITICAL, score_sample
from evaluation.engineering_vlm import literal_score


def effective_response(response):
    """Use the selected output for final transcription scoring; preserve input."""
    result = copy.deepcopy(response)
    for page in result.get("pages", []):
        for block in page.get("regions", []):
            rows = block.get("text_lines", []) + block.get("image_overlay_text", [])
            rows += (block.get("table") or {}).get("cells", [])
            for row in rows:
                row["source_text"] = row.get("text", "")
    return result


def table_structure(response):
    return [[{"bbox": [block.get(k) for k in ("x1", "y1", "x2", "y2")],
              "rows": block["table"].get("rows"), "cols": block["table"].get("cols"),
              "cells": [{key: cell.get(key) for key in ("row", "col", "rowspan", "colspan", "bbox")}
                        for cell in block["table"].get("cells", [])]}
             for block in page.get("regions", []) if block.get("table")]
            for page in response.get("pages", [])]


def paired_sample(sample, baseline, response):
    from evaluation.engineering_collaboration import paired_character_analysis
    before = score_sample(sample, baseline)
    after = score_sample(sample, effective_response(response))
    pairs = []
    for original, current in zip(before["regions"], after["regions"]):
        expected = Counter(c for c in current["expected"] if c in CRITICAL)
        prior = Counter(c for c in original["predicted"] if c in CRITICAL)
        selected = Counter(c for c in current["predicted"] if c in CRITICAL)
        new_false_symbols = (selected - expected) - (prior - expected)
        def critical_edits(predicted):
            errors = set()
            reference = current["expected"]
            for tag, a, b, c, d in SequenceMatcher(None, reference, predicted, autojunk=False).get_opcodes():
                if tag != "equal" and any(char in CRITICAL for char in reference[a:b] + predicted[c:d]):
                    errors.add((a, b, reference[a:b], predicted[c:d]))
            return errors
        newly_wrong_critical = critical_edits(current["predicted"]) - critical_edits(original["predicted"])
        pairs.append({**current, **paired_character_analysis(current["expected"], original["predicted"], current["predicted"]),
                      "original": original["predicted"],
                      "original_exact": original["exact"],
                      "corrected": not original["exact"] and current["exact"],
                      "regressed": original["exact"] and not current["exact"],
                      "new_false_critical_insertions": dict(new_false_symbols),
                      "new_critical_edit_errors": [list(error) for error in sorted(newly_wrong_critical)]})
    return {**after, "regions": pairs,
            "table_structure_unchanged": table_structure(baseline) == table_structure(response)}


def summarize_hybrid(scores, performance=None, expected_ids=None):
    groups = {}
    for kind in ("mechanical", "pid"):
        rows = [r for sample in scores if sample["kind"] == kind for r in sample["regions"]]
        groups[kind] = {"n": len(rows), "original_exact": sum(r["original_exact"] for r in rows),
                       "selected_exact": sum(r["exact"] for r in rows),
                       "corrected": sum(r["corrected"] for r in rows),
                       "regressed": sum(r["regressed"] for r in rows),
                       "needs_review": sum(r["needs_review"] for r in rows),
                       "new_false_critical_regions": sum(bool(r["new_false_critical_insertions"]) for r in rows),
                       "new_critical_error_regions": sum(bool(r.get("new_critical_edit_errors")) for r in rows),
                       "unlocated": sum(not r["found"] for r in rows)}
    mechanical, pid = groups["mechanical"], groups["pid"]
    sample_ids = [sample["sample_id"] for sample in scores]
    complete = (len(scores) == 20 and len(set(sample_ids)) == 20
                and expected_ids is not None and set(sample_ids) == set(expected_ids)
                and mechanical["n"] == 118 and pid["n"] == 120
                and all(sample.get("result_present", True) for sample in scores))
    baseline_matches = mechanical["original_exact"] == 83 and pid["original_exact"] == 113
    structure_ok = all(s["table_structure_unchanged"] for s in scores)
    known_false_insertions = sum(g["new_false_critical_regions"] + g["new_critical_error_regions"] for g in groups.values())
    eligible = (complete and baseline_matches and mechanical["selected_exact"] > 83
                and pid["selected_exact"] >= 113 and not known_false_insertions and structure_ok)
    return {"scope": "development reference consistency; no new human validation", "groups": groups,
            "complete": complete, "baseline_matches_frozen": baseline_matches,
            "missing_sample_ids": [s["sample_id"] for s in scores if not s.get("result_present", True)],
            "table_structure_unchanged": structure_ok,
            "eligible_for_conditional_test_service": eligible,
            "formal_acceptance": False, "human_verified": False,
            "review_is_recognition_credit": False, "performance": performance or {}}


def validate_weight_consistency(records):
    """Reject mixed actual weights/configs within a resumed model experiment."""
    seen = {}
    def walk(value):
        if isinstance(value, dict):
            identity = value.get("model")
            if isinstance(identity, dict) and identity.get("weight_identity"):
                key = identity.get("id")
                if not key:
                    raise ValueError("Actual model identity lacks repository ID")
                fingerprint = (identity["weight_identity"], identity.get("configuration_fingerprint"))
                if key in seen and seen[key] != fingerprint:
                    raise ValueError("Mixed actual weights/configuration for " + key)
                seen[key] = fingerprint
            for item in value.values():
                walk(item)
        elif isinstance(value, list):
            for item in value:
                walk(item)
    walk(records)
    return {key: {"weight_identity": value[0], "configuration_fingerprint": value[1]}
            for key, value in seen.items()}


def choose_model(reports):
    eligible = [(name, report) for name, report in reports.items()
                if report.get("eligible_for_conditional_test_service")]
    if not eligible:
        return {"model": None, "mode": "evidence", "reason": "No measured hybrid passed the development gate"}
    def key(entry):
        name, report = entry
        group = report["groups"]["mechanical"]
        regressions = sum(g["regressed"] for g in report["groups"].values())
        seconds = report.get("performance", {}).get("p50_seconds")
        return (-group["selected_exact"], regressions,
                float("inf") if seconds is None else seconds, name != "glm-ocr", name)
    name, report = min(eligible, key=key)
    return {"model": name, "mode": "conditional", "human_verified": False,
            "formal_acceptance": False, "reason": "Development hybrid gate only; machine-selected output remains unverified"}


def score_crop_tasks(queue, references, records):
    rows = []
    for task in queue["tasks"]:
        if task["id"] not in references:
            raise ValueError("Missing reference for selected task: " + task["id"])
        result = records.get(task["id"], {"status": "missing", "text": "", "inference_executed": False})
        reference = references[task["id"]]
        value = reference.get("text", reference.get("latex", ""))
        if not isinstance(value, str) or not value.strip():
            raise ValueError("Empty reference for selected task: " + task["id"])
        prediction = result.get("text", "") if result.get("status") == "ok" else ""
        rows.append({"id": task["id"], "suite": task["suite"], "category": task.get("category"),
                     "status": result["status"], "reference": value,
                     "inference_executed": result.get("inference_executed", not result.get("circuit_open", False)),
                     "circuit_open": result.get("circuit_open", False),
                     "prediction": prediction, "raw_output": result.get("text", ""),
                     "score": literal_score(value, prediction)})
    summaries = {}
    for suite in sorted({r["suite"] for r in rows}):
        subset = [r for r in rows if r["suite"] == suite]
        summaries[suite] = {"n": len(subset), "exact": sum(r["score"]["exact"] for r in subset),
                            "statuses": dict(Counter(r["status"] for r in subset)),
                            "metric": "Unicode exact after whitespace normalization; not CDM"}
        if suite == "formula":
            summaries[suite]["categories"] = {category: {
                "n": sum(r["category"] == category for r in subset),
                "exact": sum(r["category"] == category and r["score"]["exact"] for r in subset)}
                for category in ("spe", "cpe", "sce", "hwe")}
    return {"scope": "standalone crop outputs; never final hybrid accuracy",
            "summaries": summaries, "rows": rows}
