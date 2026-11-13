import pytest

from app.services.offline_verification import OPPOSITES, assess_offline


@pytest.mark.parametrize(("first", "second"), [pair for pair in OPPOSITES] + [
    (b, a) for a, b in OPPOSITES
])
def test_matching_context_oppositions_keep_both_evidence_stances(first, second):
    claim = f"Pilot A is {first} as of 2025."
    result = assess_offline(claim, [claim, f"Pilot A is {second} as of 2025."])
    assert result["label"] == "CONFLICTING"
    assert result["supporting_indexes"] == [0]
    assert result["contradicting_indexes"] == [1]


@pytest.mark.parametrize(("claim", "other", "expected"), [
    ("Pilot A is approved.", "Pilot B is rejected.", "SUPPORTED"),
    ("Pilot is active in 2024.", "Pilot is inactive in 2025.", "SUPPORTED"),
    ("Pilot is approved if funded.", "Pilot is rejected if unfunded.", "NOT_VERIFIABLE"),
    ("Pilot is approved if funded.", "Pilot is rejected if funded.", "CONFLICTING"),
    ("Pilot is approved.", "Pilot is rejected as of 2025.", "NOT_VERIFIABLE"),
    ("Pilot is approved.", "Pilot was rejected.", "NOT_VERIFIABLE"),
    ("Pilot A budget is 20 in 2024.", "Pilot A budget is 24 in 2025.", "SUPPORTED"),
    ("Pilot budget is 20.", "Pilot budget is 24.", "CONFLICTING"),
])
def test_context_limits_conflict_and_uncertainty(claim, other, expected):
    assert assess_offline(claim, [claim, other])["label"] == expected


def test_two_opposing_sentences_in_one_passage_require_abstention():
    result = assess_offline("The pilot is approved.", ["The pilot is approved. The pilot is rejected."])
    assert result["label"] == "NOT_VERIFIABLE"
