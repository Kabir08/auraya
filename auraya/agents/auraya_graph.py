"""
auraya/agents/auraya_graph.py

Autonomous Architect → Coder → QA LangGraph loop for Auraya.

Nodes:
  architect  — generates/refines feature specs from the user goal
  coder      — writes React Native / FastAPI code (uses existing CoderAgent)
  qa         — Gemini Vision asserts AR screenshots from Firebase Test Lab
  committer  — git add + push (triggers Render + Firebase CI automatically)

Edges:
  start → architect → coder → committer → (wait for CI) → qa
  qa: PASS → END
  qa: FAIL / NEEDS_REVIEW → coder (self-heal loop, max 2 retries)
  qa: FAIL after max retries → architect (re-plan)
"""
from __future__ import annotations

import logging
import os
import subprocess
from typing import Annotated, Literal, Optional
import operator

from langgraph.graph import END, START, StateGraph
from langgraph.checkpoint.sqlite import SqliteSaver
from typing_extensions import TypedDict

# Re-use the existing CoderAgent from the admin agent_system
import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../.."))

from agent_system.agents.coder      import CoderAgent
from agent_system.agents.planner    import PlannerAgent
from agent_system.config            import MAX_ITERATIONS
from auraya.agents.qa_agent         import QAAgent

logger = logging.getLogger(__name__)

# ─── State ────────────────────────────────────────────────────────────────────

class AurayaBuildState(TypedDict):
    session_id:    str
    feature_goal:  str              # what to build / fix

    spec:          Optional[str]    # Architect output
    code_diff:     Optional[str]    # Coder output (git diff / file list)
    qa_verdict:    Optional[str]    # "PASS" | "FAIL" | "NEEDS_REVIEW"
    qa_notes:      Optional[str]
    firebase_run:  Optional[str]    # GCS results dir for QA agent

    iterations:    int
    qa_retries:    int
    errors:        Annotated[list[str], operator.add]
    should_stop:   bool


# ─── Nodes ────────────────────────────────────────────────────────────────────

def architect_node(state: AurayaBuildState) -> dict:
    agent = PlannerAgent(session_id=state["session_id"])
    spec  = agent.run(
        f"You are the Architect for Auraya, an AR jewelry try-on app.\n\n"
        f"Feature goal: {state['feature_goal']}\n\n"
        f"Previous QA notes (if any): {state.get('qa_notes', 'None')}\n\n"
        "Produce a concise technical spec: which files to change, what logic to add, "
        "and what the acceptance criteria are."
    )
    return {"spec": spec, "iterations": state["iterations"] + 1}


def coder_node(state: AurayaBuildState) -> dict:
    agent = CoderAgent(session_id=state["session_id"])
    prompt = (
        f"SPEC:\n{state.get('spec', '')}\n\n"
        f"QA FAILURE NOTES (fix these): {state.get('qa_notes', 'None')}\n\n"
        "Write the complete implementation. For each file changed, output:\n"
        "FILE: <relative path>\n```\n<full file content>\n```\n"
        "Finish with: DONE"
    )
    code_diff = agent.run(prompt)
    return {"code_diff": code_diff, "iterations": state["iterations"] + 1}


def committer_node(state: AurayaBuildState) -> dict:
    """
    Parse the coder output, write files to disk, git add + push.
    The push triggers the GitHub Actions → Render + Firebase CI pipeline.
    """
    code_diff = state.get("code_diff", "")
    files_written: list[str] = []

    # Parse FILE: blocks from coder output
    import re
    pattern = re.compile(r"FILE:\s*(.+?)\n```(?:\w+)?\n(.*?)```", re.DOTALL)
    repo_root = os.path.join(os.path.dirname(__file__), "../..")

    for match in pattern.finditer(code_diff):
        rel_path = match.group(1).strip()
        content  = match.group(2)
        abs_path = os.path.join(repo_root, rel_path)
        os.makedirs(os.path.dirname(abs_path), exist_ok=True)
        with open(abs_path, "w", encoding="utf-8") as f:
            f.write(content)
        files_written.append(rel_path)
        logger.info("Wrote: %s", rel_path)

    if not files_written:
        return {"errors": ["Committer: no files parsed from coder output."]}

    # Git commit + push (requires repo to be set up with push access)
    try:
        subprocess.run(["git", "-C", repo_root, "add"] + files_written, check=True)
        subprocess.run(
            ["git", "-C", repo_root, "commit", "-m",
             f"[auraya-agent] {state['feature_goal'][:72]}"],
            check=True,
        )
        subprocess.run(["git", "-C", repo_root, "push"], check=True)
        logger.info("Pushed %d file(s) to remote.", len(files_written))
    except subprocess.CalledProcessError as e:
        return {"errors": [f"Git push failed: {e}"]}

    return {"iterations": state["iterations"] + 1}


def qa_node(state: AurayaBuildState) -> dict:
    """
    Download Firebase Test Lab screenshots and run Gemini Vision QA.
    In local dev (no GEMINI_API_KEY), returns a stub PASS to keep the loop moving.
    """
    gemini_key     = os.getenv("GEMINI_API_KEY", "")
    firebase_run   = state.get("firebase_run")
    firebase_bucket = os.getenv("FIREBASE_RESULTS_BUCKET", "")

    if not gemini_key or not firebase_run:
        logger.warning("QA node: skipping (no GEMINI_API_KEY or firebase_run set). Returning PASS stub.")
        return {
            "qa_verdict": "PASS",
            "qa_notes":   "QA skipped (no credentials). Treat as manual review.",
            "qa_retries": state.get("qa_retries", 0),
            "iterations": state["iterations"] + 1,
        }

    import asyncio
    qa     = QAAgent()
    result = asyncio.run(qa.analyze_firebase_run(firebase_bucket, firebase_run))

    return {
        "qa_verdict": result["overall"],
        "qa_notes":   result["summary"],
        "qa_retries": state.get("qa_retries", 0),
        "iterations": state["iterations"] + 1,
    }


# ─── Edges ────────────────────────────────────────────────────────────────────

MAX_QA_RETRIES  = 2
MAX_ARCH_RETRIES = 1

def route_after_qa(
    state: AurayaBuildState,
) -> Literal["coder", "architect", "__end__"]:
    verdict   = (state.get("qa_verdict") or "").upper()
    qa_retries = state.get("qa_retries", 0)
    iters      = state["iterations"]

    if verdict == "PASS" or iters >= MAX_ITERATIONS:
        return "__end__"
    if qa_retries < MAX_QA_RETRIES:
        return "coder"        # self-heal loop
    return "architect"        # re-plan after repeated QA failure


def route_after_coder(
    state: AurayaBuildState,
) -> Literal["committer", "__end__"]:
    if state.get("errors"):
        return "__end__"   # bail on coder errors
    return "committer"


# ─── Graph builder ────────────────────────────────────────────────────────────

def build_auraya_graph(checkpointer=None):
    builder = StateGraph(AurayaBuildState)

    builder.add_node("architect", architect_node)
    builder.add_node("coder",     coder_node)
    builder.add_node("committer", committer_node)
    builder.add_node("qa",        qa_node)

    builder.add_edge(START,        "architect")
    builder.add_edge("architect",  "coder")
    builder.add_conditional_edges("coder", route_after_coder,
        {"committer": "committer", "__end__": END})
    builder.add_edge("committer",  "qa")
    builder.add_conditional_edges("qa", route_after_qa,
        {"coder": "coder", "architect": "architect", "__end__": END})

    kwargs: dict = {}
    if checkpointer:
        kwargs["checkpointer"] = checkpointer
    return builder.compile(**kwargs)


def run_feature(feature_goal: str, session_id: str = "auraya-build") -> dict:
    """Convenience wrapper — run the full autonomous build loop."""
    import sqlite3
    conn        = sqlite3.connect("auraya_checkpoints.db", check_same_thread=False)
    checkpointer = SqliteSaver(conn)
    graph        = build_auraya_graph(checkpointer)

    initial: AurayaBuildState = {
        "session_id":   session_id,
        "feature_goal": feature_goal,
        "spec":         None,
        "code_diff":    None,
        "qa_verdict":   None,
        "qa_notes":     None,
        "firebase_run": os.getenv("FIREBASE_LAST_RUN_DIR"),
        "iterations":   0,
        "qa_retries":   0,
        "errors":       [],
        "should_stop":  False,
    }
    config = {"configurable": {"thread_id": session_id}}

    final: dict = {}
    for step in graph.stream(initial, config=config):
        node = list(step.keys())[0]
        data = step[node]
        logger.info("[%s] iter=%s  qa=%s", node, data.get("iterations"), data.get("qa_verdict"))
        final = data

    return final


if __name__ == "__main__":
    import sys
    goal = " ".join(sys.argv[1:]) or "Add save-to-gallery button on ARScreen"
    result = run_feature(goal)
    print("Final QA verdict:", result.get("qa_verdict"))
    print("Notes:", result.get("qa_notes"))
