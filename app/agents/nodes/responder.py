import logfire
from app.agents.state import AgentState
from app.gateway import portkey_client
from app.config import settings

def generate_node(state: AgentState):
    """
    Synthesizes a response using Context and Conversation History.
    """
    query = state["current_query"]

    history_str = ""
    for msg in state.get("messages", [])[:-1]:
        role = "User" if msg.get("role") == "user" else "Assistant"
        history_str += f"{role}: {msg.get('content')}\n"

    user_msg = state["messages"][-1].get("content", "") if state.get("messages") else ""

    if query == "CONVERSATIONAL":
        prompt = f"""
        You are a friendly and helpful Enterprise AI Assistant.
        Answer the user's latest message using the CONVERSATION HISTORY below.

        CONVERSATION HISTORY:
        {history_str}

        LATEST MESSAGE:
        "{user_msg}"
        """
    else:
        max_context_chars = 25000
        full_context = ""
        for doc in state.get("documents", []):
            if len(full_context) + len(doc) < max_context_chars:
                full_context += doc + "\n\n"
            else:
                break

        prompt = f"""
        You are a Senior Technical Architect.
        Answer the question using the TECHNICAL CONTEXT provided.

        TECHNICAL CONTEXT:
        {full_context}

        CONVERSATION HISTORY:
        {history_str}

        USER QUESTION:
        "{user_msg}"
        """

    with logfire.span("LLM Synthesis"):
        try:
            target_model = f"@{settings.GROQ_SLUG}/{settings.GROQ_MODEL}"
            
            # FIX: Use standard .create() instead of .with_raw_response
            response = portkey_client.chat.completions.create(
                model=target_model,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.1,
                max_tokens=600
            )
            
            content = response.choices[0].message.content

            # Safely attempt to extract cache status without breaking execution
            cache_status = "UNKNOWN"
            for attr in ("_raw_response", "_response", "_http_response"):
                raw = getattr(response, attr, None)
                if raw is not None:
                    headers = getattr(raw, "headers", {})
                    if hasattr(headers, "get"):
                        cache_status = headers.get("x-portkey-cache-status", "UNKNOWN").upper()
                    break

            status = "Cache hit — instant response." if cache_status == "HIT" else "Response generated."
            plan_update = ["Cache: Hit"] if cache_status == "HIT" else []

            return {
                "final_answer": content,
                "status": status,
                "plan": plan_update,
                "messages": [{"role": "assistant", "content": content}]
            }

        except Exception as e:
            logfire.error(f"LLM Generation failed: {e}")
            raise e