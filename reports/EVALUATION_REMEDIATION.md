# Offline evaluation remediation

The verifier matched the approval sentence literally and searched for contradiction only through differing numeric templates. Rejection contained no changed number, so the verifier returned SUPPORTED and the release gate accepted it. The revised verifier checks six opposing status pairs in both directions and compares subject, tense, date, and condition. Matching contexts can conflict, distinct comparable dates can coexist, and ambiguous recognized opposition or competing assertions in the same passage cause abstention. The numeric check also distinguishes changing a value from changing its time scope.

The original factual-conflict case now returns CONFLICTING with support from a.txt and contradiction from b.md. The finding is withheld. The original [results](evaluation-v1-offline.json) and updated [results](evaluation-v2-offline.json) have identical dataset hashes. Each contains per-class metrics, confusion matrices, case-level stances and timings.

| Measure | Original | Updated |
|---|---:|---:|
| Verdict accuracy | 8/11 | 9/11 |
| Macro-F1 | 0.733 | 0.827 |
| SUPPORTED F1 | 0.667 | 0.800 |
| PARTIALLY_SUPPORTED F1 | 0.667 | 0.667 |
| UNSUPPORTED F1 | 0.667 | 0.667 |
| CONFLICTING F1 | 0.667 | 1.000 |
| NOT_VERIFIABLE F1 | 1.000 | 1.000 |
| Conflict recall | 1/2 | 2/2 |
| Semantic evidence stance recall | 8/11 | 9/11 |
| Mechanical citation validity | 10/11 | 10/11 |
| Exact resolution among resolved refs | 10/10 | 10/10 |
| Release coverage | 3/11 | 2/11 |
| Correct abstention | 7/8 | 8/8 |
| Incorrect abstention | 1/3 | 1/3 |
| Ineligible releases | 1 | 0 |

The remaining incorrect abstention is the fully supported six-week paraphrase. The partially supported renewal paraphrase is also still misclassified as UNSUPPORTED. Citation-only and ungated policies still release six and eight ineligible claims respectively.

The updated controlled run had zero disagreements across 22 repeat and 11 reversed-order comparisons. All 44 end-to-end runs reopened identically from SQLite. Each perturbation arm matched the primary arm's compared outcomes. Injected failure, timeout, and malformed response all withheld the candidate. End-to-end mean latency ranged from 24.3 to 29.7 ms across variants. No live provider calls were made.

## Review and comparison scope

The [annotation review sheet](../evaluation/ANNOTATION_REVIEW.md) includes all case materials and provisional judgments. Independent human review remains pending. The dataset labels were unchanged.

A single-agent comparison was deferred. The deterministic backend already has separate selection and verification operations. Combining them under a single function would reuse the same judgments, and writing a new unified rule would change both the backend behavior and architecture. The release-policy ablations are the available comparisons.

The original conflict case informed the correction, so the rerun is an in-sample remediation check. The extra regression cases test rule boundaries. Alias resolution, implied negation, richer temporal and conditional reasoning, and contradictions outside retrieved passages remain limitations. Live-model accuracy and cost remain unmeasured.

## Reproduction

Run from the root of a checkout of release commit `5eefd9bbbe3c281c1b68dddaf804c77ac200b31d`, which contains the remediated verifier (`offline_rules_v2`). The runner loads [`evaluation/v1.json`](../evaluation/v1.json) automatically and writes a separate v2 reproduction result.

```powershell
uv sync --locked
uv run --locked python -m evaluation.run --repeats 3 --output .venv/reproduction-v2-offline.json
```

Compare the dataset digest and the verdict, evidence, and release metrics with the [archived v2 results](evaluation-v2-offline.json). Timing measurements can vary.

The locked offline-cache suites returned 70 passed and 1 skipped in 7.63 seconds in the base environment, and 71 passed in 9.95 seconds with the optional adapter installed. The adapter test uses a mock. The base suite emitted the existing Starlette test transport warning.
