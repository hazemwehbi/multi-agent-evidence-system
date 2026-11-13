import argparse
import asyncio
import json
import sys
from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal
from uuid import UUID, uuid4

from pydantic import AwareDatetime, ValidationError

from app.config import ModelMetadata, Settings
from app.models.contracts import Contract, ExecutionStatus
from app.orchestrator.demo import run_demo
from app.orchestrator.documents import run_documents
from app.services.ingestion import IngestionError
from app.services.model import ModelError, ModelRequest, build_model_client
from app.services.repository import EvidenceRepository, RepositoryError


class SmokeOutput(Contract):
    status: Literal["ready"]


class SmokeReport(Contract):
    execution_id: UUID
    started_at: AwareDatetime
    model: ModelMetadata
    result: SmokeOutput


async def smoke_check(settings: Settings) -> SmokeReport:
    started_at = datetime.now(UTC)
    client = build_model_client(settings, {"smoke": {"status": "ready"}})
    request = ModelRequest(
        operation="smoke",
        instruction='Return the status "ready" using the provided schema.',
        input_text="Run the MAEDS Foundation smoke check.",
    )
    result = await client.generate(request, SmokeOutput)
    return SmokeReport(
        execution_id=uuid4(), started_at=started_at, model=client.metadata, result=result
    )


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="MAEDS")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("smoke", help="Run one validated model request")
    demo = commands.add_parser("demo", help="Run bundled documents in a temporary database")
    demo.add_argument("--empty", action="store_true", help="Exercise the no-evidence route")
    run = commands.add_parser("run", help="Ingest supplied documents and persist a run")
    run.add_argument("--db", type=Path, required=True)
    run.add_argument("--question", required=True)
    run.add_argument("files", type=Path, nargs="+")
    inspect = commands.add_parser("inspect", help="Read a persisted run")
    inspect.add_argument("--db", type=Path, required=True)
    inspect.add_argument("run_id", type=UUID)
    trace = commands.add_parser("trace", help="Trace a claim to its stored passages")
    trace.add_argument("--db", type=Path, required=True)
    trace.add_argument("run_id", type=UUID)
    trace.add_argument("claim_id", type=UUID)
    args = parser.parse_args(argv)
    try:
        if args.command in ("inspect", "trace"):
            if not args.db.is_file():
                raise RepositoryError("Database file does not exist")
            repository = EvidenceRepository(args.db)
            if args.command == "inspect":
                print(repository.inspect(args.run_id).model_dump_json(indent=2))
            else:
                print(json.dumps(repository.trace_claim(args.run_id, args.claim_id), indent=2))
            return 0
        settings = Settings()
    except ValidationError as exc:
        print(f"Invalid MAEDS configuration:\n{exc}", file=sys.stderr)
        return 2
    except RepositoryError as exc:
        print(f"{args.command} failed: {exc}", file=sys.stderr)
        return 1
    try:
        if args.command in ("demo", "run"):
            workflow = (
                asyncio.run(run_demo(settings, empty=args.empty))
                if args.command == "demo" else asyncio.run(run_documents(
                    settings, EvidenceRepository(args.db), args.question, tuple(args.files),
                ))
            )
            print(workflow.model_dump_json(indent=2))
            return int(workflow.run.status == ExecutionStatus.FAILED)
        report = asyncio.run(smoke_check(settings))
    except (ModelError, RepositoryError, IngestionError) as exc:
        print(f"{args.command} failed: {exc}", file=sys.stderr)
        return 1
    print(report.model_dump_json(indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
