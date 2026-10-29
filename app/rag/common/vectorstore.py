import time
from langchain_core.embeddings import Embeddings
from pinecone import Pinecone, ServerlessSpec
from langchain_pinecone import PineconeVectorStore
from app.core.config import get_settings

settings = get_settings()

EMBED_BATCH = 96  # Pinecone Inference limit per request for llama-text-embed-v2

_client: Pinecone | None = None
_embeddings = None
_index = None
_stores: dict[str, PineconeVectorStore] = {}


def pinecone_client() -> Pinecone:
    global _client
    if _client is None:
        if not settings.pinecone_api_key:
            raise RuntimeError("PINECONE_API_KEY is missing")
        _client = Pinecone(api_key=settings.pinecone_api_key)
    return _client


class PineconeInferenceEmbeddings(Embeddings):
    """Embeddings hosted by Pinecone (llama-text-embed-v2 by default): no extra provider key.
    Indexed chunks are embedded as `passage`, user questions as `query`."""

    def __init__(self, client: Pinecone, model: str, dimension: int):
        self.client, self.model, self.dimension = client, model, dimension

    def _embed(self, texts: list[str], input_type: str) -> list[list[float]]:
        vectors: list[list[float]] = []
        for start in range(0, len(texts), EMBED_BATCH):
            result = self.client.inference.embed(
                model=self.model,
                inputs=texts[start:start + EMBED_BATCH],
                parameters={"input_type": input_type, "truncate": "END", "dimension": self.dimension},
            )
            vectors += [item.values for item in result.data]
        return vectors

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return self._embed(texts, "passage")

    def embed_query(self, text: str) -> list[float]:
        return self._embed([text], "query")[0]


def get_embeddings() -> PineconeInferenceEmbeddings:
    global _embeddings
    if _embeddings is None:
        _embeddings = PineconeInferenceEmbeddings(
            pinecone_client(), settings.embedding_model, settings.embedding_dimension
        )
    return _embeddings


def _index_dimension(index_info):
    dimension = getattr(index_info, "dimension", None)
    if dimension is None and isinstance(index_info, dict):
        dimension = index_info.get("dimension")
    return dimension


def ensure_index():
    """Return the Pinecone index, creating it if needed. Never deletes an existing index."""
    global _index
    if _index is not None:
        return _index
    name = settings.pinecone_index_name
    desired = settings.embedding_dimension
    pc = pinecone_client()

    if name in [x["name"] for x in pc.list_indexes()]:
        current = _index_dimension(pc.describe_index(name))
        if current is not None and current != desired:
            raise RuntimeError(
                f"Pinecone index '{name}' has dimension {current} but EMBEDDING_DIMENSION is {desired}. "
                "Set EMBEDDING_DIMENSION to match, use another PINECONE_INDEX_NAME, "
                "or delete the index manually."
            )
    else:
        pc.create_index(
            name=name,
            dimension=desired,
            metric="cosine",
            spec=ServerlessSpec(cloud="aws", region="us-east-1"),
        )
        while not pc.describe_index(name).status["ready"]:
            time.sleep(1)

    _index = pc.Index(name)
    return _index


def get_vectorstore(namespace: str) -> PineconeVectorStore:
    if namespace not in _stores:
        _stores[namespace] = PineconeVectorStore(
            index=ensure_index(),
            embedding=get_embeddings(),
            namespace=namespace,
        )
    return _stores[namespace]


def access_filter(groups: list[str]) -> dict:
    """Pinecone metadata filter: a chunk matches when one of its `access` groups is one of the
    user's. Applied inside the vector query, so a forbidden chunk is never retrieved, never
    graded and never reaches the LLM."""
    return {"access": {"$in": sorted(set(groups))}}


def get_retriever(namespace: str, groups: list[str]):
    return get_vectorstore(namespace).as_retriever(
        search_kwargs={"k": settings.top_k, "filter": access_filter(groups)}
    )


def add_documents(chunks, namespace: str, ids: list[str] | None = None):
    """Upsert chunks; reusing the same ids replaces the previous vectors."""
    return get_vectorstore(namespace).add_documents(chunks, ids=ids)


def delete_vectors(ids: list[str], namespace: str) -> None:
    if ids:
        get_vectorstore(namespace).delete(ids=ids, namespace=namespace)
