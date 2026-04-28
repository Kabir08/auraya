"""
safety/tools.py — LangChain tool definitions scoped to the sandbox workspace.

Each tool is plain LangChain BaseTool subclass.
The ToolRegistry in guards.py slices these per-role via ROLE_TOOL_PERMISSIONS.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Optional, Type

from langchain_core.tools import BaseTool
from pydantic import BaseModel, Field

from agent_system.config import WORKSPACE_ROOT


# ─── Input schemas (Pydantic v2) ──────────────────────────────────────────────

class ReadFileInput(BaseModel):
    path: str = Field(description="Relative path inside the sandbox workspace.")

class WriteFileInput(BaseModel):
    path: str    = Field(description="Relative path inside the sandbox workspace.")
    content: str = Field(description="Full content to write to the file.")

class ListDirectoryInput(BaseModel):
    path: str = Field(default=".", description="Relative directory path to list.")

class WebSearchInput(BaseModel):
    query: str = Field(description="Search query string.")

class GetProjectStateInput(BaseModel):
    project_id: str = Field(description="Project identifier.")
    key: str        = Field(description="State key to retrieve.")

class SetProjectStateInput(BaseModel):
    project_id: str = Field(description="Project identifier.")
    key: str        = Field(description="State key to set.")
    value: str      = Field(description="Value to store (serialised as string).")

class TerminalInput(BaseModel):
    command: str = Field(description="Shell command to run inside the sandbox.")


# ─── Sandbox path resolver ────────────────────────────────────────────────────

def _resolve_sandbox(rel_path: str) -> Path:
    """
    Resolve *rel_path* relative to WORKSPACE_ROOT and reject any path that
    escapes the sandbox via '..' traversal.
    """
    root = Path(WORKSPACE_ROOT).resolve()
    target = (root / rel_path).resolve()
    if not str(target).startswith(str(root)):
        raise PermissionError(
            f"Path '{rel_path}' escapes the sandbox root '{root}'."
        )
    return target


# ─── Tool implementations ─────────────────────────────────────────────────────

class ReadFileTool(BaseTool):
    name: str = "read_file"
    description: str = (
        "Read the contents of a file inside the sandbox workspace. "
        "Provide a path relative to the workspace root."
    )
    args_schema: Type[BaseModel] = ReadFileInput

    def _run(self, path: str) -> str:
        try:
            target = _resolve_sandbox(path)
            return target.read_text(encoding="utf-8")
        except PermissionError as e:
            return f"PERMISSION_DENIED: {e}"
        except FileNotFoundError:
            return f"ERROR: File not found: {path}"
        except Exception as e:  # noqa: BLE001
            return f"ERROR: {e}"


class WriteFileTool(BaseTool):
    name: str = "write_file"
    description: str = (
        "Write content to a file inside the sandbox workspace. "
        "Creates parent directories if they don't exist."
    )
    args_schema: Type[BaseModel] = WriteFileInput

    def _run(self, path: str, content: str) -> str:
        try:
            target = _resolve_sandbox(path)
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(content, encoding="utf-8")
            return f"OK: Written {len(content)} chars to {path}"
        except PermissionError as e:
            return f"PERMISSION_DENIED: {e}"
        except Exception as e:  # noqa: BLE001
            return f"ERROR: {e}"


class ListDirectoryTool(BaseTool):
    name: str = "list_directory"
    description: str = (
        "List files and subdirectories inside the sandbox workspace."
    )
    args_schema: Type[BaseModel] = ListDirectoryInput

    def _run(self, path: str = ".") -> str:
        try:
            target = _resolve_sandbox(path)
            if not target.is_dir():
                return f"ERROR: '{path}' is not a directory."
            entries = sorted(target.iterdir(), key=lambda p: (p.is_file(), p.name))
            lines = [
                f"{'[DIR] ' if e.is_dir() else '[FILE]'} {e.name}"
                for e in entries
            ]
            return "\n".join(lines) if lines else "(empty directory)"
        except PermissionError as e:
            return f"PERMISSION_DENIED: {e}"
        except Exception as e:  # noqa: BLE001
            return f"ERROR: {e}"


class WebSearchTool(BaseTool):
    """
    Stub web search tool.  Replace _run with a real API call (Tavily, SerpAPI, etc.)
    by setting TAVILY_API_KEY / SERPAPI_API_KEY in .env and importing the client.
    """
    name: str = "web_search"
    description: str = "Search the web for up-to-date information on a topic."
    args_schema: Type[BaseModel] = WebSearchInput

    def _run(self, query: str) -> str:
        # ── Real implementation (Tavily) ─────────────────────────────────────
        tavily_key = os.getenv("TAVILY_API_KEY", "")
        if tavily_key:
            try:
                from tavily import TavilyClient  # type: ignore
                client = TavilyClient(api_key=tavily_key)
                results = client.search(query, max_results=5)
                snippets = [
                    f"[{r['title']}] {r['content']}" for r in results.get("results", [])
                ]
                return "\n---\n".join(snippets) or "No results."
            except Exception as e:  # noqa: BLE001
                return f"Search error: {e}"
        # ── Fallback stub ────────────────────────────────────────────────────
        return (
            f"[STUB] Web search not configured. "
            f"Set TAVILY_API_KEY in .env to enable real search.\n"
            f"Query was: {query}"
        )


class GetProjectStateTool(BaseTool):
    name: str = "get_project_state"
    description: str = "Retrieve a stored key-value pair for a project from the database."
    args_schema: Type[BaseModel] = GetProjectStateInput

    def _run(self, project_id: str, key: str) -> str:
        from agent_system.memory.sql_memory import AgentMemoryManager
        mem = AgentMemoryManager(session_id=f"state_{project_id}")
        value = mem.get_project_state(project_id, key)
        return value if value is not None else f"(no value stored for key='{key}')"


class SetProjectStateTool(BaseTool):
    name: str = "set_project_state"
    description: str = "Store a key-value pair for a project in the database."
    args_schema: Type[BaseModel] = SetProjectStateInput

    def _run(self, project_id: str, key: str, value: str) -> str:
        from agent_system.memory.sql_memory import AgentMemoryManager
        mem = AgentMemoryManager(session_id=f"state_{project_id}")
        mem.set_project_state(project_id, key, value)
        return f"OK: {project_id}.{key} = {value}"


class SandboxedTerminalTool(BaseTool):
    """
    Runs a shell command with CWD locked to WORKSPACE_ROOT.
    HITL gate in BaseAgent.run() blocks this unless user approves.
    """
    name: str = "terminal"
    description: str = (
        "Execute a shell command inside the sandboxed workspace directory. "
        "Requires human approval (HITL). Use sparingly."
    )
    args_schema: Type[BaseModel] = TerminalInput

    def _run(self, command: str) -> str:
        import subprocess  # noqa: PLC0415
        try:
            result = subprocess.run(
                command,
                shell=True,
                capture_output=True,
                text=True,
                cwd=WORKSPACE_ROOT,
                timeout=20,
            )
            output = result.stdout + result.stderr
            return output.strip() or "(no output)"
        except subprocess.TimeoutExpired:
            return "ERROR: Command timed out after 20s."
        except Exception as e:  # noqa: BLE001
            return f"ERROR: {e}"


# ─── Default tool pool ────────────────────────────────────────────────────────
# Instantiated once; ToolRegistry slices per-role.

ALL_TOOLS = [
    ReadFileTool(),
    WriteFileTool(),
    ListDirectoryTool(),
    WebSearchTool(),
    GetProjectStateTool(),
    SetProjectStateTool(),
    SandboxedTerminalTool(),
]
