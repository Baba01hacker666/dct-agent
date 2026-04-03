# DCT Agent — Doraemon Cyber Team
**Multi-server Ollama agent · v3.0**

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

### Agent Mode
| Command | Description |
|---|---|
| `/agent` | Toggle agent mode ON/OFF |
| `/agent status` | Show current state |

When agent mode is ON, the model autonomously calls tools:
- `run_python` — execute Python
- `run_bash` — execute bash
- `run_shell` — shell command
- `read_file` — read file
- `write_file` — write/create file
- `patch_file` — find+replace in file
- `list_dir` — list directory
- `tree` — directory tree
- `fetch_url` — fetch a URL
- `web_search` — DuckDuckGo search

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

## Model Router

The router picks the best server automatically:
1. Preferred alias + model (if specified)
2. Fastest online server that has the requested model
3. Any online server (uses its first model)

Failover is automatic — if the active server dies mid-chat, the agent reprobes and jumps to the next available server.

## Server Registry

Servers persist in `~/.config/dct/servers.json`. Add once, use everywhere.

## Requirements

```
rich>=13.0
requests>=2.31
Python>=3.11
```
