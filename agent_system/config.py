"""
config.py — Central configuration and API key manager.
Loads .env, exposes all settings as typed constants.
Add new providers here as you integrate them.
"""
import os
from dotenv import load_dotenv

load_dotenv()


# ─── LLM Provider Keys ────────────────────────────────────────────────────────
GROQ_API_KEY: str = os.getenv("GROQ_API_KEY", "")

# Placeholders — uncomment & populate .env when ready
DEEPSEEK_API_KEY: str = os.getenv("DEEPSEEK_API_KEY", "")
OPENAI_API_KEY: str = os.getenv("OPENAI_API_KEY", "")
ANTHROPIC_API_KEY: str = os.getenv("ANTHROPIC_API_KEY", "")


# ─── Database ─────────────────────────────────────────────────────────────────
DATABASE_URL: str = os.getenv("DATABASE_URL", "sqlite:///./agent_memory.db")

# ─── Filesystem Sandbox ───────────────────────────────────────────────────────
WORKSPACE_ROOT: str = os.getenv(
    "WORKSPACE_ROOT",
    os.path.join(os.path.dirname(__file__), "workspace"),
)
os.makedirs(WORKSPACE_ROOT, exist_ok=True)

# ─── Safety Limits ────────────────────────────────────────────────────────────
MAX_ITERATIONS: int = int(os.getenv("MAX_ITERATIONS", "12"))
RECURSION_LIMIT: int = int(os.getenv("RECURSION_LIMIT", "50"))
GLOBAL_TIMEOUT: int = int(os.getenv("GLOBAL_TIMEOUT_SECONDS", "120"))
TOOL_TIMEOUT: int = int(os.getenv("TOOL_TIMEOUT_SECONDS", "20"))
MAX_CONSECUTIVE_TOOL_FAILURES: int = int(os.getenv("MAX_CONSECUTIVE_TOOL_FAILURES", "3"))
MAX_FORMAT_RETRIES: int = int(os.getenv("MAX_FORMAT_RETRIES", "2"))

# ─── Model Defaults ───────────────────────────────────────────────────────────
DEFAULT_TEMPERATURE: float = float(os.getenv("DEFAULT_TEMPERATURE", "0.2"))
WINDOW_BUFFER_SIZE: int = int(os.getenv("WINDOW_BUFFER_SIZE", "8"))

# ─── Groq model map per role ──────────────────────────────────────────────────
# Swap these out to change which Groq model each role uses.
ROLE_MODEL_MAP: dict[str, str] = {
    "planner":    "llama-3.3-70b-versatile",
    "coder":      "llama-3.3-70b-versatile",
    "reviewer":   "llama-3.3-70b-versatile",
    "researcher": "llama-3.3-70b-versatile",
    "critic":     "llama-3.1-8b-instant",   # faster/cheaper for quick feedback
    "summarizer": "llama-3.1-8b-instant",
}


def get_groq_llm(role: str):
    """Return a ChatGroq instance configured for *role*."""
    from langchain_groq import ChatGroq  # local import to keep config import fast

    if not GROQ_API_KEY:
        raise EnvironmentError(
            "GROQ_API_KEY is not set. "
            "Run: export GROQ_API_KEY='your_key'  or add it to .env"
        )

    model_name = ROLE_MODEL_MAP.get(role, "llama3-70b-8192")
    return ChatGroq(
        api_key=GROQ_API_KEY,
        model_name=model_name,
        temperature=DEFAULT_TEMPERATURE,
        max_retries=2,
    )


# ─── Future providers (stubs) ─────────────────────────────────────────────────
def get_deepseek_llm(role: str = "default"):
    """Stub — wire in once DEEPSEEK_API_KEY is available."""
    raise NotImplementedError("DeepSeek integration coming soon.")


def get_openai_llm(role: str = "default"):
    """Stub — wire in once OPENAI_API_KEY is available."""
    raise NotImplementedError("OpenAI integration coming soon.")
