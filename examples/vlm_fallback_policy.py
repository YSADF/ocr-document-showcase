"""Selected production policy helpers; no model loader, scheduler or automatic replacement.

A model agreement is evidence, not verified recognition correctness.
"""
import re


_CRITICAL = re.compile(r"[0-9Ø⌀∅Φφ±+\-−.,×x°²³⁰¹⁴⁵⁶⁷⁸⁹⁺⁻]")


_HIGH_RISKS = {"unexplained_neighbor_ink", "leading_glyph_requires_verification",
               "positioned_candidate_conflict", "stacked_tolerance_fragment",
               "diameter_glyph_ambiguous", "tolerance_sign_ambiguous",
               "letter_digit_confusable", "multiplication_glyph_ambiguous",
               "critical_candidate_conflict"}


def _risk_priority(region):
    risks = set(region.get("risks", []))
    if risks & _HIGH_RISKS:
        return 0
    if risks & {"detected_empty_region", "direction_recognition_failed", "formula_unverified"}:
        return 1
    if "low_confidence" in risks and "critical_engineering_annotation" in risks:
        return 1
    if "dimension_symbol_completeness_unverified" in risks:
        return 2  # Only the remaining bounded regional budget after error evidence.
    # Page-level needs_review by itself is never a trigger.
    return None


def _valid_output(observation, task):
    if observation.get("status") != "ok":
        return str(observation.get("status") or "invalid_response")
    if observation.get("truncated") or observation.get("finish_reason") in {"length", "max_tokens"}:
        return "truncated"
    text = observation.get("text")
    if not isinstance(text, str) or not text.strip():
        return "empty_output"
    if "```" in text or "\x00" in text or re.match(
            r"\s*(?:the (?:image|text|formula)|here (?:is|are)|识别结果[：:]|转写结果[：:])", text, re.I):
        return "nonliteral_output"
    if task == "text" and ("\n" in text.strip() or "\r" in text.strip()):
        return "multiple_annotation_output"
    if task == "formula":
        depth = 0
        for char in re.sub(r"\\[{}]", "", text):
            depth += (char == "{") - (char == "}")
            if depth < 0:
                return "invalid_formula_structure"
        if depth:
            return "invalid_formula_structure"
    return "ok"


def _weight(observation):
    model = observation.get("model") or {}
    if not isinstance(model, dict):
        return None
    identity = model.get("weight_identity") or model.get("weights_sha256") or model.get("weight_sha256")
    if identity:
        return str(identity)
    # A model label/path alone is not proof that different weights were loaded.
    revision = model.get("revision") or model.get("commit_hash")
    model_id = model.get("id") or model.get("model_id")
    return f"{model_id}@{revision}" if model_id and revision else None


def _critical_change(old, new, task):
    return task == "formula" or _CRITICAL.findall(old) != _CRITICAL.findall(new)
