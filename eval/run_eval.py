#!/usr/bin/env python3
"""
NexusBase eval harness (standard library only).

For each question in eval/questions.json, call the running API's POST /v1/query,
record the retrieved source filenames and the answer, then compute:

  1. Retrieval hit rate : fraction of questions whose expected_source appears
                          among the retrieved chunk sources.
  2. Keyword pass rate  : fraction of questions whose answer contains every
                          required keyword (case-insensitive substring match).

A question that errors (HTTP error, timeout) counts as a miss on both metrics.

Writes eval/results.json (per-question detail) and eval/results.md (table + totals).

Usage (with the stack running and the corpus ingested):
    python3 eval/run_eval.py

Options: --api URL, --delay SECONDS, --access-level LEVEL, --timeout SECONDS.
Credentials for the eval user come from EVAL_EMAIL / EVAL_PASSWORD
(defaults: eval@example.com / evalpass123). The user is registered if missing.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
QUESTIONS_PATH = HERE / "questions.json"
RESULTS_JSON = HERE / "results.json"
RESULTS_MD = HERE / "results.md"


def _request(method: str, url: str, *, data: bytes | None = None,
             headers: dict | None = None, timeout: float = 60.0) -> tuple[int, dict | str]:
    """Send an HTTP request; return (status, parsed JSON body or raw text)."""
    req = urllib.request.Request(url, data=data, method=method, headers=headers or {})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            status, raw = resp.status, resp.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        status, raw = e.code, e.read().decode("utf-8", "replace")
    try:
        return status, json.loads(raw)
    except json.JSONDecodeError:
        return status, raw


def get_token(api: str, email: str, password: str, timeout: float) -> str:
    """Register the eval user (ignored if it exists) and log in for a bearer token."""
    _request(
        "POST", f"{api}/v1/auth/register",
        data=json.dumps({"email": email, "password": password}).encode(),
        headers={"Content-Type": "application/json"}, timeout=timeout,
    )
    status, body = _request(
        "POST", f"{api}/v1/auth/login",
        data=urllib.parse.urlencode({"username": email, "password": password}).encode(),
        headers={"Content-Type": "application/x-www-form-urlencoded"}, timeout=timeout,
    )
    if status != 200 or not isinstance(body, dict) or "access_token" not in body:
        raise SystemExit(f"Login failed (HTTP {status}): {body}")
    return body["access_token"]


def run_question(api: str, token: str, q: dict, access_level: str, timeout: float) -> dict:
    """Ask one question and score it."""
    started = time.perf_counter()
    try:
        status, body = _request(
            "POST", f"{api}/v1/query",
            data=json.dumps({"query": q["question"], "access_level": access_level}).encode(),
            headers={"Content-Type": "application/json", "Authorization": f"Bearer {token}"},
            timeout=timeout,
        )
    except Exception as e:  # network error, timeout
        status, body = None, f"{type(e).__name__}: {e}"
    latency_ms = int((time.perf_counter() - started) * 1000)

    ok = status == 200 and isinstance(body, dict)
    answer = body.get("answer", "") if ok else ""
    sources: list[str] = []
    if ok:
        for chunk in body.get("chunks", []):
            src = chunk.get("source")
            if src and src not in sources:
                sources.append(src)

    answer_lc = answer.lower()
    missing = [k for k in q["required_keywords"] if k.lower() not in answer_lc]

    return {
        "id": q["id"],
        "question": q["question"],
        "expected_source": q["expected_source"],
        "required_keywords": q["required_keywords"],
        "retrieved_sources": sources,
        "answer": answer,
        "retrieval_hit": q["expected_source"] in sources,
        "keyword_pass": ok and not missing,
        "missing_keywords": missing,
        "graph_path": body.get("graph_path", []) if ok else [],
        "http_status": status,
        "error": None if ok else (body if isinstance(body, str) else json.dumps(body)),
        "latency_ms": latency_ms,
    }


def _cell(text: str) -> str:
    return text.replace("|", "\\|").replace("\n", " ")


def write_markdown(summary: dict, results: list[dict]) -> None:
    lines = [
        "# NexusBase eval results",
        "",
        f"- Run at: {summary['run_at']}",
        f"- API: `{summary['api']}` · access_level: `{summary['access_level']}`",
        f"- Questions file status: **{summary['questions_status']}**",
        f"- **Retrieval hit rate: {summary['retrieval_hits']}/{summary['total']} "
        f"= {summary['retrieval_hit_rate']:.2f}**",
        f"- **Keyword pass rate: {summary['keyword_passes']}/{summary['total']} "
        f"= {summary['keyword_pass_rate']:.2f}**",
        f"- Errors: {summary['errors']}",
        "",
        "Retrieved sources are the `chunks[].source` values returned by `/v1/query`. "
        "NexusBase returns only the chunks its grader judged relevant, so a miss can come "
        "from either search or grading.",
        "",
        "| id | expected_source | hit | keywords | missing keywords | retrieved sources | status |",
        "|---|---|---|---|---|---|---|",
    ]
    for r in results:
        lines.append(
            "| {id} | {exp} | {hit} | {kw} | {miss} | {src} | {st} |".format(
                id=r["id"],
                exp=r["expected_source"],
                hit="✅" if r["retrieval_hit"] else "❌",
                kw="✅" if r["keyword_pass"] else "❌",
                miss=_cell(", ".join(r["missing_keywords"])) or "-",
                src=_cell(", ".join(r["retrieved_sources"])) or "(none)",
                st=r["http_status"] if r["error"] is None else f"error {r['http_status']}",
            )
        )
    RESULTS_MD.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the NexusBase eval against a running API.")
    parser.add_argument("--api", default=os.environ.get("EVAL_API", "http://localhost:8000"))
    parser.add_argument("--access-level", default="public")
    parser.add_argument("--delay", type=float, default=5.0,
                        help="Seconds to wait between questions (free-tier rate limits).")
    parser.add_argument("--timeout", type=float, default=180.0)
    args = parser.parse_args()
    api = args.api.rstrip("/")

    spec = json.loads(QUESTIONS_PATH.read_text(encoding="utf-8"))
    questions = spec["questions"]

    token = get_token(
        api,
        os.environ.get("EVAL_EMAIL", "eval@example.com"),
        os.environ.get("EVAL_PASSWORD", "evalpass123"),
        args.timeout,
    )

    results = []
    for i, q in enumerate(questions, start=1):
        r = run_question(api, token, q, args.access_level, args.timeout)
        results.append(r)
        print(f"[{i:02d}/{len(questions)}] {q['id']} hit={r['retrieval_hit']} "
              f"keywords={r['keyword_pass']} status={r['http_status']} ({r['latency_ms']} ms)")
        if i < len(questions) and args.delay > 0:
            time.sleep(args.delay)

    total = len(results)
    hits = sum(r["retrieval_hit"] for r in results)
    passes = sum(r["keyword_pass"] for r in results)
    summary = {
        "run_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "api": api,
        "access_level": args.access_level,
        "questions_status": spec.get("status", "unknown"),
        "total": total,
        "retrieval_hits": hits,
        "retrieval_hit_rate": hits / total if total else 0.0,
        "keyword_passes": passes,
        "keyword_pass_rate": passes / total if total else 0.0,
        "errors": sum(r["error"] is not None for r in results),
    }

    RESULTS_JSON.write_text(
        json.dumps({"summary": summary, "results": results}, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    write_markdown(summary, results)

    print(f"\nRetrieval hit rate: {hits}/{total} = {summary['retrieval_hit_rate']:.2f}")
    print(f"Keyword pass rate:  {passes}/{total} = {summary['keyword_pass_rate']:.2f}")
    print(f"Wrote {RESULTS_JSON.relative_to(HERE.parent)} and {RESULTS_MD.relative_to(HERE.parent)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
