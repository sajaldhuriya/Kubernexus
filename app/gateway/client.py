import logfire
from portkey_ai import Portkey, createHeaders, PORTKEY_GATEWAY_URL
from langchain_openai import ChatOpenAI
from app.config import settings

PRIMARY_MODEL = "openai/gpt-oss-20b"
FALLBACK_MODEL = "openai/gpt-oss-120b"

# Native Portkey client used by the responder node
portkey_client = Portkey(
    api_key=settings.PORTKEY_API_KEY,
)

def get_langchain_llm(feature: str = "rag") -> ChatOpenAI:
    """Return the primary LLM through Portkey using the primary 'rag' slug."""
    return ChatOpenAI(
        api_key=settings.PORTKEY_API_KEY,
        base_url=PORTKEY_GATEWAY_URL,
        model=f"@{settings.GROQ_SLUG}/{PRIMARY_MODEL}",
        temperature=0,
        default_headers=createHeaders(
            api_key=settings.PORTKEY_API_KEY,
            metadata={
                "feature": feature,
                "_user": "rag-system",
                "environment": "development",
            },
        ),
    )

def get_fallback_llm(feature: str = "rag") -> ChatOpenAI:
    """Return the secondary LLM through Portkey using the fallback 'brag' slug."""
    return ChatOpenAI(
        api_key=settings.PORTKEY_API_KEY,
        base_url=PORTKEY_GATEWAY_URL,
        model=f"@{settings.GROQ_SLUG_2}/{FALLBACK_MODEL}",
        temperature=0,
        default_headers=createHeaders(
            api_key=settings.PORTKEY_API_KEY,
            metadata={
                "feature": feature,
                "_user": "rag-system",
                "environment": "development",
            },
        ),
    )