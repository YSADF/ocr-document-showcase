"""Selected scoring functions; no OCR model or private service dependencies.

aggregate distinguishes raw transcription from reviewed results. Missing matches
are scored as empty predictions by the upstream evaluator; aggregate does not
reconstruct geometry, validate labels or decide a page-level release gate.
"""

CRITICAL = set("Ø⌀∅Φφ±°×÷≤≥μµ²³′″−+-.")


def normalize(text):
    return " ".join(str(text or "").split())


def edit_counts(reference, prediction):
    """Return edit distance and errors at critical reference characters."""
    rows = [[(0, 0)] * (len(prediction)+1) for _ in range(len(reference)+1)]
    for i, char in enumerate(reference, 1):
        rows[i][0] = (i, rows[i-1][0][1] + int(char in CRITICAL))
    for j in range(1, len(prediction)+1):
        rows[0][j] = (j, 0)
    for i, char in enumerate(reference, 1):
        for j, other in enumerate(prediction, 1):
            prev = rows[i-1][j-1]
            substitution = (prev[0] + (char != other), prev[1] + int(char != other and char in CRITICAL))
            prev = rows[i-1][j]
            deletion = (prev[0]+1, prev[1]+int(char in CRITICAL))
            prev = rows[i][j-1]
            insertion = (prev[0]+1, prev[1])
            # Stable diagonal/deletion/insertion tie order; never choose an
            # alignment by whether it inflates the critical-character score.
            rows[i][j] = min((substitution, deletion, insertion), key=lambda p: p[0])
    return rows[-1][-1]


def aggregate(rows):
    total = len(rows)
    characters = sum(r["reference_characters"] for r in rows)
    critical = sum(r["critical_characters"] for r in rows)
    return {"regions": total, "cer": sum(r["edits"] for r in rows)/characters if characters else None,
            "annotation_accuracy": sum(r["exact"] and not r["needs_review"] for r in rows)/total if total else None,
            "critical_character_accuracy": max(0., 1-sum(
                max(r["critical_errors"], r["critical_characters"]) if r["needs_review"] else r["critical_errors"]
                for r in rows)/critical) if critical else None,
            "raw_annotation_accuracy": sum(r["exact"] for r in rows)/total if total else None,
            "raw_critical_character_accuracy": max(0., 1-sum(r["critical_errors"] for r in rows)/critical) if critical else None,
            "miss_rate": sum(not r["found"] for r in rows)/total if total else None,
            "review_rate": sum(r["needs_review"] for r in rows)/total if total else None,
            "reference_characters": characters, "critical_characters": critical}
