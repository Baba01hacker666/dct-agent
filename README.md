# DCT Agent — Doraemon Cyber Team
**Multi-server Ollama agent · v3.1**

## Install

```bash
pip install -e .
# module entrypoint (no console script required):
python -m dct
```

## Quick Start

```bash
# Register servers
python -m dct add localhost 11434 local
python -m dct add 192.168.1.10 11434 home "home lab box"
python -m dct add 10.0.0.5 11434 vps1 "DigitalOcean"

# Probe all
python -m dct probe

# List all models across servers
python -m dct models

# Launch interactive shell
python -m dct
```

## Shell Commands

### Server Management
| Command | Description |
|---|---|
| `/servers` | List all servers with status, latency, model count |
| `/add <host> <port> [alias] [note]` | Register + probe a new server |
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

### Agent Mode
| Command | Description |
|---|---|
| `/agent` | Toggle agent mode ON/OFF (ON by default on startup) |
| `/agent status` | Show current state |

Agent mode is active by default. You can disable it on startup using the `--no-agent` CLI flag.
When agent mode is ON, the model autonomously calls tools:
- `run_python` — execute Python
- `run_bash` — execute bash
- `run_shell` — shell command
- `read_file` — read file (supports `<start_line>`, `<end_line>`, and `<tail>` slicing to save context)
- `write_file` — write/create file (includes **Python syntax validation** via `ast`)
- `patch_file` — find+replace in file (includes **Python syntax validation** via `ast`)
- `list_dir` — list directory
- `tree` — directory tree
- `fetch_url` — fetch a URL
- `web_search` — DuckDuckGo search
- `run_subagent` — spawn a sub-agent to delegate a sub-task (accepts `<instruction>`, optional `<model>`, optional `<system_prompt>`)

### Direct Tools (no model)
| Command | Description |
|---|---|
| `/run python <code>` | Execute Python directly |
| `/run bash <code>` | Execute bash directly |
| `/read <path>` | Read and display file |
| `/write <path>` | Write file (interactive) |
| `/fetch <url>` | Fetch URL |
| `/search <query>` | Web search |

### Broadcast
| Command | Description |
|---|---|
| `/broadcast <message>` | Send to ALL online servers simultaneously |
| `/bc <message>` | Same |

### Side Queries (BTW)
| Command | Description |
|---|---|
| `/btw <question>` | Ask the active model a side question using current context without modifying the session history |

## Model Router

The router picks the best server automatically:
1. Preferred alias + model (if specified)
2. Fastest online server that has the requested model
3. Any online server (uses its first model)

Failover is automatic — if the active server dies mid-chat, the agent reprobes and jumps to the next available server.

## Reliability & Resilience

Built for long-running autonomous tasks, DCT Agent implements professional-grade resilience:
- **Context Pruning & Summarization**: A sliding window monitors the context token size. When it gets too large (~30k tokens), the agent drops older tool executions and autonomously makes a secondary API call to **summarize** the dropped interactions. This summary is injected as a persistent memory, preventing token exhaustion while maintaining high-level task awareness.
- **Network Retry Backoff**: All requests use a robust HTTP session that automatically intercepts transient API errors (`429 Too Many Requests`, `502 Bad Gateway`, `503 Service Unavailable`) and retries with an exponential backoff.

## Server Registry

Servers persist in `~/.config/dct/servers.json`. Add once, use everywhere.

## Requirements

```
rich>=13.0
requests>=2.31
Python>=3.11
```
