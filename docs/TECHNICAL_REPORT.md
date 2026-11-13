# MAEDS technical report

## Abstract

The Multi-Agent Evidence and Decision System is an independent engineering project implemented as a local Python demonstrator for answering questions over a bounded document collection. It combines explicit task dependencies, passage-level provenance, separate citation and semantic checks, and an auditable release decision. Its purpose is to make it possible to inspect why the application published or withheld a claim and to locate the evidence it used.

## Problem and objectives

A citation can point to a real passage while providing weak or contradictory support. In a multi-stage workflow, the final reader also needs to know which component selected the passage, how the claim was evaluated, and why it was eligible for release. MAEDS makes these distinctions visible using typed records, a bounded workflow, and persistent source-relative references.

## Proposed business use case

IT and consulting companies responding to public or commercial tenders often need to answer many requirements using records scattered across project summaries, capability statements, and certification registers. A bid team may need to establish whether a technology was used on a qualifying project, whether a documented certificate covers the required scope and dates, or whether two records describe the same capability inconsistently. Each proposed answer needs a source a reviewer can inspect, and gaps need to remain visible before submission.

| Agent | Implemented responsibility | Potential tender responsibility |
|---|---|---|
| Coordinator | Plans one retrieval task per supplied source and schedules dependent stages. | Organize requirements into review questions and assign analysis tasks. Today a reviewer supplies each question. |
| Research / Retrieval | Retrieves relevant passages within the run's source scope. | Find evidence in project references, capability statements, and certificate records supplied as text. |
| Analysis | Selects retrieved excerpts as candidate claims. | Identify material that could substantiate a proposed answer to a requirement. |
| Verification | Resolves citations and assesses support and contradictions within the retrieved evidence. | Flag conflicting versions, incomplete support, and statements that lack evidence. |
| Synthesis / Decision | Releases eligible findings and records unresolved claims and exclusion reasons. | Present an evidence-backed assessment for bid review and flag questions that still need a decision. |

IT service providers and software development companies could use this approach to review technical capability and delivery claims. Consulting firms and SMEs bidding for public or private work could use it to locate relevant project references and identify gaps before writing responses. Teams preparing compliance and technical documentation could use the same evidence trail to reconcile inconsistent records and show reviewers where each statement came from.

MAEDS centers the workflow on checking individual claims, tracing citations, disclosing detected contradictions, and controlling which findings are released. This design could reduce manual evidence search and make unsupported AI-assisted statements easier to catch. Human reviewers still need to confirm that evidence is current, authoritative, and applicable to the requirement, resolve discrepancies, and approve the submission. Review effort and business outcomes remain unmeasured. The documented demonstration uses fictional records. Real tender processing, commercial deployment, and tender-specific automation remain outside the demonstrated scope.

## System design

The [system, agent, and database diagrams](ARCHITECTURE.md) describe the FastAPI and CLI entry points, custom asynchronous Python runner, Pydantic contracts, and SQLite repository. The Coordinator creates one retrieval task per source. Retrieval tasks can run concurrently. Analysis selects excerpts as candidate claims. Verification compares claims against the run's retrieved evidence. Synthesis classifies claims as eligible or unresolved. The runner checks the decision against the verification inputs before persistence. Analysis and semantic verification share a model client, with a deterministic backend and an optional LangChain OpenAI adapter.

UTF-8 TXT and Markdown files are stored as immutable source versions. A passage identifies a character slice and, when available, a Markdown section. Claim IDs link to analysis messages and retrieval results. Run scope and provenance links are enforced through SQLite relationships, and exact text is checked against the stored source. Completed reports can be inspected after process restart.

## Verification, release, and decision transparency

Mechanical validation checks source and passage resolution within the run and equality to the exact stored text. Semantic verification separately records SUPPORTED, PARTIALLY_SUPPORTED, UNSUPPORTED, CONFLICTING, or NOT_VERIFIABLE, along with evidence stances, method, and explanation. A released finding needs at least one citation, all citations must pass the mechanical check, the semantic verdict must be SUPPORTED, a cited passage must be listed as supporting, and the assessment must identify zero contradicting passages. Other candidates appear as qualified or unresolved. The current implementation abstains from ranking alternatives and can publish eligible findings while withholding a recommendation.

The decision record exposes checked claim IDs, evidence references, verdicts, and exclusion reasons. These are observable workflow inputs and outputs. The record supports inspection of an application decision. Hidden model reasoning and formal verification are outside the implemented scope.

## Evaluation and demonstrated capabilities

The controlled benchmark used 11 synthetic claims with provisional reference judgments assigned before scoring. It measured verdict accuracy, macro-F1, evidence stance and resolution, and abstention. The original offline verifier achieved **72.7% accuracy and 0.733 macro-F1**. The updated verifier achieved **81.8% and 0.827** on the same cases. It withheld the previously released approval claim after detecting the rejected status in the same context. Conflict recall rose from 1/2 to 2/2. One supported paraphrase was still withheld and one partially supported paraphrase was still classified unsupported. The correction was informed by the original failure, so these updated results describe an in-sample check.

Regression and integration tests exercise bounded scheduling, failure and timeout paths, exact passage references, provenance across process restarts, release checks, and the web flow. The [Northgate demo](DEMO.md) shows a supported budget and two unresolved approval-status claims in a single persisted run. The [original benchmark](../reports/EVALUATION.md) and [remediation report](../reports/EVALUATION_REMEDIATION.md) preserve both sets of results, including citation-only and ungated release comparisons.

## Unvalidated capabilities and threats to validity

Independent human annotation remains pending. The sample is small, synthetic, and uses a controlled evidence set for semantic scoring. The repository has no matched single-agent architecture comparison. Live LLM semantic accuracy, stochastic repeatability, token use, and API costs remain unmeasured. Lexical retrieval can omit counterevidence, and rule-based conflict checks can miss aliases, implicit negation, and contextual changes. A valid trace establishes that the application recorded the stated operations. The accuracy of semantic assessments depends on the evidence and verifier.

## From Practical Engineering Challenges to Research Questions

A bid reviewer needs to reconstruct why a claim was released or withheld, especially when multiple agents selected and assessed its evidence. MAEDS records those steps, which makes it possible to study where provenance can be lost and whether a recorded justification reflects the evidence that actually influenced the decision. These challenges motivate further work in explainable AI (XAI), provenance, verification, explanation faithfulness, and reliable multi-agent systems.

- How much does multi-agent decomposition improve evidence recall or decision quality when model, context, and call budgets are matched against a single-agent baseline?
- How can systems distinguish genuine claim support from a citation that merely resolves, and detect conflicts between agents or sources when scope, dates, or entities differ?
- How should systems justify and calibrate abstention when evidence is incomplete, contradictory, or retrieved selectively?
- Which human annotation and adjudication protocols produce reliable claim and passage labels across domains?
- How can we preserve provenance across agent handoffs and test whether explanations faithfully represent observable decisions in high-stakes applications?

## Repository map

```text
app/
  agents/                 Five agent implementations
  models/                 Pydantic contracts and workflow records
  orchestrator/           Bounded runner and application entry points
  services/               Ingestion, SQLite, and model adapters
  sample_documents/       Small offline CLI fixtures
  cli.py, web.py          CLI and localhost FastAPI interface
docs/
  demo/                   Northgate input files and screenshots
  ARCHITECTURE.md         System, agent, and database diagrams
  DEMO.md                 Browser and CLI walkthrough
  TECHNICAL_REPORT.md     This report
  DESIGN_DECISIONS.md, LIMITATIONS.md, TESTING.md
evaluation/               Benchmark runner, dataset, and annotation sheet
reports/                  Original and remediation reports and JSON results
tests/                    Unit and integration suites
README.md, pyproject.toml, uv.lock
```
