from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.database.session import get_db
from app.models.models import User
from app.schemas.ai_features import AnalysisResponse, MultiDocumentAnalysisRequest
from app.services.ai.multi_document import run_multi_document_analysis
from app.services.llm.base import LLMError
from app.services.llm.manager import llm_configured
from app.utils.logger import get_logger

router = APIRouter()
logger = get_logger(__name__)


@router.post("/multi-document", response_model=AnalysisResponse)
def multi_document_analysis(
    payload: MultiDocumentAnalysisRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Answer an analysis question across multiple owned documents. Document
    boundaries stay explicit in the context; sources are attributed
    application-side; retrieval is limited to the authenticated user."""
    if not llm_configured():
        raise HTTPException(
            status_code=503,
            detail="AI features are not configured — set NVIDIA_API_KEY or OLLAMA_MODEL on the server",
        )
    try:
        return run_multi_document_analysis(
            db=db,
            user=current_user,
            document_ids=payload.document_ids,
            question=payload.question,
        )
    except LLMError as exc:
        # Includes incomplete-report style validation failures — sanitized
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    except HTTPException:
        raise
    except Exception:
        logger.exception("Unexpected analysis failure for user %s", current_user.email)
        raise HTTPException(
            status_code=500, detail="An internal error occurred while analyzing the documents"
        )
