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


def trigram_containment(query_text: str, text: str) -> float:
    """Share of the query's trigrams that appear in `text`.

    Asymmetric on purpose, and the same question PostgreSQL's `word_similarity`
    asks -- which is what the candidate search already uses. Jaccard divides by
    the union, so a `search_doc` carrying three scripts and a slug drags the
    score down for being thorough: a query naming a sheet's grade, thickness
    and size scored 0.47 against that exact sheet. Discrimination between
    candidates then comes from the attribute and brand terms, which is where it
    belongs.
    """
    c1 = extract_trigrams(query_text.lower().strip())
    if not c1:
        return 0.0
    c2 = extract_trigrams(text.lower().strip())
    if not c2:
        return 0.0

    intersection = sum((c1 & c2).values())
    return round(float(intersection / sum(c1.values())), 4)


def best_match_similarity(query_text: str, *candidate_texts: str | None) -> float:
    """Best trigram similarity between the query and any candidate text.

    `search_doc` values concatenate several scripts/aliases into one long string
    (see scripts/seed.py), so a short single-word query compared whole-string
    against it gets diluted by all the unrelated trigrams in the rest of the
    blob. Comparing against each individual token too -- in addition to the
    full string -- finds a strong match when the query is (close to) one of
    those tokens, without changing behavior for whole-string/multi-word
    queries that already score well.
    """
    best = 0.0
    for text in candidate_texts:
        if not text:
            continue
        best = max(
            best,
            trigram_similarity(query_text, text),
            trigram_containment(query_text, text),
        )
        for token in text.split():
            best = max(best, trigram_similarity(query_text, token))
        if best == 1.0:
            return best
    return best
