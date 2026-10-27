import logfire
from app.agents.state import AgentState
from app.gateway import get_langchain_llm

# This uses your primary Groq model via the LangChain Gateway integration
llm = get_langchain_llm(feature="planner")

def planner_node(state: AgentState):
    """
    The Planner determines if a vector search is needed based on the ENTIRE conversation.
    """
    history = ""
    for msg in state.get("messages", [])[:-1]:
        role = "User" if msg.get("role") == "user" else "Assistant"
        history += f"{role}: {msg.get('content')}\n"

    user_message = state["messages"][-1].get("content", "") if state.get("messages") else ""
    
    prompt = f"""
    You are an intelligent Assistant Planner. 
    Analyze the conversation history and the latest user message.
    
    CONVERSATION HISTORY:
    {history}
    
    LATEST MESSAGE:
    "{user_message}"
    
    Task:
    1. If the latest message is a greeting or a question answerable using ONLY the conversation history, respond with 'CONVERSATIONAL'.
    2. If it is a technical question requiring fresh documentation, output a refined search query.
    
    Output ONLY 'CONVERSATIONAL' or the refined search query.
    """
    
    with logfire.span("Planner Decision"):
        decision = llm.invoke(prompt).content.strip()
        logfire.info(f"Intent identified: {decision}")
        
        if decision == "CONVERSATIONAL":
            return {
                "current_query": "CONVERSATIONAL",
                "status": "Handling conversationally (using memory)...",
                "plan": ["Intent: Conversational/Memory", "Retrieval: Skipped"]
            }
        
        return {
            "current_query": decision,
            "status": f"Technical research needed. Searching for: {decision}",
            "plan": ["Intent: Technical", f"Search Term: {decision}"]
        }