from __future__ import annotations

from datetime import datetime
from uuid import UUID
from typing import Any, TYPE_CHECKING

from sqlalchemy import Boolean, DateTime, Enum as SAEnum, Float, ForeignKey, Index, Integer, JSON, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import Uuid

from db.base import Base
from db.mixins import TimestampMixin, UUIDPrimaryKeyMixin
from shared.enums import ExecutionStatus, FailureMode, ReviewStatus


class Job(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Top-level persisted execution job.

    The model stays deliberately small so all future trace artifacts can
    anchor back to a single job record.
    """

    __tablename__ = "jobs"
    __table_args__ = (
        Index("ix_jobs_status_created_at", "status", "created_at"),
    )

    original_query: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[ExecutionStatus] = mapped_column(
        SAEnum(
            ExecutionStatus,
            name="execution_status",
            native_enum=False,
            values_callable=lambda enum_cls: [e.value for e in enum_cls],
        ),
        nullable=False,
        default=ExecutionStatus.PENDING,
        server_default=ExecutionStatus.PENDING.value,
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    def __init__(self, **kwargs: Any):
        kwargs.setdefault("status", ExecutionStatus.PENDING)
        super().__init__(**kwargs)

    agent_logs: Mapped[list[AgentLog]] = relationship(
        back_populates="job",
        cascade="all, delete-orphan",
        lazy="selectin",
    )
    tool_calls: Mapped[list[ToolCall]] = relationship(
        back_populates="job",
        cascade="all, delete-orphan",
        lazy="selectin",
    )


class AgentLog(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Structured log row for an agent event."""

    __tablename__ = "agent_logs"
    __table_args__ = (
        Index("ix_agent_logs_job_id_timestamp", "job_id", "timestamp"),
        Index("ix_agent_logs_agent_id_event_type", "agent_id", "event_type"),
    )

    job_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("jobs.id", ondelete="CASCADE"), nullable=False)
    agent_id: Mapped[str] = mapped_column(String(128), nullable=False)
    event_type: Mapped[str] = mapped_column(String(64), nullable=False)
    input_payload: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    output_payload: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    token_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    latency_ms: Mapped[float | None] = mapped_column(Float, nullable=True)
    policy_violations: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())

    job: Mapped[Job] = relationship(back_populates="agent_logs")


class ToolCall(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Structured log row for a tool execution."""

    __tablename__ = "tool_calls"
    __table_args__ = (
        Index("ix_tool_calls_job_id_timestamp", "job_id", "timestamp"),
        Index("ix_tool_calls_tool_name_timestamp", "tool_name", "timestamp"),
    )

    job_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("jobs.id", ondelete="CASCADE"), nullable=False)
    tool_name: Mapped[str] = mapped_column(String(128), nullable=False)
    input_payload: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    output_payload: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    retry_number: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    latency_ms: Mapped[float | None] = mapped_column(Float, nullable=True)
    accepted: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    failure_mode: Mapped[FailureMode] = mapped_column(
        SAEnum(
            FailureMode,
            name="failure_mode",
            native_enum=False,
            values_callable=lambda enum_cls: [e.value for e in enum_cls],
        ),
        nullable=False,
        default=FailureMode.NONE,
        server_default=FailureMode.NONE.value,
    )
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())

    def __init__(self, **kwargs: Any):
        kwargs.setdefault("failure_mode", FailureMode.NONE)
        kwargs.setdefault("accepted", False)
        kwargs.setdefault("retry_number", 0)
        super().__init__(**kwargs)

    job: Mapped[Job] = relationship(back_populates="tool_calls")


class EvalRun(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Stored evaluation run summary used for reproducibility and audit."""

    __tablename__ = "eval_runs"
    __table_args__ = (
        Index("ix_eval_runs_category_triggered_at", "category", "triggered_at"),
    )

    triggered_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    category: Mapped[str] = mapped_column(String(128), nullable=False)
    summary_scores: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    justifications: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)


class PromptRewrite(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Stores proposed prompt rewrites for review and reproducibility."""

    __tablename__ = "prompt_rewrites"
    __table_args__ = (
        Index("ix_prompt_rewrites_agent_id_status", "agent_id", "status"),
        Index("ix_prompt_rewrites_proposed_at", "proposed_at"),
    )

    agent_id: Mapped[str] = mapped_column(String(128), nullable=False)
    original_prompt: Mapped[str] = mapped_column(Text, nullable=False)
    proposed_prompt: Mapped[str] = mapped_column(Text, nullable=False)
    diff: Mapped[str] = mapped_column(Text, nullable=False)
    justification: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[ReviewStatus] = mapped_column(
        SAEnum(
            ReviewStatus,
            name="review_status",
            native_enum=False,
            values_callable=lambda enum_cls: [e.value for e in enum_cls],
        ),
        nullable=False,
        default=ReviewStatus.PENDING,
        server_default=ReviewStatus.PENDING.value,
    )
    proposed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    def __init__(self, **kwargs: Any):
        kwargs.setdefault("status", ReviewStatus.PENDING)
        super().__init__(**kwargs)
