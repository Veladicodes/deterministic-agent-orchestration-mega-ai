from __future__ import annotations

import json
import logging
from datetime import datetime
from typing import Any, Dict, Optional

from shared.logging import get_logger


class ExecutionLogger:
    """Structured JSON execution logger.

    Produces compact, single-line JSON records suitable for ingestion into
    log collectors. Fields include timestamp, agent_id, event_type, latency,
    token_count, job_id, and optional policy_violation information.
    """

    def __init__(self, service_name: str = "mega-ai"):
        self._logger = get_logger("exec")
        self.service = service_name

    def log_event(
        self,
        agent_id: str,
        event_type: str,
        latency: Optional[float] = None,
        token_count: Optional[int] = None,
        job_id: Optional[str] = None,
        policy_violation: Optional[str] = None,
        extra: Optional[Dict[str, Any]] = None,
    ) -> None:
        rec = {
            "ts": datetime.utcnow().isoformat() + "Z",
            "service": self.service,
            "agent_id": agent_id,
            "event_type": event_type,
        }
        if latency is not None:
            rec["latency_ms"] = float(latency)
        if token_count is not None:
            rec["token_count"] = int(token_count)
        if job_id is not None:
            rec["job_id"] = job_id
        if policy_violation is not None:
            rec["policy_violation"] = policy_violation
        if extra:
            rec["extra"] = extra

        # Use the application logger so the runtime decides where JSON goes.
        self._logger.info(json.dumps(rec, default=str))
