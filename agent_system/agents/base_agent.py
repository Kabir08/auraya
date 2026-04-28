"""
agents/base_agent.py — Abstract base shared by every role.

Handles:
  - LLM construction from config
  - SQL memory (window buffer + thought log)
  - Circuit breaker + timeout wrapping on every tool call
  - Format-retry loop (max MAX_FORMAT_RETRIES)
  - Iteration cap enforcement
"""
from __future__ import annotations

import time
from abc import ABC, abstractmethod
from typing import Any, List, Optional

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage

from agent_system.config import (
    MAX_FORMAT_RETRIES,
    MAX_ITERATIONS,
    TOOL_TIMEOUT,
    get_groq_llm,
)
from agent_system.memory import AgentMemoryManager
from agent_system.safety.guards import (
    CircuitBreaker,
    circuit_breaker,
    hitl_gate,
    run_with_timeout,
)


class BaseAgent(ABC):
    role: str = "base"

    def __init__(self, session_id: str, tools: List[Any] | None = None):
        self.session_id = session_id
        self.llm        = get_groq_llm(self.role)
        self.tools      = tools or []
        self.memory     = AgentMemoryManager(session_id)
        self._iteration = 0

    # ── Subclasses must define their system prompt ────────────────────────────
    @property
    @abstractmethod
    def system_prompt(self) -> str: ...

    # ── Public entry point ────────────────────────────────────────────────────
    def run(self, user_input: str) -> str:
        self._iteration = 0
        self.memory.add_message("human", user_input)

        messages = self._build_messages(user_input)
        result   = self._reasoning_loop(messages)

        self.memory.add_message("ai", result)
        return result

    # ── Core reasoning loop ───────────────────────────────────────────────────
    def _reasoning_loop(self, messages: list) -> str:
        format_retries = 0

        for step in range(MAX_ITERATIONS):
            self._iteration = step + 1
            response = self._call_llm(messages)

            # ── If the model wants to call a tool ─────────────────────────────
            if hasattr(response, "tool_calls") and response.tool_calls:
                for tool_call in response.tool_calls:
                    tool_name  = tool_call["name"]
                    tool_input = tool_call["args"]

                    # HITL gate for destructive tools
                    if not hitl_gate(tool_name, tool_input):
                        tool_output = "Tool execution rejected by user."
                    else:
                        tool_output = self._invoke_tool(
                            tool_name, tool_input, step
                        )

                    self.memory.log_thought(
                        agent_role=self.role,
                        step=step,
                        tool_name=tool_name,
                        tool_input=tool_input,
                        tool_output=str(tool_output),
                    )
                    messages.append(response)
                    messages.append(
                        {"role": "tool", "content": str(tool_output),
                         "tool_call_id": tool_call.get("id", tool_name)}
                    )
                continue  # next iteration

            # ── Plain text response — we're done ──────────────────────────────
            content = response.content if hasattr(response, "content") else str(response)

            # Basic format validation hook (subclasses can override)
            if not self._validate_output(content):
                format_retries += 1
                if format_retries > MAX_FORMAT_RETRIES:
                    return (
                        f"[{self.role.upper()}] Output validation failed after "
                        f"{MAX_FORMAT_RETRIES} retries. Escalating to user.\n\n"
                        f"Last output:\n{content}"
                    )
                messages.append(
                    HumanMessage(content="Your previous response had a formatting issue. "
                                         "Please try again with the correct format.")
                )
                continue

            self.memory.log_thought(
                agent_role=self.role, step=step, thought=content
            )
            return content

        return (
            f"[{self.role.upper()}] Reached max iterations ({MAX_ITERATIONS}) "
            "without a final answer. Stopping to prevent token burn."
        )

    # ── Tool invocation with circuit breaker + timeout ────────────────────────
    def _invoke_tool(self, tool_name: str, tool_input: dict, step: int) -> str:
        tool_obj = next((t for t in self.tools if t.name == tool_name), None)
        if tool_obj is None:
            return f"Error: tool '{tool_name}' not available for role '{self.role}'."
        try:
            output = run_with_timeout(
                tool_obj.invoke, args=(tool_input,), timeout=TOOL_TIMEOUT
            )
            circuit_breaker.record_success(self.session_id, tool_name)
            return output
        except CircuitBreaker.CircuitOpenError as e:
            return f"CIRCUIT_OPEN: {e}"
        except Exception as exc:  # noqa: BLE001
            error_msg = str(exc)
            try:
                circuit_breaker.record_failure(
                    self.session_id, tool_name, error_msg
                )
            except CircuitBreaker.CircuitOpenError as e:
                return f"CIRCUIT_OPEN: {e}"
            return f"Tool error: {error_msg}"

    # ── LLM call ─────────────────────────────────────────────────────────────
    def _call_llm(self, messages: list):
        if self.tools:
            return self.llm.bind_tools(self.tools).invoke(messages)
        return self.llm.invoke(messages)

    # ── Message assembly ─────────────────────────────────────────────────────
    def _build_messages(self, user_input: str) -> list:
        history = self.memory.get_recent_messages()
        msgs    = [SystemMessage(content=self.system_prompt)]
        for m in history[:-1]:  # skip the message we just added
            cls = HumanMessage if m["role"] == "human" else AIMessage
            msgs.append(cls(content=m["content"]))
        msgs.append(HumanMessage(content=user_input))
        return msgs

    # ── Override in subclasses for role-specific output validation ────────────
    def _validate_output(self, content: str) -> bool:
        return True  # base: always valid
