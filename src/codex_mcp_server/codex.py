"""Async subprocess wrapper around the Codex CLI."""

import asyncio
import logging
import shutil
import tempfile
from dataclasses import dataclass
from pathlib import Path

logger = logging.getLogger(__name__)

DEFAULT_MODEL = "gpt-5.3-codex"
FALLBACK_MODEL = "gpt-5.2-codex"
DEFAULT_REASONING_EFFORT = "xhigh"
DEFAULT_TIMEOUT_SECONDS = 600
SIGTERM_GRACE_SECONDS = 5


@dataclass(frozen=True, slots=True)
class CodexResult:
    """Result from a codex exec invocation."""

    output: str
    stderr: str
    model_used: str
    return_code: int


def _find_codex() -> str | None:
    """Return the path to the codex binary, or None if not found."""
    return shutil.which("codex")


async def _run_once(
    prompt: str,
    *,
    model: str,
    reasoning_effort: str,
    output_schema_path: Path | None,
    timeout_seconds: int,
) -> CodexResult:
    """Run a single codex exec invocation."""
    codex_path = _find_codex()
    if codex_path is None:
        return CodexResult(
            output="",
            stderr=("codex: command not found. Install with: npm i -g @openai/codex"),
            model_used=model,
            return_code=127,
        )

    prompt_file = None
    output_file = None
    stderr_file = None
    try:
        prompt_file = Path(tempfile.mktemp(suffix=".txt", prefix="codex-prompt-"))
        output_file = Path(tempfile.mktemp(suffix=".txt", prefix="codex-output-"))
        stderr_file = Path(tempfile.mktemp(suffix=".txt", prefix="codex-stderr-"))

        prompt_file.write_text(prompt, encoding="utf-8")

        cmd = [
            codex_path,
            "exec",
            "-c",
            f'model="{model}"',
            "-c",
            f'model_reasoning_effort="{reasoning_effort}"',
            "--sandbox",
            "read-only",
            "--ephemeral",
            "-o",
            str(output_file),
        ]
        if output_schema_path is not None:
            cmd.extend(["--output-schema", str(output_schema_path)])
        cmd.append("-")

        with prompt_file.open("rb") as stdin_fh, stderr_file.open("wb") as stderr_fh:
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdin=stdin_fh,
                stdout=asyncio.subprocess.DEVNULL,
                stderr=stderr_fh,
            )

            try:
                await asyncio.wait_for(proc.wait(), timeout=timeout_seconds)
            except TimeoutError:
                proc.terminate()
                try:
                    await asyncio.wait_for(proc.wait(), timeout=SIGTERM_GRACE_SECONDS)
                except TimeoutError:
                    proc.kill()
                    await proc.wait()
                return CodexResult(
                    output="",
                    stderr=(
                        f"Codex timed out after {timeout_seconds}s. Try narrowing the diff scope."
                    ),
                    model_used=model,
                    return_code=-1,
                )

        output_text = ""
        if output_file.exists():
            output_text = output_file.read_text(encoding="utf-8").strip()
        stderr_text = ""
        if stderr_file.exists():
            stderr_text = stderr_file.read_text(encoding="utf-8").strip()

        return CodexResult(
            output=output_text,
            stderr=stderr_text,
            model_used=model,
            return_code=proc.returncode or 0,
        )
    finally:
        for f in (prompt_file, output_file, stderr_file):
            if f is not None:
                f.unlink(missing_ok=True)


def _is_auth_error(result: CodexResult) -> bool:
    """Check if the result indicates a model auth/access error."""
    markers = [
        "not supported when using Codex with a ChatGPT account",
        "model_not_found",
        "does not have access",
        "permission denied",
    ]
    text = result.stderr.lower()
    return any(m.lower() in text for m in markers)


async def run_codex_exec(
    prompt: str,
    *,
    model: str = DEFAULT_MODEL,
    reasoning_effort: str = DEFAULT_REASONING_EFFORT,
    output_schema_path: Path | None = None,
    timeout_seconds: int = DEFAULT_TIMEOUT_SECONDS,
) -> CodexResult:
    """Run codex exec with automatic model fallback on auth errors.

    Tries the primary model first. If it fails with an auth error,
    retries with the fallback model.
    """
    result = await _run_once(
        prompt,
        model=model,
        reasoning_effort=reasoning_effort,
        output_schema_path=output_schema_path,
        timeout_seconds=timeout_seconds,
    )

    if result.return_code != 0 and _is_auth_error(result):
        fallback = FALLBACK_MODEL if model == DEFAULT_MODEL else model
        if fallback != model:
            logger.info("Auth error with %s, falling back to %s", model, fallback)
            result = await _run_once(
                prompt,
                model=fallback,
                reasoning_effort=reasoning_effort,
                output_schema_path=output_schema_path,
                timeout_seconds=timeout_seconds,
            )

    return result
