import asyncio
import json

from app.models.contracts import VerificationLabel
from evaluation.metrics import release_metrics, score
from evaluation.run import DATASET, evaluate
from app.config import Settings
from app.services.repository import EvidenceRepository


def test_dataset_covers_all_labels_and_uses_valid_evidence_annotations():
    dataset = json.loads(DATASET.read_bytes())
    cases = dataset["cases"]
    assert len({case["id"] for case in cases}) == len(cases)
    assert {case["label"] for case in cases} == set(VerificationLabel)
    for case in cases:
        assert set(case["support"] + case["oppose"]) <= case["documents"].keys()


def test_evaluation_scores_error_and_abstention_separately(tmp_path):
    cases = {c["id"]: c for c in json.loads(DATASET.read_bytes())["cases"]}
    repository = EvidenceRepository(tmp_path / "eval.sqlite")

    async def run():
        return [await evaluate(cases[key], repository, Settings()) for key in
                ("direct", "factual-conflict", "missing")]

    rows = asyncio.run(run())
    assert score(rows)["confusion_matrix"]["CONFLICTING"]["CONFLICTING"] == 1
    assert rows[1]["support"] == ["a.txt"] and rows[1]["oppose"] == ["b.md"]
    assert release_metrics(rows, "released")["unsafe_releases"] == 0
    assert release_metrics(rows, "released")["unsupported_releases"] == 0
    assert release_metrics(rows, "released")["correct_abstention_rate"] == 1
    assert release_metrics(rows, "ungated")["unsafe_releases"] == 2
