# Memory Eval Handoff

This note captures the state of the project after the first serious live eval run, so the next agent can continue without re-litigating the architecture.

## Current State

- The project is still a lab/prototype for a Vietnamese companion-style memory assistant.
- Runtime API remains `POST /api/chat` returning `reply`, `retrieved_facts`, and `tool_trace`.
- Current implementation uses an agent loop in `app/llm_client.py` with memory tools backed mainly by `GraphitiMemory` in `app/graphiti_client.py`.
- A live eval suite now exists under `evals/` with 70 scenarios covering everyday memory, emotional continuity, social context, goals, updates, guardrails, no-memory queries, and noisy long-context cases.
- Generated eval reports are written to `evals/reports/` and should stay uncommitted.

## Important Existing Changes

- The old `evals/live_scenarios.json` suite was removed because it no longer matched the product target.
- `evals/run_live_eval.py` runs the suite against a live app via `/api/chat` and uses the configured LLM as judge.
- `evals/README.md` documents dry-run, smoke, and live eval commands.
- `.gitignore` ignores `evals/reports/`.
- `app/graphiti_client.py` was patched so Graphiti episode `reference_time` is converted to UTC before being sent to Neo4j. Without this, live writes hit `ValueError: utcoffset must be a whole number of minutes`.

## Live Eval Result

Latest full run:

- Report Markdown: `evals/reports/live-eval-full-local-20260607-002.md`
- Report JSON: `evals/reports/live-eval-full-local-20260607-002.json`
- App group used for the run: `eval-full-local-20260607-002`
- Pass rate: `18/70` = `26%`
- Critical pass rate: `6/14` = `43%`
- Hallucinated memory cases: `7`
- Demo-ready: `false`

Category results:

| Category | Passed | Total | Rate |
| --- | ---: | ---: | ---: |
| `dont_overuse_memory` | 8 | 8 | 100% |
| `everyday_memory` | 0 | 12 | 0% |
| `emotional_continuity` | 0 | 12 | 0% |
| `hard_guardrails` | 1 | 6 | 17% |
| `correction_update` | 2 | 8 | 25% |
| `noisy_long_context` | 1 | 4 | 25% |
| `personal_goals` | 3 | 10 | 30% |
| `social_context` | 3 | 10 | 30% |

## What The Eval Actually Says

Do not interpret the result as "the app always overuses memory". It does not.

The app is good at not dragging memory into unrelated generic questions. The `dont_overuse_memory` category passed all 8 cases.

The app is weak at retrieving and using memory when memory is required:

- Everyday preferences fail almost completely, e.g. cafe style, coriander dislike, address preference, answer style, black coffee preference.
- Emotional continuity fails completely, e.g. why the user is frustrated, what calms them down, what kind of support they want.
- Some named-entity/social facts pass, e.g. Anh Tu, Lan, Minh vs Nam.
- Some goal/update facts pass when phrasing is close to the stored text.
- Temporal guardrail had one strong pass for tomorrow schedule, but debt direction, cancellation, and deadlines are still unreliable.

The dominant failure modes are:

1. `retrieved_facts` is empty even when the seed memory is directly relevant.
2. The agent searches with a query that is too narrow, e.g. searching only `phở` and missing `không ăn rau mùi`.
3. The assistant answers generically after retrieval fails instead of retrying with broader memory queries.
4. Pinned conversational preferences such as `gọi tui là ông` and `trả lời ngắn, ý chính trước` are treated as ordinary retrievable facts, so they are often not present when needed.
5. Some answers are factually grounded but fail the companion/persona constraint because they ignore already-stated style preferences.

## Recommended Next Implementation Direction

This section is obsolete. Use `docs/memory_runtime_rebuild_plan.md` instead.
The current memory model has only `pin` and `long_term`.

Do not replace Graphiti yet. The next step should be a focused memory pipeline improvement:

1. Add a direct companion memory layer in Neo4j.
   - Store natural memory text as a simple relationship or node separate from Graphiti extraction.
   - Include fields like `uuid`, `group_id`, `text`, `kind`, `pinned`, `created_at`, and `invalid_at`.
   - Keep it simple. Do not create hard domain tables for every concept.

2. Add pinned memory.
   - Pinned memory should be loaded every chat turn and injected into the first prompt.
   - Use this for pinned preferences: address style, answer length, uncertainty handling, praise/support preference, and other durable conversation preferences.
   - This is not if/else product logic. It is stable conversational context.

3. Write to both Graphiti and companion memory.
   - Keep existing Graphiti episode writes for now.
   - Also save non-temporal `remember_fact` / `remember_current_message` into companion memory.
   - Temporal manual facts can remain as-is for now.

4. Search both Graphiti and companion memory.
   - Merge companion memory results into `retrieved_facts` so the UI still explains grounding.
   - Keep existing Graphiti search in place.
   - Dedupe by fact text and validity metadata.

5. Add broad retry search.
   - If a memory-like question returns zero facts, automatically search broader variants before answering.
   - For example, a food question should also search user food preferences and dislikes, not only the literal food name.
   - This should happen in backend search logic, not only by hoping the LLM calls the tool again.

## Concrete Target For Next Eval

Do not aim for perfect immediately. The next implementation should be judged by these targets:

- Overall pass rate: at least `40/70`.
- Critical pass rate: at least `10/14`.
- `everyday_memory`: at least `8/12`.
- `emotional_continuity`: at least `6/12`.
- Preserve `dont_overuse_memory`: should remain close to `8/8`.

## Commands To Use

Always use `uv` and keep cache local:

```sh
UV_CACHE_DIR=.uv-cache uv run pytest
UV_CACHE_DIR=.uv-cache uv run python evals/run_live_eval.py --dry-run
```

For live eval, start the app with a fresh group:

```sh
GRAPHITI_GROUP_ID=eval-<run-id> EMBEDDING_MODE=local EMBEDDING_PRELOAD=true UV_CACHE_DIR=.uv-cache uv run python -X faulthandler -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

Then run eval:

```sh
UV_CACHE_DIR=.uv-cache uv run python evals/run_live_eval.py --base-url http://127.0.0.1:8000 --graphiti-group-id eval-<run-id> --run-id <run-id>
```

Use smoke runs before full runs:

```sh
UV_CACHE_DIR=.uv-cache uv run python evals/run_live_eval.py --base-url http://127.0.0.1:8000 --limit 5 --run-id smoke-<run-id>
```

## Cautions For The Next Agent

- Do not delete Graphiti or Neo4j in the next step. The evidence does not justify a full replacement yet.
- Do not convert the product into rigid if/else task tables. The user explicitly dislikes over-specified assistant behavior.
- Do not optimize only for scheduled events or debts. The failing demo risk is mostly everyday and emotional memory.
- Do not trust a few manual chat checks. Always rerun at least dry-run, unit tests, and a smoke eval.
- Do not commit generated `evals/reports/` artifacts.
