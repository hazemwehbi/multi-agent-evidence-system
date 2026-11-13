import re

from app.models.contracts import VerificationLabel

NUMBER = re.compile(r"\b\d[\d,.]*\b")
OPPOSITES = (
    ("approved", "rejected"), ("active", "inactive"), ("valid", "invalid"),
    ("accepted", "denied"), ("completed", "pending"), ("allowed", "prohibited"),
)
OPPOSITE = {word: other for pair in OPPOSITES for word, other in (pair, pair[::-1])}
STATUS = re.compile(
    rf"(?P<subject>.+?) (?P<verb>is|are|was|were) "
    rf"(?P<status>{'|'.join(OPPOSITE)})(?P<scope>(?: .*)?)$"
)
SCOPE_MARKER = re.compile(r"\b(?:if|unless|when|while|provided|subject to|as of|before|after|during|until)\b")
NUMERIC_VALUE = re.compile(r"\b(?:budget|cost|price|capacity|limit|total|count) (?:is|was|equals) (?:[a-z]{3} )?#")
DATE_CONTEXT = re.compile(r" (on|in|as of) (\d{4}(?:-\d{2}-\d{2})?)")


def _normalize(text: str) -> str:
    return " ".join(text.casefold().split()).strip(" .!?")


def _opposition(clause: str, sentence: str) -> tuple[bool, bool]:
    """Return definite opposition and possible opposition with missing scope."""
    left, right = STATUS.fullmatch(clause), STATUS.fullmatch(sentence)
    if left and right and OPPOSITE[left["status"]] == right["status"]:
        if left["subject"] != right["subject"]:
            return False, False
        if left["verb"] == right["verb"] and left["scope"] == right["scope"]:
            return True, False
        if not left["scope"] or not right["scope"] or left["scope"] == right["scope"]:
            return False, True
        left_date, right_date = map(DATE_CONTEXT.fullmatch, (left["scope"], right["scope"]))
        comparable_dates = (
            left_date and right_date and left_date[1] == right_date[1]
            and len(left_date[2]) == len(right_date[2]) and left_date[2] != right_date[2]
        )
        return False, not bool(comparable_dates)
    first, second = NUMBER.findall(clause), NUMBER.findall(sentence)
    # Replacing every number used to conflate a changed value with a changed year.
    same_numeric_frame = (
        bool(first) and NUMBER.sub("#", clause) == NUMBER.sub("#", sentence)
        and len(first) == len(second)
    )
    if not same_numeric_frame:
        return False, False
    # Only compare a single unambiguous value in an unqualified numeric statement.
    if (len(first) == 1 and first != second
        and NUMERIC_VALUE.search(NUMBER.sub("#", clause)) and not SCOPE_MARKER.search(clause)):
        return True, False
    if first != second and first[0] != second[0] and first[1:] == second[1:]:
        return False, True
    return False, False


def assess_offline(claim: str, passages: list[str]) -> dict:
    """Match literal clauses and compare opposite predicates with their context."""
    parts = [claim] if SCOPE_MARKER.search(claim.casefold()) else re.split(r"\s+and\s+|;", claim, flags=re.I)
    clauses = tuple(filter(None, map(_normalize, parts)))
    matched: set[int] = set()
    supporting: set[int] = set()
    opposing: set[int] = set()
    uncertain = False
    for index, passage in enumerate(passages):
        sentences = tuple(map(_normalize, re.split(r"[!?\n]|\.(?=\s|$)", passage)))
        for number, clause in enumerate(clauses):
            if clause in sentences:
                matched.add(number)
                supporting.add(index)
            for sentence in sentences:
                conflict, ambiguous = _opposition(clause, sentence)
                if conflict:
                    opposing.add(index)
                uncertain |= ambiguous
    if supporting and opposing and not supporting & opposing:
        label, explanation = VerificationLabel.CONFLICTING, "Retrieved passages give competing assertions in the same context."
    elif uncertain or supporting & opposing:
        label, explanation = VerificationLabel.NOT_VERIFIABLE, "Potentially opposing statements could not be resolved by the offline rules."
    elif supporting and len(matched) == len(clauses):
        label, explanation = VerificationLabel.SUPPORTED, "Every claim clause matches a retrieved sentence."
    elif supporting:
        label, explanation = VerificationLabel.PARTIALLY_SUPPORTED, "Only some claim clauses match retrieved sentences."
    else:
        label, explanation = VerificationLabel.UNSUPPORTED, "No claim clause matched a retrieved sentence under the offline rules."
    cites_support = label in {
        VerificationLabel.SUPPORTED, VerificationLabel.PARTIALLY_SUPPORTED, VerificationLabel.CONFLICTING,
    }
    return {
        "label": label, "explanation": explanation,
        "supporting_indexes": sorted(supporting) if cites_support else [],
        "contradicting_indexes": sorted(opposing) if label in {
            VerificationLabel.CONFLICTING, VerificationLabel.UNSUPPORTED,
        } else [],
    }
