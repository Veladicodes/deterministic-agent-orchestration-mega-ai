"""RetryCoordinator implementation.

Centralized retry handling with exponential backoff and exhaustion tracking.
"""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass
from typing import Optional

from shared.logging import get_logger
from orchestration.schemas import RetryRecord


@dataclass
class RetryConfig:
    """Configuration for retry behavior.

    Attributes:
        max_retries: Maximum number of retry attempts (0 = no retries).
        initial_backoff_ms: Initial backoff delay in milliseconds.
        backoff_multiplier: Exponential multiplier per retry (default 2.0).
        max_backoff_ms: Cap on backoff delay to prevent excessive waits.
    """

    max_retries: int = 3
    initial_backoff_ms: float = 100.0
    backoff_multiplier: float = 2.0
    max_backoff_ms: float = 30000.0  # 30 seconds

    def __post_init__(self):
        """Validate config values."""
        self.max_retries = max(0, int(self.max_retries))
        self.initial_backoff_ms = max(10.0, float(self.initial_backoff_ms))
        self.backoff_multiplier = max(1.0, float(self.backoff_multiplier))
        self.max_backoff_ms = max(self.initial_backoff_ms, float(self.max_backoff_ms))


class RetryCoordinator:
    """Manages retry attempts with exponential backoff.

    - Tracks retry attempts per operation
    - Computes exponential backoff delays
    - Detects retry exhaustion
    - Records all retry events
    - Supports async waiting with cancellation
    """

    def __init__(self, config: Optional[RetryConfig] = None):
        """Initialize with retry configuration.

        Args:
            config: RetryConfig instance (uses defaults if None).
        """
        self.config = config or RetryConfig()
        self._logger = get_logger("retry_coordinator")
        self._retry_records: dict[str, list[RetryRecord]] = {}  # operation_id -> list of retry records

    async def execute_with_retry(
        self,
        operation_id: str,
        async_func,
        *args,
        **kwargs,
    ) -> tuple[bool, object, list[RetryRecord]]:
        """Execute an async function with retry logic.

        Automatically retries on failure with exponential backoff.

        Args:
            operation_id: Unique identifier for this operation (for tracking).
            async_func: Async function to execute.
            *args: Positional arguments for async_func.
            **kwargs: Keyword arguments for async_func.

        Returns:
            Tuple of (success, result, retry_records) where:
            - success: True if operation succeeded
            - result: Return value on success or exception on failure
            - retry_records: List of all retry attempts
        """
        if operation_id not in self._retry_records:
            self._retry_records[operation_id] = []

        retry_records = self._retry_records[operation_id]

        for attempt in range(self.config.max_retries + 1):
            try:
                start_time = time.perf_counter()
                result = await async_func(*args, **kwargs)
                latency_ms = (time.perf_counter() - start_time) * 1000.0

                # Success on first attempt
                if attempt == 0:
                    self._logger.debug("operation %s succeeded on first attempt", operation_id)
                    return True, result, []

                # Success after retries
                self._logger.info(
                    "operation %s succeeded on attempt %d after %d retries",
                    operation_id,
                    attempt,
                    attempt - 1,
                )
                return True, result, retry_records

            except Exception as e:
                latency_ms = (time.perf_counter() - start_time) * 1000.0
                error_msg = str(e)

                record = RetryRecord(
                    retry_number=attempt,
                    latency_ms=latency_ms,
                    success=False,
                    failure_mode=type(e).__name__,
                    error_message=error_msg,
                )
                retry_records.append(record)

                # Check if we should retry
                if attempt >= self.config.max_retries:
                    self._logger.error(
                        "operation %s exhausted retries (%d attempts). final error: %s",
                        operation_id,
                        attempt + 1,
                        error_msg,
                    )
                    return False, e, retry_records

                # Compute backoff delay
                backoff_ms = self._compute_backoff(attempt)
                self._logger.warning(
                    "operation %s failed on attempt %d, retrying in %.0f ms: %s",
                    operation_id,
                    attempt + 1,
                    backoff_ms,
                    error_msg,
                )

                # Wait before retry
                await asyncio.sleep(backoff_ms / 1000.0)

        # Should not reach here, but return failure if we do
        return False, None, retry_records

    def check_exhausted(self, operation_id: str) -> bool:
        """Check if retry budget is exhausted for an operation.

        Returns:
            True if all retries have been used.
        """
        if operation_id not in self._retry_records:
            return False

        records = self._retry_records[operation_id]
        if not records:
            return False

        # If we have max_retries + 1 failed records (initial + retries), retries are exhausted
        return len(records) > self.config.max_retries

    def get_retry_count(self, operation_id: str) -> int:
        """Get total retry attempts for an operation.

        Returns:
            Number of retries attempted.
        """
        if operation_id not in self._retry_records:
            return 0

        records = self._retry_records[operation_id]
        return len(records) - 1 if records else 0  # Subtract 1 for initial attempt

    def get_retry_records(self, operation_id: str) -> list[RetryRecord]:
        """Get all retry records for an operation.

        Returns:
            List of RetryRecord objects.
        """
        return self._retry_records.get(operation_id, [])

    def clear_records(self, operation_id: Optional[str] = None) -> None:
        """Clear retry records.

        Args:
            operation_id: If provided, clear records for this operation only.
                         If None, clear all records.
        """
        if operation_id:
            if operation_id in self._retry_records:
                del self._retry_records[operation_id]
        else:
            self._retry_records.clear()

    def _compute_backoff(self, attempt: int) -> float:
        """Compute exponential backoff delay in milliseconds.

        Formula: min(max_backoff, initial_backoff * (multiplier ^ attempt))

        Args:
            attempt: Which attempt this is (0-indexed).

        Returns:
            Backoff delay in milliseconds.
        """
        # For attempt 0 (first retry after initial failure), use initial backoff
        # For attempt 1, use initial_backoff * multiplier, etc.
        delay = self.config.initial_backoff_ms * (self.config.backoff_multiplier ** attempt)
        return min(delay, self.config.max_backoff_ms)
