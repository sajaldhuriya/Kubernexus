import logfire
from langchain_groq import ChatGroq
from nemoguardrails import RailsConfig, LLMRails

from app.config import settings
from app.guardrails.colang_rules import (
    COLANG_CONTENT,
    YAML_CONTENT,
    RAIL_INDICATORS,
)

_rails: LLMRails | None = None
GUARD_MODEL = "openai/gpt-oss-20b"

def initialize_rails() -> None:
    global _rails
    try:
        guard_llm = ChatGroq(
            api_key=settings.GROQ_API_KEY,
            model=GUARD_MODEL,
                temperature=0,
        )

        config = RailsConfig.from_content(
            colang_content=COLANG_CONTENT,
            yaml_content=YAML_CONTENT,
        )

        # Explicitly pass the llm object to bind the rails correctly
        _rails = LLMRails(config, llm=guard_llm)
        logfire.info(f"NeMo Guardrails successfully initialized with model: {GUARD_MODEL}")
    except Exception as e:
        logfire.error(f"❌ Failed to initialize NeMo Guardrails: {e}")
        _rails = None


def guard(message: str) -> tuple[bool, str | None]:
    if _rails is None:
        logfire.warning("Guardrails not initialized; skipping gate.")
        return False, None

    with logfire.span("Guardrails Check"):
        try:
            # Layer 1: Standard NeMo Guardrails
            result = _rails.generate(
                messages=[{"role": "user", "content": message}]
            )

            content = (
                result.get("content", "")
                if isinstance(result, dict)
                else str(result)
            )

            import re
            clean_content = re.sub(r'<think>.*?</think>', '', content, flags=re.DOTALL).strip()

            # Match indicators
            fired = any(indicator.lower() in clean_content.lower() for indicator in RAIL_INDICATORS)

            # Layer 2: a "Helpful LLM" Fallback
            # If the LLM provided a long answer but it doesn't contain our core technical domains,
            # it's likely answering an off-topic question (the "helpful chatbot" problem).
            if not fired:
                tech_terms = ["kubernetes", "k8s", "intel", "cpu", "fpga", "sriov", "networking", "sdn", "vlan", "bgp", "pod", "cluster"]
                has_tech = any(term in clean_content.lower() for term in tech_terms)

                if len(clean_content) > 40 and not has_tech:
                    logfire.info("🛡️ Classification Fallback: LLM answered off-topic query without technical keywords.")
                    return True, "I'm sorry, but I can only assist with Kubernetes, Intel hardware, and enterprise networking."

            if fired:
                logfire.info(f"🎯 Guardrails fired | query='{message[:80]}'")
                return True, clean_content

            logfire.info("Guardrails passed.")
            return False, None
        except Exception as e:
            logfire.error(f"Guardrails execution error: {e}")
            return False, None
