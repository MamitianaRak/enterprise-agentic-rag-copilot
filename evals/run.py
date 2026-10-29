"""Runs the evaluation set against the real agent (LLM gateway, Pinecone, Tavily) and scores it.

    python -m evals.run                      # every case
    python -m evals.run --domain it          # one domain
    python -m evals.run --case it-mfa-methods
    python -m evals.run --min-pass 0.8       # exit 1 below that pass rate (regression gate)

Each case runs in a fresh conversation, so memory from one question never helps the next.
Results go to evals/results/: a JSON file per run and latest.md, the table shown in the README.
With LANGSMITH_TRACING=true in .env, every run is also traced in LangSmith, tagged with the run id."""
import argparse
import json
import os
import re
import sys
import tempfile
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
load_dotenv(ROOT / ".env")
# The eval must not write into the app's own conversation memory or audit log.
_tmp = tempfile.mkdtemp(prefix="copilot-eval-")
os.environ["MEMORY_DB_PATH"] = os.path.join(_tmp, "memory.db")
os.environ["AUDIT_DB_PATH"] = os.path.join(_tmp, "audit.db")
os.environ.setdefault("LLM_CACHE_TTL_SECONDS", "0")  # every case must reach a model, not the cache

from evals.evaluators import score, summarize  # noqa: E402
from app.rag.registry import DOMAINS, thread_config  # noqa: E402
from app.rag.common.state import initial_state  # noqa: E402

DATASET = Path(__file__).with_name("dataset.json")
RESULTS = Path(__file__).with_name("results")
MODEL_LABEL = re.compile(r"\[([\w.-]+:[^\]]+)\]")
LABELS = {
    "source_ok": "Source chosen (KB, web, direct, refusal)",
    "retrieval_hit": "Expected document cited",
    "fact_recall": "Expected facts in the answer",
    "guardrail_ok": "No forbidden advice",
    "severity_ok": "Priority / severity",
    "passed": "Cases passing every check",
}


def run_case(case: dict, run_id: str) -> dict:
    domain = DOMAINS[case["domain"]]
    config = thread_config(domain.name, f"eval-{run_id}-{case['id']}")
    config["metadata"] = {"eval_run": run_id, "eval_case": case["id"], "domain": case["domain"]}
    config["tags"] = ["eval", run_id]
    started = time.perf_counter()
    try:
        state = domain.graph.invoke(initial_state(case["question"], case.get("groups", ["all"])), config=config)
        error = None
    except Exception as exc:  # a provider outage or quota is recorded, not hidden
        state, error = {}, f"{type(exc).__name__}: {exc}"
    seconds = round(time.perf_counter() - started, 1)
    trace = state.get("trace", [])
    return {
        "id": case["id"], "domain": case["domain"], "kind": case.get("kind"), "question": case["question"],
        "seconds": seconds, "error": error,
        "source_used": state.get("source_used"),
        "documents": sorted({c.get("title") for c in state.get("citations", []) if c.get("type") == "private_kb"}),
        "answer": state.get("answer", ""),
        "llm_steps": sum(1 for line in trace if MODEL_LABEL.search(line)),
        "models": sorted({m for line in trace for m in MODEL_LABEL.findall(line)}),
        "fallbacks": sum("(fallback)" in line for line in trace),
        "trace": trace,
        "score": score(case, state),
    }


def markdown(run: dict) -> str:
    summary, rows = run["summary"], run["rows"]
    lines = [
        f"# Evaluation run {run['run_id']}",
        "",
        f"{run['started']} · {len(rows)} cases · dataset v{run['dataset_version']} · models: {', '.join(run['models']) or 'n/a'}",
        "",
        "| Check | Score | Cases |",
        "|---|---|---|",
    ]
    for key, label in LABELS.items():
        value, count = summary[key]
        shown = "n/a" if value is None else (f"{value:.0%}" if key != "fact_recall" else f"{value:.0%} (mean)")
        lines.append(f"| {label} | {shown} | {count} |")
    seconds = sorted(r["seconds"] for r in rows)
    lines += [
        "",
        f"Latency per question: median {seconds[len(seconds) // 2]} s, max {seconds[-1]} s. "
        f"LLM calls per question: {sum(r['llm_steps'] for r in rows) / len(rows):.1f} on average. "
        f"Malformed structured outputs recovered by a fallback: {sum(r['fallbacks'] for r in rows)}.",
        "",
        "| Case | Source | Severity | Facts | Result | Note |",
        "|---|---|---|---|---|---|",
    ]
    for r in rows:
        s = r["score"]
        note = r["error"] or "; ".join(
            [f"missing: {', '.join(s['missing_facts'])}"] * bool(s["missing_facts"])
            + [f"forbidden: {', '.join(s['violations'])}"] * bool(s["violations"])
            + [f"expected doc not cited ({', '.join(r['documents']) or 'none'})"] * (s["retrieval_hit"] is False)
        )
        facts = "" if s["fact_recall"] is None else f"{s['fact_recall']:.0%}"
        lines.append(
            f"| {r['id']} | {r['source_used'] or 'error'} | {s['severity'] or ''} | {facts} | "
            f"{'pass' if s['passed'] else 'FAIL'} | {note} |"
        )
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--domain", choices=sorted(DOMAINS))
    parser.add_argument("--case", action="append", help="case id, repeatable")
    parser.add_argument("--delay", type=float, default=3.0, help="seconds between cases (free-tier rate limits)")
    parser.add_argument("--min-pass", type=float, help="exit 1 when the pass rate is below this value")
    args = parser.parse_args()

    dataset = json.loads(DATASET.read_text(encoding="utf-8"))
    cases = [c for c in dataset["cases"]
             if (not args.domain or c["domain"] == args.domain) and (not args.case or c["id"] in args.case)]
    if not cases:
        print("No case matches.")
        return 1

    run_id = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S") + "-" + uuid.uuid4().hex[:4]
    rows = []
    for i, case in enumerate(cases, 1):
        row = run_case(case, run_id)
        rows.append(row)
        verdict = "pass" if row["score"]["passed"] else "FAIL"
        print(f"[{i}/{len(cases)}] {verdict:4} {case['id']:28} {row['source_used'] or 'error':22} {row['seconds']:>5} s"
              + (f"  {row['error'][:90]}" if row["error"] else ""), flush=True)
        if i < len(cases):
            time.sleep(args.delay)

    run = {
        "run_id": run_id, "started": run_id[:15], "dataset_version": dataset["version"],
        "models": sorted({m for r in rows for m in r["models"]}),
        "summary": summarize(rows), "rows": rows,
    }
    RESULTS.mkdir(exist_ok=True)
    (RESULTS / f"{run_id}.json").write_text(json.dumps(run, indent=2, ensure_ascii=False), encoding="utf-8")
    report = markdown(run)
    if not args.domain and not args.case:
        (RESULTS / "latest.md").write_text(report, encoding="utf-8")
    print("\n" + report)

    pass_rate = run["summary"]["passed"][0] or 0
    if args.min_pass is not None and pass_rate < args.min_pass:
        print(f"Pass rate {pass_rate:.0%} is below the required {args.min_pass:.0%}.")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
