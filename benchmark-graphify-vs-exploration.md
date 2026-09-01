# Benchmark: graphify vs. non-graphify answering — forecast_analysis repo

**Date:** 2026-08-31 · **Repo:** `/root/GitHub/forecast_analysis` · **Corpus:** ~17 modules + dashboard + ETL + tests + docs (graph: `graphify-out/graph.json`)

## Protocol

- 10 fixed questions about the repo, designed from filenames only (no graph content consulted).
- **Phase G (graphify-only):** per the graphify skill — vocab expansion against graph vocabulary (up to 12 tokens/question), `graphify query "<tokens>"` BFS traversals, `graphify explain` for node detail. Answers written **only** from graph output. No repo file was opened during this phase.
- **Phase N (non-graphify):** the same 10 questions answered by normal exploration only — `rg`, `sed`/`head` file reads, `wc`. Every payload tee'd to a capture dir. `graphify-out/` and the graphify CLI were **never** touched in this phase.
- **Token counting:** exact, via `tiktoken` (cl100k_base) on the captured byte content of everything consumed (tool outputs) + everything written (final answers). Question prompt text (172 tokens) is identical in both phases and counted once per phase.
- **Excluded (identical in both phases):** system/harness prompts, tool-call argument tokens, question-design setup. Note: ~3.5KB of `graphify query --help` output during harness setup was not counted (discovery only).

## Per-question token consumption (tokens)

| Q | graphify in | graphify out | **G total** | non-graphify in | non-graphify out | **N total** |
| --- | ------------- | -------------- | ------------- | ----------------- | ------------------ | ------------- |
| 1  Modules & relationships | 1,526 | 352 | **1,878** | 1,856 | 292 | **2,148** |
| 2  ETL data flow | 1,858 | 240 | **2,098** | 1,753 | 365 | **2,118** |
| 3  Accuracy metrics | 1,505 | 187 | **1,692** | 2,394 | 314 | **2,708** |
| 4  require_columns + callers | 1,862 | 221 | **2,083** | 1,093 | 211 | **1,304** |
| 5  Vintages usage | 1,901 | 221 | **2,122** | 1,079 | 214 | **1,293** |
| 6  Six-column contract | 1,600 | 158 | **1,758** | 1,437 | 201 | **1,638** |
| 7  Normalization helpers | 1,549 | 152 | **1,701** | 1,093 | 270 | **1,363** |
| 8  Dashboard data source | 1,522 | 201 | **1,723** | 1,079 | 237 | **1,316** |
| 9  comparison.py | 1,522 | 124 | **1,646** | 574 | 185 | **759** |
| 10 Test coverage | 1,540 | 263 | **1,803** | 507 | 374 | **881** |
| **Subtotal** | 16,385 | 2,119 | **18,504** | 12,865 | 2,663 | **15,528** |
| Fixed graphify overhead (vocab 1,115 tokens + lessons) | | | 2,676 | | | 0 |
| Questions text (identical) | | | 172 | | | 172 |
| **TOTAL** | | | **21,352** | | | **15,700** |

## Headline results

| Metric | graphify | non-graphify |
| --- | --- | --- |
| **Total tokens (10 questions)** | **21,352** | **15,700** |
| **Tokens per question (avg)** | 2,135 | 1,570 |
| Ratio | — | **G is 1.36× more expensive** |
| Failures | 0 hard / 3 partial | 0 |

## Why graphify cost more here

1. **Vocab expansion overhead (+2,676 tokens):** the skill requires reading the 1,115-token graph vocabulary into context before every query session.
2. **Flat BFS blast radius:** every query returned a ~300–560-node BFS traversal (truncated at the CLI's ~2,000-token budget) — mostly irrelevant neighbors (e.g. `DataFrame`, `datetime`, `test_*` nodes) for leaf-level questions. Per-question graphify cost is nearly flat (~1.6–1.9K) regardless of question difficulty, while non-graphify scales with the question (574 tokens for Q9, 2,394 for Q3).
3. Non-graphify targeted reads (docstrings, function bodies, `rg` callers) delivered more detail per token.

## Failures & quality notes

**Hard failures: none on either side.** All 10 graphify queries ran; all 10 non-graphify answers completed.

**Partial failures (graphify side, detail-level):**

- **Q2** — graph named the pipeline functions and edges but not the actual output CSV column names.
- **Q3** — graph gave function locations/relations but not the metric definitions (e.g. `forecast_accuracy_pct`, `wape_pct`, `bias_pct`, `mae_kl`, numerator/denominator audit fields).
- **Q6** — the graph has a concept node "Six-column consolidated output contract" (community 39) but the **six column names are not recoverable from the graph's queryable surface** — traversal/explain expose only the label.

**Non-graphify side:** zero failures; answers were strictly more detailed on every shared topic (exact six columns `[calculation_month, snop_month, parent_code, parent_description, qty, source]`, exact 12-column vintage-pair contract, real test-class list, `VintageRule` kinds, metric formula fields).

**Trade-off (accuracy/latency caveat):** the non-graphify phase ran after the graphify phase in the same session, so the model had seen graph responses first — a mild leakage that would *favor* non-graphify. Token counts are unaffected by leakage. A fully isolated benchmark (two fresh sessions) would be the strict version.

## Answer-content comparison (highlights)

| Q | graphify answered | non-graphify answered additionally |
| --- | --- | --- |
| 2 | pipeline call graph, atomic write, artifact path | 16 expected files, 8 ML input columns, two header layouts, month-provenance rules, tolerance details |
| 3 | `calculate_metrics` L452, `MetricSummary` L215, relation to actuals | full KPI field list, numerator/denominator audit model, revision metrics semantics |
| 4 | degree-43 helper, 12 named callers + imports | exact behavior ("fail clearly, raise ValueError"), per-file call-site counts (filters 13, metrics 14, quality 14), the 12-column required list |
| 5 | rule kinds + pair selection + 6 test names | default rules (oldest/latest), coverage-population semantics, group-by mechanics |
| 6 | **six-column contract exists, names unavailable** | the six names + key columns + sort order + oracle manifest paths |
| 10 | test files + 14 named classes | all 30 test classes with line numbers + domains |

## Verdict

- **Token efficiency:** non-graphify wins (15,700 vs 21,352 → graphify consumes ~36% more).
- **Detail/accuracy:** non-graphify wins on every question where details mattered; graphify's only wins are architectural orientation (Q1 module map compiled from one traversal) and zero-touch exploration (no file reads needed at all).
- **When graphify still makes sense:** cold unfamiliar-repo orientation, relationship questions ("what reaches X?"), and when you want answers without opening any file. For precision (columns, contracts, formulas, exact callers), direct exploration is cheaper and more accurate — here it capitalized on docstrings + a well-seamed `_utils.py`.
- The fixed vocab overhead hits small single-session benchmarks hard; it amortizes across many queries in a long-lived session.

*Methodology: tiktoken cl100k_base over captured tool-output bytes + answer text; per-phase capture dirs `/tmp/bench/g_phase` and `/tmp/bench/n_phase` (raw evidence + answers retained for reproduction).*
