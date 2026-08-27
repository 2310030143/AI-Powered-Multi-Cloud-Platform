"""Token-aware text chunking with overlap.

Splits extracted page text into overlapping chunks sized in (approximate)
tokens, keeping the page number where each chunk starts. Uses tiktoken when
available and falls back to a deterministic chars/4 estimate otherwise, so
chunking works fully offline.
"""
import re

from app.config.settings import get_settings
from app.services.document_processing.extractors import PageText

settings = get_settings()

_encoder = None
_encoder_tried = False


def get_encoder():
    """Return a tiktoken encoder, or None when unavailable (offline, etc.)."""
    global _encoder, _encoder_tried
    if not _encoder_tried:
        _encoder_tried = True
        try:
            import tiktoken

            _encoder = tiktoken.get_encoding("cl100k_base")
        except Exception:
            _encoder = None
    return _encoder


def token_count(text: str) -> int:
    """Best-effort token count (tiktoken, or ~4 characters per token)."""
    encoder = get_encoder()
    if encoder is not None:
        return len(encoder.encode(text))
    return max(1, (len(text) + 3) // 4)  # ceil(len/4)


def _split_paragraphs(text: str) -> list[str]:
    return [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]


def _split_long_piece(piece: str, max_tokens: int) -> list[str]:
    """Word-split a paragraph that alone exceeds the chunk size."""
    words = piece.split()
    parts: list[str] = []
    current: list[str] = []
    for word in words:
        current.append(word)
        if token_count(" ".join(current)) >= max_tokens:
            parts.append(" ".join(current))
            current = []
    if current:
        parts.append(" ".join(current))
    return parts


def _tail_overlap(text: str, overlap_tokens: int) -> str:
    """Return the trailing ~overlap_tokens worth of words from text."""
    if overlap_tokens <= 0:
        return ""
    words = text.split()
    tail: list[str] = []
    used = 0
    for word in reversed(words):
        cost = token_count(word) + (1 if tail else 0)
        if used + cost > overlap_tokens:
            break
        tail.insert(0, word)
        used += cost
    return " ".join(tail)


def chunk_pages(
    pages: list[PageText],
    chunk_tokens: int | None = None,
    overlap_tokens: int | None = None,
) -> list[dict]:
    """Chunk page texts into overlapping dicts:

    ``{"content": str, "page_number": int | None, "token_count": int}``
    """
    chunk_tokens = chunk_tokens or settings.CHUNK_SIZE_TOKENS
    overlap_tokens = overlap_tokens if overlap_tokens is not None else settings.CHUNK_OVERLAP_TOKENS

    # 1. Flatten pages into (page_number, paragraph) pieces,
    #    hard-splitting paragraphs that alone exceed the chunk size.
    pieces: list[tuple[int | None, str]] = []
    for page in pages:
        for paragraph in _split_paragraphs(page.text):
            if token_count(paragraph) <= chunk_tokens:
                pieces.append((page.page_number, paragraph))
            else:
                for part in _split_long_piece(paragraph, chunk_tokens):
                    pieces.append((page.page_number, part))

    # 2. Greedily assemble pieces into chunks, carrying a tail overlap forward.
    chunks: list[dict] = []
    buffer: list[str] = []
    buffer_page: int | None = None

    def flush():
        nonlocal buffer, buffer_page
        if not buffer:
            return
        content = "\n\n".join(buffer)
        chunks.append(
            {
                "content": content,
                "page_number": buffer_page,
                "token_count": token_count(content),
            }
        )
        buffer = []

    for page_number, piece in pieces:
        if not buffer:
            buffer_page = page_number
        elif token_count("\n\n".join(buffer + [piece])) > chunk_tokens:
            flush()
            tail = _tail_overlap(chunks[-1]["content"], overlap_tokens) if chunks else ""
            if tail:
                buffer = [tail]
                buffer_page = page_number
            else:
                buffer_page = page_number
        buffer.append(piece)

    flush()
    return chunks


def chunk_text(text: str, **kwargs) -> list[dict]:
    """Chunk plain text (no page metadata)."""
    if not text or not text.strip():
        return []
    return chunk_pages([PageText(page_number=1, text=text)], **kwargs)
