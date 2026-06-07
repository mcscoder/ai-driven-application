from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any

import httpx
from dotenv import load_dotenv


SCENARIO_PATH = Path(__file__).with_name("target_scenarios.json")
REPORT_DIR = Path(__file__).with_name("reports")

REQUIRED_CASE_FIELDS = {
    "id",
    "category",
    "critical",
    "should_retrieve",
    "seed_messages",
    "probe_message",
    "expected_memory",
    "forbidden_memory",
    "judge_notes",
}

JUDGE_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "passed": {"type": "boolean"},
        "retrieval_correct": {"type": "boolean"},
        "answer_grounded": {"type": "boolean"},
        "hallucinated_memory": {"type": "boolean"},
        "natural_friend_tone": {
            "type": "string",
            "enum": ["pass", "warning", "fail"],
        },
        "score": {"type": "integer"},
        "reason": {"type": "string"},
    },
    "required": [
        "passed",
        "retrieval_correct",
        "answer_grounded",
        "hallucinated_memory",
        "natural_friend_tone",
        "score",
        "reason",
    ],
    "additionalProperties": False,
}


def main() -> int:
    load_dotenv()
    args = parse_args()

    suite = load_suite(args.scenarios)
    cases = suite["cases"]
    if args.limit:
        cases = cases[: args.limit]

    errors = validate_cases(cases)
    if errors:
        for error in errors:
            print(f"schema error: {error}", file=sys.stderr)
        return 2

    print_suite_summary(cases)
    if args.dry_run:
        return 0

    missing = missing_judge_env()
    if missing and not args.skip_judge:
        print(
            "missing judge env: "
            + ", ".join(missing)
            + ". Use --skip-judge to collect raw app results only.",
            file=sys.stderr,
        )
        return 2

    results = asyncio.run(run_suite(cases, args))
    write_reports(results, args)
    if args.skip_judge:
        return 0
    return 1 if any(not case_passed(result) for result in results) else 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run live memory evals against the chat memory API."
    )
    parser.add_argument(
        "--base-url",
        default="http://127.0.0.1:8000",
        help="App base URL, not including /api/chat.",
    )
    parser.add_argument(
        "--scenarios",
        type=Path,
        default=SCENARIO_PATH,
        help=(
            "Scenario JSON path. Defaults to the target natural-conversation suite; "
            "use evals/natural_smoke_scenarios.json for a shorter smoke check."
        ),
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=REPORT_DIR,
        help="Directory for generated JSON and Markdown reports.",
    )
    parser.add_argument(
        "--run-id",
        default=datetime.now().strftime("%Y%m%d-%H%M%S"),
        help="Report file suffix.",
    )
    parser.add_argument(
        "--memory-group-id",
        default=None,
        help="Optional app MEMORY_GROUP_ID to record in the report metadata.",
    )
    parser.add_argument(
        "--graphiti-group-id",
        default=None,
        help="Deprecated alias for --memory-group-id.",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=180.0,
        help="HTTP timeout in seconds for app and judge calls.",
    )
    parser.add_argument(
        "--seed-delay",
        type=float,
        default=0.0,
        help="Optional delay between seed messages in seconds.",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=0,
        help="Run only the first N cases.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Validate and summarize scenarios without network calls.",
    )
    parser.add_argument(
        "--skip-judge",
        action="store_true",
        help="Collect raw /api/chat results without calling the LLM judge.",
    )
    return parser.parse_args()


def load_suite(path: Path) -> dict[str, Any]:
    with path.open(encoding="utf-8") as file:
        suite = json.load(file)
    if not isinstance(suite, dict) or not isinstance(suite.get("cases"), list):
        raise SystemExit("scenario file must be an object with a cases list")
    return suite


def validate_cases(cases: list[dict[str, Any]]) -> list[str]:
    errors = []
    seen_ids = set()
    for index, case in enumerate(cases, start=1):
        if not isinstance(case, dict):
            errors.append(f"case #{index} is not an object")
            continue

        missing = REQUIRED_CASE_FIELDS - set(case)
        if missing:
            errors.append(f"{case.get('id', f'case #{index}')} missing {sorted(missing)}")

        case_id = case.get("id")
        if not isinstance(case_id, str) or not case_id:
            errors.append(f"case #{index} has invalid id")
        elif case_id in seen_ids:
            errors.append(f"duplicate id {case_id}")
        else:
            seen_ids.add(case_id)

        for field in ("category", "probe_message", "judge_notes"):
            if not isinstance(case.get(field), str) or not case.get(field):
                errors.append(f"{case_id} has invalid {field}")

        for field in ("critical", "should_retrieve"):
            if not isinstance(case.get(field), bool):
                errors.append(f"{case_id} has invalid {field}")

        for field in ("seed_messages", "expected_memory", "forbidden_memory"):
            value = case.get(field)
            if not isinstance(value, list) or not all(
                isinstance(item, str) for item in value
            ):
                errors.append(f"{case_id} has invalid {field}")

    return errors


def print_suite_summary(cases: list[dict[str, Any]]) -> None:
    by_category = Counter(case["category"] for case in cases)
    critical = sum(1 for case in cases if case["critical"])
    print(f"loaded {len(cases)} cases ({critical} critical)", flush=True)
    for category, count in sorted(by_category.items()):
        print(f"- {category}: {count}", flush=True)


def missing_judge_env() -> list[str]:
    required = ["LLM_BASE_URL", "LLM_API_KEY", "LLM_MODEL"]
    return [name for name in required if not os.getenv(name)]


async def run_suite(
    cases: list[dict[str, Any]], args: argparse.Namespace
) -> list[dict[str, Any]]:
    results = []
    known_memory_context: list[str] = []
    async with httpx.AsyncClient(timeout=args.timeout) as client:
        for index, case in enumerate(cases, start=1):
            print(
                f"[{index:02d}/{len(cases):02d}] {case['id']} {case['category']}",
                flush=True,
            )
            result = await run_case(client, case, args, known_memory_context)
            results.append(result)
            known_memory_context.extend(case["seed_messages"])
            judge = result.get("judge") or {}
            if judge:
                status = "PASS" if judge.get("passed") else "FAIL"
                print(f"  {status}: {judge.get('reason', '')}", flush=True)
            else:
                print("  collected raw result", flush=True)
    return results


async def run_case(
    client: httpx.AsyncClient,
    case: dict[str, Any],
    args: argparse.Namespace,
    known_memory_context: list[str],
) -> dict[str, Any]:
    seed_results = []
    for message in case["seed_messages"]:
        seed_response = await post_chat(client, args.base_url, message)
        seed_results.append(
            {
                "message": message,
                "reply": seed_response.get("reply", ""),
                "retrieved_facts": seed_response.get("retrieved_facts", []),
                "tool_trace": seed_response.get("tool_trace", []),
            }
        )
        if args.seed_delay:
            await asyncio.sleep(args.seed_delay)

    probe_response = await post_chat(client, args.base_url, case["probe_message"])
    result = {
        "case": case,
        "known_memory_context": [*known_memory_context, *case["seed_messages"]],
        "seed_results": seed_results,
        "probe_response": probe_response,
    }
    if not args.skip_judge:
        result["judge"] = await judge_case(
            client,
            case,
            probe_response,
            result["known_memory_context"],
        )
    return result


async def post_chat(
    client: httpx.AsyncClient, base_url: str, message: str
) -> dict[str, Any]:
    response = await client.post(
        f"{base_url.rstrip('/')}/api/chat",
        json={"message": message},
    )
    response.raise_for_status()
    payload = response.json()
    if not isinstance(payload, dict):
        raise ValueError("/api/chat returned non-object JSON")
    return payload


async def judge_case(
    client: httpx.AsyncClient,
    case: dict[str, Any],
    probe_response: dict[str, Any],
    known_memory_context: list[str],
) -> dict[str, Any]:
    body = {
        "contents": [
            {
                "role": "user",
                "parts": [
                    {
                        "text": build_judge_prompt(
                            case,
                            probe_response,
                            known_memory_context,
                        )
                    }
                ],
            }
        ],
        "generationConfig": {
            "temperature": 0,
            "maxOutputTokens": 1024,
            "thinkingConfig": {"thinkingBudget": 0},
            "responseMimeType": "application/json",
            "responseSchema": JUDGE_SCHEMA,
        },
        "systemInstruction": {
            "parts": [
                {
                    "text": (
                        "You are a strict evaluator for a Vietnamese companion "
                        "memory assistant. Return only valid JSON."
                    )
                }
            ]
        },
    }
    response = await client.post(
        gemini_generate_content_url(os.environ["LLM_BASE_URL"], os.environ["LLM_MODEL"]),
        headers={
            "Authorization": f"Bearer {os.environ['LLM_API_KEY']}",
            "Content-Type": "application/json",
        },
        json=body,
    )
    response.raise_for_status()
    return parse_judge_payload(response.json())


def build_judge_prompt(
    case: dict[str, Any],
    probe_response: dict[str, Any],
    known_memory_context: list[str],
) -> str:
    judge_input = {
        "case_id": case["id"],
        "category": case["category"],
        "critical": case["critical"],
        "should_retrieve": case["should_retrieve"],
        "known_memory_context": known_memory_context,
        "seed_messages": case["seed_messages"],
        "probe_message": case["probe_message"],
        "expected_memory": case["expected_memory"],
        "forbidden_memory": case["forbidden_memory"],
        "judge_notes": case["judge_notes"],
        "assistant_reply": probe_response.get("reply", ""),
        "retrieved_facts": probe_response.get("retrieved_facts", []),
        "tool_trace": probe_response.get("tool_trace", []),
    }
    return (
        "Evaluate this live /api/chat result.\n\n"
        "Scoring rules:\n"
        "- retrieval_correct is true when retrieved_facts/tool_trace show the relevant "
        "memory was searched and found. For should_retrieve=false, it is true when "
        "the answer avoids unrelated personal memory.\n"
        "- answer_grounded is true when the reply uses the expected memory correctly "
        "and does not contradict updates/cancellations.\n"
        "- hallucinated_memory is true if the reply invents personal memory not present "
        "in known_memory_context or retrieved_facts.\n"
        "- Mentioning older known memory is not hallucination by itself, but it should "
        "fail passed/retrieval_correct when it is unrelated or distracts from the "
        "current probe.\n"
        "- natural_friend_tone should be pass, warning, or fail. Do not require a "
        "cheerful tone; concise and natural is acceptable.\n"
        "- passed must be true only when the case would be safe to show in a demo.\n"
        "- score is 1 to 5.\n\n"
        "Return JSON only for this input:\n"
        f"{json.dumps(judge_input, ensure_ascii=False, indent=2)}"
    )


def parse_judge_payload(payload: dict[str, Any]) -> dict[str, Any]:
    candidates = payload.get("candidates") or []
    if not candidates:
        raise ValueError("judge returned no candidates")
    parts = candidates[0].get("content", {}).get("parts") or []
    text_parts = [part.get("text", "") for part in parts if isinstance(part, dict)]
    text = "\n".join(part for part in text_parts if part).strip()
    if not text:
        raise ValueError("judge returned empty text")
    parsed = json.loads(text)
    if not isinstance(parsed, dict):
        raise ValueError("judge returned non-object JSON")
    return parsed


def gemini_generate_content_url(base_url: str, model: str) -> str:
    root = base_url.rstrip("/")
    if root.endswith("/v1"):
        root = root[:-3]
    return f"{root}/v1beta/models/{model}:generateContent"


def write_reports(results: list[dict[str, Any]], args: argparse.Namespace) -> None:
    args.output_dir.mkdir(parents=True, exist_ok=True)
    json_path = args.output_dir / f"live-eval-{args.run_id}.json"
    md_path = args.output_dir / f"live-eval-{args.run_id}.md"

    report = {
        "run_id": args.run_id,
        "created_at": datetime.now().isoformat(),
        "base_url": args.base_url,
        "memory_group_id": args.memory_group_id
        or args.graphiti_group_id
        or os.getenv("MEMORY_GROUP_ID")
        or os.getenv("GRAPHITI_GROUP_ID"),
        "summary": summarize(results),
        "results": results,
    }
    json_path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    md_path.write_text(render_markdown(report), encoding="utf-8")
    print(f"wrote {json_path}", flush=True)
    print(f"wrote {md_path}", flush=True)


def summarize(results: list[dict[str, Any]]) -> dict[str, Any]:
    total = len(results)
    passed = sum(1 for result in results if case_passed(result))
    critical = [result for result in results if result["case"]["critical"]]
    critical_passed = sum(1 for result in critical if case_passed(result))
    hallucinated = sum(
        1
        for result in results
        if (result.get("judge") or {}).get("hallucinated_memory") is True
    )

    by_category: dict[str, dict[str, int]] = defaultdict(lambda: {"total": 0, "passed": 0})
    for result in results:
        category = result["case"]["category"]
        by_category[category]["total"] += 1
        if case_passed(result):
            by_category[category]["passed"] += 1

    return {
        "total": total,
        "passed": passed,
        "pass_rate": rate(passed, total),
        "critical_total": len(critical),
        "critical_passed": critical_passed,
        "critical_pass_rate": rate(critical_passed, len(critical)),
        "hallucinated_memory_count": hallucinated,
        "demo_ready": rate(passed, total) >= 0.85
        and rate(critical_passed, len(critical)) >= 0.95
        and hallucinated == 0,
        "by_category": dict(sorted(by_category.items())),
    }


def case_passed(result: dict[str, Any]) -> bool:
    judge = result.get("judge")
    if judge is None:
        return False
    return judge.get("passed") is True


def rate(numerator: int, denominator: int) -> float:
    if denominator == 0:
        return 0.0
    return round(numerator / denominator, 4)


def render_markdown(report: dict[str, Any]) -> str:
    summary = report["summary"]
    lines = [
        f"# Live Eval {report['run_id']}",
        "",
        f"- Created: {report['created_at']}",
        f"- Base URL: `{report['base_url']}`",
        f"- MEMORY_GROUP_ID: `{report.get('memory_group_id')}`",
        f"- Demo ready: **{summary['demo_ready']}**",
        f"- Pass rate: {summary['passed']}/{summary['total']} ({summary['pass_rate']:.0%})",
        (
            "- Critical pass rate: "
            f"{summary['critical_passed']}/{summary['critical_total']} "
            f"({summary['critical_pass_rate']:.0%})"
        ),
        f"- Hallucinated memory cases: {summary['hallucinated_memory_count']}",
        "",
        "## Category Results",
        "",
        "| Category | Passed | Total | Rate |",
        "| --- | ---: | ---: | ---: |",
    ]
    for category, stats in summary["by_category"].items():
        category_rate = rate(stats["passed"], stats["total"])
        lines.append(
            f"| {category} | {stats['passed']} | {stats['total']} | {category_rate:.0%} |"
        )

    failed = [result for result in report["results"] if not case_passed(result)]
    lines.extend(["", "## Failed Cases", ""])
    if not failed:
        lines.append("No failed cases.")
    for result in failed:
        case = result["case"]
        judge = result.get("judge") or {}
        probe = result["probe_response"]
        lines.extend(
            [
                f"### {case['id']} ({case['category']})",
                "",
                f"- Critical: `{case['critical']}`",
                f"- Probe: {case['probe_message']}",
                f"- Expected memory: {', '.join(case['expected_memory']) or '(none)'}",
                f"- Forbidden memory: {', '.join(case['forbidden_memory']) or '(none)'}",
                f"- Judge reason: {judge.get('reason', '(no judge result)')}",
                f"- Reply: {probe.get('reply', '')}",
                "- Retrieved facts:",
            ]
        )
        retrieved = probe.get("retrieved_facts") or []
        if retrieved:
            for fact in retrieved:
                lines.append(f"  - {fact.get('fact', fact)}")
        else:
            lines.append("  - (none)")
        lines.append("")

    lines.extend(["", "## All Cases", ""])
    for result in report["results"]:
        case = result["case"]
        judge = result.get("judge") or {}
        status = "PASS" if judge.get("passed") else "FAIL"
        score = judge.get("score", "?")
        lines.append(f"- **{status}** `{case['id']}` score={score}: {judge.get('reason', '')}")

    return "\n".join(lines) + "\n"


if __name__ == "__main__":
    raise SystemExit(main())
