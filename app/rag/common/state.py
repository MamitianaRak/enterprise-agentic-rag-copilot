import operator
from typing import Annotated, List, Literal
from typing_extensions import TypedDict
from pydantic import BaseModel, Field
from langchain_core.documents import Document


class RouteDecision(BaseModel):
    route: Literal["kb", "direct"] = Field(description="kb for domain questions; direct for greetings/simple chat")


class EvidenceGrade(BaseModel):
    grade: Literal["good", "weak"] = Field(description="Whether evidence is sufficient to answer")


class QueryRewrite(BaseModel):
    query: str = Field(description="Standalone question or search query")


class SupportDecision(BaseModel):
    status: Literal["fully_supported", "partially_supported", "no_support"]
    evidence: List[str] = Field(default_factory=list, description="Short supporting excerpts")


class UsefulnessDecision(BaseModel):
    status: Literal["useful", "not_useful"]
    reason: str = ""


class RelevantDocuments(BaseModel):
    relevant: List[int] = Field(default_factory=list, description="1-based numbers of the relevant documents")


class Triage(BaseModel):
    """Routing decision plus a first assessment, produced in a single call.
    severity: incident severity SEV1-SEV4 (CloudOps) or ticket priority P1-P4 (IT Support)."""
    route: Literal["kb", "direct"]
    severity: Literal["SEV1", "SEV2", "SEV3", "SEV4", "P1", "P2", "P3", "P4", "none"] = "none"
    service: str = ""
    category: str = ""


class MemoryTurn(TypedDict):
    question: str
    answer: str
    source_used: str
    citations: List[dict]


class AgentState(TypedDict):
    user_question: str  # raw message as typed by the user
    question: str       # standalone version, after contextualization
    current_query: str
    access_groups: List[str]  # document groups of the asking user; retrieval filters on them
    kb_docs: List[Document]
    web_results: str
    kb_grade: str
    web_grade: str
    answer: str
    source_used: str
    retry_count: int
    trace: List[str]
    citations: List[dict]
    # Self-check of the generated answer
    context: str
    support_status: str
    support_evidence: List[str]
    support_retries: int
    usefulness: str
    use_reason: str
    # Graded-retrieval workflows (CloudOps): per-document relevance, separate rewrite budgets
    candidate_docs: List[Document]  # retrieved chunks or web results awaiting relevance grading
    relevant_docs: List[Document]
    source_mode: str  # "internal" or "web" while gathering evidence
    web_query: str
    retrieval_rewrites: int
    web_rewrites: int
    triage: dict | None
    # Accumulates across turns of the same thread (persisted by the checkpointer).
    memory: Annotated[List[MemoryTurn], operator.add]


def initial_state(question: str, access_groups: List[str]) -> AgentState:
    """Per-turn fields are reset; memory=[] adds nothing, so history is kept. The user's groups
    are set on every turn, never inherited from an earlier turn of the thread."""
    return {
        "user_question": question,
        "question": question,
        "current_query": question,
        "access_groups": list(access_groups),
        "kb_docs": [],
        "web_results": "",
        "kb_grade": "",
        "web_grade": "",
        "answer": "",
        "source_used": "",
        "retry_count": 0,
        "trace": [],
        "citations": [],
        "context": "",
        "support_status": "",
        "support_evidence": [],
        "support_retries": 0,
        "usefulness": "",
        "use_reason": "",
        "candidate_docs": [],
        "relevant_docs": [],
        "source_mode": "internal",
        "web_query": "",
        "retrieval_rewrites": 0,
        "web_rewrites": 0,
        "triage": None,
        "memory": [],
    }
