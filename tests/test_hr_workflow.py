import sqlite3
import pytest
from langchain_core.exceptions import OutputParserException
from langchain_core.messages import AIMessage
from app.rag.common.nodes import excerpt
from langgraph.checkpoint.sqlite import SqliteSaver
from app.core.llm import text_of
from app.rag.common.memory import thread_config
from app.rag.common.state import initial_state
from app.rag.hr.graph import build_graph


FULL = {"status": "fully_supported", "evidence": ["20 annual leave days"]}
PARTIAL = {"status": "partially_supported", "evidence": []}
NO_SUPPORT = {"status": "no_support", "evidence": []}
USEFUL = {"status": "useful", "reason": "answers it"}
NOT_USEFUL = {"status": "not_useful", "reason": "off topic"}


def run(question):
    return build_graph().invoke(initial_state(question))


def test_greeting_goes_direct_without_calling_the_router(patch_rag):
    patch_rag([], text="Hello!")
    result = run("Hi there")
    assert result["source_used"] == "direct"
    assert result["answer"] == "Hello!"
    assert result["trace"] == [
        "Memory → new conversation",
        "Router → DIRECT (small talk, no LLM call)",
        "Direct response → no retrieval",
        "Memory → conversation saved",
    ]


def test_casual_chat_is_routed_direct_by_the_llm(patch_rag):
    patch_rag([{"route": "direct"}], text="Doing well, thanks!")
    result = run("How are you doing today?")
    assert result["source_used"] == "direct"
    assert result["trace"][1] == "Router → DIRECT"


def test_good_kb_evidence_answers_from_private_kb(patch_rag):
    fake = patch_rag([{"route": "kb"}, {"grade": "good"}, FULL, USEFUL], text="20 days.")
    result = run("How many annual leave days do employees receive?")
    assert result["source_used"] == "private_kb"
    assert result["answer"] == "20 days."
    assert result["support_status"] == "fully_supported"
    assert result["usefulness"] == "useful"
    # Citations deduplicated by (file, page), including Linux-style source paths; PDF pages are 1-based.
    assert result["citations"] == [
        {"title": "company_hr_handbook.md", "page": None, "excerpt": "Employees receive 20 annual leave days.",
         "url": "", "type": "private_kb"},
        {"title": "policy.pdf", "page": 3, "excerpt": "Sick leave: 10 days per year, with a medical certificate after 3 days.",
         "url": "", "type": "private_kb"},
    ]
    # The support check receives the answer and the KB evidence, with page numbers.
    support_prompt = fake.prompts[-2]
    assert "20 days." in support_prompt and "[Source: company_hr_handbook.md]" in support_prompt
    assert "[Source: policy.pdf | page 3]" in support_prompt
    assert result["trace"][-3:] == ["Support check → FULLY_SUPPORTED", "Usefulness check → USEFUL", "Memory → conversation saved"]


def test_weak_kb_falls_back_to_web(patch_rag):
    patch_rag([{"route": "kb"}, {"grade": "weak"}, {"grade": "good"}, FULL, USEFUL], text="Public holidays...")
    result = run("What are the latest public holiday rules in France?")
    assert result["source_used"] == "web_search"
    assert result["citations"][0]["url"] == "https://example.gov"
    assert "Web fallback → Tavily search" in result["trace"]


def test_partially_supported_answer_is_revised(patch_rag):
    patch_rag([{"route": "kb"}, {"grade": "good"}, PARTIAL, FULL, USEFUL], text="20 days.")
    result = run("How many annual leave days?")
    assert result["source_used"] == "private_kb"
    assert result["support_retries"] == 1
    assert "Revised answer for grounding" in result["trace"]
    assert result["support_status"] == "fully_supported"


def test_partially_supported_after_revision_is_still_shown(patch_rag):
    patch_rag([{"route": "kb"}, {"grade": "good"}, PARTIAL, PARTIAL, USEFUL], text="20 days.")
    result = run("How many annual leave days?")
    assert result["source_used"] == "private_kb"
    assert result["support_status"] == "partially_supported"


def test_unsupported_answer_is_never_shown(patch_rag):
    patch_rag([{"route": "kb"}, {"grade": "good"}, NO_SUPPORT, NO_SUPPORT], text="Invented policy.")
    result = run("How many annual leave days?")
    assert result["source_used"] == "insufficient_evidence"
    assert result["answer"] != "Invented policy."
    assert result["citations"] == []


def test_useless_answer_triggers_query_rewrite(patch_rag):
    patch_rag(
        [{"route": "kb"}, {"grade": "good"}, FULL, NOT_USEFUL,   # first attempt
         {"query": "annual leave days policy"},                  # rewrite (fast lane, JSON)
         {"grade": "good"}, FULL, USEFUL],                       # after rewrite
        text="20 days.",
    )
    result = run("How many annual leave days?")
    assert result["source_used"] == "private_kb"
    assert result["retry_count"] == 1
    assert result["trace"].count("Usefulness check → NOT_USEFUL") == 1
    assert result["usefulness"] == "useful"


def test_weak_everywhere_rewrites_once_then_stops(patch_rag):
    patch_rag(
        [{"route": "kb"}, {"grade": "weak"}, {"grade": "weak"}, {"query": "rewritten query"},
         {"grade": "weak"}, {"grade": "weak"}],
    )
    result = run("What happens if mine is wrong?")
    assert result["source_used"] == "insufficient_evidence"
    assert result["retry_count"] == 1
    assert result["current_query"] == "rewritten query"
    assert result["trace"][-2] == "Stopped → insufficient reliable evidence"


def test_follow_up_question_uses_memory(patch_rag, tmp_path):
    con = sqlite3.connect(str(tmp_path / "memory.db"), check_same_thread=False)
    graph = build_graph(SqliteSaver(con))
    config = thread_config("hr", "thread-1")

    patch_rag([{"route": "kb"}, {"grade": "good"}, FULL, USEFUL], text="20 annual leave days.")
    graph.invoke(initial_state("How many annual leave days do I get?"), config=config)

    fake = patch_rag(
        [{"query": "How many sick leave days do employees get?"}, {"route": "kb"}, {"grade": "good"}, FULL, USEFUL],
        text="10 sick days.",
    )
    second = graph.invoke(initial_state("And for sick leave?"), config=config)

    # The contextualizer saw the previous turn and produced a standalone question.
    assert "User: How many annual leave days do I get?" in fake.prompts[0]
    assert second["question"] == "How many sick leave days do employees get?"
    assert second["user_question"] == "And for sick leave?"
    assert "Memory → standalone question: How many sick leave days do employees get?" in second["trace"]
    # Per-turn fields were reset, history accumulated.
    assert [t["question"] for t in second["memory"]] == ["How many annual leave days do I get?", "And for sick leave?"]
    assert second["memory"][1]["answer"] == "10 sick days."
    assert second["memory"][1]["citations"][0]["title"] == "company_hr_handbook.md"  # sources restored with history

    # Another thread starts fresh.
    patch_rag([{"route": "direct"}], text="Hi")
    other = graph.invoke(initial_state("Hello"), config=thread_config("hr", "thread-2"))
    assert len(other["memory"]) == 1
    con.close()


def test_malformed_router_output_falls_back_to_kb(patch_rag):
    patch_rag([OutputParserException("not json"), {"grade": "good"}, FULL, USEFUL], text="20 days.")
    result = run("How many annual leave days?")
    assert result["source_used"] == "private_kb"
    assert "Router → KB (fallback)" in result["trace"]


def test_malformed_support_verdict_never_shows_answer(patch_rag):
    patch_rag([{"route": "kb"}, {"grade": "good"}, OutputParserException("x"), OutputParserException("x")], text="20 days.")
    result = run("How many annual leave days?")
    assert result["source_used"] == "insufficient_evidence"


def test_api_errors_are_not_swallowed(patch_rag):
    patch_rag([RuntimeError("429 RESOURCE_EXHAUSTED")])
    with pytest.raises(RuntimeError):
        run("How many annual leave days?")


def test_long_excerpts_are_cut_on_a_word():
    text = "word " * 100
    cut = excerpt(text, 30)
    assert cut.endswith("…") and len(cut) <= 31 and not cut[:-1].endswith(" ")


def test_text_of_handles_strings_and_blocks():
    assert text_of(AIMessage(content="  plain  ")) == "plain"
    assert text_of(AIMessage(content=[{"type": "text", "text": "a"}, "b"])) == "ab"
