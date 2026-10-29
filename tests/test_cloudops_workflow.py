from langchain_core.exceptions import OutputParserException
from app.rag.cloudops.graph import build_graph
from app.rag.common.memory import thread_config
from app.rag.common.state import initial_state

FULL = {"status": "fully_supported", "evidence": ["roll back"]}
USEFUL = {"status": "useful", "reason": "actionable"}
NOT_USEFUL = {"status": "not_useful", "reason": "vague"}
TRIAGE_KB = {"route": "kb", "severity": "SEV2", "service": "checkout-api", "category": "deployment"}


def run(question):
    return build_graph().invoke(initial_state(question, ["all"]), config={"recursion_limit": 50})


def test_greeting_goes_direct(patch_rag):
    patch_rag([{"route": "direct", "severity": "none"}], text="Hi! How can I help?")
    result = run("Hello")
    assert result["source_used"] == "direct"
    assert result["triage"] == {"severity": "none", "service": "", "category": ""}
    assert result["trace"][1] == "Triage → DIRECT"


def test_runbook_answer_cites_only_relevant_documents(patch_rag):
    fake = patch_rag([TRIAGE_KB, {"relevant": [1, 3]}, FULL, USEFUL], text="1. Compare the deployment time.")
    result = run("Checkout API returns 502 after deployment")

    assert result["source_used"] == "private_kb"
    assert result["triage"] == {"severity": "SEV2", "service": "checkout-api", "category": "deployment"}
    assert "Triage → KB · SEV2 · checkout-api" in result["trace"]
    assert "Relevance grade (internal) → 2/3 relevant" in result["trace"]
    # The irrelevant chunk (document 2) is neither used nor cited.
    assert [(c["title"], c["page"]) for c in result["citations"]] == [("company_hr_handbook.md", None), ("policy.pdf", 3)]
    grading_prompt = fake.prompts[1]
    assert "[1] company_hr_handbook.md" in grading_prompt and "[3] policy.pdf" in grading_prompt
    assert "Leave requests go through the HR portal." not in fake.prompts[2]  # generation prompt


def test_no_relevant_chunk_rewrites_internal_query_first(patch_rag):
    patch_rag([TRIAGE_KB, {"relevant": []}, {"query": "checkout-api 502 readiness probe"}, {"relevant": [1]}, FULL, USEFUL])
    result = run("checkout broken")
    assert result["source_used"] == "private_kb"
    assert result["retrieval_rewrites"] == 1
    assert result["current_query"] == "checkout-api 502 readiness probe"
    assert "Internal query rewrite → checkout-api 502 readiness probe" in result["trace"]


def test_falls_back_to_web_after_internal_rewrite(patch_rag):
    fake = patch_rag([
        TRIAGE_KB,
        {"relevant": []}, {"query": "internal retry"},   # private KB, then one rewrite
        {"relevant": []}, {"query": "kubernetes crashloopbackoff troubleshooting"},
        {"relevant": [1]}, FULL, USEFUL,                  # web results
    ], text="External guidance: check the container logs.")
    result = run("Pod keeps restarting with CrashLoopBackOff")

    assert result["source_used"] == "web_search"
    assert result["web_query"] == "kubernetes crashloopbackoff troubleshooting"
    assert "Web search → 1 results" in result["trace"]
    assert "Relevance grade (web) → 1/1 relevant" in result["trace"]
    assert result["citations"] == [
        {"title": "Gov page", "page": None, "excerpt": "Public info", "url": "https://example.gov", "type": "web"}
    ]
    assert "[Web: Gov page | https://example.gov]" in fake.prompts[-3]  # generation prompt


def test_stops_when_neither_runbooks_nor_web_help(patch_rag):
    patch_rag([TRIAGE_KB, {"relevant": []}, {"query": "q1"}, {"relevant": []}, {"query": "q2"}, {"relevant": []}])
    result = run("Something nobody documented")
    assert result["source_used"] == "insufficient_evidence"
    assert result["citations"] == []
    assert "Escalate to the on-call platform team" in result["answer"]


def test_useless_runbook_answer_retries_with_rewritten_query(patch_rag):
    patch_rag([
        TRIAGE_KB, {"relevant": [1]}, FULL, NOT_USEFUL,
        {"query": "payments high cpu response procedure"}, {"relevant": [1]}, FULL, USEFUL,
    ])
    result = run("payments cpu")
    assert result["retrieval_rewrites"] == 1
    assert result["usefulness"] == "useful"


def test_malformed_relevance_verdict_keeps_all_documents(patch_rag):
    patch_rag([TRIAGE_KB, OutputParserException("not json"), FULL, USEFUL])
    result = run("checkout 502")
    assert "Relevance grade (internal) → 3/3 relevant (fallback)" in result["trace"]


def test_relevance_numbers_are_deduplicated_and_bounded(patch_rag):
    patch_rag([TRIAGE_KB, {"relevant": [2, 2, 9, 0]}, FULL, USEFUL])
    result = run("checkout 502")
    assert "Relevance grade (internal) → 1/3 relevant" in result["trace"]


def test_follow_up_keeps_incident_context(patch_rag, tmp_path):
    import sqlite3
    from langgraph.checkpoint.sqlite import SqliteSaver

    graph = build_graph(SqliteSaver(sqlite3.connect(str(tmp_path / "m.db"), check_same_thread=False)))
    config = thread_config("cloudops", "incident-1")
    patch_rag([TRIAGE_KB, {"relevant": [1]}, FULL, USEFUL], text="Check readiness probes first.")
    graph.invoke(initial_state("checkout-api 502 after deploy", ["all"]), config=config)

    fake = patch_rag([{"query": "What to check next if checkout-api 502 persists after readiness checks?"},
                      TRIAGE_KB, {"relevant": [1]}, FULL, USEFUL])
    second = graph.invoke(initial_state("What should I check next?", ["all"]), config=config)
    assert "User: checkout-api 502 after deploy" in fake.prompts[0]
    assert second["question"].startswith("What to check next if checkout-api 502")
    assert len(second["memory"]) == 2
