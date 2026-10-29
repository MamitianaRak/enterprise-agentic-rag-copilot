"""Code evaluators for the agent's final state. Deterministic and free: no LLM judge, so a score
can be trusted and re-run. Each check returns None when the case does not ask for it."""
import re
from pathlib import Path

# Words that, just before a forbidden phrase, turn it into a warning ("do not disable the firewall").
NEGATIONS = ("not", "never", "don't", "dont", "avoid", "no", "without")
NEGATION_WINDOW = 4  # words looked at before the phrase


def normalize(text: str) -> str:
    text = text.lower().replace("’", "'").replace(" ", " ").replace(" ", " ")
    text = re.sub(r"[‐-―]", "-", text)  # typographic hyphens and dashes ("backward‑compatible")
    text = re.sub(r"[*_`]", "", text)  # Markdown emphasis would split "**SEV1**"
    text = re.sub(r"\b(sev|p) (\d)\b", r"\1\2", text)  # "SEV 1" and "P 1" are the same level as "SEV1", "P1"
    return re.sub(r"\s+", " ", text).strip()


def found(answer: str, phrases: list[str]) -> bool:
    text = normalize(answer)
    return any(normalize(p) in text for p in phrases)


def unnegated(answer: str, phrase: str) -> bool:
    """True when `phrase` appears at least once without a negation in the few words before it."""
    text, target = normalize(answer), normalize(phrase)
    for match in re.finditer(re.escape(target), text):
        before = re.findall(r"[a-z']+", text[:match.start()])[-NEGATION_WINDOW:]
        if not any(word in NEGATIONS or word.endswith("n't") for word in before):
            return True
    return False


def cited_documents(state: dict) -> set[str]:
    return {Path(c.get("title", "")).name for c in state.get("citations", []) if c.get("type") == "private_kb"}


def score(case: dict, state: dict) -> dict:
    """One case → its checks (True/False, or None when not asked) and fact recall."""
    expect, answer = case["expect"], state.get("answer", "") or ""
    result: dict = {}

    sources = expect.get("sources")
    result["source_ok"] = None if not sources else state.get("source_used") in sources

    documents = expect.get("documents")
    result["retrieval_hit"] = None if not documents else bool(set(documents) & cited_documents(state))

    facts = expect.get("facts") or []
    matched = [group for group in facts if found(answer, group)]
    result["fact_recall"] = None if not facts else len(matched) / len(facts)
    result["missing_facts"] = [group[0] for group in facts if group not in matched]

    forbidden = expect.get("forbidden") or []
    violations = [phrase for phrase in forbidden if unnegated(answer, phrase)]
    result["guardrail_ok"] = None if not forbidden else not violations
    result["violations"] = violations

    severities = expect.get("severity")
    actual = (state.get("triage") or {}).get("severity")
    result["severity_ok"] = None if not severities else actual in severities
    result["severity"] = actual

    checks = [result[k] for k in ("source_ok", "retrieval_hit", "guardrail_ok", "severity_ok") if result[k] is not None]
    result["passed"] = all(checks) and (result["fact_recall"] in (None, 1.0))
    return result


def summarize(rows: list[dict]) -> dict:
    """Mean of each check over the cases that ask for it, plus the overall pass rate."""
    def mean(key):
        values = [r["score"][key] for r in rows if r["score"].get(key) is not None]
        return (round(sum(values) / len(values), 3), len(values)) if values else (None, 0)

    summary = {key: mean(key) for key in ("source_ok", "retrieval_hit", "fact_recall", "guardrail_ok", "severity_ok")}
    summary["passed"] = (round(sum(r["score"]["passed"] for r in rows) / len(rows), 3), len(rows)) if rows else (None, 0)
    return summary
