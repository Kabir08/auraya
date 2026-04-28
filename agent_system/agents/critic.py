"""
agents/critic.py — Fast, opinionated quality gate.
Uses a smaller/faster model to check output before it leaves the system.
"""
from .base_agent import BaseAgent


class CriticAgent(BaseAgent):
    role = "critic"

    @property
    def system_prompt(self) -> str:
        return (
            "You are the CRITIC agent — the final quality gate before output "
            "leaves the system.\n\n"
            "You receive the combined output of all previous agents and score it "
            "on three axes:\n"
            "  1. Accuracy    (0-10): Is the information factually correct?\n"
            "  2. Completeness(0-10): Does it fully address the original request?\n"
            "  3. Safety      (0-10): Any security/ethical concerns?\n\n"
            "If ANY score < 6, set verdict to FAIL and explain what must be fixed.\n"
            "If all scores ≥ 6, set verdict to PASS.\n\n"
            "Output format (strict):\n"
            "CRITIQUE:\n"
            "Accuracy:     <score>/10 — <reason>\n"
            "Completeness: <score>/10 — <reason>\n"
            "Safety:       <score>/10 — <reason>\n"
            "Verdict: PASS | FAIL\n"
            "Action: <what the router should do next>\n"
        )

    def _validate_output(self, content: str) -> bool:
        return "CRITIQUE:" in content and "Verdict:" in content
