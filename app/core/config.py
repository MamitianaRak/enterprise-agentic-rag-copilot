from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings, SettingsConfigDict
from functools import lru_cache
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    app_name: str = "Enterprise Agentic RAG Copilot"
    app_env: str = "development"

    # LLM gateway (LiteLLM Router). Two lanes, each a fallback chain tried in order, skipping
    # providers without credentials; a provider that fails is put in cooldown and the next answers.
    # answer lane: writes the answers. fast lane: contextualize, triage, grading, rewrites, checks.
    llm_providers: str = "gemini,groq,cloudflare,openrouter"
    llm_fast_providers: str = "groq,cloudflare,gemini,openrouter"
    google_api_key: str = ""
    gemini_model: str = "gemini-3.5-flash-lite"
    groq_api_key: str = ""
    groq_model: str = "openai/gpt-oss-120b"
    groq_fast_model: str = "openai/gpt-oss-20b"
    cloudflare_api_token: str = ""
    cloudflare_account_id: str = ""
    cloudflare_llm_model: str = "@cf/meta/llama-3.3-70b-instruct-fp8-fast"
    openrouter_api_key: str = ""
    openrouter_model: str = "nvidia/nemotron-3-super-120b-a12b:free"
    llm_timeout: float = 60
    llm_cooldown_seconds: float = 60  # how long a failing provider is skipped
    llm_cache_ttl_seconds: int = 3600  # in-memory cache of identical prompts; 0 disables it

    tavily_api_key: str = ""
    pinecone_api_key: str = ""
    pinecone_index_name: str = "enterprise-copilot"  # one index, one namespace per domain
    hr_namespace: str = Field(
        default="company-hr-kb",
        validation_alias=AliasChoices("HR_NAMESPACE", "PINECONE_NAMESPACE"),
    )
    cloudops_namespace: str = "cloudops-runbooks"
    it_namespace: str = "it-support-kb"
    # Embeddings: Pinecone Inference (no extra provider key). Must match the index dimension.
    embedding_model: str = "llama-text-embed-v2"
    embedding_dimension: int = 768
    max_context_chars: int = 12000
    # Retrieve wide, then let the relevance grading filter: with 4, a multi-part question ("which severity, and who
    # do I page?") lost the section answering its second part, ranked 6th behind same-keyword runbooks (evals/).
    top_k: int = 6
    max_retries: int = 1
    max_support_retries: int = 1
    max_retrieval_rewrites: int = 1  # CloudOps: internal query rewrites before going to the web
    max_web_rewrites: int = 1
    # Auth: JWT signed with this secret (required in production). Demo accounts give the public
    # demo one-click logins with different rights; turn them off for a real deployment.
    jwt_secret: str = "dev-only-secret-change-me"
    token_ttl_minutes: int = 480
    demo_accounts: bool = True
    # Comma-separated origins allowed to call the API from a browser, e.g. the frontend's URL
    # when it is hosted separately. Empty = same-origin only (Vite proxy, nginx, docker compose).
    cors_origins: str = ""
    memory_turns: int = 4
    audit_db_path: str = str(BASE_DIR / "data" / "audit.db")
    memory_db_path: str = str(BASE_DIR / "data" / "memory.db")
    upload_dir: str = str(BASE_DIR / "uploads")
    documents_dir: str = str(BASE_DIR / "data" / "documents")
    model_config = SettingsConfigDict(env_file=str(BASE_DIR / ".env"), extra="ignore")


@lru_cache
def get_settings() -> Settings:
    return Settings()
