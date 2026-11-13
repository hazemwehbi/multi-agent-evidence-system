# Design decisions

## Offline conflict remediation

The offline verifier compares approved/rejected, active/inactive, valid/invalid, accepted/denied, completed/pending, and allowed/prohibited in matching subject, tense, and qualifier contexts. Comparable distinct explicit dates can coexist. Recognized opposition with ambiguous scope is withheld as NOT_VERIFIABLE, as are competing assertions within the same indexed passage. The release policy and provider interface are unchanged. See the [remediation report](../reports/EVALUATION_REMEDIATION.md).

## Model boundary

Use an asynchronous backend protocol and a common validating client. Operation-keyed fixtures support deterministic tests and allow future agents to share the same request and response contracts across modes. OpenAI is the first real adapter and lives in a single optional module. Environment settings select the model and bound calls. Each smoke execution reports effective provider, model, timeout, and token limit. The OpenAI adapter disables implicit retries so the future runner can own retry policy.

## Evidence and verification

An evidence reference carries both a source ID and a passage ID. Passage locations are zero-based, end-exclusive character offsets into the stored source text. Schema validation checks span length while preserving whitespace. The future evidence store must also compare the exact source slice, resolve the IDs within the run, and assign stable IDs when ingesting documents.

Verification records contain separate mechanical citation and semantic assessment fields. Synthesis returns a decision ID and claim IDs. The later workflow must resolve those IDs against the current run and check verdicts before rendering factual findings from the stored claims.

## Workflow and deployment

Use a custom bounded Python runner for the MVP, with explicit inputs and outputs at agent boundaries. Use local SQLite for persisted workflow state and trace data in later milestones. Keep the smoke CLI and provider configuration independent of the future FastAPI interface.

## Milestone 2 contracts and execution policy

`WorkflowTask` extends the existing task with a source assignment for retrieval. `Plan` and `TaskInput` carry the task graph and validated upstream messages. Stage result wrappers carry existing passages, claims, verification records, and synthesis references. `WorkflowDecision` constrains the decision to a fixed action and two outcome codes. `TaskStatus` and `WorkflowReport` expose the in-memory trace using the existing generic message envelope.

The coordinator uses a fixed decomposition policy. Plan validation enforces a retrieval layer, an analysis join, verification with access to the original retrieval outputs, and a final synthesis task. Exact dependency sets rule out cycles and missing dependencies before dispatch. Each invocation, including coordinator attempts and retries, consumes one step. Defaults are 32 steps, one retry per invocation, four concurrent specialists, and 20 seconds per attempt. An exhausted required dependency blocks downstream work. An empty retrieval skips analysis and runs verification and synthesis with empty candidates.

Analysis is the only model-backed stage in this milestone. The model returns indexes and the agent constructs candidates from exact fixture excerpts. Verification checks reference membership in retrieved messages and marks semantic assessment as deferred. Synthesis can report unresolved IDs from its input. The runner rejects factual finding IDs and validates the decision's provenance and outcome before publishing it.

## Milestone 3 ingestion and storage

The format dispatcher accepts UTF-8 TXT and Markdown. The source ID is SHA-256 of the filename, a NUL separator, and the original bytes. Reingesting the same name and bytes reuses the source. A rename or edit creates a new source ID. Passage IDs are zero-based, end-exclusive character spans within that source. Ingestion preserves line endings and Unicode and attaches the latest ATX heading to Markdown spans. Larger blocks are split into bounded spans.

Retrieval ranks passages by shared terms after removing common English stop words. It takes up to two per source, with ties broken by source offset. Offline analysis selects a bounded prefix of those candidates. The retrieval agent accepts an injected search implementation. The file-backed CLI always uses the repository implementation, while isolated runner tests can still use fixtures.

Existing agent and message schemas were preserved. The parser adds an internal `ParsedDocument` contract. The runner adds a start callback so the document workflow can persist the run before retrieval without importing storage into the runner. SQLite foreign keys enforce run scope and evidence links. The repository also checks exact passage slices and checks that claim citations appear in the analysis task's retrieved inputs. A failed final write rolls back the trace and marks the previously committed run failed when the database remains writable.

## Milestone 4 release policy

A verified factual finding requires at least one citation, resolution of every cited reference against a matching retrieved passage in the run, a `SUPPORTED` verdict, at least one cited passage among the semantic supporting references, and zero contradicting references. The policy is fixed. The runner verifies the verdict batch against the analysis and retrieval inputs and recomputes the expected synthesis record before release.

All other claims are excluded from verified findings. `PARTIALLY_SUPPORTED` appears with its qualification and supporting references. `CONFLICTING` appears with both sides. `UNSUPPORTED` and `NOT_VERIFIABLE` appear as unresolved candidates with reasons. Missing citations and invalid model outputs fail closed. The decision records every considered verdict, the release or exclusion reason, the evidence references, and recommendation abstention. The UI renders the original checked claim by ID. The workflow abstains from ranking alternatives and publishes eligible findings when available.

Verification adds optional model metadata and a method field. Decision records add per-claim dispositions and abstention. Defaults retain compatibility with earlier stored report JSON. The deterministic backend uses literal clause matches and same-template numeric conflicts. The OpenAI adapter uses the same structured output contract, with index and verdict consistency checks after inference.
