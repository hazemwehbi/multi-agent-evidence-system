from pathlib import Path
from tempfile import TemporaryDirectory

from app.config import Settings
from app.models.workflow import WorkflowReport
from app.orchestrator.documents import run_documents
from app.services.repository import EvidenceRepository

SAMPLES = Path(__file__).resolve().parents[1] / "sample_documents"


async def run_demo(settings: Settings, *, empty: bool = False) -> WorkflowReport:
    question = "Astronomy" if empty else "Cedar Birch pilot budgets"
    with TemporaryDirectory() as directory:
        return await run_documents(
            settings, EvidenceRepository(Path(directory) / "demo.sqlite"), question,
            (SAMPLES / "cedar.txt", SAMPLES / "birch.md"),
        )
