"""The evaluation's own checks: a wrong evaluator would make every score meaningless."""
import json
from pathlib import Path

from evals.evaluators import found, score, summarize, unnegated

ROOT = Path(__file__).resolve().parents[1]
DATASET = json.loads((ROOT / "evals" / "dataset.json").read_text(encoding="utf-8"))


def test_facts_are_matched_case_insensitively_and_through_markdown():
    assert found("You get **20 Days** of paid leave.", ["20 days"])
    assert not found("You get 25 days of paid leave.", ["20 days"])


def test_a_negated_forbidden_phrase_is_not_a_violation():
    assert not unnegated("Do not disable the firewall to make the VPN work.", "disable the firewall")
    assert not unnegated("You should never, under any circumstances, disable the firewall.", "disable the firewall")
    assert not unnegated("Please don't turn off the firewall.", "turn off the firewall")
    assert unnegated("Restart the client, then disable the firewall if it still fails.", "disable the firewall")


def test_one_unnegated_occurrence_is_enough_to_flag():
    text = "Do not disable the firewall. If nothing works, disable the firewall."
    assert unnegated(text, "disable the firewall")


def test_score_checks_source_document_facts_and_severity():
    case = {"expect": {
        "sources": ["private_kb"], "documents": ["company_it_handbook.md"], "severity": ["P1"],
        "facts": [["asset tag"], ["service desk"]],
    }}
    state = {
        "answer": "Report it to the Service Desk right away.",
        "source_used": "private_kb",
        "citations": [{"title": "company_it_handbook.md", "type": "private_kb"}],
        "triage": {"severity": "P1"},
    }
    result = score(case, state)
    assert result["source_ok"] and result["retrieval_hit"] and result["severity_ok"]
    assert result["fact_recall"] == 0.5 and result["missing_facts"] == ["asset tag"]
    assert result["passed"] is False  # every fact is required


def test_web_citations_do_not_count_as_the_expected_document():
    case = {"expect": {"documents": ["company_it_handbook.md"]}}
    state = {"answer": "", "citations": [{"title": "company_it_handbook.md", "type": "web"}]}
    assert score(case, state)["retrieval_hit"] is False


def test_checks_not_asked_for_are_ignored_by_the_summary():
    rows = [
        {"score": score({"expect": {"sources": ["direct"]}}, {"answer": "Hi!", "source_used": "direct"})},
        {"score": score({"expect": {"sources": ["private_kb"]}}, {"answer": "", "source_used": "web_search"})},
    ]
    summary = summarize(rows)
    assert summary["source_ok"] == (0.5, 2)
    assert summary["retrieval_hit"] == (None, 0)
    assert summary["passed"] == (0.5, 2)


def test_dataset_is_consistent_with_the_knowledge_base():
    ids = [c["id"] for c in DATASET["cases"]]
    assert len(ids) == len(set(ids)), "duplicate case id"
    for case in DATASET["cases"]:
        assert case["domain"] in {"hr", "it", "cloudops"}
        assert case["expect"], f"{case['id']} expects nothing"
        for document in case["expect"].get("documents", []):
            assert (ROOT / "data" / "documents" / case["domain"] / document).exists(), f"{case['id']}: {document}"


def test_generation_is_told_the_triage_severity():
    from app.rag.common.nodes import with_triage
    prompt = with_triage("Checkout fails for everyone. Who do I page?", {"severity": "SEV1", "service": "checkout-api"})
    assert "Triage of this request: SEV1, service checkout-api" in prompt
    assert with_triage("How do I reset my password?", {"severity": "none"}) == "How do I reset my password?"
    assert with_triage("Hello", None) == "Hello"


def test_plain_greetings_skip_the_llm_router_but_questions_do_not():
    from app.rag.common.nodes import is_small_talk
    for text in ("Hi there!", "hello", "Thanks a lot!", "Merci beaucoup", "Good morning.", "ok"):
        assert is_small_talk(text), text
    for text in ("Hi, how many days of leave do I have?", "Thanks, and who do I page for a SEV1?", "hello world outage"):
        assert not is_small_talk(text), text


def test_equivalent_spellings_of_a_level_and_typographic_hyphens_match():
    assert found("Declare the incident as **SEV 1**.", ["sev1"])
    assert found("Open a P 2 ticket.", ["p2"])
    assert found("Check that migrations are backward‑compatible.", ["backward-compatible"])
    assert not found("This is a SEV 12 drill.", ["sev1"])
