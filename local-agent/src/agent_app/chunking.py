from __future__ import annotations
from typing import List, Tuple

def chunk_text(text: str, target_tokens: int = 800, overlap: int = 80) -> List[Tuple[int, int, str]]:
    """
    Token-agnostic char-based chunking. Good enough for local RAG.
    Returns list of (start_char, end_char, chunk_text).
    """
    if not text:
        return []
    # Approximate token ~ 4 chars; adjust as needed
    approx_chars = max(200, target_tokens * 4)
    stride = max(0, approx_chars - overlap * 4)

    chunks = []
    i = 0
    n = len(text)
    while i < n:
        j = min(n, i + approx_chars)
        chunks.append((i, j, text[i:j]))
        if j == n:
            break
        i += stride if stride > 0 else approx_chars
    return chunks
