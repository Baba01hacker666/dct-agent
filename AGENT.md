# AGENT.md - Agent Instructions for DCT Agent

This file provides guidance and technical context for autonomous agents and AI assistants working on the **DCT Agent (Doraemon Cyber Team)** codebase.

## 🤖 What is DCT Agent?

DCT Agent is a multi-server, highly resilient AI agent CLI built with Python. It features:
- Support for **Ollama**, **OpenRouter**, and any **OpenAI-compatible** provider.
- Automatic failover and load-balancing via a Model Router.
- An autonomous "Agent Mode" capable of interacting with the local OS, web, and files.
- Multi-agent orchestration via "Squads" and hierarchical task decomposition.
- Robust state management with auto-probing, background cleanup, and network retries.

## 📂 Detailed Directory Structure

The source code resides under the `dct/` directory:

```text
dct/
├── agent/            # Autonomous Agent Loop
│   ├── codeagent.py  # Houses the main agent loop, injects context, parses XML tools.
│   ├── session.py    # Maintains chat history, session state, token limits, mode.
│   └── __init__.py
├── cli/              # Interactive REPL & UI
│   ├── shell.py      # Main interactive loop using `prompt_toolkit`. Handles `/` commands.
│   ├── display.py    # Uses `rich` for formatting terminal outputs, tables, etc.
│   ├── clipboard.py  # Utilities for copying text to OS clipboard.
│   ├── help.py       # CLI help text and documentation.
│   ├── main.py       # Entry point for the CLI.
│   └── __init__.py
├── core/             # State, Config, Clients & APIs
│   ├── registry.py   # Manages `servers.json`, handles model routing and failover logic.
│   ├── config.py     # Manages application-level `config.json`.
│   ├── http.py       # Robust HTTP session manager with backoffs and retries.
│   ├── client.py     # Base clients for providers.
│   ├── ollama.py     # Streaming HTTP clients specific to Ollama APIs.
│   ├── openrouter.py # OpenRouter-specific integration.
│   ├── probe.py      # Parallel health checking/probing of registered endpoints.
│   └── theme.py      # `rich` theme configurations.
├── skills/           # Agent Personas & Specialized Instructions
│   ├── notebook.py   # Skill definition for Jupyter notebook interaction.
│   └── web.py        # Web interaction specific logic.
├── tools/            # Agent Execution Layer (Tool Functions)
│   ├── executor.py   # Runs Python/Bash locally via `subprocess`. Auto-handles pip installs.
│   ├── files.py      # File system tools (read, write, patch, tree, ripgrep).
│   ├── image.py      # Vision handling (read_image).
│   ├── tasks.py      # Structured task and goal tracking logic.
│   └── web.py        # HTTP fetching, DuckDuckGo search, CSS selectors.
├── __main__.py       # Module entry point (`python -m dct`).
└── __init__.py
```

Outside of `dct/`:
- `tests/`: Contains pytest tests (`test_background_tasks.py`, `test_providers.py`, etc.).
- `pyproject.toml`: Dependency and build configuration.

## 🛠️ How to Work on this Codebase

When writing code or debugging, follow these workflows:

### Setup & Execution
- **Install/Setup**: `pip install -e .`
- **Run Application**: `python -m dct` (or `dct` if installed globally)
- **Run Single Test**: `pytest tests/test_file.py::test_function_name`
- **Run All Tests**: `pytest tests/`

### Linting & Formatting
- **Format Code**: `black --line-length 79 dct/`
- **Lint Code**: `flake8 dct/` (Note: `.flake8` ignores E501, E128, E126, W503, W504, F841)

### Key Architectural Concepts for Agents

1. **Agent Tool Execution (`dct/tools/`)**:
   Tools are the actions the agent can perform. They are defined primarily in `files.py`, `executor.py`, and `web.py`. When modifying how the agent interacts with the world, look here.
2. **The Shell REPL (`dct/cli/shell.py`)**:
   All user slash commands (e.g., `/use`, `/models`, `/squad`) are handled here. If adding a new slash command, add the handler here.
3. **Model Router & Registry (`dct/core/registry.py`)**:
   When implementing new provider integrations or tweaking how models are selected during failover, modify the registry.
4. **State Persistence**:
   - Servers are saved to `~/.config/dct/servers.json`.
   - Configs are saved to `~/.config/dct/config.json`.
5. **Token Management**:
   The agent dynamically truncates memory when token limits are reached, utilizing summarization. Check `session.py` and `codeagent.py` for context window management.

## 📝 General Rules for Agents

- Write clean, idiomatic Python 3.11+.
- Use type hints wherever possible to maintain clarity.
- When creating or modifying CLI output, use the `rich` library to ensure consistent formatting.
- Respect the existing 79-character line length limit for formatting.
- If implementing new tools, make sure to add safe fallbacks, timeout limits, and error handling so that the main agent loop doesn't crash during execution.

## ⚙️ How It Works Internally

### 1. The Agent Loop (`dct/agent/codeagent.py`)
The `CodeAgent` runs a continuously polling loop that receives responses from the streaming model and parses them for XML-like tool execution tags (e.g., `<tool>run_bash</tool><code>...</code>`). 
- When a valid tool tag is detected, the agent dispatches the tool call to the execution layer (`dct.tools.*`).
- Results (stdout, stderr, diffs) are collected and fed back into the chat as "Tool Output".
- The loop continues until the agent emits a `<tool>DONE</tool>` tag to signal completion.

### 2. Background Tasks & Sub-agents
The agent loop supports running arbitrary processes in the background via the `<background>true</background>` XML parameter.
- Background tools (like `run_bash` or `run_subagent`) spawn isolated daemon threads.
- Their output is continuously appended to an internal thread-safe dictionary (`BACKGROUND_TASKS` / `BACKGROUND_SUBAGENTS`).
- The main agent uses `bg_status` to asynchronously check logs, `bg_kill` to terminate, and `bg_send_input` to write to standard input streams without halting the primary loop.

### 3. Model Router & Failover (`dct/core/registry.py`)
The application is designed to survive offline models and endpoints mid-generation.
- When an interaction is initiated, the router determines the `Server` by:
  1. Evaluating the explicitly requested alias or model.
  2. Resolving the fastest registered endpoint with the requested model.
  3. Falling back to the fastest online server's best model.
- If a streaming HTTP response fails dynamically, the exception triggers a re-probe and automatically rolls over to the next available Server in the `servers.json` registry.

### 4. Context Pruning & Summarization (`dct/agent/session.py`)
To prevent infinite context expansion during long autonomous runs:
- `session.py` maintains a token counter estimation per turn.
- Once a threshold is breached (~30k tokens), the system triggers a background pruning wave. 
- It isolates old tool executions (keeping the latest few turns for immediate context), makes a secondary API call to summarize them, and injects that summary as a persistent memory block. This preserves high-level objectives while freeing up raw token space.

### 5. Multi-Agent Orchestration (`dct/cli/shell.py`)
The `/orchestrate` command elevates single-agent execution by decomposing high-level tasks:
- **Planning Phase**: A "planner" agent creates a Directed Acyclic Graph (DAG) of sub-tasks.
- **Execution Waves**: Sub-tasks with no dependencies are executed simultaneously in parallel using separate `CodeAgent` instances.
- **Context Flow**: The stdout/summary of completed tasks is pipelined directly into the system prompts of dependent downstream tasks.

### 6. Autonomous Memory Architecture (`dct/agent/codeagent.py`)
DCT Agent incorporates a state-of-the-art hybrid memory system to achieve recursive self-improvement:
- **Global Persona**: Core identities (`soul.md`, `user.md`, `memory.md`) are persisted globally in `~/.config/dct/`. The agent can autonomously modify them using `<tool>core_memory_manage</tool>`.
- **Project Context**: Repository-specific context is automatically loaded from `.dct/project.md` in the current working directory, providing codebase-isolated learning.
- **Archival Memory**: An infinite vector database (`~/.config/dct/memory.json`) powered by pure-Python cosine similarity allows deep RAG lookup using `<tool>memory_store</tool>` and `<tool>memory_search</tool>`.
- **Recursive Learning**: Goal mode explicitly triggers an autonomous `/learn` loop upon completion. The agent reads its own conversation history, identifies successes and failures, and extracts reusable insights into its memory files to prevent repeating mistakes.

## 🚀 Roadmap (The Final Frontiers)

When extending the architecture, these are the high-priority "Final Frontiers" left to implement:
1. **Docker Sandboxing**: Currently, terminal execution happens on the host machine. We need ephemeral Docker sandboxing (like OpenHands) for security.
2. **Browser/Playwright Integration**: The agent needs a headless browser environment to visually interact with web apps and debug UI natively.
3. **LSP Integration**: Add `goto_definition` and `find_references` to give the agent true IDE-like capabilities beyond raw `grep`.
4. **Semantic Repo Map**: Implement an auto-generating `repo_map.md` (via `ctags` or Tree-sitter) for large repositories to prevent blind file searches.
5. **Dynamic Swarm Routing**: Upgrade the Orchestrator to automatically select the optimal model per-task (e.g., using a fast 7B model for file search, and a deep reasoning model for logic).
