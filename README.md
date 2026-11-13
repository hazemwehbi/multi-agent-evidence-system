# Multi-Agent Evidence and Decision System

MAEDS runs five agents over UTF-8 TXT and Markdown files, verifies candidate claims against stored passages, and saves the decision and run trace in SQLite.

## Install and run

Install Python 3.11 or newer and [uv](https://docs.astral.sh/uv/), then run from the project root. The final verification used CPython 3.13.1 on Windows. On a clean checkout, uv creates the project virtual environment from the lockfile. A first install may need network access for packages.

```powershell
uv lock --check
uv sync --locked
$env:MAEDS_PROVIDER = 'offline'
uv run --locked maeds smoke
uv run --locked maeds demo
uv run --locked maeds demo --empty
uv run --locked pytest
```

Offline is the default and requires no API credentials. The smoke check prints JSON with an execution ID, start time, provider, model identifier, configured timeout and output-token limit, and a validated `ready` result.

The demo uses the bundled Cedar and Birch files with a temporary database. To keep a run and inspect it later, use a database path in an existing writable directory.

```powershell
$report = uv run --locked maeds run --db evidence.sqlite --question "What are the Cedar and Birch pilot budgets?" app/sample_documents/cedar.txt app/sample_documents/birch.md | ConvertFrom-Json
$runId = $report.run.run_id
$claim = ($report.messages | Where-Object { $_.content.PSObject.Properties.Name -contains 'claims' }).content.claims[1]
uv run --locked maeds inspect --db evidence.sqlite $runId
uv run --locked maeds trace --db evidence.sqlite $runId $claim.claim_id
```

The offline budget run publishes two verified findings under the deterministic test rules. The empty demo skips analysis and ends with a no-candidate decision. Both routes exit zero. A failed run exits one.

## Local interface

Use the [Northgate Library walkthrough](docs/DEMO.md) to demonstrate a supported budget and a conflicting approval status in the same run.

```powershell
uv run --locked uvicorn app.web:create_app --factory --host 127.0.0.1 --port 8000
```

Open [MAEDS locally](http://127.0.0.1:8000), enter a question, and select TXT or Markdown files. The run page refreshes while work is in progress. It then shows verified findings, excluded claims with verdicts, evidence links, the decision record, and the execution trace. Evidence pages display the exact passage and highlight it within the original source. JSON status and reports are available at `/api/runs/{run_id}`. Set `MAEDS_DB` to use a database path other than `evidence.sqlite`.

## Optional OpenAI mode

Install the provider extra with `uv sync --locked --extra openai`. Copy `.env.example` to `.env` or configure equivalent environment variables. Set `MAEDS_PROVIDER=openai`, choose a structured-output-capable model via `MAEDS_MODEL`, and supply `OPENAI_API_KEY` through your local environment or ignored `.env`. Then run `uv run --locked --extra openai maeds smoke`. The live command calls the configured model and may incur API charges. The smoke input is a fixed synthetic prompt.

To include the mocked adapter test in the credential-free test suite, run `uv run --locked --extra openai pytest`.

In OpenAI mode, analysis and verification send task-relevant text to the provider. Offline mode keeps that data local. Adapter contract tests use a mock. Live API behavior, accuracy, and cost have yet to be measured.

## Design and status

Run the offline benchmark from the repository root with a separate output path:

```powershell
uv run --locked python -m evaluation.run --repeats 3 --output reports/reproduction-offline.json
```

The [original evaluation](reports/EVALUATION.md) and [remediation comparison](reports/EVALUATION_REMEDIATION.md) preserve the published runs.

- [Architecture](docs/ARCHITECTURE.md)
- [Design decisions](docs/DESIGN_DECISIONS.md)
- [Testing](docs/TESTING.md)
- [Limitations](docs/LIMITATIONS.md)
- [Technical report and repository map](docs/TECHNICAL_REPORT.md)
