# DCT Agent — Doraemon Cyber Team
**Multi-server AI agent · v3.2**
made by baba01hacker

Supports **Ollama**, **OpenRouter**, and **any OpenAI-compatible provider** (DeepSeek, Qwen, Z.ai, Groq, etc.). Automatic failover, load-balancing, autonomous agent mode, multi-agent squads, and hierarchical task orchestration.

## Install

### Stable Release (PyPI)
Install the stable version from PyPI using `pip` or `pipx`:
```bash
# Using pip
pip install dct-agent

# Using pipx (recommended for CLI apps)
pipx install dct-agent
```

### Latest Development Version (GitHub)
Install the latest version directly from GitHub:
```bash
# Using pipx (recommended)
pipx install git+https://github.com/Baba01hacker666/dct-agent.git

# Using pip
pip install git+https://github.com/Baba01hacker666/dct-agent.git
```

Once installed, launch the interactive CLI:
```bash
dct
# or as a module:
python -m dct
```

## Quick Start

### Ollama (local or remote)
```bash
# Register servers
python -m dct add localhost 11434 local
python -m dct add 192.168.1.10 11434 home "home lab box"
python -m dct add 10.0.0.5 11434 vps1 "DigitalOcean"

# With auth + TLS
python -m dct add secure-host.example.com 443 prod --api-key mytoken --tls --no-tls-verify

# Probe all
python -m dct probe

# List all models across servers
python -m dct models

# Launch interactive shell
python -m dct
```

### OpenAI-Compatible Providers (DeepSeek, Qwen, Z.ai, Groq, etc.)
```bash
# Convenience — built-in presets (13 providers)
python -m dct add-provider deepseek sk-xxx
python -m dct add-provider qwen sk-xxx
python -m dct add-provider groq sk-xxx
python -m dct add-provider together sk-xxx

# Or with full URL for any OpenAI-compatible API
python -m dct add-openai https://api.deepseek.com sk-xxx deepseek

# Register OpenRouter
python -m dct add-openrouter sk-or-xxx
```

### Agent Skills
```bash
# List all skill presets
/skills

# Load a specialized persona (sets system prompt + enables agent mode)
/skill web-design    # Frontend — HTML, CSS, JS, responsive UIs
/skill python        # Idiomatic typed Python 3.11+
/skill pentest       # Penetration testing workflow
/skill bug-hunt      # Security code review
/skill devops        # Docker, K8s, CI/CD, cloud
```

### Config
```bash
# Set defaults (persisted to ~/.config/dct/config.json)
/config set default_server deepseek
/config set default_model deepseek-chat
/config set auto_probe_interval 120   # background health check every 2 min (0 = off)
```

## Shell Commands

### Server Management
| Command | Description |
|---|---|
| `/servers` | List all servers with status, latency, model count |
| `/add <host> <port> [alias] [note] [--api-key KEY] [--tls] [--no-tls-verify]` | Register + probe an Ollama server |
| `/add-openai <base_url> <api_key> [alias] [note]` | Register an OpenAI-compatible provider |
| `/add-provider <name> <api_key> [alias]` | Quick-add from built-in presets (deepseek, qwen, groq, etc.) — use `--list` to see all |
| `/remove <alias\|#>` | Unregister a server |
| `/probe` | Probe **all** servers in parallel |
| `/probe <alias\|#>` | Detailed probe of one server (all endpoints) |
| `/use <alias\|#>` | Switch active server |

### Model Management
| Command | Description |
|---|---|
| `/models` | Models on active server |
| `/models <alias\|#>` | Models on specific server |
| `/allmodels` | All models across all servers |
| `/model <n>` | Switch model |
| `/pull <model>` | Pull on active server |
| `/pull <alias\|#> <model>` | Pull on specific server |
| `/delete <model>` | Delete from active server |
| `/show <model>` | Model info, system prompt, modelfile |

### Chat & Session
| Command | Description |
|---|---|
| `/clear` | Clear history |
| `/history` | Turn count + token estimate |
| `/system <prompt>` | Set system prompt |
| `/prompts` | List built-in system prompt presets |
| `/prompt <name>` | Apply a built-in system prompt preset |
| `/skills` | List agent skill presets (specialized personas) |
| `/skill <name>` | Load an agent skill (sets system prompt + auto-enables agent) |

### Multi-Agent Commands
| Command | Description |
|---|---|
| `/squad list` | List all squads |
| `/squad create <name>` | Create a new agent squad |
| `/squad add <name> <role> <model> [--provider <a>] [--skill <s>]` | Add a member with role, model, optional provider and skill |
| `/squad remove <name> <role>` | Remove a member |
| `/squad show <name>` | Show squad configuration |
| `/squad run <name> <task>` | Execute task with all squad members in parallel |
| `/orchestrate <goal>` | Hierarchical decomposition → parallel wave execution → synthesis |
| `/copy` | Copy transcript to clipboard (fallback prints text) |
| `/save <file>` | Save conversation JSON |
| `/load <file>` | Resume saved conversation |
| `/status` | Full server table |

### Advanced Agent Control
| Command | Description |
|---|---|
| `/rewind` or `/back` | Rewind conversation by 1 turn (drop last user prompt and AI response) |
| `/retry` | Rewind conversation and immediately resend the last user prompt |
| `/editai` | Open the last AI response in an interactive editor to manually steer the agent |
| `/commit` | Generate a conventional Git commit message for staged files using the AI model |
| `/goal <description>` | Enter goal mode — agent autonomously works toward a high-level objective |
| `/learn` | Trigger autonomous recursive reflection to extract workflows and rules from history |

### Agent Mode
| Command | Description |
|---|---|
| `/agent` | Toggle agent mode ON/OFF (ON by default on startup) |
| `/agent status` | Show current state |

Agent mode is active by default. You can disable it on startup using the `--no-agent` CLI flag.
When agent mode is ON, the model autonomously calls tools:

**Execution:**
- `run_python` — execute Python code (with background support)
- `run_bash` — execute bash script (with background support)
- `run_shell` — run a shell command (with background support)

**Files:**
- `read_file` — read file (supports `<start_line>`, `<end_line>`, `<tail>` slicing)
- `write_file` — write/create file (50MB limit, **Python syntax validation** via `ast`, diff skipped for files >100KB)
- `patch_file` — find+replace in file (**Python syntax validation** via `ast`)
- `list_dir` — list directory
- `tree` — directory tree
- `glob` — fast file discovery using ripgrep
- `grep` — fast regex search using ripgrep

**Web:**
- `fetch_url` — fetch a URL
- `web_search` — DuckDuckGo search
- `web_extract` — fetch URL and extract via CSS selector

**Vision / Images:**
- `read_image` — read an image file, returns base64 data URL for vision models (PNG, JPG, GIF, WebP, BMP; max 20MB)

**Sub-agents & Background:**
- `run_subagent` — spawn a sub-agent to delegate a sub-task (supports `<background>true</background>`, optional `<model>`, optional `<system_prompt>`)
- `bg_status` — check status and logs of background tasks/sub-agents (optional `<id>`)

**Notebooks:**
- `notebook_edit` — replace, insert, or delete cells in Jupyter notebooks

**User interaction:**
- `ask_user` — ask the user a question (optional `<choices>` for radiolist dialog)
- `enter_plan_mode` / `exit_plan_mode` — structured planning before execution

**Task tracking & Memory:**
- `task_create` / `task_update` / `task_list` — manage structured task lists
- `core_memory_manage` — Deep CRUD persona/project management (append/replace/rewrite)
- `memory_store` / `memory_search` — Infinite vector RAG memory

### Vision
| Command | Description |
|---|---|
| `/vision <image_path> <prompt>` | Send an image to a vision model with a question |
| `/image <image_path> <prompt>` | Alias for `/vision` |

### Direct Tools (no model)
| Command | Description |
|---|---|
| `/run python <code>` | Execute Python directly |
| `/run bash <code>` | Execute bash directly |
| `/read <path>` | Read and display file |
| `/write <path>` | Write file (interactive) |
| `/fetch <url>` | Fetch URL |
| `/search <query>` | Web search |
| `/vision <path> <prompt>` | Send image + prompt to vision model |

### Broadcast
| Command | Description |
|---|---|
| `/broadcast <message>` | Send to ALL online servers simultaneously |
| `/bc <message>` | Same |

### Side Queries (BTW)
| Command | Description |
|---|---|
| `/btw <question>` | Ask the active model a side question without modifying session history |

### Config
| Command | Description |
|---|---|
| `/config` | Show all config values |
| `/config set <key> <value>` | Set a config value |

Config keys: `default_server`, `default_model`, `agent_enabled`, `max_agent_turns`, `history_limit`, `no_probe_on_start`, `auto_probe_interval`

## Model Router

The router picks the best server automatically:
1. Preferred alias + model (if specified)
2. Fastest online server that has the requested model
3. Any online server (uses its first model)

Failover is automatic — if the active server dies mid-chat, the agent reprobes and jumps to the next available server.

## Provider Support

| Provider | Type | Auth | Notes |
|---|---|---|---|
| **Ollama** | Native | API key (Bearer), TLS | Local or remote, streaming, model pull/delete |
| **OpenRouter** | OpenAI-compatible | API key | 200+ models, streaming |
| **OpenAI-compatible** | Generic | API key (Bearer) | DeepSeek, Qwen, Z.ai, Groq, any `/v1/chat/completions` endpoint |

### Built-in Provider Presets
Use `/add-provider <name> <key>` or `python -m dct add-provider <name> <key>`:
```
deepseek     qwen         groq         together     openai
mistral      xai          perplexity   fireworks    hyperbolic
cerebras     sambanova    zai
```

### Built-in Agent Skills
Use `/skill <name>` to load a specialized persona:
```
web-design   react        backend      python       pentest
devops       data         bug-hunt     cli-tool     refactor
```

Custom skills can be created with `/skill add <name> <desc>` (persisted to config).

## Multi-Agent Systems

### Squads — Parallel Agent Teams
Define a team of agents with different roles, models, and providers. Run them in parallel on any task:
```bash
/squad create webteam
/squad add webteam frontend qwen-coder --provider qwen --skill web-design
/squad add webteam backend deepseek-chat --provider deepseek --skill backend
/squad add webteam security deepseek-chat --skill bug-hunt
/squad run webteam "Build a task management dashboard"
```

Each squad member runs as an independent agent with its own model, provider, role, and skill preset. Results from all members are collected and displayed. Squads persist in config.

### Orchestrator — Hierarchical Task Decomposition
For large complex goals, the orchestrator decomposes the work into a DAG of subtasks and executes them in parallel waves:
```bash
/orchestrate "Build a full-stack e-commerce app with auth, cart, and checkout"
```

**How it works:**
1. **Plan** — The planner agent decomposes the goal into structured tasks with dependencies
2. **DAG** — Tasks form a dependency graph (task 3 depends on task 1 → runs after it)
3. **Waves** — Each wave runs all ready tasks in parallel using independent CodeAgents
4. **Context flow** — Dependent tasks receive output from their predecessors
5. **Synthesize** — All results are collected into a final summary

Example execution:
```
Wave 1 (parallel): [1. Scaffold] [2. DB schema]
Wave 2 (parallel): [3. Auth API ← 2] [4. Frontend ← 1]
Wave 3 (serial):   [5. Integration ← 3,4]
```

## Autonomous Memory & Recursive Learning

DCT Agent features a state-of-the-art hybrid memory system heavily inspired by **MemGPT (Letta)**, **OpenHands**, and **NousResearch Hermes**:

1. **Global Persona (MemGPT Style):**
   - Maintained in `~/.config/dct/soul.md` (Core Persona), `user.md` (Human Profile), and `memory.md` (Global Context).
   - The agent uses `<tool>core_memory_manage</tool>` to autonomously `append`, `replace`, and even `rewrite` these blocks to compress data when it grows too large.

2. **Project-Level Context (OpenHands Style):**
   - Automatically loads and maintains `.dct/project.md` in the current working directory.
   - The agent actively learns repository-specific workflows, build commands, and architectural patterns and caches them here to share across sessions.

3. **Infinite RAG Archival Memory:**
   - Powered by an embedded pure-Python vector database (`~/.config/dct/memory.json`).
   - The agent uses `<tool>memory_store</tool>` and `<tool>memory_search</tool>` for deep codebase and historical lookups.

4. **Recursive Self-Improvement (`/learn`):**
   - When you type `/learn` (or when `/goal` mode finishes), the agent reads its entire conversation history and reflects on what tasks succeeded and which strategies failed.
   - It extracts the reusable lessons and uses its memory tools to permanently rewrite `.dct/project.md` or `user.md` so that it **never repeats the same mistakes twice**.

## Reliability & Resilience

Built for long-running autonomous tasks, DCT Agent implements professional-grade resilience:
- **Context Pruning & Summarization**: A sliding window monitors the context token size. When it gets too large (~30k tokens), the agent drops older tool executions and autonomously makes a secondary API call to **summarize** the dropped interactions. This summary is injected as a persistent memory, preventing token exhaustion while maintaining high-level task awareness.
- **Network Retry Backoff**: All requests use a robust HTTP session that automatically intercepts transient API errors (`429 Too Many Requests`, `502 Bad Gateway`, `503 Service Unavailable`) and retries with exponential backoff.
- **Auto-Probing**: Background thread periodically refreshes server health status (configurable interval, default 60s). Servers that go offline are automatically detected without manual `/probe` calls.
- **Background Cleanup**: Completed background tasks and sub-agents are automatically purged after 5 minutes to prevent memory leaks. Background logs are capped at 10,000 characters.
- **Large File Safety**: File writes are capped at 50MB. Diff generation is skipped for files over 100KB to avoid memory issues.

## Server Registry

Servers persist in `~/.config/dct/servers.json`. Config persists in `~/.config/dct/config.json`. Add once, use everywhere.

## Requirements

```
rich>=13.0
requests>=2.31
prompt_toolkit>=3.0.36
beautifulsoup4>=4.12.0
Python>=3.11
```
