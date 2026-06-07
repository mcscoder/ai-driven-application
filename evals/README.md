# Live Eval

Thu muc nay chua bo eval live cho Graphiti Chat Lab. Eval goi API that
`/api/chat`, seed memory bang cac cau chat tu nhien, hoi lai bang tieng Viet,
roi dung cung LLM config hien co de judge ket qua.

## Chuan bi

Chay app voi group rieng cho moi lan eval de tranh nhieu du lieu cu:

```sh
GRAPHITI_GROUP_ID=eval-$(date +%Y%m%d-%H%M%S) UV_CACHE_DIR=.uv-cache uv run uvicorn app.main:app --host 127.0.0.1 --port 8000
```

Runner doc judge config tu `.env`:

```sh
LLM_BASE_URL
LLM_API_KEY
LLM_MODEL
```

## Kiem tra scenario khong goi network

```sh
UV_CACHE_DIR=.uv-cache uv run python evals/run_live_eval.py --dry-run
```

Lenh nay chi validate `evals/live_scenarios.json` va in so case theo category.

## Chay live eval

```sh
UV_CACHE_DIR=.uv-cache uv run python evals/run_live_eval.py \
  --base-url http://127.0.0.1:8000 \
  --graphiti-group-id eval-<run-id>
```

Neu muon chay nhanh vai case dau:

```sh
UV_CACHE_DIR=.uv-cache uv run python evals/run_live_eval.py --base-url http://127.0.0.1:8000 --limit 5
```

Neu chi muon thu app response, khong goi LLM judge:

```sh
UV_CACHE_DIR=.uv-cache uv run python evals/run_live_eval.py --base-url http://127.0.0.1:8000 --skip-judge
```

## Output

Runner ghi report vao `evals/reports/`:

- `live-eval-<run-id>.json`: raw result day du.
- `live-eval-<run-id>.md`: report doc nhanh khi demo/debug.

Thu muc `evals/reports/` duoc ignore de khong commit artifact chay eval.

## Tieu chi demo-ready

Runner danh dau `demo_ready=true` khi:

- Tong pass rate >= 85%.
- Critical pass rate >= 95%.
- Khong co case nao bi judge la hallucinated memory.

Neu fail, doc report Markdown theo thu tu:

1. `Category Results` de biet nhom nao yeu.
2. `Failed Cases` de xem probe, expected memory, forbidden memory, reply va facts.
3. `All Cases` de xem ly do judge ngan gon cho tung case.
