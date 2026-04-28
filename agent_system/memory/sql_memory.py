"""
memory/sql_memory.py — SQL-backed memory for all agents.

Two layers:
  1. AgentMemory  — per-session conversation window (last N messages).
  2. ThoughtLog   — persistent append-only log of every agent action/thought
                    so you can audit, replay, or resume after a crash.

Uses SQLAlchemy Core (no ORM bloat) with a default SQLite backend.
Swap DATABASE_URL to PostgreSQL / MySQL without changing this file.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import List

from sqlalchemy import (
    Column, DateTime, Integer, String, Text,
    create_engine, text,
)
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from agent_system.config import DATABASE_URL, WINDOW_BUFFER_SIZE


# ─── ORM Base ─────────────────────────────────────────────────────────────────
class Base(DeclarativeBase):
    pass


# ─── Tables ───────────────────────────────────────────────────────────────────
class MessageRecord(Base):
    """Sliding-window conversation history for a session."""
    __tablename__ = "messages"

    id         = Column(Integer, primary_key=True, autoincrement=True)
    session_id = Column(String(128), nullable=False, index=True)
    role       = Column(String(32),  nullable=False)   # human | ai | system | tool
    content    = Column(Text,        nullable=False)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))


class ThoughtLog(Base):
    """Append-only log: agent thoughts, tool calls, and outputs."""
    __tablename__ = "thought_log"

    id         = Column(Integer, primary_key=True, autoincrement=True)
    session_id = Column(String(128), nullable=False, index=True)
    agent_role = Column(String(64),  nullable=False)
    step       = Column(Integer,     nullable=False)
    thought    = Column(Text,        nullable=True)
    tool_name  = Column(String(128), nullable=True)
    tool_input = Column(Text,        nullable=True)   # JSON string
    tool_output= Column(Text,        nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))


class ProjectState(Base):
    """Key-value store for project-level state shared across agents."""
    __tablename__ = "project_state"

    id         = Column(Integer, primary_key=True, autoincrement=True)
    project_id = Column(String(128), nullable=False, index=True)
    key        = Column(String(256), nullable=False)
    value      = Column(Text,        nullable=True)   # JSON-serialised
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc),
                        onupdate=lambda: datetime.now(timezone.utc))


# ─── Engine / Session Factory ─────────────────────────────────────────────────
_engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False} if "sqlite" in DATABASE_URL else {},
    echo=False,
)
Base.metadata.create_all(_engine)
SessionLocal = sessionmaker(bind=_engine, expire_on_commit=False)


def init_db() -> None:
    """Idempotent — safe to call multiple times. Creates tables if missing."""
    Base.metadata.create_all(_engine)


# ─── Memory Manager ───────────────────────────────────────────────────────────
class AgentMemoryManager:
    """High-level API used by every agent to read/write memory."""

    def __init__(self, session_id: str, window: int = WINDOW_BUFFER_SIZE):
        self.session_id = session_id
        self.window     = window

    # ── Conversation window ───────────────────────────────────────────────────
    def add_message(self, role: str, content: str) -> None:
        with SessionLocal() as db:
            db.add(MessageRecord(
                session_id=self.session_id,
                role=role,
                content=content,
            ))
            db.commit()

    def get_recent_messages(self) -> List[dict]:
        """Return the last *window* messages as {role, content} dicts."""
        with SessionLocal() as db:
            rows = (
                db.query(MessageRecord)
                .filter(MessageRecord.session_id == self.session_id)
                .order_by(MessageRecord.id.desc())
                .limit(self.window)
                .all()
            )
        return [{"role": r.role, "content": r.content} for r in reversed(rows)]

    def clear_session(self) -> None:
        with SessionLocal() as db:
            db.query(MessageRecord).filter(
                MessageRecord.session_id == self.session_id
            ).delete()
            db.commit()

    # ── Thought log ───────────────────────────────────────────────────────────
    def log_thought(
        self,
        agent_role: str,
        step: int,
        thought: str | None = None,
        tool_name: str | None = None,
        tool_input: dict | None = None,
        tool_output: str | None = None,
    ) -> None:
        with SessionLocal() as db:
            db.add(ThoughtLog(
                session_id=self.session_id,
                agent_role=agent_role,
                step=step,
                thought=thought,
                tool_name=tool_name,
                tool_input=json.dumps(tool_input) if tool_input else None,
                tool_output=tool_output,
            ))
            db.commit()

    def get_thought_log(self, agent_role: str | None = None) -> List[dict]:
        with SessionLocal() as db:
            q = db.query(ThoughtLog).filter(
                ThoughtLog.session_id == self.session_id
            )
            if agent_role:
                q = q.filter(ThoughtLog.agent_role == agent_role)
            rows = q.order_by(ThoughtLog.step).all()
        return [
            {
                "step":        r.step,
                "agent":       r.agent_role,
                "thought":     r.thought,
                "tool":        r.tool_name,
                "tool_input":  json.loads(r.tool_input) if r.tool_input else None,
                "tool_output": r.tool_output,
                "at":          r.created_at.isoformat(),
            }
            for r in rows
        ]

    # ── Project state (shared KV) ─────────────────────────────────────────────
    def set_project_state(self, project_id: str, key: str, value) -> None:
        serialized = json.dumps(value)
        with SessionLocal() as db:
            existing = (
                db.query(ProjectState)
                .filter_by(project_id=project_id, key=key)
                .first()
            )
            if existing:
                existing.value = serialized
                existing.updated_at = datetime.now(timezone.utc)
            else:
                db.add(ProjectState(project_id=project_id, key=key, value=serialized))
            db.commit()

    def get_project_state(self, project_id: str, key: str, default=None):
        with SessionLocal() as db:
            row = (
                db.query(ProjectState)
                .filter_by(project_id=project_id, key=key)
                .first()
            )
        if row is None:
            return default
        return json.loads(row.value)
