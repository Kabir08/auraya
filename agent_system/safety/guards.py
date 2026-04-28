"""
safety/guards.py — Circuit breakers, timeout wrappers, and RBAC tool registry.

Key concepts:
  • CircuitBreaker  — kills a tool after N consecutive failures (same error).
  • run_with_timeout — wraps any callable with a hard wall-clock timeout.
  • ToolRegistry     — RBAC: each role gets an explicit allow-list of tools.
  • HITL             — Human-in-the-Loop flag for destructive operations.
"""
from __future__ import annotations

import functools
import signal
import threading
from collections import defaultdict
from typing import Any, Callable, Dict, List, Optional, Set

from agent_system.config import MAX_CONSECUTIVE_TOOL_FAILURES, TOOL_TIMEOUT


# ─── Timeout helper ───────────────────────────────────────────────────────────
class ToolTimeoutError(Exception):
    pass


def run_with_timeout(fn: Callable, args=(), kwargs=None, timeout: int = TOOL_TIMEOUT):
    """Run *fn* in a thread; raise ToolTimeoutError if it exceeds *timeout* s."""
    kwargs = kwargs or {}
    result: list = []
    error:  list = []

    def target():
        try:
            result.append(fn(*args, **kwargs))
        except Exception as exc:  # noqa: BLE001
            error.append(exc)

    t = threading.Thread(target=target, daemon=True)
    t.start()
    t.join(timeout)
    if t.is_alive():
        raise ToolTimeoutError(f"Tool timed out after {timeout}s")
    if error:
        raise error[0]
    return result[0]


# ─── Circuit Breaker ──────────────────────────────────────────────────────────
class CircuitBreaker:
    """
    Track consecutive failures per (session, tool_name) pair.
    Raises CircuitOpenError when the threshold is reached.
    """

    class CircuitOpenError(Exception):
        pass

    def __init__(self, max_failures: int = MAX_CONSECUTIVE_TOOL_FAILURES):
        self._max = max_failures
        # { (session_id, tool_name): (count, last_error_msg) }
        self._state: Dict[tuple, tuple] = defaultdict(lambda: (0, ""))

    def record_success(self, session_id: str, tool_name: str) -> None:
        self._state[(session_id, tool_name)] = (0, "")

    def record_failure(self, session_id: str, tool_name: str, error_msg: str) -> None:
        count, last = self._state[(session_id, tool_name)]
        if last == error_msg:
            count += 1
        else:
            count = 1          # different error → reset streak
        self._state[(session_id, tool_name)] = (count, error_msg)

        if count >= self._max:
            raise CircuitBreaker.CircuitOpenError(
                f"Tool '{tool_name}' failed {count}x with the same error: {error_msg!r}. "
                "Circuit open — escalating to user."
            )

    def reset(self, session_id: str, tool_name: str) -> None:
        self._state.pop((session_id, tool_name), None)


# ─── Human-in-the-Loop guard ──────────────────────────────────────────────────
# Tools in this set require explicit human approval before execution.
DESTRUCTIVE_TOOLS: Set[str] = {
    "terminal",
    "shell",
    "bash",
    "git_push",
    "git_reset",
    "delete_file",
    "drop_table",
    "rm",
}


def requires_human_approval(tool_name: str) -> bool:
    return tool_name.lower() in DESTRUCTIVE_TOOLS


def hitl_gate(tool_name: str, tool_input: Any) -> bool:
    """
    Returns True if the user approves execution.
    In production replace the input() call with a proper approval queue / UI.
    """
    if not requires_human_approval(tool_name):
        return True
    print(f"\n⚠️  [HITL] Destructive tool requested: '{tool_name}'")
    print(f"   Input: {tool_input}")
    answer = input("   Approve? [y/N]: ").strip().lower()
    return answer == "y"


# ─── RBAC Tool Registry ───────────────────────────────────────────────────────
# Each role has an explicit allow-list of tool names.
# Add new tools here; agents will only see tools they are allowed to use.
ROLE_TOOL_PERMISSIONS: Dict[str, List[str]] = {
    "planner": [
        "read_file",
        "list_directory",
        "web_search",
        "get_project_state",
        "set_project_state",
    ],
    "researcher": [
        "read_file",
        "list_directory",
        "web_search",
        "get_project_state",
    ],
    "coder": [
        "read_file",
        "write_file",
        "list_directory",
        "terminal",          # sandboxed; HITL gate active
        "get_project_state",
        "set_project_state",
    ],
    "reviewer": [
        "read_file",
        "list_directory",
        "get_project_state",
        "set_project_state",
    ],
    "critic": [
        "read_file",
        "get_project_state",
    ],
    "summarizer": [
        "read_file",
        "get_project_state",
    ],
}


class ToolRegistry:
    """Resolves which LangChain tools a role may use and wraps them safely."""

    def __init__(self, all_tools: List[Any]):
        # key: tool.name → tool object
        self._tools: Dict[str, Any] = {t.name: t for t in all_tools}

    def get_tools_for_role(self, role: str) -> List[Any]:
        allowed = ROLE_TOOL_PERMISSIONS.get(role, [])
        return [self._tools[name] for name in allowed if name in self._tools]


# ─── Singleton instances ──────────────────────────────────────────────────────
circuit_breaker = CircuitBreaker()
