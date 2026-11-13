from statistics import mean

from app.models.contracts import VerificationLabel


def ratio(numerator, denominator):
    return numerator / denominator if denominator else None


def score(rows):
    labels = list(VerificationLabel)
    matrix = {gold: dict.fromkeys(labels, 0) for gold in labels}
    for row in rows:
        matrix[row["expected"]][row["predicted"]] += 1
    per_class = {}
    for label in labels:
        tp = matrix[label][label]
        actual = sum(matrix[label].values())
        predicted = sum(matrix[gold][label] for gold in labels)
        per_class[label] = {
            "count": actual, "precision": ratio(tp, predicted) or 0.0,
            "recall": ratio(tp, actual) or 0.0, "f1": ratio(2 * tp, actual + predicted) or 0.0,
        }
    annotated = {
        (i, stance, name) for i, row in enumerate(rows)
        for stance in ("support", "oppose") for name in row[f"gold_{stance}"]
    }
    selected = {
        (i, stance, name) for i, row in enumerate(rows)
        for stance in ("support", "oppose") for name in row[stance]
    }
    citations = sum(r["citations"] for r in rows)
    resolved = sum(r["resolved"] for r in rows)
    return {
        "accuracy": ratio(sum(matrix[label][label] for label in labels), len(rows)),
        "macro_f1": mean(row["f1"] for row in per_class.values()),
        "per_class": per_class, "confusion_matrix": matrix,
        "evidence": {
            "citation_validity": ratio(resolved, citations),
            "resolution_success": ratio(sum(r["exact_links"] for r in rows), resolved),
            "coverage": ratio(sum(bool(r["resolved"]) for r in rows), len(rows)),
            "stance_precision": ratio(len(annotated & selected), len(selected)),
            "stance_recall": ratio(len(annotated & selected), len(annotated)),
            "unsupported_candidate_rate": ratio(sum(r["expected"] == "UNSUPPORTED" for r in rows), len(rows)),
            "contradiction_precision": per_class["CONFLICTING"]["precision"],
            "contradiction_recall": per_class["CONFLICTING"]["recall"],
        },
    }


def release_metrics(rows, key):
    safe = sum(not row["expected_release"] for row in rows)
    supported = len(rows) - safe
    unsafe_released = sum(row[key] and not row["expected_release"] for row in rows)
    withheld = sum(not row[key] and row["expected_release"] for row in rows)
    released = sum(row[key] for row in rows)
    return {
        "released": released, "coverage": ratio(released, len(rows)),
        "correct_abstention_rate": ratio(safe - unsafe_released, safe),
        "incorrect_abstention_rate": ratio(withheld, supported),
        "unsafe_releases": unsafe_released,
        "unsupported_releases": sum(row[key] and row["expected"] == "UNSUPPORTED" for row in rows),
        "supported_withheld": withheld,
        "unsafe_release_rate": ratio(unsafe_released, released),
    }
