"""
memory/embeddings.py

Embedding generation via Google Gemini for Flux.
Model: models/text-embedding-004 → 768-dimensional vectors.
"""

import math
from typing import Optional

from google import genai
from google.genai import types

from config import GEMINI_API_KEY

# ---------------------------------------------------------------------------
# Client (module-level singleton)
# ---------------------------------------------------------------------------

_client = genai.Client(api_key=GEMINI_API_KEY)
_MODEL  = "models/gemini-embedding-001"   # produces 3072-dim vectors
_DIMS   = 3072

# ---------------------------------------------------------------------------
# Public functions
# ---------------------------------------------------------------------------

def generate_embedding(text: str) -> Optional[list[float]]:
    """
    Generate a 768-dimensional embedding for storage / indexing.

    Uses task_type RETRIEVAL_DOCUMENT — optimised for documents being
    inserted into a vector store, not for query-time lookup.

    Returns list of 768 floats, or None on empty input or API failure.
    """
    if not text or not text.strip():
        return None

    try:
        result = _client.models.embed_content(
            model=_MODEL,
            contents=text,
            config=types.EmbedContentConfig(task_type="RETRIEVAL_QUERY"),
        )

        return list(result.embeddings[0].values)
    except Exception as exc:
        print(f"[embeddings] generate_embedding failed: {exc}")
        return None


def generate_query_embedding(text: str) -> Optional[list[float]]:
    """
    Generate a 768-dimensional embedding optimised for similarity search.

    Uses task_type RETRIEVAL_QUERY — aligns query vectors with document
    vectors in the same space for better nearest-neighbour recall.

    Returns list of 768 floats, or None on empty input or API failure.
    """
    if not text or not text.strip():
        return None

    try:
        result = _client.models.embed_content(
            model=_MODEL,
            contents=text,
            config=types.EmbedContentConfig(task_type="RETRIEVAL_QUERY"),
        )
        return list(result.embeddings[0].values)
    except Exception as exc:
        print(f"[embeddings] generate_query_embedding failed: {exc}")
        return None


def cosine_similarity(vec1: list[float], vec2: list[float]) -> float:
    """
    Cosine similarity between two vectors, computed without any ML library.

    Returns float in [-1.0, 1.0]. Returns 0.0 on empty, mismatched, or
    zero-magnitude vectors.
    """
    if not vec1 or not vec2:
        return 0.0

    if len(vec1) != len(vec2):
        print(f"[embeddings] dimension mismatch ({len(vec1)} vs {len(vec2)})")
        return 0.0

    dot_product = sum(a * b for a, b in zip(vec1, vec2))
    mag1 = math.sqrt(sum(a * a for a in vec1))
    mag2 = math.sqrt(sum(b * b for b in vec2))

    if mag1 == 0.0 or mag2 == 0.0:
        return 0.0

    return dot_product / (mag1 * mag2)


# ---------------------------------------------------------------------------
# Standalone test
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    TEST_TEXT = "Ethereum price is rising with strong volume"

    print("=" * 55)
    print("Embedding generation test")
    print("=" * 55)
    print(f"  Input : {TEST_TEXT!r}")

    embedding = generate_embedding(TEST_TEXT)
    if embedding:
        print(f"  Length: {len(embedding)} dimensions")
        print("  First 5 values:")
        for i, val in enumerate(embedding[:5]):
            print(f"    [{i}]  {val:.8f}")
    else:
        print("  Failed to generate embedding.")

    print()
    print("=" * 55)
    print("Cosine similarity sanity check")
    print("=" * 55)

    query_embedding = generate_query_embedding(TEST_TEXT)
    if embedding and query_embedding:
        print(f"  doc vs query (same text) : {cosine_similarity(embedding, query_embedding):.6f}")

    unrelated = generate_embedding("The weather in Paris is cloudy today")
    if embedding and unrelated:
        print(f"  doc vs unrelated text    : {cosine_similarity(embedding, unrelated):.6f}")
