from __future__ import annotations

import threading
from typing import Dict, Optional

from shared.logging import get_logger


class BudgetManager:
    """Tracks and enforces token budgets per agent.

    - `max_budgets` is a mapping agent_id -> max tokens allowed.
    - `usage` tracks consumed tokens per agent.
    - `consume()` records usage and returns True if allowed.
      It logs violations rather than silently truncating.
    - `remaining()` returns remaining tokens for an agent.
    - `requires_compression()` is a heuristic that signals when remaining
      budget is low (default threshold 10%).

    The component is intentionally small, thread-safe, and framework-agnostic.
    """

    def __init__(self, max_budgets: Optional[Dict[str, int]] = None, warning_threshold: float = 0.1):
        self._lock = threading.Lock()
        self.max_budgets: Dict[str, int] = dict(max_budgets or {})
        self.usage: Dict[str, int] = {k: 0 for k in self.max_budgets}
        self.warning_threshold = max(0.0, min(1.0, warning_threshold))
        self._logger = get_logger("BudgetManager")

    def set_budget(self, agent_id: str, max_tokens: int) -> None:
        with self._lock:
            self.max_budgets[agent_id] = int(max_tokens)
            self.usage.setdefault(agent_id, 0)

    def consume(self, agent_id: str, tokens: int) -> bool:
        """Consume `tokens` for `agent_id`.

        Returns True when the consumption is recorded. If the consumption
        would exceed the declared budget, records a violation through logging
        and still records the usage (so overages are observable).
        """
        tokens = int(tokens)
        with self._lock:
            if agent_id not in self.usage:
                # If no budget set, default to unlimited but log the condition.
                self.usage[agent_id] = 0
                self._logger.warning("consume called for agent without budget: %s", agent_id)

            self.usage[agent_id] += tokens

            max_b = self.max_budgets.get(agent_id)
            if max_b is None:
                return True

            if self.usage[agent_id] > max_b:
                self._logger.error(
                    "budget violation for agent=%s used=%d max=%d",
                    agent_id,
                    self.usage[agent_id],
                    max_b,
                )
                return False

            # Optionally warn near threshold
            if self.usage[agent_id] / max_b >= (1 - self.warning_threshold):
                self._logger.warning(
                    "budget nearing limit for agent=%s used=%d max=%d",
                    agent_id,
                    self.usage[agent_id],
                    max_b,
                )

            return True

    def remaining(self, agent_id: str) -> Optional[int]:
        with self._lock:
            max_b = self.max_budgets.get(agent_id)
            used = self.usage.get(agent_id, 0)
            if max_b is None:
                return None
            return max_b - used

    def requires_compression(self, agent_id: str, threshold: Optional[float] = None) -> bool:
        """Heuristic: returns True if the remaining budget is below threshold.

        Default uses the manager warning threshold.
        """
        thr = self.warning_threshold if threshold is None else threshold
        rem = self.remaining(agent_id)
        if rem is None:
            return False
        max_b = self.max_budgets[agent_id]
        return (rem / max_b) <= thr

    def get_usage(self, agent_id: str) -> int:
        return int(self.usage.get(agent_id, 0))

    def snapshot(self) -> Dict[str, int]:
        with self._lock:
            return dict(self.usage)
