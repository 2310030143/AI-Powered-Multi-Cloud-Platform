from uuid import UUID

from pydantic import BaseModel, Field, field_validator

from app.config.settings import get_settings

# Hard structural cap on any document list; the configurable cap
# (AI_MAX_DOCUMENTS) is checked dynamically in the validators below.
_LIST_HARD_CAP = 100


def _check_document_ids(value: list[UUID]) -> list[UUID]:
    max_documents = get_settings().AI_MAX_DOCUMENTS
    if not value:
        raise ValueError("At least one document ID is required")
    if len(value) > max_documents:
        raise ValueError(f"Too many documents — the maximum is {max_documents}")
    return value


def _reject_whitespace_only(value: str) -> str:
    if not value.strip():
        raise ValueError("must not be empty or whitespace-only")
    return value


class FeatureSource(BaseModel):
    """Application-side source attribution (Phase 5 conventions; score is
    None when chunks were selected non-semantically)."""
    document_id: str | None
    chunk_id: str
    filename: str | None
    page_number: int | None
    score: float | None


class SummarizeResponse(BaseModel):
    document_id: str
    filename: str | None
    summary: str
    sources: list[FeatureSource]
    provider: str | None


class ReportGenerateRequest(BaseModel):
    document_ids: list[UUID] = Field(min_length=1, max_length=_LIST_HARD_CAP)
    instruction: str = Field(min_length=1, max_length=2000)

    @field_validator("document_ids")
    @classmethod
    def validate_document_ids(cls, value: list[UUID]) -> list[UUID]:
        return _check_document_ids(value)

    @field_validator("instruction")
    @classmethod
    def validate_instruction(cls, value: str) -> str:
        return _reject_whitespace_only(value)


class StructuredReport(BaseModel):
    """Validated report — every section is guaranteed non-empty by the
    service layer before this model is ever returned."""
    executive_summary: str
    key_findings: str
    evidence: str
    recommendations: str
    conclusion: str


class ReportResponse(BaseModel):
    instruction: str
    report: StructuredReport
    sources: list[FeatureSource]
    provider: str | None


class MultiDocumentAnalysisRequest(BaseModel):
    document_ids: list[UUID] = Field(min_length=1, max_length=_LIST_HARD_CAP)
    question: str = Field(min_length=1, max_length=2000)

    @field_validator("document_ids")
    @classmethod
    def validate_document_ids(cls, value: list[UUID]) -> list[UUID]:
        return _check_document_ids(value)

    @field_validator("question")
    @classmethod
    def validate_question(cls, value: str) -> str:
        return _reject_whitespace_only(value)


class AnalysisResponse(BaseModel):
    question: str
    analysis: str
    sources: list[FeatureSource]
    provider: str | None
