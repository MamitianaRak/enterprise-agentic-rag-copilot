"""IT Support domain. The graph topology is shared with CloudOps (tested in test_cloudops_workflow.py);
these tests cover what is specific to IT: ticket priority, security rules and messages."""
from app.rag.common.state import Triage, initial_state
from app.rag.it import prompts
from app.rag.it.graph import build_graph

FULL = {"status": "fully_supported", "evidence": ["Install the NovaSecure VPN client"]}
USEFUL = {"status": "useful", "reason": "actionable"}


def run(question):
    return build_graph().invoke(initial_state(question, ["all"]), config={"recursion_limit": 50})


def test_ticket_priority_is_returned_as_triage(patch_rag):
    patch_rag([{"route": "kb", "severity": "P3", "service": "VPN", "category": "network"},
               {"relevant": [1]}, FULL, USEFUL], text="1. Restart the VPN client.")
    result = run("The VPN keeps disconnecting")
    assert result["source_used"] == "private_kb"
    assert result["triage"] == {"severity": "P3", "service": "VPN", "category": "network"}
    assert "Triage → KB · P3 · VPN" in result["trace"]


def test_security_rules_are_in_every_answer_prompt(patch_rag):
    fake = patch_rag([{"route": "kb", "severity": "P1", "service": "Outlook", "category": "security"},
                      {"relevant": [1]}, FULL, USEFUL])
    run("I clicked a phishing link")
    generation_prompt = fake.prompts[2]
    assert "Never ask for, accept or repeat passwords, MFA codes" in generation_prompt
    assert "Never suggest disabling antivirus" in generation_prompt
    for template in (prompts.GENERATE, prompts.REVISE, prompts.DIRECT):
        assert prompts.SECURITY_RULES in template


def test_direct_replies_also_follow_security_rules(patch_rag):
    fake = patch_rag([{"route": "direct", "severity": "none"}], text="Hello!")
    result = run("Hi, can I give you my password so you fix it?")
    assert result["source_used"] == "direct"
    assert "Never ask for, accept or repeat passwords" in fake.prompts[-1]


def test_insufficient_answer_points_to_the_service_desk_without_credentials(patch_rag):
    patch_rag([{"route": "kb", "severity": "P3", "service": "", "category": "other"},
               {"relevant": []}, {"query": "q1"}, {"relevant": []}, {"query": "q2"}, {"relevant": []}])
    result = run("Some undocumented device issue")
    assert result["source_used"] == "insufficient_evidence"
    assert "IT Service Desk" in result["answer"]
    assert "Never include your password" in result["answer"]


def test_triage_accepts_both_priority_scales():
    assert Triage(route="kb", severity="P1").severity == "P1"
    assert Triage(route="kb", severity="SEV2").severity == "SEV2"
