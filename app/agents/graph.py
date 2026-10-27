from langgraph.graph import StateGraph, END
from langgraph.checkpoint.memory import MemorySaver

from app.agents.state import AgentState
from app.agents.nodes.planner import planner_node
from app.agents.nodes.retriever import retrieve_node
from app.agents.nodes.responder import generate_node

def route_planner(state: AgentState):
    """Conditional routing logic based on planner's decision."""
    if state.get("current_query") == "CONVERSATIONAL":
        return "generate"
    return "retrieve"

# Initialize Graph
workflow = StateGraph(AgentState)

workflow.add_node("planner", planner_node)
workflow.add_node("retrieve", retrieve_node)
workflow.add_node("generate", generate_node)

workflow.set_entry_point("planner")

workflow.add_conditional_edges(
    "planner",
    route_planner,
    {
        "retrieve": "retrieve",
        "generate": "generate"
    }
)

workflow.add_edge("retrieve", "generate")
workflow.add_edge("generate", END)

# Compile with memory saver to persist history context across thread_ids
memory = MemorySaver()
rag_agent = workflow.compile(checkpointer=memory)