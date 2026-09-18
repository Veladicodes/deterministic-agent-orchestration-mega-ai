"""Tests for the deterministic contradiction-rule tiers.

Each tier is tested in isolation to document exactly what class of
contradiction it catches and to lock in deterministic, reproducible
behavior (same inputs -> same evidence, every run).
"""

from __future__ import annotations

from agents.contradiction_rules import (
    detect_keyword_contradiction,
    detect_numeric_contradiction,
    detect_negation_contradiction,
    detect_contradiction,
    NUMERIC_DIVERGENCE_THRESHOLD,
)


class TestKeywordContradiction:
    def test_detects_direct_antonym_pair(self):
        evidence = detect_keyword_contradiction("The answer is yes.", "The answer is no.")
        assert evidence is not None
        assert evidence["rule"] == "keyword_pair"

    def test_returns_none_for_unrelated_text(self):
        evidence = detect_keyword_contradiction("The sky is blue.", "Water is wet.")
        assert evidence is None


class TestNumericContradiction:
    def test_detects_diverging_numeric_claims_on_shared_subject(self):
        evidence = detect_numeric_contradiction(
            "Model accuracy is 76%.",
            "Model accuracy is 91%.",
        )
        assert evidence is not None
        assert evidence["rule"] == "numeric_divergence"
        assert evidence["subject"] == "model accuracy"
        assert evidence["divergence"] == 15.0

    def test_ignores_small_divergence_within_threshold(self):
        evidence = detect_numeric_contradiction(
            "Model accuracy is 80%.",
            "Model accuracy is 82%.",
        )
        assert evidence is None

    def test_ignores_numeric_claims_about_different_subjects(self):
        evidence = detect_numeric_contradiction(
            "Model accuracy is 76%.",
            "Server uptime is 99%.",
        )
        assert evidence is None

    def test_boundary_at_threshold_is_flagged(self):
        evidence = detect_numeric_contradiction(
            f"Coverage is 50%.",
            f"Coverage is {50 + NUMERIC_DIVERGENCE_THRESHOLD}%.",
        )
        assert evidence is not None
        assert evidence["divergence"] == NUMERIC_DIVERGENCE_THRESHOLD


class TestNegationContradiction:
    def test_detects_assertion_vs_negated_assertion(self):
        evidence = detect_negation_contradiction(
            "The pipeline improved significantly after the change.",
            "The pipeline did not improve after the change.",
        )
        assert evidence is not None
        assert evidence["rule"] == "negation"
        assert evidence["keyword"] == "improved" or evidence["keyword"] == "change"

    def test_returns_none_when_both_sides_agree(self):
        evidence = detect_negation_contradiction(
            "The pipeline improved after the change.",
            "The pipeline improved significantly.",
        )
        assert evidence is None


class TestDetectContradictionDispatcher:
    def test_prefers_keyword_tier_when_multiple_tiers_could_match(self):
        evidence = detect_contradiction("The result is yes.", "The result is no.")
        assert evidence["rule"] == "keyword_pair"

    def test_falls_through_to_numeric_tier(self):
        evidence = detect_contradiction("Latency is 120ms and throughput is 40%.", "Throughput is 95%.")
        assert evidence["rule"] == "numeric_divergence"

    def test_returns_none_when_no_tier_matches(self):
        evidence = detect_contradiction("The sky is blue.", "Grass is green.")
        assert evidence is None

    def test_is_deterministic_across_repeated_calls(self):
        text1 = "Accuracy is 70%."
        text2 = "Accuracy is 95%."
        results = [detect_contradiction(text1, text2) for _ in range(5)]
        assert all(r == results[0] for r in results)
