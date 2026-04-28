"""
main.py — Entrypoint for the multi-agent LangGraph system.

Usage:
    python main.py                          # interactive REPL
    python main.py "your task here"         # single-shot
    python main.py --session <id> "task"    # resume existing session
"""
from __future__ import annotations

import argparse
import sys
import uuid
from typing import Optional

from agent_system.config import GLOBAL_TIMEOUT, MAX_ITERATIONS, RECURSION_LIMIT
from agent_system.graph.router import get_default_graph
from agent_system.graph.state import AgentState
from agent_system.memory.sql_memory import init_db
from agent_system.safety.guards import run_with_timeout, ToolTimeoutError


# ─── Bootstrap ────────────────────────────────────────────────────────────────

def bootstrap() -> None:
    """Initialise the database tables on first run."""
    init_db()
    print("[system] Database initialised.")


# ─── Runner ───────────────────────────────────────────────────────────────────

def run_task(
    user_input: str,
    session_id: Optional[str] = None,
    project_id: str = "default",
    stream: bool = True,
) -> str:
    """
    Execute a single task through the full agent pipeline.

    Args:
        user_input : The user's request / task description.
        session_id : Resume an existing session, or None to start a new one.
        project_id : Logical project namespace for shared state.
        stream     : If True, print each node's output as it arrives.

    Returns:
        The final summarised answer as a string.
    """
    session_id = session_id or str(uuid.uuid4())
    graph = get_default_graph()

    initial_state: AgentState = {
        "session_id":   session_id,
        "project_id":   project_id,
        "user_input":   user_input,
        "plan":         None,
        "research":     None,
        "code":         None,
        "review":       None,
        "critique":     None,
        "final_answer": None,
        "current_agent": "start",
        "iterations":   0,
        "errors":       [],
        "should_stop":  False,
        "next_agent":   None,
        "retry_count":  0,
    }

    config = {
        "configurable": {"thread_id": session_id},
        "recursion_limit": RECURSION_LIMIT,
    }

    print(f"\n{'='*60}")
    print(f"  Session : {session_id}")
    print(f"  Project : {project_id}")
    print(f"  Task    : {user_input[:80]}{'...' if len(user_input) > 80 else ''}")
    print(f"  Limits  : max_iter={MAX_ITERATIONS}, timeout={GLOBAL_TIMEOUT}s")
    print(f"{'='*60}\n")

    final_state: dict = {}

    def _run():
        nonlocal final_state
        if stream:
            for step in graph.stream(initial_state, config=config):
                node_name = list(step.keys())[0]
                node_state = step[node_name]
                _print_step(node_name, node_state)
                final_state = node_state
        else:
            final_state = graph.invoke(initial_state, config=config)

    try:
        run_with_timeout(_run, timeout=GLOBAL_TIMEOUT)
    except ToolTimeoutError:
        print(
            f"\n[TIMEOUT] Global timeout of {GLOBAL_TIMEOUT}s exceeded. "
            "The last checkpoint was saved — resume with the same session_id."
        )
        return final_state.get("final_answer") or "(timed out — partial result above)"

    answer = final_state.get("final_answer", "(no final answer produced)")
    print(f"\n{'='*60}")
    print("  FINAL ANSWER")
    print(f"{'='*60}")
    print(answer)
    print(f"{'='*60}\n")
    return answer


def _print_step(node_name: str, state: dict) -> None:
    """Pretty-print a single graph step during streaming."""
    icons = {
        "planner":    "📋",
        "researcher": "🔍",
        "coder":      "💻",
        "reviewer":   "🔎",
        "critic":     "🧠",
        "summarizer": "📝",
    }
    icon = icons.get(node_name, "⚙️")
    itr  = state.get("iterations", "?")
    print(f"\n{icon}  [{node_name.upper()}]  (iteration {itr})")
    print("-" * 50)

    field_map = {
        "planner":    "plan",
        "researcher": "research",
        "coder":      "code",
        "reviewer":   "review",
        "critic":     "critique",
        "summarizer": "final_answer",
    }
    content_key = field_map.get(node_name)
    content = state.get(content_key, "") if content_key else ""
    if content:
        # Print first 600 chars to keep terminal readable
        preview = content[:600]
        if len(content) > 600:
            preview += "\n... [truncated] ..."
        print(preview)

    if state.get("errors"):
        print(f"\n⚠️  Errors so far: {state['errors'][-3:]}")


# ─── REPL ────────────────────────────────────────────────────────────────────

def repl(project_id: str = "default") -> None:
    session_id = str(uuid.uuid4())
    print("\n Multi-Agent System — Interactive Mode")
    print(f" Session: {session_id}  |  Project: {project_id}")
    print(" Type 'exit' or Ctrl-C to quit.\n")

    while True:
        try:
            user_input = input("You › ").strip()
        except (KeyboardInterrupt, EOFError):
            print("\n[system] Goodbye.")
            break

        if not user_input:
            continue
        if user_input.lower() in {"exit", "quit", "q"}:
            print("[system] Goodbye.")
            break

        run_task(user_input, session_id=session_id, project_id=project_id)


# ─── CLI ──────────────────────────────────────────────────────────────────────

def main() -> None:
    bootstrap()

    parser = argparse.ArgumentParser(
        description="Multi-agent LangGraph system."
    )
    parser.add_argument(
        "task",
        nargs="?",
        help="Task to run. Omit for interactive REPL.",
    )
    parser.add_argument(
        "--session", "-s",
        default=None,
        help="Resume an existing session by ID.",
    )
    parser.add_argument(
        "--project", "-p",
        default="default",
        help="Project namespace (default: 'default').",
    )
    parser.add_argument(
        "--no-stream",
        action="store_true",
        help="Disable streaming output (wait for full result).",
    )
    args = parser.parse_args()

    if args.task:
        run_task(
            args.task,
            session_id=args.session,
            project_id=args.project,
            stream=not args.no_stream,
        )
    else:
        repl(project_id=args.project)


if __name__ == "__main__":
    main()
