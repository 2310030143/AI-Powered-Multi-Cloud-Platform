from fastapi import APIRouter

router = APIRouter()


@router.get("/{doc_id}/status")
def document_status(doc_id: str):
    return {"message": f"Status for {doc_id} — coming in Phase 3"}


@router.post("/{doc_id}/summarize")
def summarize_document(doc_id: str):
    return {"message": f"Summarize {doc_id} — coming in Phase 6"}
