"""Deterministic, explainable contradiction-detection rules for CriticAgent.

Extracted from `agents/critic.py` so each rule tier is independently
testable and the rationale for each detection is visible as data (not
buried in a black-box model call). Three tiers, in increasing order of
sophistication, all deterministic given the same input text:

1. Keyword-pair contradictions (the original fixed antonym list) — cheap,
   exact, catches direct assertions like "yes" vs "no".
2. Numeric-divergence contradictions — catches conflicting numeric claims
   about the same subject (e.g. "accuracy is 76%" vs "accuracy is 82%"),
   a class of contradiction the keyword list cannot see at all.
3. Negation-aware contradictions — catches a claim and its negated form
   sharing a keyword (e.g. "the model improved" vs "the model did not
   improve").

Each detector returns a small, structured evidence dict rather than a
bare boolean, so CriticAgent can attach a human-readable justification to
every flagged claim (explainability was the project's own stated reason
for not using an LLM judge; this module keeps that property while fixing
the keyword list's real blind spots).
"""

from __future__ import annotations

import re
from typing import Dict, List, Optional

# Tier 1: keyword-pair contradictions (unchanged from the original
# CriticAgent.CONTRADICTION_KEYWORDS, moved here for independent testing).
KEYWORD_CONTRADICTIONS = {
    ("yes", "no"),
    ("true", "false"),
    ("agree", "disagree"),
    ("support", "oppose"),
    ("increase", "decrease"),
    ("positive", "negative"),
    ("good", "bad"),
}

# Tier 2: numeric-divergence detection.
_NUMERIC_CLAIM_PATTERN = re.compile(
    r"(?P<subject>[a-zA-Z][a-zA-Z _-]{1,40}?)\s+(?:is|was|are|were|of|at|reached|hit)\s+(?:about|approximately|roughly)?\s*"
    r"(?P<value>\d{1,3}(?:\.\d+)?)\s*(?:%|percent)",
    re.IGNORECASE,
)

# Minimum absolute point difference between two numeric claims about the
# same subject before it's treated as a contradiction rather than normal
# measurement variance.
NUMERIC_DIVERGENCE_THRESHOLD = 8.0

# Words too generic to anchor a subject match on their own (avoids
# false positives like "the rate is 10%" vs "the rate is 90%" for two
# genuinely unrelated rates).
_STOPWORDS = {"the", "a", "an", "its", "this", "that", "overall", "total"}

# Tier 3: negation-aware contradiction detection.
_NEGATION_MARKERS = ("not", "never", "no longer", "cannot", "can't", "doesn't", "didn't", "isn't", "wasn't", "won't")

# Common connector/function words excluded as negation anchors so the
# reported keyword is a meaningful content word (e.g. "improve") rather
# than an incidental preposition (e.g. "after") that happens to sit near
# a negation marker.
_NEGATION_IGNORE_WORDS = {
    "after",
    "before",
    "during",
    "while",
    "since",
    "because",
    "although",
    "however",
    "significantly",
    "really",
    "very",
    "quite",
    "more",
    "less",
    "further",
    "then",
    "than",
    "also",
    "still",
    "with",
    "from",
    "into",
    "onto",
    "about",
}


def _extract_numeric_claims(text: str) -> List[Dict[str, object]]:
    claims = []
    for match in _NUMERIC_CLAIM_PATTERN.finditer(text):
        subject_words = [w for w in match.group("subject").lower().split() if w not in _STOPWORDS]
        if not subject_words:
            continue
        claims.append(
            {
                "subject": " ".join(subject_words),
                "value": float(match.group("value")),
                "raw": match.group(0),
            }
        )
    return claims


def _subjects_overlap(subject1: str, subject2: str) -> bool:
    words1 = set(subject1.split())
    words2 = set(subject2.split())
    return bool(words1 & words2)


def detect_keyword_contradiction(text1: str, text2: str) -> Optional[Dict[str, object]]:
    """Tier 1: fixed antonym-pair matching (deterministic, exact).

    Returns evidence dict with the matched keywords, or None.
    """
    lower1, lower2 = text1.lower(), text2.lower()
    for keyword1, keyword2 in KEYWORD_CONTRADICTIONS:
        if keyword1 in lower1 and keyword2 in lower2:
            return {"rule": "keyword_pair", "keyword_a": keyword1, "keyword_b": keyword2}
        if keyword1 in lower2 and keyword2 in lower1:
            return {"rule": "keyword_pair", "keyword_a": keyword2, "keyword_b": keyword1}
    return None


def detect_numeric_contradiction(text1: str, text2: str) -> Optional[Dict[str, object]]:
    """Tier 2: conflicting numeric claims about the same subject.

    Example: "accuracy is 76%" vs "accuracy is 82%" -> flagged (8+ point
    divergence on the shared subject "accuracy"). Deterministic and
    explainable: the evidence dict names the exact subject, both values,
    and the divergence.

    Returns evidence dict, or None.
    """
    claims1 = _extract_numeric_claims(text1)
    claims2 = _extract_numeric_claims(text2)

    for claim1 in claims1:
        for claim2 in claims2:
            if not _subjects_overlap(claim1["subject"], claim2["subject"]):
                continue
            divergence = abs(claim1["value"] - claim2["value"])
            if divergence >= NUMERIC_DIVERGENCE_THRESHOLD:
                return {
                    "rule": "numeric_divergence",
                    "subject": claim1["subject"],
                    "value_a": claim1["value"],
                    "value_b": claim2["value"],
                    "divergence": divergence,
                    "claim_a": claim1["raw"],
                    "claim_b": claim2["raw"],
                }
    return None


def _negated_keyword_positions(text: str, keyword: str) -> List[bool]:
    """Return, for each occurrence of `keyword` in `text`, whether a
    negation marker appears within the preceding 4 words."""
    lower = text.lower()
    tokens = lower.split()
    results = []
    for idx, token in enumerate(tokens):
        if keyword not in token:
            continue
        window = tokens[max(0, idx - 4) : idx]
        negated = any(marker in " ".join(window) for marker in _NEGATION_MARKERS)
        results.append(negated)
    return results


def detect_negation_contradiction(text1: str, text2: str) -> Optional[Dict[str, object]]:
    """Tier 3: a shared keyword asserted plainly in one text and negated
    in the other (e.g. "the model improved" vs "the model did not
    improve").

    Deterministic (fixed negation marker list, fixed window size).
    Returns evidence dict, or None.
    """
    words1 = {w.strip(".,!?;:") for w in text1.lower().split() if len(w) > 3}
    words2 = {w.strip(".,!?;:") for w in text2.lower().split() if len(w) > 3}
    shared = (words1 & words2) - _STOPWORDS - _NEGATION_IGNORE_WORDS

    # Sorted for determinism: Python's string hashing is randomized per
    # process (PYTHONHASHSEED), so iterating a `set` directly could report
    # a different anchor keyword across otherwise-identical runs, which
    # would undermine execution-trace replay guarantees.
    for keyword in sorted(shared):
        negated1 = _negated_keyword_positions(text1, keyword)
        negated2 = _negated_keyword_positions(text2, keyword)
        if not negated1 or not negated2:
            continue
        # Contradiction: asserted (not negated) in one text, negated in the other.
        if (any(not n for n in negated1) and any(n for n in negated2)) or (
            any(n for n in negated1) and any(not n for n in negated2)
        ):
            return {"rule": "negation", "keyword": keyword}
    return None


def detect_contradiction(text1: str, text2: str) -> Optional[Dict[str, object]]:
    """Run all tiers in order (cheapest/most-precise first) and return the
    first match's evidence, or None if no tier finds a contradiction."""
    for detector in (detect_keyword_contradiction, detect_numeric_contradiction, detect_negation_contradiction):
        evidence = detector(text1, text2)
        if evidence:
            return evidence
    return None
