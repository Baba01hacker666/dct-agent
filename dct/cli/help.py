"""
dct.cli.help
All help text, command reference, and usage examples.
"""

from dct.core.theme import C, con

HELP_SECTIONS = {
    "servers": f"""
[{C['accent']}]── Server Management ────────────────────────────────────────────[/{C['accent']}]

  [{C['fg']}]/servers[/{C['fg']}]
      [{C['dim']}]List all registered servers with status, latency, model count.[/{C['dim']}]

  [{C['fg']}]/add <host> <port> [alias] [note][/{C['fg']}]
      [{C['dim']}]Register + probe a new server. alias is a short name you use in commands.
      Examples:
        /add 192.168.1.10 11434 home
        /add 10.0.0.5 11434 vps1 "DigitalOcean SFO"
        /add myserver.local 11434[/{C['dim']}]

  [{C['fg']}]/remove <alias|#>[/{C['fg']}]
      [{C['dim']}]Unregister a server. Use alias or row number from /servers.[/{C['dim']}]

  [{C['fg']}]/probe[/{C['fg']}]
      [{C['dim']}]Probe ALL servers in parallel. Updates status, latency, model lists.[/{C['dim']}]

  [{C['fg']}]/probe <alias|#>[/{C['fg']}]
      [{C['dim']}]Detailed probe of one server — shows every endpoint with latency.[/{C['dim']}]

  [{C['fg']}]/use <alias|#>[/{C['fg']}]
      [{C['dim']}]Switch active server. Auto-swaps model if current one isn't available.
      Examples:
        /use vps1
        /use 2[/{C['dim']}]
""",
    "models": f"""
[{C['accent']}]── Model Management ─────────────────────────────────────────────[/{C['accent']}]

  [{C['fg']}]/models[/{C['fg']}]
      [{C['dim']}]List models on the active server.[/{C['dim']}]

  [{C['fg']}]/models <alias|#>[/{C['fg']}]
      [{C['dim']}]List models on a specific server.[/{C['dim']}]

  [{C['fg']}]/allmodels[/{C['fg']}]
      [{C['dim']}]All models across every registered server in one table.[/{C['dim']}]

  [{C['fg']}]/model <name>[/{C['fg']}]
      [{C['dim']}]Switch model on the active server.
      Example: /model mistral:7b[/{C['dim']}]

  [{C['fg']}]/pull <model>[/{C['fg']}]
      [{C['dim']}]Pull a model on the active server with live progress bar.[/{C['dim']}]

  [{C['fg']}]/pull <alias|#> <model>[/{C['fg']}]
      [{C['dim']}]Pull on a specific server.
      Example: /pull vps1 codellama[/{C['dim']}]

  [{C['fg']}]/delete <model>[/{C['fg']}]
      [{C['dim']}]Delete a model from the active server.[/{C['dim']}]

  [{C['fg']}]/show <model>[/{C['fg']}]
      [{C['dim']}]Show model info: family, params, quant, system prompt, modelfile.[/{C['dim']}]
""",
    "chat": f"""
[{C['accent']}]── Chat & Session ───────────────────────────────────────────────[/{C['accent']}]

  [{C['fg']}]/status[/{C['fg']}]
      [{C['dim']}]Show active server, model, session stats.[/{C['dim']}]

  [{C['fg']}]/clear[/{C['fg']}]
      [{C['dim']}]Clear conversation history. Keeps system prompt if set.[/{C['dim']}]

  [{C['fg']}]/history[/{C['fg']}]
      [{C['dim']}]Show turn count and token estimate.[/{C['dim']}]

  [{C['fg']}]/system <prompt>[/{C['fg']}]
      [{C['dim']}]Set a system prompt. Clears history.
      Example: /system You are a CTF solver specializing in binary exploitation.[/{C['dim']}]

  [{C['fg']}]/save <file>[/{C['fg']}]
      [{C['dim']}]Save conversation to JSON.
      Example: /save session_2024.json[/{C['dim']}]

  [{C['fg']}]/load <file>[/{C['fg']}]
      [{C['dim']}]Load and resume a saved conversation.[/{C['dim']}]
""",
    "broadcast": f"""
[{C['accent']}]── Broadcast ────────────────────────────────────────────────────[/{C['accent']}]

  [{C['fg']}]/broadcast <message>[/{C['fg']}]   [{C['warn']}](alias: /bc)[/{C['warn']}]
      [{C['dim']}]Send the same message to ALL online servers simultaneously.
      Each server replies independently with its best available model.
      Responses are labelled by server alias.
      Example: /bc What is your current context window size?[/{C['dim']}]
""",
    "agent": f"""
[{C['accent']}]── Agent Mode ───────────────────────────────────────────────────[/{C['accent']}]

  [{C['fg']}]/agent[/{C['fg']}]
      [{C['dim']}]Toggle agent mode ON/OFF.
      When ON: the model can use tools autonomously — running code,
      reading/writing files, fetching URLs, searching the web.
      The model loops until it emits <tool>DONE</tool>.[/{C['dim']}]

  [{C['fg']}]/agent status[/{C['fg']}]
      [{C['dim']}]Show whether agent mode is currently on or off.[/{C['dim']}]

  [{C['fg']}]Agent tool calls (model emits these automatically):[/{C['fg']}]
      [{C['dim']}]run_python   — execute Python code
      run_bash     — execute bash script
      run_shell    — run shell command
      read_file    — read file contents
      write_file   — write/create a file
      patch_file   — find+replace in a file
      list_dir     — list directory
      tree         — directory tree
      fetch_url    — fetch a URL
      web_search   — DuckDuckGo search[/{C['dim']}]
""",
    "tools": f"""
[{C['accent']}]── Direct Tool Commands ─────────────────────────────────────────[/{C['accent']}]

  [{C['fg']}]/run python <code>[/{C['fg']}]
      [{C['dim']}]Execute Python directly without going through the model.
      Example: /run python print("hello")[/{C['dim']}]

  [{C['fg']}]/run bash <code>[/{C['fg']}]
      [{C['dim']}]Execute bash directly.
      Example: /run bash ls -la /tmp[/{C['dim']}]

  [{C['fg']}]/read <path>[/{C['fg']}]
      [{C['dim']}]Read and display a file.
      Example: /read /etc/os-release[/{C['dim']}]

  [{C['fg']}]/write <path>[/{C['fg']}]
      [{C['dim']}]Write content to a file (interactive — paste content, end with ///)[/{C['dim']}]

  [{C['fg']}]/fetch <url>[/{C['fg']}]
      [{C['dim']}]Fetch a URL and display text content.
      Example: /fetch https://example.com[/{C['dim']}]

  [{C['fg']}]/search <query>[/{C['fg']}]
      [{C['dim']}]DuckDuckGo search.
      Example: /search CVE-2024-55556 Laravel[/{C['dim']}]
""",
    "misc": f"""
[{C['accent']}]── Navigation ───────────────────────────────────────────────────[/{C['accent']}]

  [{C['fg']}]/help[/{C['fg']}]               [{C['dim']}]this overview[/{C['dim']}]
  [{C['fg']}]/help servers[/{C['fg']}]       [{C['dim']}]server management commands[/{C['dim']}]
  [{C['fg']}]/help models[/{C['fg']}]        [{C['dim']}]model management commands[/{C['dim']}]
  [{C['fg']}]/help chat[/{C['fg']}]          [{C['dim']}]chat and session commands[/{C['dim']}]
  [{C['fg']}]/help agent[/{C['fg']}]         [{C['dim']}]agent mode and tools[/{C['dim']}]
  [{C['fg']}]/help tools[/{C['fg']}]         [{C['dim']}]direct tool commands[/{C['dim']}]
  [{C['fg']}]/help broadcast[/{C['fg']}]     [{C['dim']}]broadcast to all servers[/{C['dim']}]
  [{C['fg']}]/exit  Ctrl+C[/{C['fg']}]      [{C['dim']}]quit[/{C['dim']}]
""",
}

HELP_OVERVIEW = f"""
[{C['accent']}]DCT Agent — Doraemon Cyber Team[/{C['accent']}]  [{C['dim']}]Multi-server Ollama agent v3[/{C['dim']}]

[{C['fg']}]How it works:[/{C['fg']}]
  [{C['dim']}]· Register any number of Ollama servers (local or remote)[/{C['dim']}]
  [{C['dim']}]· The model router picks the best available server automatically[/{C['dim']}]
  [{C['dim']}]· Chat normally — or enable agent mode for autonomous tool use[/{C['dim']}]
  [{C['dim']}]· Broadcast one message to all servers at once[/{C['dim']}]

[{C['fg']}]Quick start:[/{C['fg']}]
  [{C['yellow']}]/add 192.168.1.10 11434 home[/{C['yellow']}]     [{C['dim']}]register your first server[/{C['dim']}]
  [{C['yellow']}]/probe[/{C['yellow']}]                           [{C['dim']}]check all servers[/{C['dim']}]
  [{C['yellow']}]/models[/{C['yellow']}]                          [{C['dim']}]see available models[/{C['dim']}]
  [{C['yellow']}]just type your message[/{C['yellow']}]           [{C['dim']}]start chatting[/{C['dim']}]

[{C['fg']}]Help sections:[/{C['fg']}]
  /help servers   /help models   /help chat
  /help agent     /help tools    /help broadcast
"""


def show_help(topic: str = ""):
    topic = topic.strip().lower()
    if topic in HELP_SECTIONS:
        con.print(HELP_SECTIONS[topic])
    else:
        con.print(HELP_OVERVIEW)
        for key, body in HELP_SECTIONS.items():
            if key == "misc":
                con.print(body)
