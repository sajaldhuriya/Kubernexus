import logfire
from qdrant_client import QdrantClient
from qdrant_client.http import models
from app.config import settings
from app.services.retrieval.embedding import embed_query

# Initialize Qdrant Client with a timeout so it doesn't hang indefinitely
client = QdrantClient(
    url=settings.QDRANT_URL,
    api_key=settings.QDRANT_API_KEY,
    timeout=15.0  # Fails fast if the database cluster is sleeping
)

def search_enterprise_knowledge(query: str, limit: int = 8):
    """
    Performs a high-precision search in the enterprise knowledge base.
    """
    try:
        # SPAN 1: Measure exactly how long Gemini takes
        with logfire.span("Diagnostic: Gemini API Embedding"):
            query_vector = embed_query(query)

        # SPAN 2: Measure exactly how long Qdrant takes
        with logfire.span("Diagnostic: Qdrant Vector Search"):
            response = client.query_points(
                collection_name=settings.QDRANT_COLLECTION,
                query=query_vector,
                limit=limit,
                with_payload=True 
            )

        results = []
        for res in response.points:
            results.append({
                "content": res.payload.get("text", ""),
                "source": res.payload.get("source", "Unknown"),
                "score": res.score
            })
        
        return results
    except Exception as e:
        logfire.error(f"❌ Qdrant Search Failed: {e}")
        return []