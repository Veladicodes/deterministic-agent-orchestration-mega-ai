"""persistence backbone

Revision ID: 0002_persistence_backbone
Revises: 0001_initial
Create Date: 2026-05-08
"""

from alembic import op
import sqlalchemy as sa


revision = "0002_persistence_backbone"
down_revision = "0001_initial"
branch_labels = None
depends_on = None


execution_status = sa.Enum(
    "pending",
    "running",
    "succeeded",
    "failed",
    "cancelled",
    name="execution_status",
    native_enum=False,
)

failure_mode = sa.Enum(
    "timeout",
    "empty",
    "malformed",
    "internal",
    "none",
    name="failure_mode",
    native_enum=False,
)

review_status = sa.Enum(
    "pending",
    "approved",
    "rejected",
    name="review_status",
    native_enum=False,
)


def upgrade() -> None:
    op.create_table(
        "jobs",
        sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("original_query", sa.Text(), nullable=False),
        sa.Column("status", execution_status, nullable=False, server_default="pending"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_jobs_status_created_at", "jobs", ["status", "created_at"])

    op.create_table(
        "agent_logs",
        sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("job_id", sa.Uuid(as_uuid=True), sa.ForeignKey("jobs.id", ondelete="CASCADE"), nullable=False),
        sa.Column("agent_id", sa.String(length=128), nullable=False),
        sa.Column("event_type", sa.String(length=64), nullable=False),
        sa.Column("input_payload", sa.JSON(), nullable=False),
        sa.Column("output_payload", sa.JSON(), nullable=False),
        sa.Column("token_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("latency_ms", sa.Float(), nullable=True),
        sa.Column("policy_violations", sa.JSON(), nullable=False),
        sa.Column("timestamp", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_agent_logs_job_id_timestamp", "agent_logs", ["job_id", "timestamp"])
    op.create_index("ix_agent_logs_agent_id_event_type", "agent_logs", ["agent_id", "event_type"])

    op.create_table(
        "tool_calls",
        sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("job_id", sa.Uuid(as_uuid=True), sa.ForeignKey("jobs.id", ondelete="CASCADE"), nullable=False),
        sa.Column("tool_name", sa.String(length=128), nullable=False),
        sa.Column("input_payload", sa.JSON(), nullable=False),
        sa.Column("output_payload", sa.JSON(), nullable=False),
        sa.Column("retry_number", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("latency_ms", sa.Float(), nullable=True),
        sa.Column("accepted", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("failure_mode", failure_mode, nullable=False, server_default="none"),
        sa.Column("timestamp", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_tool_calls_job_id_timestamp", "tool_calls", ["job_id", "timestamp"])
    op.create_index("ix_tool_calls_tool_name_timestamp", "tool_calls", ["tool_name", "timestamp"])

    op.create_table(
        "eval_runs",
        sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("triggered_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.Column("category", sa.String(length=128), nullable=False),
        sa.Column("summary_scores", sa.JSON(), nullable=False),
        sa.Column("justifications", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_eval_runs_category_triggered_at", "eval_runs", ["category", "triggered_at"])

    op.create_table(
        "prompt_rewrites",
        sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("agent_id", sa.String(length=128), nullable=False),
        sa.Column("original_prompt", sa.Text(), nullable=False),
        sa.Column("proposed_prompt", sa.Text(), nullable=False),
        sa.Column("diff", sa.Text(), nullable=False),
        sa.Column("justification", sa.Text(), nullable=False),
        sa.Column("status", review_status, nullable=False, server_default="pending"),
        sa.Column("proposed_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_prompt_rewrites_agent_id_status", "prompt_rewrites", ["agent_id", "status"])
    op.create_index("ix_prompt_rewrites_proposed_at", "prompt_rewrites", ["proposed_at"])


def downgrade() -> None:
    op.drop_index("ix_prompt_rewrites_proposed_at", table_name="prompt_rewrites")
    op.drop_index("ix_prompt_rewrites_agent_id_status", table_name="prompt_rewrites")
    op.drop_table("prompt_rewrites")

    op.drop_index("ix_eval_runs_category_triggered_at", table_name="eval_runs")
    op.drop_table("eval_runs")

    op.drop_index("ix_tool_calls_tool_name_timestamp", table_name="tool_calls")
    op.drop_index("ix_tool_calls_job_id_timestamp", table_name="tool_calls")
    op.drop_table("tool_calls")

    op.drop_index("ix_agent_logs_agent_id_event_type", table_name="agent_logs")
    op.drop_index("ix_agent_logs_job_id_timestamp", table_name="agent_logs")
    op.drop_table("agent_logs")

    op.drop_index("ix_jobs_status_created_at", table_name="jobs")
    op.drop_table("jobs")
