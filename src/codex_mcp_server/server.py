"""FastMCP server exposing Codex CLI as MCP tools."""

from pathlib import Path

from fastmcp import FastMCP

from codex_mcp_server.codex import (
    DEFAULT_MODEL,
    DEFAULT_REASONING_EFFORT,
    DEFAULT_TIMEOUT_SECONDS,
    run_codex_exec,
)

SCHEMAS_DIR = Path(__file__).parent / "schemas"
REVIEW_SCHEMA_PATH = SCHEMAS_DIR / "codex-review-schema.json"

# fmt: off
# ruff: noqa: E501
# This prompt is verbatim from OpenAI's cookbook and must not be reformatted.
REVIEW_PROMPT = (
    "You are acting as a reviewer for a proposed code change made by another engineer.\n"
    "Focus on issues that impact correctness, performance, security, maintainability, or developer experience.\n"
    "Flag only actionable issues introduced by the pull request.\n"
    "When you flag an issue, provide a short, direct explanation and cite the affected file and line range.\n"
    "Prioritize severe issues and avoid nit-level comments unless they block understanding of the diff.\n"
    'After listing findings, produce an overall correctness verdict ("patch is correct" or "patch is incorrect") with a concise justification and a confidence score between 0 and 1.\n'
    "Ensure that file citations and line numbers are exactly correct using the tools available; if they are incorrect your comments will be rejected."
)
# fmt: on

ASK_SYSTEM_PROMPT = (
    "You are a helpful software engineering assistant. "
    "You are being consulted inline during another engineer's session. "
    "Answer directly and concisely. "
    "If conversation context is provided, use it to inform your answer "
    "but focus on the question asked."
)

mcp = FastMCP(
    "codex-mcp-server",
    instructions=(
        "MCP server wrapping the OpenAI Codex CLI. "
        "Provides codex_ask for inline questions, "
        "codex_exec for general prompts, and "
        "codex_review for structured code reviews."
    ),
)


def _format_result(
    output: str,
    stderr: str,
    model_used: str,
    return_code: int,
) -> str:
    """Format a CodexResult into a tool response string."""
    parts: list[str] = []
    if output:
        parts.append(output)
    if return_code != 0:
        parts.append(f"[exit code {return_code}]")
    if stderr:
        parts.append(f"[stderr] {stderr}")
    if not parts:
        parts.append("[no output]")
    parts.append(f"[model: {model_used}]")
    return "\n".join(parts)


@mcp.tool()
async def codex_ask(
    question: str,
    conversation_context: str = "",
    model: str = DEFAULT_MODEL,
    reasoning_effort: str = DEFAULT_REASONING_EFFORT,
    timeout_seconds: int = DEFAULT_TIMEOUT_SECONDS,
) -> str:
    """Ask Codex a question inline, like swapping in an OpenAI model for one turn.

    USE THIS when the user wants Codex's opinion, wants to "ask codex",
    or wants a second perspective on a question mid-conversation.
    Pass conversation_context so Codex knows what's been discussed.
    Returns plain text — NOT structured JSON.

    DO NOT use this for code review (use codex_review instead) or for
    raw prompt control with custom schemas (use codex_exec instead).

    Args:
        question: The question or instruction for Codex.
        conversation_context: Recent conversation history or relevant
            context to inform the answer.
        model: Codex model to use. Defaults to gpt-5.3-codex.
        reasoning_effort: Reasoning effort level. Defaults to xhigh.
        timeout_seconds: Timeout in seconds. Defaults to 600.
    """
    prompt_parts = [ASK_SYSTEM_PROMPT, ""]

    if conversation_context.strip():
        prompt_parts.append("Conversation context:")
        prompt_parts.append("---")
        prompt_parts.append(conversation_context.strip())
        prompt_parts.append("---")
        prompt_parts.append("")

    prompt_parts.append(question)

    full_prompt = "\n".join(prompt_parts)

    result = await run_codex_exec(
        full_prompt,
        model=model,
        reasoning_effort=reasoning_effort,
        timeout_seconds=timeout_seconds,
    )
    return _format_result(result.output, result.stderr, result.model_used, result.return_code)


@mcp.tool()
async def codex_exec(
    prompt: str,
    model: str = DEFAULT_MODEL,
    reasoning_effort: str = DEFAULT_REASONING_EFFORT,
    output_schema: str = "",
    timeout_seconds: int = DEFAULT_TIMEOUT_SECONDS,
) -> str:
    """Send a raw prompt to Codex with full control over the input.

    USE THIS when you need to craft a custom prompt from scratch, or
    need structured output via a custom JSON schema. This is the
    low-level tool — you control the entire prompt.

    DO NOT use this for code review (use codex_review instead) or for
    simple questions mid-conversation (use codex_ask instead).

    Args:
        prompt: The complete prompt text to send to Codex.
        model: Codex model to use. Defaults to gpt-5.3-codex.
        reasoning_effort: Reasoning effort level. Defaults to xhigh.
        output_schema: Path to a JSON schema file for structured output.
        timeout_seconds: Timeout in seconds. Defaults to 600.
    """
    schema_path = Path(output_schema) if output_schema else None
    if schema_path is not None and not schema_path.exists():
        return f"Error: output_schema file not found: {output_schema}"

    result = await run_codex_exec(
        prompt,
        model=model,
        reasoning_effort=reasoning_effort,
        output_schema_path=schema_path,
        timeout_seconds=timeout_seconds,
    )
    return _format_result(result.output, result.stderr, result.model_used, result.return_code)


@mcp.tool()
async def codex_review(
    diff: str,
    focus: str = "",
    project_context: str = "",
    model: str = DEFAULT_MODEL,
    reasoning_effort: str = DEFAULT_REASONING_EFFORT,
    timeout_seconds: int = DEFAULT_TIMEOUT_SECONDS,
) -> str:
    """Review a git diff for bugs, security issues, and correctness.

    USE THIS when you have a git diff to review. Returns structured
    JSON with prioritized findings, confidence scores, and exact file
    locations. Uses OpenAI's published code review prompt.

    DO NOT use this for general questions (use codex_ask) or for
    non-review prompts (use codex_exec).

    Args:
        diff: The git diff text to review.
        focus: Optional focus area (e.g., "security", "performance").
        project_context: Project conventions (e.g., CLAUDE.md contents).
        model: Codex model to use. Defaults to gpt-5.3-codex.
        reasoning_effort: Reasoning effort level. Defaults to xhigh.
        timeout_seconds: Timeout in seconds. Defaults to 600.
    """
    if not diff.strip():
        return "Error: diff is empty. Nothing to review."

    prompt_parts = [REVIEW_PROMPT, ""]

    if project_context.strip():
        prompt_parts.append("Project conventions and standards:")
        prompt_parts.append("---")
        prompt_parts.append(project_context.strip())
        prompt_parts.append("---")
        prompt_parts.append("")

    if focus.strip():
        prompt_parts.append(f"Focus: {focus.strip()}")
        prompt_parts.append("")

    prompt_parts.append("Diff to review:")
    prompt_parts.append("---")
    prompt_parts.append(diff)
    prompt_parts.append("---")

    full_prompt = "\n".join(prompt_parts)

    result = await run_codex_exec(
        full_prompt,
        model=model,
        reasoning_effort=reasoning_effort,
        output_schema_path=REVIEW_SCHEMA_PATH,
        timeout_seconds=timeout_seconds,
    )

    return _format_result(result.output, result.stderr, result.model_used, result.return_code)


def main() -> None:
    """Entry point for the codex-mcp-server command."""
    mcp.run()


if __name__ == "__main__":
    main()
