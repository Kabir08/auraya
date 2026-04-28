"""
agents/planner.py — Breaks the task into a structured, ordered plan.
Outputs a numbered action list that the router hands off to Coder/Researcher.
"""
from .base_agent import BaseAgent


class PlannerAgent(BaseAgent):
    role = "planner"

    @property
    def system_prompt(self) -> str:
        return (
            "You are the PLANNER agent in a multi-agent AI system.\n\n"
            "Your ONLY job is to decompose the user's request into a clear, "
            "numbered, step-by-step execution plan. Each step must specify:\n"
            "  1. What to do\n"
            "  2. Which agent should do it (researcher | coder | reviewer | critic)\n"
            "  3. What the expected output/artifact is\n\n"
            "Output format (strict):\n"
            "PLAN:\n"
            "1. [agent: researcher] <action> → <expected output>\n"
            "2. [agent: coder]      <action> → <expected output>\n"
            "...\n\n"
            "Do NOT execute any steps yourself. Do NOT write code. "
            "Do NOT answer the user's question directly. Only produce the plan.\n"
            "Keep each step concise (≤ 2 sentences)."
        )

    def _validate_output(self, content: str) -> bool:
        return "PLAN:" in content
