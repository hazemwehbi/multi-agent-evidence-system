# Reference annotation review sheet v1.0.0

**Provisional labels.** Codex drafted the proposed judgments before running MAEDS. Independent human review is pending. The frozen dataset remains the source of record.

Reviewer ____________________  Date ____________________

For a blinded review, hide the proposed judgment column. Read the question, claim, exact document text, and supplied citations. Each document represents one passage. Record a verdict, supporting and contradicting filenames, and a short rationale. Compare entities, dates, quantities, and conditions. Use only the supplied documents. Preserve disagreements and adjudicate them in a new dataset version.

| Verdict | Annotation rule |
|---|---|
| SUPPORTED | The evidence supports every material part, including equivalent paraphrases. |
| PARTIALLY_SUPPORTED | Evidence supports some material clauses and leaves others unestablished. |
| UNSUPPORTED | A citation resolves but available evidence supports none of the claim. Refutation without supporting evidence also falls here. |
| CONFLICTING | Comparable evidence supports and contradicts the claim in the same context, with no supplied reason to prefer one source. Record both sides. |
| NOT_VERIFIABLE | Missing or unusable citations prevent assessment under this protocol. |

| Case | Question | Claim | Exact document text | Supplied citations | Proposed judgment | Reviewer verdict, stances, and rationale |
|---|---|---|---|---|---|---|
| direct | What is the pilot budget? | Pilot budget is 20. | **a.txt** Pilot budget is 20.<br>**noise.md** Migratory birds return in spring. | a.txt | SUPPORTED. Support a.txt. Oppose none. Exact statement. |  |
| paraphrase | How long does the trial run? | The trial runs for six weeks. | **a.txt** The trial lasts six weeks. | a.txt | SUPPORTED. Support a.txt. Oppose none. Runs for and lasts express the same duration. |  |
| multiple | What are the cost and launch date? | Pilot budget is 20 and pilot opens in May. | **a.txt** Pilot budget is 20.<br>**b.md** Pilot opens in May. | a.txt, b.md | SUPPORTED. Support a.txt, b.md. Oppose none. Both clauses have direct evidence across two passages. |  |
| partial | What are the cost and launch date? | Pilot budget is 20 and pilot opens in May. | **a.txt** Pilot budget is 20. | a.txt | PARTIALLY_SUPPORTED. Support a.txt. Oppose none. Budget is stated, opening month is absent. |  |
| partial-paraphrase | What is the term and renewal policy? | The agreement runs for two years and renews automatically. | **a.txt** The agreement lasts two years. | a.txt | PARTIALLY_SUPPORTED. Support a.txt. Oppose none. Duration is entailed, renewal is absent. |  |
| irrelevant | When does the pilot open? | Pilot opens in May. | **a.txt** The city has three libraries. | a.txt | UNSUPPORTED. Support none. Oppose none. The cited text is available and irrelevant. |  |
| wrong-number | What is the pilot budget? | Pilot budget is 20. | **a.txt** Pilot budget is 24. | a.txt | UNSUPPORTED. Support none. Oppose a.txt. The sole value directly contradicts the candidate. |  |
| numeric-conflict | What is the pilot budget? | Pilot budget is 20. | **a.txt** Pilot budget is 20.<br>**b.md** Pilot budget is 24. | a.txt | CONFLICTING. Support a.txt. Oppose b.md. Comparable sources assert different values with no precedence. |  |
| factual-conflict | What is the pilot status? | The pilot is approved. | **a.txt** The pilot is approved.<br>**b.md** The pilot is rejected. | a.txt | CONFLICTING. Support a.txt. Oppose b.md. Sources give mutually exclusive statuses for the same decision. |  |
| missing | When does the pilot open? | Pilot opens in May. | **a.txt** Pilot budget is 20. | None | NOT_VERIFIABLE. Support none. Oppose none. No evidence reference is supplied. |  |
| invalid | What is the pilot budget? | Pilot budget is 20. | **a.txt** Pilot budget is 20. | missing.txt | NOT_VERIFIABLE. Support none. Oppose none. The sole citation cannot resolve. |  |
