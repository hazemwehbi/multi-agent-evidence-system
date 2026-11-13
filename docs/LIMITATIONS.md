# MAEDS limitations

## Current scope and proposed tender extensions

The implemented workflow accepts bounded TXT and Markdown inputs and produces claim-level findings and a trace in a single-user localhost application. The documented demonstration uses fictional records. Use of this workflow for tender and RFP review is a proposed application. Real tender processing, commercial deployment, and reductions in review effort remain unvalidated.

Tender-specific requirement extraction, evidence matrices across multiple runs, certificate authenticity or eligibility checks, multi-user review and approvals, and submission integrations are possible extensions. PDF, DOCX, and Excel ingestion are outside the current implementation. A human bid reviewer would remain responsible for determining evidence authority, interpreting tender requirements, and approving the response.

## Verification and operation

The revised offline verifier detects a bounded set of explicit status oppositions. Entity aliases, implicit negation, temporal transitions, and nuanced conditions can escape these checks. The [updated benchmark](../reports/EVALUATION_REMEDIATION.md) uses the same provisional reference dataset, including the case that motivated the correction. Independent human review and a matched single-agent comparison remain pending.

Each run accepts up to 16 UTF-8 TXT or Markdown files of 256 KiB each. Markdown section extraction recognizes ATX headings using text patterns. Lexical retrieval can miss paraphrases, rank incidental matches, and miss counterevidence outside the retrieved set.

Offline verification uses literal clause matching, bounded numeric comparisons, and explicit status opposition rules. It can miss paraphrases, contextual qualifications, unit conversions, and less direct contradictions. An LLM can misread passages, overlook contradictions, or assign the wrong verdict even when its response passes schema checks. Live OpenAI verification and semantic accuracy remain unmeasured.

Completed reports persist across process restarts. Trace details are written at the end of a run. An abrupt process termination can leave a `running` record without a terminal report. The bundled demo uses a temporary database, and the `run` command retains its database. Database files contain the original documents and trace payloads.

Timeouts rely on cooperative asynchronous handlers. Parallel batches wait for their slowest attempt, and a failed required branch blocks its dependents after retries. The web interface is intended for a single user on localhost. It refreshes run status and renders the complete persisted trace at completion. The workflow publishes findings and abstains from making recommendations.
