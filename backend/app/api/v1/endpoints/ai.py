from fastapi import APIRouter

router = APIRouter()


@router.post("/search")
def semantic_search():
    return {"message": "Semantic search — coming in Phase 4"}


@router.post("/chat")
def rag_chat():
    return {"message": "RAG chat — coming in Phase 5"}
