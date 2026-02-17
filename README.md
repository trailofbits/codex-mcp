# codex-mcp

MCP server wrapping the [OpenAI Codex CLI](https://github.com/openai/codex). Three tools:

- **codex_ask** — ask Codex a question inline, swapping in an OpenAI model for one turn
- **codex_exec** — send a raw prompt to Codex with full control over the input
- **codex_review** — review a git diff for bugs, security issues, and correctness

## Install

```
uvx codex-mcp-server
```

Or add to your Claude Code MCP settings:

```json
{
  "mcpServers": {
    "codex-mcp-server": {
      "command": "uvx",
      "args": ["codex-mcp-server"]
    }
  }
}
```

If using the [Trail of Bits skills marketplace](https://github.com/trailofbits/skills), install the `codex-mcp` plugin — it configures the MCP server automatically.

## Prerequisites

- [OpenAI Codex CLI](https://github.com/openai/codex): `npm i -g @openai/codex`
- Python 3.11+

## Tools

### codex_ask

Ask Codex a question inline, like swapping in an OpenAI model for one turn. Pass `conversation_context` so Codex knows what's been discussed.

```
codex_ask(
  question="How would you approach this differently?",
  conversation_context="<recent conversation text>",
)
```

### codex_review

Review a git diff for bugs, security issues, and correctness. Returns structured JSON with prioritized findings.

```
codex_review(
  diff="<git diff output>",
  focus="security",
  project_context="<CLAUDE.md contents>",
)
```

### codex_exec

Send a raw prompt with full control. Supports custom JSON schemas via `output_schema`.

```
codex_exec(
  prompt="Analyze this function: ...",
  output_schema="/path/to/schema.json",
)
```

## How It Works

- Runs `codex exec` with `--sandbox read-only` and `--ephemeral`
- Pipes prompts via stdin using temp files
- Uses `--output-schema` for structured JSON output (codex_review)
- Automatic model fallback: `gpt-5.3-codex` → `gpt-5.2-codex` on auth errors
- Timeout handling with SIGTERM → SIGKILL escalation

## License

[Apache 2.0](https://www.apache.org/licenses/LICENSE-2.0)
