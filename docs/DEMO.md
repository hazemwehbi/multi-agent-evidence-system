# Reproduce the Northgate Library demonstration

Northgate Library is a fictional scenario. The finance record gives the equipment pilot budget and says the pilot was approved. The committee minutes say it was rejected on the same date. The scenario supplies no rule giving one source precedence.

This illustrates an evidence review a bid team might perform before drafting a tender response. The budget shows how a supported statement can be traced to its exact source. The conflicting approval records show where a reviewer would need to reconcile sources before using a status claim. The walkthrough uses the generic document workflow and fictional records. [Proposed tender application](TECHNICAL_REPORT.md#proposed-business-use-case)

## Browser walkthrough

From the repository root, run the [setup commands](../README.md), then start the localhost server.

```powershell
$env:MAEDS_PROVIDER = 'offline'
$env:MAEDS_DB = 'northgate.sqlite'
uv run --locked uvicorn app.web:create_app --factory --host 127.0.0.1 --port 8000
```

1. Open [MAEDS](http://127.0.0.1:8000). Ask **What are the Northgate Library equipment pilot budget and approval status?** Choose [finance-record.txt](demo/finance-record.txt) and [governance-minutes.md](demo/governance-minutes.md), then select **Start run**.
2. The run page publishes the EUR 24,000 budget as a verified finding under the offline rules. The approval and rejection candidates both appear under **Qualified and unresolved claims** with `CONFLICTING` verdicts. The workflow abstains from a recommendation.
3. Open a supporting link for the budget. The source view shows its filename, offsets, exact passage, and highlighted location in the original text. Open the opposing links for either status candidate to compare the finance and governance records.
4. Expand **Decision record** to see each claim's verdict, citations, eligibility, and exclusion reason. Expand **Execution trace** to see the Coordinator's plan, separate retrieval tasks, candidate excerpts from Analysis, Verification results, and Synthesis output.
5. Save the run URL. Stop and restart Uvicorn with the same database path, then reopen the run URL to inspect the persisted result.

## CLI walkthrough

```powershell
$env:MAEDS_PROVIDER = 'offline'
$report = uv run --locked maeds run --db northgate.sqlite --question "What are the Northgate Library equipment pilot budget and approval status?" docs/demo/finance-record.txt docs/demo/governance-minutes.md | ConvertFrom-Json
$runId = $report.run.run_id
$budgetId = $report.result.synthesis.finding_claim_ids[0]
$conflictId = $report.result.synthesis.unresolved_claim_ids[0]
uv run --locked maeds inspect --db northgate.sqlite $runId
uv run --locked maeds trace --db northgate.sqlite $runId $budgetId
uv run --locked maeds trace --db northgate.sqlite $runId $conflictId
```

The mixed result has status `partial`. The decision's verification record shows both sides of each conflict. The CLI claim trace follows the original analysis citation. Run IDs, message IDs, and timestamps vary per execution.

## Captured interface

- [Question and document upload](demo/upload-form.png)
- [Mixed findings and conflict disclosures](demo/run-result.png)
- [Highlighted passage in the original source](demo/source-passage.png)
