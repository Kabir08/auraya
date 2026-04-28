"""
graph/state.py — LangGraph shared state schema.

Every node in the graph reads from and writes to AgentState.
LangGraph checkpoints this after every node, so a crash can resume exactly.
"""
from __future__ import annotations

from typing import Annotated, Any, Dict, List, Optional
from typing_extensions import TypedDict
import operator


class AgentState(TypedDict):
    # ── Input ──────────────────────────────────────────────────────────────
    session_id:     str
    project_id:     str
    user_input:     str

    # ── Inter-agent artifacts ───────────────────────────────────────────────
    plan:           Optional[str]           # Planner output
    research:       Optional[str]           # Researcher output
    code:           Optional[str]           # Coder output
    review:         Optional[str]           # Reviewer output
    critique:       Optional[str]           # Critic output
    final_answer:   Optional[str]           # Summarizer output

    # ── Control flow ───────────────────────────────────────────────────────
    current_agent:  str                     # which node is active
    iterations:     int                     # global step counter
    errors:         Annotated[List[str], operator.add]  # accumulated errors
    should_stop:    bool                    # circuit-breaker / max-iter flag

    # ── Routing metadata ───────────────────────────────────────────────────
    next_agent:     Optional[str]           # explicit router override
    retry_count:    int                     # how many times we've re-planned
