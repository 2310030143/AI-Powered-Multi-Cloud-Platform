"""Feature C — structured report generation.

Generates a structured report from selected owned documents through the
centralized LLM manager, reusing the Phase 5 bounded, injection-hardened
context builder. The LLM output is parsed AND VALIDATED — if any required
section is missing or empty, an LLMError is raised (surfaced as a sanitized
502) instead of returning an incomplete report with HTTP 200.
"""
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.config.settings import get_settings
from app.models.models import User
from app.services.ai.context import (
    build_bounded_context,
    load_document_chunks,
    load_owned_documents,
    to_retrieved_chunks,
)
from app.services.ai.prompts import REPORT_SYSTEM_PROMPT
from app.services.llm.base import LLMError
from app.services.llm.manager import get_llm_provider
from app.utils.logger import get_logger

settings = get_settings()
logger = get_logger(__name__)

# Required report sections — markers enforced by the system prompt and
# validated application-side after parsing.
_REPORT_SECTIONS: tuple[tuple[str, str], ...] = (
    ("EXECUTIVE SUMMARY:", "executive_summary"),
    ("KEY FINDINGS:", "key_findings"),
    ("EVIDENCE:", "evidence"),
    ("RECOMMENDATIONS:", "recommendations"),
    ("CONCLUSION:", "conclusion"),
)


def parse_structured_report(text: str) -> dict:
    """Parse the marker-formatted model output into report fields.

    Tolerant of formatting noise: markers are matched case-insensitively at
    line starts; body lines join the current section.
    """
    sections = {key: [] for _, key in _REPORT_SECTIONS}
    current: str | None = None
    for line in (text or "").splitlines():
        stripped = line.strip()
        matched = False
        for marker, key in _REPORT_SECTIONS:
            if stripped.upper().startswith(marker):
                current = key
                remainder = stripped[len(marker):].strip()
                if remainder:
                    sections[current].append(remainder)
                matched = True
                break
        if not matched and current is not None and stripped:
            sections[current].append(stripped)
    return {key: "\n".join(lines).strip() for key, lines in sections.items()}


def validate_structured_report(report: dict) -> dict:
    """Every required section must be present and non-empty.

    Raises LLMError (never returns an incomplete report) listing the missing
    section names — no model output is leaked in the error.
    """
    missing = [key for _, key in _REPORT_SECTIONS if not report.get(key, "").strip()]
    if missing:
        raise LLMError(
            "LLM returned an incomplete report — missing or empty sections: "
            + ", ".join(missing)
        )
    return report


def generate_report(db: Session, user: User, document_ids: list[UUID], instruction: str) -> dict:
    """Generate a structured report from the user's selected documents.

    Returns ``{"instruction", "report", "sources", "provider"}``.
    """
    documents = load_owned_documents(db, user, document_ids)

    per_document = []
    for document in documents:
        chunks = load_document_chunks(db, document.id, settings.AI_CHUNKS_PER_DOCUMENT)
        if not chunks:
            raise HTTPException(
                status_code=409,
                detail=f"Document '{document.file_name}' has no chunks — process it first "
                "(POST /api/v1/documents/{id}/process)",
            )
        per_document.append(to_retrieved_chunks(document, chunks))

    context, sources = build_bounded_context(per_document)
    if not sources:
        raise HTTPException(
            status_code=503,
            detail="Document content does not fit within the configured context limits",
        )

    provider = get_llm_provider()
    user_message = f"CONTEXT:\n{context}\n\nREPORT INSTRUCTION:\n{instruction}"
    raw = provider.generate_answer(system_prompt=REPORT_SYSTEM_PROMPT, user_message=user_message)
    report = validate_structured_report(parse_structured_report(raw))

    logger.info(
        "Report generated for user %s from %d documents (provider=%s)",
        user.email, len(documents), provider.last_provider,
    )
    return {
        "instruction": instruction,
        "report": report,
        "sources": [source.as_dict() for source in sources],
        "provider": provider.last_provider,
    }
