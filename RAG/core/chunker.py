"""
RAG Text Chunker
Splits text into chunks and computes SHA-256 content hashes.
"""
import hashlib
from typing import List, Dict, Any


def hash_content(text: str) -> str:
    """Compute SHA-256 hash of text."""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def chunk_text(text: str, chunk_size: int = 500, overlap: int = 50) -> List[Dict[str, Any]]:
    """
    Split text into chunks with simple sliding window.
    Returns list of dicts with index, content, content_hash, token_count.
    """
    if not text:
        return []

    words = text.split()
    if not words:
        return []

    chunks = []
    idx = 0
    start = 0

    while start < len(words):
        end = min(start + chunk_size, len(words))
        chunk_words = words[start:end]
        chunk_str = " ".join(chunk_words)
        chunks.append({
            "chunk_index": idx,
            "content": chunk_str,
            "content_hash": hash_content(chunk_str),
            "token_count": len(chunk_words),  # Approximate word count as tokens
        })
        idx += 1
        if end == len(words):
            break
        start += max(1, chunk_size - overlap)

    return chunks
