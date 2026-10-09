"""Versioned, manifest-driven evaluation. No inference or candidate selection here."""
from collections import Counter
import hashlib
import json
import random

SENSITIVE = set("0123456789Ø⌀∅Φφ±°×÷≤≥μµ²³′″−+-.,")


def fingerprint(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False,
                                     separators=(",", ":")).encode()).hexdigest()


def character_edits(reference, prediction):
    """Minimum-edit alignment including insertions; deterministic diagonal tie order."""
    dp = [list(range(len(prediction) + 1))]
    for i, a in enumerate(reference, 1):
        row = [i]
        for j, b in enumerate(prediction, 1):
            row.append(min(dp[i-1][j-1] + (a != b), dp[i-1][j] + 1, row[-1] + 1))
        dp.append(row)
    edits, i, j = [], len(reference), len(prediction)
    while i or j:
        if i and j and dp[i][j] == dp[i-1][j-1] + (reference[i-1] != prediction[j-1]):
            if reference[i-1] != prediction[j-1]:
                edits.append(("substitute", i-1, reference[i-1], prediction[j-1]))
            i, j = i-1, j-1
        elif i and dp[i][j] == dp[i-1][j] + 1:
            edits.append(("delete", i-1, reference[i-1], ""))
            i -= 1
        else:
            edits.append(("insert", i, "", prediction[j-1]))
            j -= 1
    return list(reversed(edits))


def sensitive_edits(reference, prediction):
    return [e for e in character_edits(reference, prediction) if SENSITIVE.intersection(e[2] + e[3])]


def paired_character_analysis(reference, original, selected):
    before = sensitive_edits(reference, original)
    after = sensitive_edits(reference, selected)
    added = Counter(after) - Counter(before)
    return {"character_edits_v2": character_edits(reference, selected),
            "sensitive_errors_before": before, "sensitive_errors_after": after,
            "new_sensitive_errors": list(added.elements())}


def bootstrap_pages(scores, repeats=1000):
    if not scores:
        return None
    rng, values = random.Random(1729), []
    for _ in range(repeats):
        pages = [rng.choice(scores) for _ in scores]
        rows = [r for page in pages for r in page["regions"]]
        if rows:
            values.append(100 * sum(int(r["exact"]) - int(r["original_exact"]) for r in rows) / len(rows))
    if not values:
        return None
    values.sort()
    return {"unit": "page", "seed": 1729, "replicates": repeats,
            "delta_percentage_points_95_percentile": [values[int(.025*len(values))], values[int(.975*len(values))]],
            "note": "Small-sample descriptive uncertainty; pages within a family may be correlated"}


def metrics(rows):
    changed = [r for r in rows if r["original"] != r["predicted"]]
    correct = sum(r["exact"] for r in rows)
    before = sum(r["original_exact"] for r in rows)
    edits = [e for r in rows for e in r.get("character_edits_v2", character_edits(r["expected"], r["predicted"]))]
    chars = sum(len(r["expected"]) for r in rows)
    return {"n": len(rows), "original_exact": before, "selected_exact": correct,
            "corrected": sum(r["corrected"] for r in rows), "regressed": sum(r["regressed"] for r in rows),
            "net_corrected": correct-before,
            "delta_percentage_points": 100*(correct-before)/len(rows) if rows else None,
            "cer": len(edits)/chars if chars else None,
            "edit_operations": dict(Counter(e[0] for e in edits)),
            "changed_annotated_regions": len(changed),
            "selected_correct_fraction": sum(r["exact"] for r in changed)/len(changed) if changed else None,
            "new_sensitive_error_regions": sum(bool(r.get("new_sensitive_errors")) for r in rows),
            "needs_review": sum(r["needs_review"] for r in rows),
            "unlocated": sum(not r["found"] for r in rows)}


def changes_for_review(records):
    changes = []
    for task_id, record in sorted(records.items()):
        for row in record.get("summary", {}).get("regions", []):
            if row.get("status") == "selected":
                item = {"task_id": task_id, "region_id": row["unique_region_id"],
                        "bbox": row.get("bbox"), "original": row["source_text"],
                        "selected": row["selected_text"]}
                item["change_sha256"] = fingerprint(item)
                changes.append(item)
    return changes


def human_label_verified(region):
    review = region.get("human_review") or {}
    return (review.get("method") == "human" and bool(review.get("reviewer"))
            and review.get("decision") == "confirmed" and bool(review.get("reviewed_at"))
            and review.get("text") == region["text"])


def routing_metrics(scores, samples, records):
    from evaluation.engineering_metrics import intersection_over_union
    by_sample = {s["sample_id"]: s for s in scores}
    by_record = {r.get("task", {}).get("sample_id", key): r for key, r in records.items()}
    counts = Counter()
    for sample in samples:
        record = by_record.get(sample["id"], {})
        candidates = record.get("summary", {}).get("regions", [])
        counts["routed_candidates"] += len(candidates)
        used = set()
        original = {r["id"]: r for r in by_sample.get(sample["id"], {}).get("regions", [])}
        pages = record.get("response", {}).get("pages", [])
        page = pages[0] if pages else {}
        sx, sy = sample.get("width", 1)/float(page.get("width") or sample.get("width", 1)), sample.get("height", 1)/float(page.get("height") or sample.get("height", 1))
        for reference in sample["regions"]:
            counts["annotated_regions"] += 1
            wrong = not original.get(reference["id"], {}).get("original_exact", False)
            counts["annotated_errors"] += wrong
            options = []
            for index, candidate in enumerate(candidates):
                box = candidate.get("bbox")
                if index in used or not box or reference.get("kind", "line") not in candidate.get("geometry_kinds", []):
                    continue
                scaled = [box[0]*sx, box[1]*sy, box[2]*sx, box[3]*sy]
                options.append((intersection_over_union(reference["bbox"], scaled), index))
            overlap, index = max(options, default=(0., -1))
            if overlap < .2:
                continue
            used.add(index)
            candidate = candidates[index]
            counts["matched_annotated_candidates"] += 1
            counts["errors_in_candidates"] += wrong
            counts["errors_in_budget"] += wrong and bool(candidate.get("within_region_budget"))
            counts["errors_completed"] += wrong and bool(candidate.get("invocation_completed"))
    denominator = counts["annotated_errors"]
    return {**dict(counts), "unannotated_candidates": counts["routed_candidates"]-counts["matched_annotated_candidates"],
            "candidate_error_recall": counts["errors_in_candidates"]/denominator if denominator else None,
            "budget_error_recall": counts["errors_in_budget"]/denominator if denominator else None,
            "completed_error_recall": counts["errors_completed"]/denominator if denominator else None,
            "precision_on_annotated_only": counts["errors_in_candidates"]/counts["matched_annotated_candidates"] if counts["matched_annotated_candidates"] else None,
            "scope": "Sparse annotations only; unannotated candidates are unknown, not correct"}


def summarize_experiment(scores, samples, *, profile="development", performance=None,
                         configuration=None, change_reviews=None, records=None):
    if profile not in {"development", "holdout"}:
        raise ValueError("Unknown evaluation profile")
    configuration, records = configuration or {}, records or {}
    expected = {s["id"]: s for s in samples}
    ids = [s["sample_id"] for s in scores]
    complete = bool(samples) and len(expected) == len(samples) and len(set(ids)) == len(ids) and set(ids) == set(expected)
    for sample in scores:
        spec = expected.get(sample["sample_id"], {})
        wanted = [r["id"] for r in spec.get("regions", [])]
        actual = [r["id"] for r in sample["regions"]]
        complete = complete and len(set(wanted)) == len(wanted) and actual == wanted and sample.get("result_present", True)
    rows = [r for s in scores for r in s["regions"]]
    groups = {kind: metrics([r for s in scores if s["kind"] == kind for r in s["regions"]])
              for kind in ("mechanical", "pid")}
    families = sorted({s.get("drawing_family", "unknown") for s in samples})
    family_scores = {}
    for family in families:
        subset = [s for s in scores if expected.get(s["sample_id"], {}).get("drawing_family", "unknown") == family]
        family_scores[family] = {**metrics([r for s in subset for r in s["regions"]]),
                                 "pages": len(subset), "uncertainty": bootstrap_pages(subset)}
    for kind in groups:
        subset = [s for s in scores if s["kind"] == kind]
        groups[kind].update(pages=len(subset), uncertainty=bootstrap_pages(subset))
    human = bool(samples) and all(human_label_verified(r) for s in samples for r in s["regions"])
    changes = changes_for_review(records)
    submitted = (change_reviews or {}).get("records", [])
    reviews = {r.get("change_sha256"): r for r in submitted}
    reviewed = bool(change_reviews) and len(reviews) == len(submitted) and all(
        c["change_sha256"] in reviews and reviews[c["change_sha256"]].get("method") == "human"
        and reviews[c["change_sha256"]].get("reviewer") and reviews[c["change_sha256"]].get("reviewed_at")
        and reviews[c["change_sha256"]].get("decision") == "confirmed"
        and reviews[c["change_sha256"]].get("text") == c["selected"] for c in changes)
    total = metrics(rows)
    reviewed = reviewed and bool(changes) and set(reviews) == {c["change_sha256"] for c in changes}
    structure = bool(scores) and all(s["table_structure_unchanged"] for s in scores)
    coverage = (len(samples) >= 20 and len(rows) >= 200 and len(families) >= 4 and "unknown" not in families
                and all(sum(s["kind"] == k for s in samples) >= 10 for k in groups))
    isolated = bool(samples) and all(s.get("split") == "test" and s.get("drawing_family_verified") for s in samples)
    label_freeze = configuration.get("label_freeze", {})
    repeat_checked = label_freeze.get("repeat_review_completed") is True and bool(label_freeze.get("development_manifest_sha256"))
    selection_locked = bool(configuration.get("selection_lock_sha256"))
    locked_models = (configuration.get("selection_lock") or {}).get("actual_model_identities")
    models_match = bool(locked_models) and configuration.get("measured_model_identities") == locked_models
    checks = {"complete": complete, "human_labels": human, "minimum_holdout_coverage": coverage,
              "family_isolation_declared": isolated, "selection_locked": selection_locked,
              "label_freeze_and_repeat_review": repeat_checked,
              "actual_weights_match_development_lock": models_match,
              "all_actual_changes_reviewed": reviewed, "table_structure_unchanged": structure,
              "positive_net_gain": total["net_corrected"] > 0,
              "neither_kind_regressed": all(g["n"] > 0 and g["net_corrected"] >= 0 for g in groups.values()),
              "no_new_sensitive_errors": total["new_sensitive_error_regions"] == 0}
    return {"schema_version": 1, "evaluation_profile": profile, "scope": "selected annotated regions; not whole-page accuracy",
            "groups": groups, "families": family_scores, "overall": total, "complete": complete,
            "uncertainty": bootstrap_pages(scores), "performance": performance or {},
            "routing_metrics": routing_metrics(scores, samples, records),
            "actual_changes": changes, "actual_changes_to_review": len(changes),
            "gate_checks": checks, "human_verified": human,
            "eligible_for_conditional_demo": profile == "holdout" and all(checks.values()),
            "formal_acceptance": False, "review_is_recognition_credit": False,
            "configuration": configuration}


def choose_development_configuration(reports):
    candidates = []
    for name, report in reports.items():
        if report.get("evaluation_profile") != "development":
            raise ValueError("Configuration selection may only consume development reports")
        if report.get("configuration", {}).get("offline_ablation"):
            continue  # Relaxed counterfactual policies cannot become service defaults.
        total = report["overall"]
        if not report.get("complete") or total["new_sensitive_error_regions"] or not report["gate_checks"]["table_structure_unchanged"]:
            continue
        selection = report["configuration"].get("selection", {})
        seconds = report.get("performance", {}).get("p50_seconds")
        candidates.append(((-total["net_corrected"], total["regressed"],
                            float("inf") if seconds is None else seconds, selection.get("max_regions", 16), name), name, report))
    if not candidates:
        return {"mode": "evidence", "selected": None, "reason": "No complete safe development configuration"}
    _, name, report = min(candidates, key=lambda row: row[0])
    return {"mode": "evidence", "selected": name, "selection": report["configuration"].get("selection", {}),
            "runner_config_sha256": fingerprint(report["configuration"].get("runner_config", {})),
            "code_hashes": report["configuration"].get("code_hashes", {}),
            "actual_model_identities": report.get("actual_model_identities", {}),
            "report_sha256": fingerprint(report), "scope": "development choice only; holdout still required"}
