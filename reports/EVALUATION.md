# MAEDS evaluation v1.0.0

The sections below preserve the original benchmark. See the [remediation results](EVALUATION_REMEDIATION.md) for the rerun on the identical dataset.

## Dataset and reference judgments

The benchmark contains 11 synthetic English cases. Each stores a question, TXT or Markdown contents, a candidate claim, supplied citations, a reference verdict, annotated supporting and contradicting passages, and a rationale. Each document in this version represents one passage, so the dataset uses filenames as evidence selectors and resolves them to stored source and passage IDs at execution. The JSON report includes the dataset SHA-256 digest.

Codex assigned reference judgments by reading the case text before running the verifier. No MAEDS output supplied a reference label. Independent human annotation or review has **not** been completed. These are provisional reference judgments. The production rules and prompts remained unchanged during evaluation. Earlier integration fixtures are development checks, and this version is a separate benchmark. The shared subject matter and authorship limit its independence.

| Reference verdict | Annotation rule |
|---|---|
| SUPPORTED | Available evidence entails all material parts, including equivalent paraphrases. |
| PARTIALLY_SUPPORTED | Available evidence entails some material clauses and leaves others open. |
| UNSUPPORTED | Available cited evidence supplies no support, including when the only relevant passage directly refutes the claim. |
| CONFLICTING | Comparable evidence both supports and contradicts the claim, with no supplied basis for preferring one source. |
| NOT_VERIFIABLE | There is no usable cited evidence, including an absent or invalid reference. |

For future independent review, give reviewers the questions, claims, documents, and citation selectors before showing predictions. Ask reviewers to record a verdict, stance for each relevant passage, and a brief rationale. Preserve disagreements and adjudicate them before issuing a new benchmark version.

## Experimental design

The controlled verifier benchmark supplies the fixed candidate and all stored case passages to the production Verification and Synthesis agents. This isolates verification from retrieval and candidate generation. The end-to-end arm runs the actual workflow on the same questions and documents, then compares run completion, retrieval, produced claims, verdicts, and release decisions under perturbations. It does not score the generated claims against the fixed candidates. Candidate extraction and retrieval change what can be assessed.

The two release ablations reuse the exact cases and citations. **Citation-only** releases whenever all citations resolve and at least one exists. **Ungated** releases every candidate. Both are counterfactual scoring rules, with no additional model calls and no changes to production release logic. This measures the contribution of verification and gating on fixed candidates. A same-model single-agent architecture comparison was outside this run. The results cannot attribute gains to collaboration or estimate a latency benefit from an ablation.

Executed with Windows 10, CPython 3.13.1, SQLite 3.45.3, locked dependencies, and the `deterministic-v1` backend. The verifier timeout was 1 second and the configured output limit was 512 tokens. The run made zero provider requests. Token counts and estimated API cost are recorded as null because the deterministic backend does not meter usage. No live LLM provider results were collected.

## Metrics and results

Accuracy is correct verdicts divided by cases. Per-class precision is TP / predicted positives, recall is TP / reference positives, and F1 is 2 × TP / (predicted positives + reference positives). Macro-F1 is the unweighted mean across all five labels. Undefined classification scores count as zero. Other ratios with an empty denominator are null.

**Accuracy was 8/11 (72.7%). Macro-F1 was 0.733.**

| Verdict | Cases | Precision | Recall | F1 |
|---|---:|---:|---:|---:|
| SUPPORTED | 3 | .667 | .667 | .667 |
| PARTIALLY_SUPPORTED | 2 | 1.000 | .500 | .667 |
| UNSUPPORTED | 2 | .500 | 1.000 | .667 |
| CONFLICTING | 2 | 1.000 | .500 | .667 |
| NOT_VERIFIABLE | 2 | 1.000 | 1.000 | 1.000 |

Confusion matrix with reference labels on rows and predictions on columns.

| Reference | SUPPORTED | PARTIAL | UNSUPPORTED | CONFLICTING | NOT_VERIFIABLE |
|---|---:|---:|---:|---:|---:|
| SUPPORTED | 2 | 0 | 1 | 0 | 0 |
| PARTIALLY_SUPPORTED | 0 | 1 | 1 | 0 | 0 |
| UNSUPPORTED | 0 | 0 | 2 | 0 | 0 |
| CONFLICTING | 1 | 0 | 0 | 1 | 0 |
| NOT_VERIFIABLE | 0 | 0 | 0 | 0 | 2 |

| Evidence measure | Definition | Result |
|---|---|---:|
| Mechanical citation validity | Mechanically resolved supplied refs / supplied refs | 10/11 |
| Reference resolution success | Resolved refs independently reread from the store with matching passage / resolved refs | 10/10 |
| Evidence coverage | Cases with at least one resolved ref / candidates | 9/11 |
| Semantic stance precision | Matched case, passage, and stance assignments / predicted assignments | 8/8 |
| Semantic stance recall | Matched assignments / annotated assignments | 8/11 |
| Unsupported candidate rate | Reference UNSUPPORTED / candidates | 2/11 |
| Contradiction detection | Precision and recall for CONFLICTING | 1/1 precision, 1/2 recall |

Claim-level abstention means withholding a candidate from verified findings. The reference policy permits only fully supported claims with valid supplied evidence. Recommendation abstention is a separate application behavior and is not scored here. Coverage is releases / candidates. Correct abstention is withheld reference-ineligible / reference-ineligible. Incorrect abstention is withheld reference-eligible / reference-eligible. Unsafe releases include all ineligible verdicts. The unsupported release count uses the specific reference label UNSUPPORTED.

| Policy | Coverage | Correct abstention | Incorrect abstention | Unsafe releases | UNSUPPORTED releases | Supported withheld |
|---|---:|---:|---:|---:|---:|---:|
| MAEDS | 3/11 | 7/8 | 1/3 | 1 | 0 | 1 |
| Citation-only | 9/11 | 2/8 | 0/3 | 6 | 2 | 0 |
| Ungated | 11/11 | 0/8 | 0/3 | 8 | 2 | 0 |

## Representative cases

- **Multi-passage success.** The budget and May opening clauses were both supported using separate passages.
- **Conflict detected.** The numeric conflict paired a budget of 20 with 24 and returned both stances.
- **Unsafe release.** “The pilot is approved” was released despite a separate passage saying it was rejected. The offline rules do not detect that factual contradiction. One of the three released claims was ineligible by reference.
- **Supported claim withheld.** “Runs for six weeks” and “lasts six weeks” are equivalent here, but the offline literal matcher returned UNSUPPORTED. A second paraphrase also caused a PARTIALLY_SUPPORTED case to be classified as UNSUPPORTED.
- **Mechanically valid but semantically unsupported.** A passage about library count resolved correctly and supplied no evidence for a May opening.

## Robustness and repeatability

The controlled arm had zero verdict, evidence-selection, or release changes across 22 repeat comparisons and 11 reversed-order comparisons. Mean elapsed time per candidate across the four passes was 9.2–13.7 ms, including SQLite setup for each case. The injected failure, timeout, and malformed response each produced NOT_VERIFIABLE and withheld the candidate. Their observed latencies were 14.2 ms, 1019.2 ms, and 22.8 ms respectively. The fault runs target the semantic backend within the agent and are excluded from primary accuracy. Full runner retries and dependency-failure propagation are covered by the workflow integration tests.

All 44 end-to-end runs produced a terminal report that reopened identically from SQLite. Each of the repeat, reversed-order, and added-distractor arms matched the primary arm on all 11 case signatures. Signatures cover terminal status, retrieved filenames, claim text, verdicts, and release flags, excluding UUIDs and timestamps. Mean elapsed times were 24.0 ms primary, 23.6 ms repeat, 24.9 ms reversed, and 28.5 ms with a distractor. This short-run latency includes ingestion and persistence and is specific to the test machine.

## Limitations

This is a small synthetic dataset with provisional, single-author judgments and no independent human adjudication. The controlled arm supplies the passages, so citation validity and resolution measure handling of the supplied references. They do not estimate retrieval recall. The distractor is deliberately unrelated, and ordering comparisons cover reversal only. Latencies are descriptive, and the deterministic backend says little about live provider accuracy, stochastic variance, or cost. Results do not establish multi-agent superiority.

## Reproduction

Run from the repository root after installing the locked dependencies.

```powershell
uv sync --locked
uv run --locked python -m evaluation.run --repeats 3 --output reports/evaluation-v1-offline.json
uv run --locked pytest -q
```

The [dataset](../evaluation/v1.json) contains the case rationale and the [machine-readable results](evaluation-v1-offline.json) retain per-case predictions, evidence stances, fault outcomes, and timings.
