# Agent Instructions

## Project Context

- This is a Python project named `graphiti-chat-lab`.
- The project requires Python `>=3.12`; `.python-version` currently specifies `3.12`.
- Use `pyproject.toml` as the source of truth for project metadata and dependencies.

## Package And Environment Management

- Use `uv` only for Python environment, dependency, lockfile, and execution tasks.
- Do not use `pip`, `pipenv`, `poetry`, `conda`, or system Python package installation commands for this project.
- Keep the `uv` cache inside this repository by setting:

```sh
export UV_CACHE_DIR=.uv-cache
```

- When running one-off commands, prefix them with the cache setting if the shell environment is not already configured:

```sh
UV_CACHE_DIR=.uv-cache uv sync
UV_CACHE_DIR=.uv-cache uv run python main.py
UV_CACHE_DIR=.uv-cache uv add <package>
UV_CACHE_DIR=.uv-cache uv remove <package>
```

- If a lockfile is present or generated, keep it updated through `uv` commands only.
- Do not write dependency artifacts or caches outside the repository unless the user explicitly asks for it.

## Development Commands

- Install or update the environment:

```sh
UV_CACHE_DIR=.uv-cache uv sync
```

- Run project code:

```sh
UV_CACHE_DIR=.uv-cache uv run python main.py
```

- Add dependencies:

```sh
UV_CACHE_DIR=.uv-cache uv add <package>
```

## Repository Hygiene

- Keep changes scoped to the requested task.
- Do not commit generated caches such as `.uv-cache/`.
- Prefer `rg` for repository searches.

## 1. Think Before Coding

**Don't assume. Don't hide confusion. Surface tradeoffs.**

Before implementing:
- State your assumptions explicitly. If uncertain, ask.
- If multiple interpretations exist, present them - don't pick silently.
- If a simpler approach exists, say so. Push back when warranted.
- If something is unclear, stop. Name what's confusing. Ask.

## 2. Simplicity First

**Minimum code that solves the problem. Nothing speculative.**

- No features beyond what was asked.
- No abstractions for single-use code.
- No "flexibility" or "configurability" that wasn't requested.
- No error handling for impossible scenarios.
- If you write 200 lines and it could be 50, rewrite it.

Ask yourself: "Would a senior engineer say this is overcomplicated?" If yes, simplify.

## 3. Surgical Changes

**Touch only what you must. Clean up only your own mess.**

When editing existing code:
- Don't "improve" adjacent code, comments, or formatting.
- Don't refactor things that aren't broken.
- Match existing style, even if you'd do it differently.
- If you notice unrelated dead code, mention it - don't delete it.

When your changes create orphans:
- Remove imports/variables/functions that YOUR changes made unused.
- Don't remove pre-existing dead code unless asked.

The test: Every changed line should trace directly to the user's request.

## 4. Goal-Driven Execution

**Define success criteria. Loop until verified.**

Transform tasks into verifiable goals:
- "Add validation" → "Write tests for invalid inputs, then make them pass"
- "Fix the bug" → "Write a test that reproduces it, then make it pass"
- "Refactor X" → "Ensure tests pass before and after"

For multi-step tasks, state a brief plan:
```
1. [Step] → verify: [check]
2. [Step] → verify: [check]
3. [Step] → verify: [check]
```
