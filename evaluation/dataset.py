"""Evaluation dataset loading and management."""

from __future__ import annotations

import json
from pathlib import Path
from typing import List, Dict, Any, Optional

from shared.logging import get_logger


class EvaluationDataset:
    """Loads and manages evaluation dataset."""

    def __init__(self, dataset_path: str | Path):
        """Initialize dataset loader.

        Args:
            dataset_path: Path to evaluation dataset JSON file.
        """
        self._logger = get_logger("evaluation.dataset")
        self.dataset_path = Path(dataset_path)
        self._data: Dict[str, Any] = {}
        self._entries: List[Dict[str, Any]] = []

    def load(self) -> EvaluationDataset:
        """Load dataset from JSON file.

        Returns:
            Self for chaining.

        Raises:
            FileNotFoundError: If dataset file not found.
            json.JSONDecodeError: If JSON is invalid.
        """
        if not self.dataset_path.exists():
            raise FileNotFoundError(f"Dataset file not found: {self.dataset_path}")

        with open(self.dataset_path, "r") as f:
            self._data = json.load(f)

        self._entries = self._data.get("evaluation_entries", [])
        self._logger.info("loaded dataset with %d entries", len(self._entries))

        return self

    @property
    def metadata(self) -> Dict[str, Any]:
        """Get dataset metadata."""
        return self._data.get("metadata", {})

    @property
    def dataset_id(self) -> str:
        """Get dataset version identifier."""
        return self.metadata.get("dataset_id", "unknown")

    def all_entries(self) -> List[Dict[str, Any]]:
        """Get all evaluation entries.

        Returns:
            List of evaluation entry dictionaries.
        """
        return self._entries.copy()

    def entries_by_category(self, category: str) -> List[Dict[str, Any]]:
        """Get entries for a specific category.

        Args:
            category: Category name (normal, ambiguous, adversarial, etc.)

        Returns:
            List of entries in that category.
        """
        return [e for e in self._entries if e.get("category") == category]

    def get_entry(self, query_id: str) -> Optional[Dict[str, Any]]:
        """Get a specific entry by query ID.

        Args:
            query_id: Query identifier.

        Returns:
            Entry dict or None if not found.
        """
        for entry in self._entries:
            if entry.get("query_id") == query_id:
                return entry
        return None

    def category_distribution(self) -> Dict[str, int]:
        """Get distribution of queries by category.

        Returns:
            Dict mapping category to count.
        """
        dist: Dict[str, int] = {}
        for entry in self._entries:
            category = entry.get("category", "unknown")
            dist[category] = dist.get(category, 0) + 1
        return dist

    def total_entries(self) -> int:
        """Get total number of entries."""
        return len(self._entries)
