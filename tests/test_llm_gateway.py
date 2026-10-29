"""LLM gateway (lanes, deployments, LangChain adapter, cache), Pinecone embeddings and the
routing of each agent step to its lane. No network: LiteLLM and Pinecone are replaced by fakes."""
from types import SimpleNamespace

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage

from app.core.config import Settings
from app.core.llm import (
    GatewayChatModel, ResponseCache, deployments, gateway_chain, pop_model_label, remember_model,
)
from app.rag.common import nodes
from app.rag.common.state import initial_state
from app.rag.common.vectorstore import PineconeInferenceEmbeddings
from app.rag.hr.graph import build_graph as build_hr_graph

ALL_KEYS = {
    "google_api_key": "g",
    "groq_api_key": "q",
    "openrouter_api_key": "o",
    "cloudflare_api_token": "t",
    "cloudflare_account_id": "acc",
}


def names(settings: Settings, lane: str) -> list[str]:
    return [d["model_name"] for d in deployments(settings, lane)]


# ---- Lanes and deployments ----

def test_each_lane_follows_its_own_order():
    settings = Settings(_env_file=None, **ALL_KEYS)
    assert names(settings, "answer") == ["answer-gemini", "answer-groq", "answer-cloudflare", "answer-openrouter"]
    assert names(settings, "fast") == ["fast-groq", "fast-cloudflare", "fast-gemini", "fast-openrouter"]
    # The deployment id is reported back by LiteLLM, so the trace shows who answered.
    assert all(d["model_info"]["id"] == d["model_name"] for d in deployments(settings, "fast"))


def test_fast_lane_uses_the_smaller_groq_model():
    settings = Settings(_env_file=None, **ALL_KEYS)
    answer_groq = deployments(settings, "answer")[1]["litellm_params"]
    fast_groq = deployments(settings, "fast")[0]["litellm_params"]
    assert answer_groq["model"] == "groq/openai/gpt-oss-120b"
    assert fast_groq["model"] == "groq/openai/gpt-oss-20b"
    assert fast_groq["reasoning_effort"] == "low"


def test_providers_without_credentials_are_skipped():
    settings = Settings(_env_file=None, groq_api_key="q", openrouter_api_key="o")
    assert names(settings, "answer") == ["answer-groq", "answer-openrouter"]
    assert names(settings, "fast") == ["fast-groq", "fast-openrouter"]


def test_cloudflare_goes_through_its_openai_compatible_endpoint():
    settings = Settings(_env_file=None, llm_providers="cloudflare", **ALL_KEYS)
    params = deployments(settings, "answer")[0]["litellm_params"]
    assert params["model"] == "openai/@cf/meta/llama-3.3-70b-instruct-fp8-fast"
    assert params["api_base"].endswith("/accounts/acc/ai/v1")


def test_gateway_chain_is_human_readable():
    settings = Settings(_env_file=None, groq_api_key="q", google_api_key="g")
    assert gateway_chain(settings, "answer") == "gemini:gemini-3.5-flash-lite → groq:openai/gpt-oss-120b"
    assert gateway_chain(settings, "fast") == "groq:openai/gpt-oss-20b → gemini:gemini-3.5-flash-lite"
    assert gateway_chain(Settings(_env_file=None)) == ""


# ---- LangChain adapter ----

class FakeRouter:
    """Stands in for litellm.Router: records the call, answers like a LiteLLM response."""

    def __init__(self, served_by: str = "answer-groq", content: str = '{"ok": true}'):
        self.calls: list[dict] = []
        self.served_by, self.content = served_by, content

    def completion(self, **params):
        self.calls.append(params)
        response = SimpleNamespace(
            model="openai/gpt-oss-120b",
            choices=[SimpleNamespace(message=SimpleNamespace(content=self.content))],
        )
        response._hidden_params = {"model_id": self.served_by}
        return response


def test_fast_lane_calls_the_router_in_json_mode():
    router = FakeRouter()
    llm = GatewayChatModel(router=router, primary="fast-groq", json_mode=True)
    reply = llm.invoke([SystemMessage(content="Return a JSON object."), HumanMessage(content="hi")])

    call = router.calls[0]
    assert call["model"] == "fast-groq"
    assert call["response_format"] == {"type": "json_object"}
    assert call["messages"] == [
        {"role": "system", "content": "Return a JSON object."},
        {"role": "user", "content": "hi"},
    ]
    # The fallback deployment that actually answered is reported.
    assert reply.response_metadata == {"model_name": "openai/gpt-oss-120b", "provider": "answer-groq", "cached": False}


def test_answer_lane_returns_free_text_without_json_mode():
    router = FakeRouter(content="**20 days** of annual leave.")
    reply = GatewayChatModel(router=router, primary="answer-gemini").invoke("How many leave days?")
    assert "response_format" not in router.calls[0]
    assert reply.content == "**20 days** of annual leave."


def test_json_mode_mentions_json_when_the_prompt_does_not():
    router = FakeRouter()
    GatewayChatModel(router=router, primary="fast-groq", json_mode=True).invoke([HumanMessage(content="ping")])
    assert router.calls[0]["messages"][0] == {"role": "system", "content": "Respond with a JSON object."}


def test_identical_prompts_are_served_from_the_cache():
    router = FakeRouter()
    llm = GatewayChatModel(router=router, primary="fast-groq", json_mode=True, response_cache=ResponseCache(60))
    prompt = [HumanMessage(content="json please")]

    first, second = llm.invoke(prompt), llm.invoke(prompt)
    llm.invoke([HumanMessage(content="another json prompt")])

    assert len(router.calls) == 2  # the repeated prompt never reached a provider
    assert first.response_metadata["cached"] is False
    assert second.response_metadata == {**first.response_metadata, "cached": True}


def test_cache_is_separate_per_lane():
    router, cache = FakeRouter(), ResponseCache(60)
    prompt = [HumanMessage(content="json please")]
    GatewayChatModel(router=router, primary="fast-groq", json_mode=True, response_cache=cache).invoke(prompt)
    GatewayChatModel(router=router, primary="answer-gemini", response_cache=cache).invoke(prompt)
    assert len(router.calls) == 2


def test_cache_entries_expire_and_are_bounded():
    now = [0.0]
    cache = ResponseCache(ttl_seconds=10, max_items=2, clock=lambda: now[0])
    cache.set("a", {"v": 1})
    cache.set("b", {"v": 2})
    cache.set("c", {"v": 3})  # evicts the least recently used entry
    assert cache.get("a") is None
    assert cache.get("c") == {"v": 3}
    now[0] = 11
    assert cache.get("c") is None


# ---- Model shown in the trace ----

def test_trace_line_reports_the_model_that_answered():
    remember_model(AIMessage(content="{}", response_metadata={
        "model_name": "openai/gpt-oss-20b", "provider": "fast-groq", "cached": False}))
    assert nodes.add_trace({"trace": []}, "Router → KB") == ["Router → KB [groq:openai/gpt-oss-20b]"]
    # The label is consumed: the next, non-LLM step has none.
    assert nodes.add_trace({"trace": []}, "Private KB retrieval → 4 chunks") == ["Private KB retrieval → 4 chunks"]


def test_cached_answers_are_flagged_in_the_trace():
    remember_model(AIMessage(content="x", response_metadata={
        "model_name": "gemini-3.5-flash-lite", "provider": "answer-gemini", "cached": True}))
    assert pop_model_label() == "gemini:gemini-3.5-flash-lite (cached)"


def test_json_reply_is_read_even_with_fences_or_text_around_it():
    assert nodes.parse_json_object('```json\n{"route": "kb"}\n```') == {"route": "kb"}
    assert nodes.parse_json_object('Sure! {"grade": "good"} Hope it helps.') == {"grade": "good"}


# ---- Each step goes to its lane ----

class RecordingLane:
    def __init__(self, replies):
        self.replies, self.prompts = list(replies), []

    def invoke(self, prompt):
        self.prompts.append(prompt)
        return AIMessage(content=self.replies.pop(0))


def test_only_answers_use_the_answer_lane(monkeypatch, kb_docs):
    from tests.conftest import FakeRetriever

    fast = RecordingLane(['{"route":"kb"}', '{"grade":"good"}',
                          '{"status":"fully_supported","evidence":[]}', '{"status":"useful","reason":"ok"}'])
    answer = RecordingLane(["20 days."])
    monkeypatch.setattr(nodes, "fast_llm", lambda: fast)
    monkeypatch.setattr(nodes, "answer_llm", lambda: answer)
    monkeypatch.setattr(nodes, "get_retriever", lambda namespace, groups: FakeRetriever(kb_docs, groups))

    result = build_hr_graph().invoke(initial_state("How many annual leave days?", ["all"]))

    assert result["answer"] == "20 days."
    assert len(answer.prompts) == 1 and "Answer ONLY from the private company HR KB" in answer.prompts[0]
    assert len(fast.prompts) == 4  # router, grade, support check, usefulness check


# ---- Pinecone Inference embeddings ----

class FakeInference:
    def __init__(self):
        self.calls = []

    def embed(self, model, inputs, parameters):
        self.calls.append({"model": model, "n": len(inputs), "parameters": parameters})
        return SimpleNamespace(data=[SimpleNamespace(values=[0.1, 0.2]) for _ in inputs])


def test_documents_and_queries_use_their_input_type():
    client = SimpleNamespace(inference=FakeInference())
    emb = PineconeInferenceEmbeddings(client, "llama-text-embed-v2", 768)

    assert emb.embed_documents(["a", "b"]) == [[0.1, 0.2], [0.1, 0.2]]
    assert emb.embed_query("q") == [0.1, 0.2]
    first, second = client.inference.calls
    assert first["model"] == "llama-text-embed-v2"
    assert first["parameters"] == {"input_type": "passage", "truncate": "END", "dimension": 768}
    assert second["parameters"]["input_type"] == "query"


def test_large_ingestions_are_embedded_in_batches():
    client = SimpleNamespace(inference=FakeInference())
    vectors = PineconeInferenceEmbeddings(client, "llama-text-embed-v2", 768).embed_documents(["x"] * 200)
    assert len(vectors) == 200
    assert [c["n"] for c in client.inference.calls] == [96, 96, 8]
