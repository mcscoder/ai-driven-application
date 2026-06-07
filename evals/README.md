# Live Eval

This directory contains live eval scenarios for the `/api/chat` memory runtime.
The default suite is the target natural-conversation suite. A shorter smoke
suite is available for quick checks.

## Prepare

Run the app with a separate memory group for each eval to avoid old data:

```sh
MEMORY_GROUP_ID=eval-$(date +%Y%m%d-%H%M%S) UV_CACHE_DIR=.uv-cache uv run uvicorn app.main:app --host 127.0.0.1 --port 8000
```

The runner reads judge config from `.env`:

```sh
LLM_BASE_URL
LLM_API_KEY
LLM_MODEL
```

## Validate Scenarios Without Network

```sh
UV_CACHE_DIR=.uv-cache uv run python evals/run_live_eval.py --dry-run
```

This validates `evals/target_scenarios.json` and prints case counts by category.

To validate the smaller smoke suite:

```sh
UV_CACHE_DIR=.uv-cache uv run python evals/run_live_eval.py --dry-run --scenarios evals/natural_smoke_scenarios.json
```

## Run Live Eval

```sh
UV_CACHE_DIR=.uv-cache uv run python evals/run_live_eval.py \
  --base-url http://127.0.0.1:8000 \
  --memory-group-id eval-<run-id>
```

Run only the first N cases:

```sh
UV_CACHE_DIR=.uv-cache uv run python evals/run_live_eval.py --base-url http://127.0.0.1:8000 --limit 5
```

Collect raw app responses without calling the LLM judge:

```sh
UV_CACHE_DIR=.uv-cache uv run python evals/run_live_eval.py --base-url http://127.0.0.1:8000 --skip-judge
```

## Output

Runner writes reports into `evals/reports/`:

- `live-eval-<run-id>.json`: full raw result.
- `live-eval-<run-id>.md`: compact debug report.

`evals/reports/` is ignored so generated eval artifacts are not committed.

## Demo-Ready Criteria

Runner marks `demo_ready=true` when:

- Total pass rate is at least 85%.
- Critical pass rate is at least 95%.
- No case is judged as hallucinated memory.

When a run fails, read the Markdown report in this order:

1. `Category Results`
2. `Failed Cases`
3. `All Cases`
