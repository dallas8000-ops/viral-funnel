from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import JSON, DateTime, Float, Index, Integer, String, Text, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class OperatorConfig(Base):
    __tablename__ = "operator_config"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    niche: Mapped[str] = mapped_column(String(240), default="")
    voice: Mapped[str] = mapped_column(Text, default="")
    enemy: Mapped[str] = mapped_column(Text, default="")
    promise: Mapped[str] = mapped_column(Text, default="")
    offer_name: Mapped[str] = mapped_column(String(240), default="")
    offer_bullets: Mapped[str] = mapped_column(Text, default="")
    subs: Mapped[str] = mapped_column(Text, default="Entrepreneur,smallbusiness,marketing,sales")
    day_zero: Mapped[str] = mapped_column(String(32), default="")
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    stripe_price_id: Mapped[str] = mapped_column(String(64), default="")


class SourceItem(Base):
    __tablename__ = "source_items"
    __table_args__ = (
        Index("ix_source_hash", "content_hash", unique=True),
        Index("ix_source_score", "score"),
        Index("ix_source_seen", "seen_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    content_hash: Mapped[str] = mapped_column(String(64))
    platform: Mapped[str] = mapped_column(String(32))
    url: Mapped[str] = mapped_column(Text, default="")
    title: Mapped[str] = mapped_column(Text)
    body: Mapped[str] = mapped_column(Text, default="")
    score: Mapped[float] = mapped_column(Float, default=0)
    raw: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class FactoryJob(Base):
    __tablename__ = "factory_jobs"
    __table_args__ = (
        Index("ix_job_status", "status"),
        Index("ix_job_source", "source_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    source_id: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(24), default="queued")
    hook: Mapped[str] = mapped_column(Text, default="")
    caption: Mapped[str] = mapped_column(Text, default="")
    reel_script: Mapped[str] = mapped_column(Text, default="")
    slides: Mapped[list[Any]] = mapped_column(JSON, default=list)
    asset_dir: Mapped[str] = mapped_column(Text, default="")
    error: Mapped[str] = mapped_column(Text, default="")
    timings_ms: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class ScheduledPost(Base):
    __tablename__ = "scheduled_posts"
    __table_args__ = (
        Index("ix_post_when_status", "publish_at", "status"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    job_id: Mapped[int] = mapped_column(Integer)
    kind: Mapped[str] = mapped_column(String(24))
    publish_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    status: Mapped[str] = mapped_column(String(24), default="pending")
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    last_error: Mapped[str] = mapped_column(Text, default="")
    published_url: Mapped[str] = mapped_column(Text, default="")


class Member(Base):
    __tablename__ = "members"
    __table_args__ = (Index("ix_member_email", "email", unique=True),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    email: Mapped[str] = mapped_column(String(320))
    stripe_customer_id: Mapped[str] = mapped_column(String(64), default="")
    stripe_subscription_id: Mapped[str] = mapped_column(String(64), default="")
    status: Mapped[str] = mapped_column(String(24), default="active")
    access_token: Mapped[str] = mapped_column(String(64), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class PipelineRun(Base):
    __tablename__ = "pipeline_runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    kind: Mapped[str] = mapped_column(String(32))
    ok: Mapped[int] = mapped_column(Integer, default=1)
    stats: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    duration_ms: Mapped[int] = mapped_column(Integer, default=0)
