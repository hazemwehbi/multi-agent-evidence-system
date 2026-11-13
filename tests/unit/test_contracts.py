from datetime import UTC, datetime
from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.models.contracts import (
    AgentMessage,
    EvidenceRef,
    Passage,
    SynthesisResult,
    Task,
)


def test_message_requires_typed_payload_and_aware_timestamp():
    fields = {
        "message_id": uuid4(),
        "run_id": uuid4(),
        "task_id": uuid4(),
        "sender_agent": "coordinator",
        "recipient_agent": "retrieval",
        "message_type": "task",
        "content": {"task_id": uuid4(), "agent": "retrieval", "objective": "Find costs"},
        "timestamp": datetime.now(UTC),
        "execution_status": "pending",
    }
    message = AgentMessage[Task].model_validate(fields)
    assert message.content.objective == "Find costs"
    assert AgentMessage[Task].model_validate_json(message.model_dump_json()) == message
    with pytest.raises(ValidationError, match="objective"):
        AgentMessage[Task].model_validate({**fields, "content": {**fields["content"], "objective": " "}})
    with pytest.raises(ValidationError, match="timestamp"):
        AgentMessage[Task].model_validate({**fields, "timestamp": datetime(2026, 1, 1)})


def test_passage_preserves_exact_text_and_checks_character_span():
    reference = EvidenceRef(source_id="source", passage_id="passage")
    assert Passage(ref=reference, text=" café ", start=3, end=9).text == " café "
    with pytest.raises(ValidationError, match="character span"):
        Passage(ref=reference, text=" café ", start=3, end=8)


def test_synthesis_contract_rejects_freeform_factual_output():
    with pytest.raises(ValidationError, match="extra_forbidden"):
        SynthesisResult.model_validate({"decision_id": uuid4(), "findings": ["New fact"]})
