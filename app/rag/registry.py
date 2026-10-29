"""Maps each domain to its own workflow, knowledge base namespace and UI settings."""
from dataclasses import dataclass, field
from typing import Any, Iterator
from app.core.config import get_settings
from app.rag.cloudops.graph import build_graph as build_cloudops_graph
from app.rag.cloudops.ui import UI as CLOUDOPS_UI
from app.rag.common.memory import get_checkpointer, thread_config
from app.rag.common.state import initial_state
from app.rag.hr.graph import build_graph as build_hr_graph
from app.rag.hr.ui import UI as HR_UI
from app.rag.it.graph import build_graph as build_it_graph
from app.rag.it.ui import UI as IT_UI

settings = get_settings()


@dataclass(frozen=True)
class Domain:
    name: str
    namespace: str
    graph: Any
    ui: dict = field(default_factory=dict)

    @property
    def label(self) -> str:
        return self.ui.get("label", self.name)

    def public(self) -> dict:
        """What the browser needs to render this domain."""
        return {"name": self.name, **self.ui}


DOMAINS: dict[str, Domain] = {
    "hr": Domain("hr", settings.hr_namespace, build_hr_graph(get_checkpointer()), HR_UI),
    "it": Domain("it", settings.it_namespace, build_it_graph(get_checkpointer()), IT_UI),
    "cloudops": Domain("cloudops", settings.cloudops_namespace, build_cloudops_graph(get_checkpointer()), CLOUDOPS_UI),
}

DEFAULT_DOMAIN = "hr"


def get_domain(name: str) -> Domain:
    """Raise KeyError for an unknown domain."""
    return DOMAINS[name]


def public_config() -> dict:
    return {"default": DEFAULT_DOMAIN, "domains": [d.public() for d in DOMAINS.values()]}


def ask(domain: Domain, question: str, thread_id: str, access_groups: list[str]):
    return domain.graph.invoke(
        initial_state(question, access_groups), config=thread_config(domain.name, thread_id)
    )


def stream(domain: Domain, question: str, thread_id: str, access_groups: list[str]) -> Iterator[dict]:
    """Yield the full state after each graph step; the last one is the final result."""
    return domain.graph.stream(
        initial_state(question, access_groups), config=thread_config(domain.name, thread_id),
        stream_mode="values",
    )


def get_history(domain: Domain, thread_id: str) -> list[dict]:
    snapshot = domain.graph.get_state(thread_config(domain.name, thread_id))
    return list(snapshot.values.get("memory", []))


def clear_history(domain: Domain, thread_id: str) -> None:
    get_checkpointer().delete_thread(thread_config(domain.name, thread_id)["configurable"]["thread_id"])
