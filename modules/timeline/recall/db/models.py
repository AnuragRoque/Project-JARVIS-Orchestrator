"""SQLAlchemy ORM models for the activity recall database.

Design overview
---------------
* ``applications`` - normalised registry of programs seen (one row per exe).
* ``sessions``     - a continuous foreground-focus session on one window.
                     This is the primary timeline unit produced by capture.
* ``browser_visits`` - a browser tab visit (URL/title/domain/browser).
* ``file_events``  - meaningful file activity (path/name/type/app).
* ``resources``    - detected higher-level resources (coding projects, folders).

A separate FTS5 virtual table ``search_fts`` (created in migrations.py) provides
unified full-text keyword search across all record kinds. It is kept in sync by
the repository layer rather than by triggers, so we control exactly what text is
indexed.
"""
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import (
    ForeignKey,
    Index,
    Integer,
    String,
    Float,
    DateTime,
    Text,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


def utcnow() -> datetime:
    """Naive UTC timestamp. We store naive-UTC everywhere so SQLite datetime
    comparisons stay consistent (mixing aware/naive raises TypeError)."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


class Base(DeclarativeBase):
    pass


class Application(Base):
    __tablename__ = "applications"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    # Process name, e.g. "Code.exe" (lower-cased for stable identity).
    name: Mapped[str] = mapped_column(String(255), index=True)
    exe_path: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    # Friendly name, e.g. "Visual Studio Code".
    display_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    first_seen: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    last_seen: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    # Aggregate usage in seconds (denormalised for quick stats).
    total_seconds: Mapped[float] = mapped_column(Float, default=0.0)

    sessions: Mapped[list["Session"]] = relationship(back_populates="application")

    __table_args__ = (
        Index("ix_applications_name_path", "name", "exe_path", unique=True),
    )


class Session(Base):
    """A continuous foreground session on a single window title."""

    __tablename__ = "sessions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    application_id: Mapped[int] = mapped_column(
        ForeignKey("applications.id"), index=True
    )
    window_title: Mapped[str] = mapped_column(Text, default="")
    pid: Mapped[int | None] = mapped_column(Integer, nullable=True)
    start_time: Mapped[datetime] = mapped_column(DateTime, index=True)
    end_time: Mapped[datetime] = mapped_column(DateTime, index=True)
    duration_seconds: Mapped[float] = mapped_column(Float, default=0.0)
    # "app" | "browser" | "explorer" - a coarse category for filtering/icons.
    kind: Mapped[str] = mapped_column(String(32), default="app", index=True)

    application: Mapped["Application"] = relationship(back_populates="sessions")

    __table_args__ = (
        Index("ix_sessions_time_range", "start_time", "end_time"),
    )


class BrowserVisit(Base):
    __tablename__ = "browser_visits"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    url: Mapped[str] = mapped_column(Text)
    title: Mapped[str] = mapped_column(Text, default="")
    domain: Mapped[str] = mapped_column(String(255), index=True)
    browser: Mapped[str] = mapped_column(String(64), default="", index=True)
    tab_activated: Mapped[datetime] = mapped_column(DateTime, index=True)
    tab_closed: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    duration_seconds: Mapped[float] = mapped_column(Float, default=0.0)
    # Optional source: "extension" | "history_import".
    source: Mapped[str] = mapped_column(String(32), default="extension")

    __table_args__ = (
        Index("ix_browser_visits_domain_time", "domain", "tab_activated"),
    )


class FileEvent(Base):
    __tablename__ = "file_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    path: Mapped[str] = mapped_column(Text, index=True)
    filename: Mapped[str] = mapped_column(String(512), index=True)
    file_type: Mapped[str] = mapped_column(String(32), default="", index=True)
    application: Mapped[str | None] = mapped_column(String(255), nullable=True)
    last_activity: Mapped[datetime] = mapped_column(DateTime, index=True)
    # "recent" | "session_title" | "explorer".
    source: Mapped[str] = mapped_column(String(32), default="recent")

    __table_args__ = (
        Index("ix_file_events_path_unique", "path", unique=True),
    )


class Resource(Base):
    """A higher-level grouping: coding project, folder, or workspace."""

    __tablename__ = "resources"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(512), index=True)
    kind: Mapped[str] = mapped_column(String(32), default="project", index=True)
    path: Mapped[str | None] = mapped_column(Text, nullable=True)
    first_seen: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    last_seen: Mapped[datetime] = mapped_column(DateTime, default=utcnow, index=True)
    total_seconds: Mapped[float] = mapped_column(Float, default=0.0)

    __table_args__ = (
        Index("ix_resources_kind_path", "kind", "path", unique=True),
    )
