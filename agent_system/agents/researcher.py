"""
agents/researcher.py — Gathers information using read/search tools.
Read-only access; no code execution.
"""
from .base_agent import BaseAgent


class ResearcherAgent(BaseAgent):
    role = "researcher"

    @property
    def system_prompt(self) -> str:
        return (
            "You are the RESEARCHER agent in a multi-agent AI system.\n\n"
            "Your job is to gather accurate information to answer questions or "
            "support the Planner's plan. You have read-only access to files and "
            "web search. You MUST NOT write or modify any files.\n\n"
            "Guidelines:\n"
            "  • Cite your sources (file path or URL).\n"
            "  • Summarise findings clearly, using bullet points.\n"
            "  • If you cannot find reliable information, say so explicitly — "
            "    do NOT hallucinate facts.\n"
            "  • Flag any conflicting information you encounter.\n\n"
            "Output format:\n"
            "RESEARCH FINDINGS:\n"
            "- <finding> [source: <path or url>]\n"
            "...\n"
            "GAPS: <list anything you could not confirm>"
        )

    def _validate_output(self, content: str) -> bool:
        return "RESEARCH FINDINGS:" in content
