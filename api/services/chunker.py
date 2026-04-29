"""Text chunker with header breadcrumb tracking.

Splits document content into ~512 token chunks with ~128 token overlap.
Tracks markdown headers to build breadcrumb context per chunk.
"""

import re
import logging
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)

CHUNK_SIZE = 512
CHUNK_OVERLAP = 128
MIN_CHUNK_TOKENS = 32

SENTENCE_RE = re.compile(r'(?<=[.!?])\s+')
HEADER_RE = re.compile(r'^(#{1,6})\s+(.+)$', re.MULTILINE)


def _estimate_tokens(text: str) -> int:
    return max(1, len(text) // 4)


@dataclass
class Chunk:
    index: int
    content: str
    page: int | None
    start_char: int
    token_count: int
    header_breadcrumb: str = ""


def chunk_text(
    content: str,
    chunk_size: int = CHUNK_SIZE,
    overlap: int = CHUNK_OVERLAP,
    page: int | None = None,
    start_char_offset: int = 0,
) -> list[Chunk]:
    """Chunk a text string into overlapping segments with header tracking."""
    if not content or not content.strip():
        return []

    paragraphs = _split_paragraphs(content)
    header_stack: list[tuple[int, str]] = []
    chunks: list[Chunk] = []
    current_blocks: list[str] = []
    current_tokens = 0
    current_start = start_char_offset
    char_pos = start_char_offset

    for para in paragraphs:
        para_tokens = _estimate_tokens(para)

        header_match = HEADER_RE.match(para)
        if header_match:
            level = len(header_match.group(1))
            heading = header_match.group(2).strip()
            header_stack = [(l, t) for l, t in header_stack if l < level]
            header_stack.append((level, heading))

        if current_tokens + para_tokens > chunk_size and current_blocks:
            chunk_text_str = "\n\n".join(current_blocks)
            if _estimate_tokens(chunk_text_str) >= MIN_CHUNK_TOKENS:
                breadcrumb = " > ".join(t for _, t in header_stack)
                chunks.append(Chunk(
                    index=len(chunks),
                    content=chunk_text_str,
                    page=page,
                    start_char=current_start,
                    token_count=_estimate_tokens(chunk_text_str),
                    header_breadcrumb=breadcrumb,
                ))

            overlap_blocks, overlap_tokens = _get_overlap(current_blocks, overlap)
            current_blocks = overlap_blocks
            current_tokens = overlap_tokens
            current_start = char_pos - sum(len(b) + 2 for b in overlap_blocks)

        current_blocks.append(para)
        current_tokens += para_tokens
        char_pos += len(para) + 2

    if current_blocks:
        chunk_text_str = "\n\n".join(current_blocks)
        if _estimate_tokens(chunk_text_str) >= MIN_CHUNK_TOKENS:
            breadcrumb = " > ".join(t for _, t in header_stack)
            chunks.append(Chunk(
                index=len(chunks),
                content=chunk_text_str,
                page=page,
                start_char=current_start,
                token_count=_estimate_tokens(chunk_text_str),
                header_breadcrumb=breadcrumb,
            ))

    return chunks


def chunk_pages(page_contents: list[tuple[int, str]]) -> list[Chunk]:
    """Chunk multiple pages, preserving page numbers. Each (page_number, content) tuple."""
    all_chunks: list[Chunk] = []
    for page_num, content in page_contents:
        page_chunks = chunk_text(content, page=page_num)
        for c in page_chunks:
            c.index = len(all_chunks)
            all_chunks.append(c)
    return all_chunks


def _split_paragraphs(text: str) -> list[str]:
    """Split on double newlines, preserving paragraph structure."""
    parts = re.split(r'\n\s*\n', text)
    return [p.strip() for p in parts if p.strip()]


def _get_overlap(blocks: list[str], target_tokens: int) -> tuple[list[str], int]:
    """Get trailing blocks that fit within target_tokens for overlap."""
    result: list[str] = []
    tokens = 0
    for block in reversed(blocks):
        block_tokens = _estimate_tokens(block)
        if tokens + block_tokens > target_tokens:
            break
        result.insert(0, block)
        tokens += block_tokens
    return result, tokens
