from collections import Counter


def extract_trigrams(text: str) -> Counter[str]:
    """Generate padded trigrams from input string matching PostgreSQL pg_trgm behavior."""
    if not text:
        return Counter()
    padded = f"  {text} "
    trigrams = [padded[i : i + 3] for i in range(len(padded) - 2)]
    return Counter(trigrams)


def trigram_similarity(s1: str, s2: str) -> float:
    """Calculate trigram similarity between two strings."""
    c1 = extract_trigrams(s1.lower().strip())
    c2 = extract_trigrams(s2.lower().strip())

    if not c1 and not c2:
        return 1.0
    if not c1 or not c2:
        return 0.0

    # Intersection and union counts
    intersection = sum((c1 & c2).values())
    union = sum((c1 | c2).values())

    if union == 0:
        return 0.0

    return round(float(intersection / union), 4)
