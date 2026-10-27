from typing import TypedDict, List, Annotated
import operator

class AgentState(TypedDict):
    # Annotated + operator.add ensures LangGraph appends to the list automatically
    messages: Annotated[List[dict], operator.add]
    plan: Annotated[List[str], operator.add]
    
    # Standard fields are overwritten with the latest value
    current_query: str
    documents: List[str]
    status: str
    final_answer: str