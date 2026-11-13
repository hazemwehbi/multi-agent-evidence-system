# MAEDS testing

## Final demonstrator checks

The final checks used Windows and CPython 3.13.1. A fresh base virtual environment installed from the existing package cache with `uv sync --locked --offline --python 3.13`. `uv lock --check --offline` confirmed the lockfile resolved 55 packages.

| Check | Observed result |
|---|---|
| `python -m pytest -q` in the fresh base environment | 70 passed, 1 skipped in 6.03 s. The skip was the optional adapter test. Starlette emitted its existing test transport deprecation warning. |
| `uv run --locked --extra openai --offline --cache-dir .venv/uv-cache pytest -q` | 71 passed in 9.45 s. The optional adapter test uses a mock. |
| Offline smoke and evaluation | Smoke returned ready. The benchmark regenerated the same dataset digest and verdict, evidence, and release metrics as the archived remediation run. |
| Northgate run through a live localhost Uvicorn process | Multipart upload returned 303. The workflow produced 6 attempts and 12 messages, with one supported finding, two conflicts, and recommendation abstention. |
| Second Uvicorn process and separate CLI trace | The persisted report and source page reopened. The budget claim resolved to finance-record.txt at offsets [0, 55). |

The screenshot review used Chrome against the localhost routes. A pattern scan of shareable text files found no common OpenAI key, AWS access key, or private-key markers. Demonstration documents are fictional. Virtual environments, databases, and local dotenv files are excluded from Git. Both archived benchmark JSON hashes were unchanged. The initial release is recorded in commit `5eefd9b`.

## Milestone 5 benchmark

The [evaluation report](../reports/EVALUATION.md) documents the fixed-case verifier benchmark, release ablations, end-to-end perturbations, reference annotation status, and reproduction commands. This benchmark is separate from the software regression suite.

- `uv run --locked --extra openai --offline --cache-dir .venv/uv-cache pytest -q` returned **50 passed** in 9.43 seconds.
- The base-environment equivalent without `--extra openai` returned **49 passed, 1 skipped** in 7.30 seconds. Starlette emitted its test-client transport deprecation warning.
- The original run used the project virtual environment and produced the archived v1 results. See the [v1 reproduction notes](../reports/EVALUATION.md#reproduction) for the required verifier revision and a separate rerun output path.

Run `uv run --locked pytest` for the base suite, or `uv run --locked --extra openai pytest` to include the mocked OpenAI adapter test. The suite clears MAEDS and OpenAI environment settings and runs from temporary directories to isolate local dotenv files.

## Milestone 1 checks

| Check | Observed result on Windows with CPython 3.13.1 |
| --- | --- |
| Pytest with OpenAI extra | 11 passed in 5.37 seconds |
| Pytest in a fresh base environment | 10 passed and 1 skipped in 1.80 seconds. The skipped test requires the optional adapter dependencies. |
| Installed `maeds smoke` in the base environment without credentials | Exit code 0, provider `offline`, model `deterministic-v1`, status `ready` |
| Offline lockfile validation | Succeeded |

Tests cover environment configuration, credential exclusion, a typed message round trip, exact passage text and span lengths, the reference-only synthesis contract, deterministic fixture responses, and injected model failures, timeouts, and malformed output. The optional adapter test replaces the external client with a mock. A live API request and the six end-to-end evaluation scenarios remain pending.

## Milestone 2 checks

Executed on Windows with CPython 3.13.1, using the existing locked environments and uv's offline cache.

| Command | Observed result |
| --- | --- |
| `uv run --locked --extra openai --offline --cache-dir .venv/uv-cache pytest -q` | 28 passed in 4.42 seconds |
| `uv run --locked --offline --cache-dir .venv/uv-cache pytest -q` in the base environment | 27 passed and 1 skipped in 2.63 seconds. The skip is the mocked OpenAI adapter test. |
| Installed `maeds demo` with the API key unset | Exit 0, six steps, twelve messages, two unresolved claims, `awaiting_semantic_verification` |
| Installed `maeds demo --empty` with the API key unset | Exit 0, five steps, twelve messages, `no_candidate_claims` |

Workflow tests cover all five roles, serialized message round trips, upstream dependency routing, sequential and concurrent retrieval, the empty-evidence branch, failure recovery, timeout cancellation, malformed responses, invalid plans, step exhaustion, and rejection of an unverified finding at release.

## Milestone 3 checks

Executed on Windows with CPython 3.13.1. The OpenAI adapter test uses a mock.

| Command | Observed result |
| --- | --- |
| `uv run --locked --extra openai --offline --cache-dir .venv/uv-cache pytest -q` | 40 passed in 8.21 seconds |
| `uv run --locked --offline --cache-dir .venv/uv-cache pytest -q` in the base environment | 39 passed and 1 skipped in 6.35 seconds. The skip requires the optional adapter. |
| Installed `maeds run`, `maeds inspect`, and `maeds trace` with the API key unset | All exited zero. A new process reopened the partial run with 6 steps, 12 messages, and 2 unresolved claims. A separate trace process resolved the Birch candidate to `birch.md`, section `Budget`, offsets `[10, 48)`. |

Evidence tests cover TXT and Markdown validation, stable IDs, exact Unicode and CRLF slices, multi-source retrieval, CLI restart, cross-run rejection, unknown sources, ingestion rollback, unusable database paths, and rollback of a final trace with forged evidence.

## Milestone 4 checks

Executed on Windows with CPython 3.13.1 and the locked offline cache.

| Command | Observed result |
| --- | --- |
| `uv run --locked --extra openai --offline --cache-dir .venv/uv-cache pytest -q` | 48 passed in 7.98 seconds. The OpenAI adapter test uses a mock. |
| `uv run --locked --offline --cache-dir .venv/uv-cache pytest -q` in the base environment | 47 passed, 1 skipped in 6.96 seconds. The optional adapter test was skipped. Starlette emitted a test-client deprecation warning about its httpx transport. |
| Installed `maeds run` and `maeds trace` against bundled TXT and Markdown with offline mode selected | Run succeeded in 6 steps with 12 messages and 2 eligible claims. The decision published findings and abstained from a recommendation. The Birch claim resolved to `birch.md`, section `Budget`, offsets `[10, 48)`. |

Deterministic verification cases cover all five verdicts, multiple supporting passages, conflicting passages, an irrelevant but valid citation, missing and invalid citations, and invalid model evidence indexes. Release tests check excluded findings and reject injected finding IDs. FastAPI integration tests exercise multipart upload, status and report reads, conflict display, highlighted original-source navigation, escaping, invalid uploads, and reopening the report with a new app instance. These checks measure application behavior on controlled inputs. Live provider accuracy remains unmeasured.
