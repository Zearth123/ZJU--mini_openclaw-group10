# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

mini-OpenClaw is a student build-your-own CLI agent (like Claude Code) over 10 days. It's a **ReAct loop** agent that takes a natural-language task, iteratively calls an LLM backend, executes tool calls the model generates, and feeds results back until completion.

This is a **skeleton repo** — almost every function body is `raise NotImplementedError("DayX: ...")`. Only the structural scaffolding and type definitions are complete.

## Quick Start

```bash
# Environment
conda create -n openclaw python=3.11 && conda activate openclaw
pip install -r requirements.txt

# Self-check (verifies all modules import correctly)
python -m agent.cli --selfcheck

# Run with fake backend (offline stub)
python -m agent.cli "创建 hello.py 并运行"

# Run with real backend (requires DEEPSEEK_API_KEY)
export DEEPSEEK_API_KEY=sk-...
python -m agent.cli "创建 hello.py 并运行"
```

## Key Commands

- **Entry point**: `python -m agent.cli [--selfcheck | "task string"]`
- **Self-check**: `python -m agent.cli --selfcheck` — validates module imports and basic plumbing
- **View all TODOs**: `grep -rn "TODO\[Day" .` — shows every unimplemented section by day
- **Git tags**: milestones tagged as `v1` (Day6), `v3` (Day9), `final` (Day10)

## Dependencies

- `httpx` — DeepSeek API calls + web_fetch
- `pydantic` — tool schema validation
- `markdownify` — web_fetch HTML→markdown (Day7)
- `ripgrep` — system package (grep tool, Day6)
- No ML dependencies (vllm/peft/torch) — uses DeepSeek API, not local models

## Architecture

### Data Flow

```
User request → agent/cli.py → AgentLoop.run()
  → backend.chat(messages, tool_schemas)    # LLM responds
  → parse tool_calls from response
  → for each tool_call: registry.get(name).run(**args)
  → append result as role="tool" message
  → loop until model returns text (no tool_calls)
  → return final answer
```

### Module Layout

| Module | Purpose | Implemented By |
|--------|---------|---------------|
| `agent/` | Entry point (`cli.py`), ReAct loop (`loop.py`), context/token management (`context.py`), system prompt (`prompts.py`) | Day2,5,7 |
| `backend/` | DeepSeek API client (`client.py`), offline stub (`fake_backend.py`) | Day1-2 |
| `prompt/` | Prompt template rendering + tool call parsing (no special API) | Day3 |
| `tools/` | Tool abstraction (`base.py`), file ops (`fs.py`), shell (`shell.py`), extended tools (`more_tools.py`) | Day5-7 |
| `mcp/` | Minimal MCP client (`client.py`), echo server (`echo_server.py`) | Day8 |
| `skills/` | Skill loader (`loader.py`), example skill | Day9 |
| `eval/` | Test sets + metrics (`metrics.py`, `tasks.py`) | Day7,10 |

### Key Abstractions

**Tool** (`tools/base.py`): A dataclass with `name`, `description`, `parameters` (JSON Schema), and `run(**args) -> str`. The model never calls functions directly — it generates `<tool_call>{...}</tool_call>` text that the loop parses and dispatches.

**ToolRegistry** (`tools/base.py`): Collects tools, generates OpenAI-compatible schemas via `.schemas()`, dispatches calls via `.get(name).run(...)`.

**Backend Interface**: Both `DeepSeekBackend` and `FakeBackend` implement `chat(messages, tools) -> {"role", "content", "tool_calls"}`. `FakeBackend` is a rule-based stub that "calls" one tool then returns — useful for offline pipeline testing.

**MCP Integration** (`mcp/client.py`): MCP server tools are wrapped as regular `Tool` objects and merged into the same `ToolRegistry` (prefixed `mcp__` to avoid name collisions). Transparent to the loop.

**Skills** (`skills/loader.py`): SKILL.md files with YAML frontmatter (`name`, `description`) + markdown body. Loaded into system context for domain guidance. Not tools — they guide the model's behavior for specific task types.

### Build Order (by Day)

1. **Day1-2**: Backend connectivity (DeepSeek API client) + first tool schemas
2. **Day3**: Prompt rendering — turn structured messages+tools into a single prompt string; parse tool calls from model output
3. **Day5**: Implement read/write/bash tools + AgentLoop.run() → **v0.5**
4. **Day6**: Add edit/grep/glob tools → **v1 milestone** (end-to-end agent)
5. **Day7**: Add web_fetch/task_list, context compaction, error recovery → v2
6. **Day8**: MCP client (stdio+JSON-RPC) → **v3 milestone** (extensible)
7. **Day9**: Skills loader + domain-specific skill
8. **Day10**: Security layer (permissions/sandbox/injection), eval/ablation → **final**

### Environment Variables

- `DEEPSEEK_API_KEY` — required for real backend
- `DEEPSEEK_BASE_URL` — default `https://api.deepseek.com`
- `DEEPSEEK_MODEL` — default `deepseek-chat`

## Conventions

- Each module has its own `README.md` recording design decisions (counts toward documentation grade)
- All TODO markers follow the pattern `# TODO[DayN]` — `grep -rn "TODO\[Day" .` to find them
- Single git repo, milestone tags (`v1`, `v3`, `final`)
- The model runs via API (DeepSeek) — no local GPU/ML infra needed
