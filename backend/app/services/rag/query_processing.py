"""Query processing for the RAG pipeline.

Keeps the user's actual question intact while trimming and normalizing
whitespace so the query is well-formed for semantic embedding/retrieval.
Validation of length/emptiness also happens here (defense in depth beneath
the API schema). Kept separate from retrieval and LLM logic.
"""

MAX_QUERY_CHARS = 2000


class InvalidQueryError(ValueError):
    """Raised when a user message cannot be turned into a retrieval query."""


def prepare_query(raw: str) -> str:
    """Validate, trim and normalize a user message into a retrieval query.

    - strips leading/trailing whitespace
    - collapses internal runs of whitespace into single spaces
    - preserves the wording (meaning) of the actual question
    """
    if raw is None:
        raise InvalidQueryError("Query is empty")
    query = " ".join(raw.split())
    if not query:
        raise InvalidQueryError("Query is empty or whitespace-only")
    if len(query) > MAX_QUERY_CHARS:
        raise InvalidQueryError(f"Query exceeds the maximum length of {MAX_QUERY_CHARS} characters")
    return query
