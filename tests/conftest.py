import os
import tempfile
from collections import deque

# Must be set before any app module reads the settings.
_tmp = tempfile.mkdtemp()
os.environ["AUDIT_DB_PATH"] = os.path.join(_tmp, "audit_test.db")
os.environ["MEMORY_DB_PATH"] = os.path.join(_tmp, "memory_test.db")
os.environ["MAX_RETRIES"] = "1"

import json
import pytest
from langchain_core.documents import Document
from langchain_core.exceptions import OutputParserException
from langchain_core.messages import AIMessage
from app.rag.common import nodes


class FakeLane:
    def __init__(self, parent, json_mode):
        self.parent, self.json_mode = parent, json_mode

    def invoke(self, prompt):
        self.parent.prompts.append(prompt)
        if not self.json_mode:
            # Answer lane: list-of-blocks content, as some chat models return.
            return AIMessage(content=[{"type": "text", "text": self.parent.text}])
        value = self.parent.structured.popleft()
        if isinstance(value, OutputParserException):
            return AIMessage(content="Sorry, I cannot answer in JSON.")  # malformed reply
        if isinstance(value, Exception):
            raise value  # provider failure (quota, timeout...)
        return AIMessage(content=f"```json\n{json.dumps(value)}\n```")


class FakeLLM:
    """Stands in for the LLM gateway. The fast lane returns the queued JSON objects in order
    (an OutputParserException item yields a malformed reply, any other exception is raised);
    the answer lane returns `text`. Prompts of both lanes are recorded in call order."""

    def __init__(self, structured=(), text="fake answer"):
        self.structured = deque(structured)
        self.text = text
        self.prompts = []
        self.fast = FakeLane(self, json_mode=True)
        self.answer = FakeLane(self, json_mode=False)


class FakeRetriever:
    """Applies the same rule as the Pinecone filter: a chunk is returned only when one of its
    `access` groups (public when absent) is one of the user's groups."""

    calls: list = []

    def __init__(self, docs, groups=("all",)):
        self.docs, self.groups = docs, list(groups)
        FakeRetriever.calls.append(self.groups)

    def invoke(self, query):
        return [d for d in self.docs if set(d.metadata.get("access", ["all"])) & set(self.groups)]


class FakeWebSearch:
    def invoke(self, payload):
        return {
            "answer": "Public answer",
            "results": [{"title": "Gov page", "url": "https://example.gov", "content": "Public info"}],
        }


@pytest.fixture
def kb_docs():
    return [
        Document(page_content="Employees receive 20 annual leave days.",
                 metadata={"source": r"C:\data\documents\hr\company_hr_handbook.md", "filename": "company_hr_handbook.md"}),
        Document(page_content="Leave requests go through the HR portal.",
                 metadata={"source": "/app/data/documents/hr/company_hr_handbook.md"}),
        Document(page_content="Sick leave:   10 days per year,\n with a medical certificate after 3 days.",
                 metadata={"source": "/uploads/hr/policy.pdf", "filename": "policy.pdf", "page": 2}),
    ]


@pytest.fixture
def patch_rag(monkeypatch, kb_docs):
    """Patch LLM, retriever and web search; returns a function that installs a FakeLLM."""
    monkeypatch.setattr(nodes, "get_retriever", lambda namespace, groups: FakeRetriever(kb_docs, groups))
    monkeypatch.setattr(nodes, "web_search_tool", lambda: FakeWebSearch())

    def install(structured, text="fake answer"):
        fake = FakeLLM(structured, text)
        monkeypatch.setattr(nodes, "fast_llm", lambda: fake.fast)
        monkeypatch.setattr(nodes, "answer_llm", lambda: fake.answer)
        return fake

    return install
