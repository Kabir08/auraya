"""
graph/router.py — LangGraph state machine that orchestrates all agents.

Flow:
  START → planner → researcher? → coder? → reviewer → critic → summarizer → END
                       ↑__________________________|  (if NEEDS_CHANGES, loop back)

Nodes     : pure functions that accept AgentState and return partial state dicts.
Edges     : conditional — next node is determined by the current state.
Checkpoint: LangGraph persists state after every node via SqliteSaver,
            so a crash can resume from the exact last node.
"""
from __future__ import annotations

import uuid
from typing import Literal

from langgraph.graph import END, START, StateGraph
from langgraph.checkpoint.sqlite import SqliteSaver

from agent_system.config import MAX_ITERATIONS, RECURSION_LIMIT
from agent_system.graph.state import AgentState
from agent_system.agents.planner import PlannerAgent
from agent_system.agents.researcher import ResearcherAgent
from agent_system.agents.coder import CoderAgent
from agent_system.agents.reviewer import ReviewerAgent
from agent_system.agents.critic import CriticAgent
from agent_system.agents.summarizer import SummarizerAgent


# ─── Node implementations ─────────────────────────────────────────────────────

def planner_node(state: AgentState) -> dict:
    agent = PlannerAgent(session_id=state["session_id"])
    plan = agent.run(state["user_input"])
    return {
        "plan": plan,
        "current_agent": "planner",
        "iterations": state["iterations"] + 1,
    }


def researcher_node(state: AgentState) -> dict:
    agent = ResearcherAgent(session_id=state["session_id"])
    context = f"PLAN:\n{state.get('plan', '')}\n\nUSER REQUEST:\n{state['user_input']}"
    research = agent.run(context)
    return {
        "research": research,
        "current_agent": "researcher",
        "iterations": state["iterations"] + 1,
    }


def coder_node(state: AgentState) -> dict:
    agent = CoderAgent(session_id=state["session_id"])
    context = (
        f"PLAN:\n{state.get('plan', '')}\n\n"
        f"RESEARCH:\n{state.get('research', 'N/A')}\n\n"
        f"USER REQUEST:\n{state['user_input']}"
    )
    code = agent.run(context)
    return {
        "code": code,
        "current_agent": "coder",
        "iterations": state["iterations"] + 1,
    }


def reviewer_node(state: AgentState) -> dict:
    agent = ReviewerAgent(session_id=state["session_id"])
    context = (
        f"PLAN:\n{state.get('plan', '')}\n\n"
        f"CODE / ARTIFACT:\n{state.get('code', state.get('research', 'N/A'))}\n\n"
        f"USER REQUEST:\n{state['user_input']}"
    )
    review = agent.run(context)
    return {
        "review": review,
        "current_agent": "reviewer",
        "iterations": state["iterations"] + 1,
    }


def critic_node(state: AgentState) -> dict:
    agent = CriticAgent(session_id=state["session_id"])
    context = (
        f"PLAN:\n{state.get('plan', '')}\n\n"
        f"REVIEW:\n{state.get('review', 'N/A')}\n\n"
        f"CODE / ARTIFACT:\n{state.get('code', 'N/A')}"
    )
    critique = agent.run(context)
    return {
        "critique": critique,
        "current_agent": "critic",
        "iterations": state["iterations"] + 1,
    }


def summarizer_node(state: AgentState) -> dict:
    agent = SummarizerAgent(session_id=state["session_id"])
    context = (
        f"USER REQUEST:\n{state['user_input']}\n\n"
        f"PLAN:\n{state.get('plan', 'N/A')}\n\n"
        f"RESEARCH:\n{state.get('research', 'N/A')}\n\n"
        f"CODE:\n{state.get('code', 'N/A')}\n\n"
        f"REVIEW:\n{state.get('review', 'N/A')}\n\n"
        f"CRITIQUE:\n{state.get('critique', 'N/A')}"
    )
    final = agent.run(context)
    return {
        "final_answer": final,
        "current_agent": "summarizer",
        "should_stop": True,
        "iterations": state["iterations"] + 1,
    }


# ─── Edge / routing logic ─────────────────────────────────────────────────────

def route_after_planner(
    state: AgentState,
) -> Literal["researcher", "coder", "summarizer"]:
    """
    Inspect the plan to decide if we need research, direct coding, or
    if the task is purely analytical (→ summarizer directly).
    """
    if state["iterations"] >= MAX_ITERATIONS or state.get("should_stop"):
        return "summarizer"

    plan_lower = (state.get("plan") or "").lower()
    if "researcher" in plan_lower or "research" in plan_lower:
        return "researcher"
    if "coder" in plan_lower or "code" in plan_lower or "implement" in plan_lower:
        return "coder"
    return "summarizer"


def route_after_researcher(
    state: AgentState,
) -> Literal["coder", "reviewer"]:
    """After research, check if the plan still calls for coding."""
    if state["iterations"] >= MAX_ITERATIONS or state.get("should_stop"):
        return "reviewer"

    plan_lower = (state.get("plan") or "").lower()
    if "coder" in plan_lower or "code" in plan_lower or "implement" in plan_lower:
        return "coder"
    return "reviewer"


def route_after_reviewer(
    state: AgentState,
) -> Literal["coder", "critic"]:
    """
    If reviewer says NEEDS_CHANGES and retry budget remains → back to coder.
    Otherwise proceed to critic.
    """
    review = (state.get("review") or "").upper()
    retry = state.get("retry_count", 0)

    if (
        "NEEDS_CHANGES" in review
        and retry < 2
        and state["iterations"] < MAX_ITERATIONS
    ):
        return "coder"
    return "critic"


def route_after_critic(
    state: AgentState,
) -> Literal["planner", "summarizer"]:
    """
    If critic says the whole plan is flawed and we have retry budget → re-plan.
    Otherwise close out with summarizer.
    """
    critique = (state.get("critique") or "").upper()
    retry = state.get("retry_count", 0)

    if (
        "REPLAN" in critique
        and retry < 1
        and state["iterations"] < MAX_ITERATIONS
    ):
        return "planner"
    return "summarizer"


# ─── Graph builder ────────────────────────────────────────────────────────────

def build_graph(checkpointer=None):
    """
    Construct and compile the LangGraph state machine.

    Args:
        checkpointer: A LangGraph checkpointer (e.g. SqliteSaver) for crash
                      recovery.  Pass None to run without persistence.

    Returns:
        A compiled CompiledStateGraph ready for .invoke() / .stream().
    """
    builder = StateGraph(AgentState)

    # ── Register nodes ───────────────────────────────────────────────────────
    builder.add_node("planner",    planner_node)
    builder.add_node("researcher", researcher_node)
    builder.add_node("coder",      coder_node)
    builder.add_node("reviewer",   reviewer_node)
    builder.add_node("critic",     critic_node)
    builder.add_node("summarizer", summarizer_node)

    # ── Entry edge ───────────────────────────────────────────────────────────
    builder.add_edge(START, "planner")

    # ── Conditional edges ────────────────────────────────────────────────────
    builder.add_conditional_edges(
        "planner",
        route_after_planner,
        {"researcher": "researcher", "coder": "coder", "summarizer": "summarizer"},
    )
    builder.add_conditional_edges(
        "researcher",
        route_after_researcher,
        {"coder": "coder", "reviewer": "reviewer"},
    )
    builder.add_edge("coder", "reviewer")
    builder.add_conditional_edges(
        "reviewer",
        route_after_reviewer,
        {"coder": "coder", "critic": "critic"},
    )
    builder.add_conditional_edges(
        "critic",
        route_after_critic,
        {"planner": "planner", "summarizer": "summarizer"},
    )
    builder.add_edge("summarizer", END)

    # ── Compile ──────────────────────────────────────────────────────────────
    compile_kwargs: dict = {}
    if checkpointer:
        compile_kwargs["checkpointer"] = checkpointer

    # recursion_limit is passed at invoke/stream time via config, not at compile
    return builder.compile(**compile_kwargs)


def get_default_graph():
    """
    Returns a graph backed by the SQLite checkpointer for persistent state.
    The DB file lives alongside agent_memory.db.
    """
    import sqlite3
    conn = sqlite3.connect("checkpoints.db", check_same_thread=False)
    checkpointer = SqliteSaver(conn)
    return build_graph(checkpointer=checkpointer)
