"""
dct.cli.help
All help text, command reference, and usage examples.
"""

from dct.core.theme import C, con

HELP_SECTIONS = {
    "servers": f"""
[{C["accent"]}]── Server Management ────────────────────────────────────────────[/{C["accent"]}]

  [{C["fg"]}]/servers[/{C["fg"]}]
      [{C["dim"]}]List all registered servers with status, latency, model count.[/{C["dim"]}]

  [{C["fg"]}]/add <host> <port> [alias] [note][/{C["fg"]}]
      [{C["dim"]}]Register + probe a new server. alias is a short name you use in commands.
      Examples:
        /add 192.168.1.10 11434 home
        /add 10.0.0.5 11434 vps1 "DigitalOcean SFO"
        /add myserver.local 11434[/{C["dim"]}]

  [{C["fg"]}]/remove <alias|#>[/{C["fg"]}]
      [{C["dim"]}]Unregister a server. Use alias or row number from /servers.[/{C["dim"]}]

  [{C["fg"]}]/probe[/{C["fg"]}]
      [{C["dim"]}]Probe ALL servers in parallel. Updates status, latency, model lists.[/{C["dim"]}]

  [{C["fg"]}]/probe <alias|#>[/{C["fg"]}]
      [{C["dim"]}]Detailed probe of one server — shows every endpoint with latency.[/{C["dim"]}]

  [{C["fg"]}]/use <alias|#>[/{C["fg"]}]
      [{C["dim"]}]Switch active server. Auto-swaps model if current one isn't available.
      Examples:
        /use vps1
        /use 2[/{C["dim"]}]
""",
    "models": f"""
[{C["accent"]}]── Model Management ─────────────────────────────────────────────[/{C["accent"]}]

  [{C["fg"]}]/models[/{C["fg"]}]
      [{C["dim"]}]List models on the active server.[/{C["dim"]}]

  [{C["fg"]}]/models <alias|#>[/{C["fg"]}]
      [{C["dim"]}]List models on a specific server.[/{C["dim"]}]

  [{C["fg"]}]/allmodels[/{C["fg"]}]
      [{C["dim"]}]All models across every registered server in one table.[/{C["dim"]}]

  [{C["fg"]}]/model <name>[/{C["fg"]}]
      [{C["dim"]}]Switch model on the active server.
      Example: /model mistral:7b[/{C["dim"]}]

  [{C["fg"]}]/pull <model>[/{C["fg"]}]
      [{C["dim"]}]Pull a model on the active server with live progress bar.[/{C["dim"]}]

  [{C["fg"]}]/pull <alias|#> <model>[/{C["fg"]}]
      [{C["dim"]}]Pull on a specific server.
      Example: /pull vps1 codellama[/{C["dim"]}]

  [{C["fg"]}]/delete <model>[/{C["fg"]}]
      [{C["dim"]}]Delete a model from the active server.[/{C["dim"]}]

  [{C["fg"]}]/show <model>[/{C["fg"]}]
      [{C["dim"]}]Show model info: family, params, quant, system prompt, modelfile.[/{C["dim"]}]
""",
    "chat": f"""
[{C["accent"]}]── Chat & Session ───────────────────────────────────────────────[/{C["accent"]}]

  [{C["fg"]}]/status[/{C["fg"]}]
      [{C["dim"]}]Show active server, model, session stats.[/{C["dim"]}]

  [{C["fg"]}]/clear[/{C["fg"]}]
      [{C["dim"]}]Clear conversation history. Keeps system prompt if set.[/{C["dim"]}]

  [{C["fg"]}]/learn[/{C["fg"]}]
      [{C["dim"]}]Trigger autonomous reflection. The agent will review history,
      identify mistakes/successes, and save workflows to memory
      for recursive self-improvement.[/{C["dim"]}]

  [{C["fg"]}]/history[/{C["fg"]}]
      [{C["dim"]}]Show turn count and token estimate.[/{C["dim"]}]

  [{C["fg"]}]/system <prompt>[/{C["fg"]}]
      [{C["dim"]}]Set a system prompt. Clears history.
      Example: /system You are a CTF solver specializing in binary exploitation.[/{C["dim"]}]

  [{C["fg"]}]/prompts[/{C["fg"]}]
      [{C["dim"]}]List built-in system prompt presets.[/{C["dim"]}]

  [{C["fg"]}]/prompt <name>[/{C["fg"]}]
      [{C["dim"]}]Apply a built-in prompt preset as system prompt.[/{C["dim"]}]

  [{C["fg"]}]/copy[/{C["fg"]}]
      [{C["dim"]}]Copy the current transcript to clipboard (or print fallback).[/{C["dim"]}]

  [{C["fg"]}]/save <file>[/{C["fg"]}]
      [{C["dim"]}]Save conversation to JSON.
      Example: /save session_2024.json[/{C["dim"]}]

  [{C["fg"]}]/load <file>[/{C["fg"]}]
      [{C["dim"]}]Load a previously saved JSON conversation.[/{C["dim"]}]

  [{C["fg"]}]/new[/{C["fg"]}]
      [{C["dim"]}]Start a new, blank chat session (auto-saves current).[/{C["dim"]}]

  [{C["fg"]}]/fork [n][/{C["fg"]}]
      [{C["dim"]}]Branch off the current session. Optionally rewind 'n' turns to clean up history.[/{C["dim"]}]

  [{C["fg"]}]/compact[/{C["fg"]}]
      [{C["dim"]}]Strip all intermediate raw tool outputs from the current session's history to save context space.[/{C["dim"]}]

  [{C["fg"]}]/chats[/{C["fg"]}]
      [{C["dim"]}]List all saved chat sessions.[/{C["dim"]}]

  [{C["fg"]}]/chat switch <id>[/{C["fg"]}]
      [{C["dim"]}]Switch to a saved chat session by ID from /chats.[/{C["dim"]}]

  [{C["fg"]}]/btw <question>[/{C["fg"]}]
      [{C["dim"]}]Ask the AI a side question utilizing the current context,
      without appending either the question or answer to the session history.[/{C["dim"]}]
""",
    "broadcast": f"""
[{C["accent"]}]── Broadcast ────────────────────────────────────────────────────[/{C["accent"]}]

  [{C["fg"]}]/broadcast <message>[/{C["fg"]}]   [{C["warn"]}](alias: /bc)[/{C["warn"]}]
      [{C["dim"]}]Send the same message to ALL online servers simultaneously.
      Each server replies independently with its best available model.
      Responses are labelled by server alias.
      Example: /bc What is your current context window size?[/{C["dim"]}]
""",
    "agent": f"""
[{C["accent"]}]── Agent Mode ─────────────────────────────────────────[/{C["accent"]}]

  [{C["fg"]}]/agent[/{C["fg"]}]
      [{C["dim"]}]Toggle agent mode ON/OFF (ON by default on startup).
      When ON: the model can use tools autonomously — running code,
      reading/writing files, fetching URLs, searching the web, and spawning sub-agents.
      The model loops until it emits <tool>DONE</tool>.[/{C["dim"]}]

  [{C["fg"]}]/agent status[/{C["fg"]}]
      [{C["dim"]}]Show whether agent mode is currently on or off.[/{C["dim"]}]

  [{C["fg"]}]/goal <description>[/{C["fg"]}]
      [{C["dim"]}]Run the agent in Goal Mode. The agent will execute autonomously
      and continue to run across multiple iterations until it completes the goal
      and emits <tool>DONE</tool> or is manually cancelled with Ctrl+C.[/{C["dim"]}]

  [{C["fg"]}]Agent tool calls (model emits these automatically):[/{C["fg"]}]
      [{C["dim"]}]run_python          — execute Python code
      run_bash            — execute bash script
      run_shell           — run shell command
      read_file           — read file (supports start_line, end_line, tail)
      write_file          — write/create a file
      patch_file          — find+replace in a file
      multi_patch_file    — multiple non-contiguous find+replaces in one file
      list_dir            — list directory
      tree                — directory tree
      grep                — ripgrep regex search (content or file list mode)
      glob                — fast file discovery by pattern
      fetch_url           — fetch a URL (HTML → markdown)
      web_search          — DuckDuckGo search
      web_extract         — fetch URL + optional CSS selector extraction
      run_subagent        — spawn a sub-agent to delegate a sub-task
      bg_status           — check status/logs of background tasks
      bg_kill             — terminate a running background task
      bg_send_input       — send stdin to a running background task
      task_create         — create a tracked task with subject + description
      task_update         — update task status (pending|in_progress|completed)
      task_list           — list all tracked tasks
      notebook_edit       — edit Jupyter notebook cells
      ask_user            — ask the user a question (optional radio dialog)
      read_image          — read image for vision models
      enter_plan_mode     — switch to read-only planning mode
      exit_plan_mode      — return to execution mode
      get_cwd             — get current working directory[/{C["dim"]}]

  [{C["fg"]}]Background tasks:[/{C["fg"]}]
      [{C["dim"]}]Add <background>true</background> to run_python/run_bash/run_shell
      or run_subagent to run asynchronously. Use bg_status to poll, bg_kill
      to terminate, and bg_send_input to write to stdin.[/{C["dim"]}]
""",
    "tools": f"""
[{C["accent"]}]── Direct Tool Commands ─────────────────────────────────────────[/{C["accent"]}]

  [{C["fg"]}]/run python <code>[/{C["fg"]}]
      [{C["dim"]}]Execute Python directly without going through the model.
      Example: /run python print("hello")[/{C["dim"]}]

  [{C["fg"]}]/run bash <code>[/{C["fg"]}]
      [{C["dim"]}]Execute bash directly.
      Example: /run bash ls -la /tmp[/{C["dim"]}]

  [{C["fg"]}]/read <path>[/{C["fg"]}]
      [{C["dim"]}]Read and display a file.
      Example: /read /etc/os-release[/{C["dim"]}]

  [{C["fg"]}]/write <path>[/{C["fg"]}]
      [{C["dim"]}]Write content to a file (interactive — paste content, end with ///)[/{C["dim"]}]

  [{C["fg"]}]/fetch <url>[/{C["fg"]}]
      [{C["dim"]}]Fetch a URL and display text content.
      Example: /fetch https://example.com[/{C["dim"]}]

  [{C["fg"]}]/search <query>[/{C["fg"]}]
      [{C["dim"]}]DuckDuckGo search.
      Example: /search CVE-2024-55556 Laravel[/{C["dim"]}]
""",
    "misc": f"""
[{C["accent"]}]── Navigation ───────────────────────────────────────────[/{C["accent"]}]

  [{C["fg"]}]/help[/{C["fg"]}]               [{C["dim"]}]this overview[/{C["dim"]}]
  [{C["fg"]}]/help servers[/{C["fg"]}]       [{C["dim"]}]server management commands[/{C["dim"]}]
  [{C["fg"]}]/help models[/{C["fg"]}]        [{C["dim"]}]model management commands[/{C["dim"]}]
  [{C["fg"]}]/help chat[/{C["fg"]}]          [{C["dim"]}]chat and session commands[/{C["dim"]}]
  [{C["fg"]}]/help agent[/{C["fg"]}]         [{C["dim"]}]agent mode and tools[/{C["dim"]}]
  [{C["fg"]}]/help tools[/{C["fg"]}]         [{C["dim"]}]direct tool commands[/{C["dim"]}]
  [{C["fg"]}]/help broadcast[/{C["fg"]}]     [{C["dim"]}]broadcast to all servers[/{C["fg"]}]

[{C["accent"]}]── Session Rewind ──────────────────────────────────────[/{C["accent"]}]

  [{C["fg"]}]/rewind [n][/{C["fg"]}]
      [{C["dim"]}]Interactively pick a past user message to rewind and resume from.
      Pass an index n to rewind to that message directly.
      Aliases: /rewindto, /back, /undo[/{C["dim"]}]

  [{C["fg"]}]/retry[/{C["fg"]}]
      [{C["dim"]}]Re-send the last user message (removes last response and replays).[/{C["dim"]}]

  [{C["fg"]}]/editai[/{C["fg"]}]
      [{C["dim"]}]Open the last AI response in an inline editor to fix it in-session.[/{C["dim"]}]

  [{C["fg"]}]/commit[/{C["fg"]}]
      [{C["dim"]}]Auto-generate a commit message for staged changes using the model
      and optionally commit right from DCT.[/{C["dim"]}]

  [{C["fg"]}]/tasks[/{C["fg"]}]
      [{C["dim"]}]List all agent-created tracked tasks and their status.[/{C["dim"]}]

  [{C["fg"]}]/trace[/{C["fg"]}]
      [{C["dim"]}]Toggle session JSONL tracing on/off.
      Logs are written to ~/.config/dct/transcripts/[/{C["dim"]}]

  [{C["fg"]}]/exit  Ctrl+C[/{C["fg"]}]      [{C["dim"]}]quit[/{C["dim"]}]
""",
}

HELP_OVERVIEW = f"""
[{C["accent"]}]DCT Agent — Doraemon Cyber Team[/{C["accent"]}]  [{C["dim"]}]Multi-server Ollama agent v3[/{C["dim"]}]

[{C["fg"]}]How it works:[/{C["fg"]}]
  [{C["dim"]}]· Register any number of Ollama servers (local or remote)[/{C["dim"]}]
  [{C["dim"]}]· The model router picks the best available server automatically[/{C["dim"]}]
  [{C["dim"]}]· Chat normally — or enable agent mode for autonomous tool use[/{C["dim"]}]
  [{C["dim"]}]· Broadcast one message to all servers at once[/{C["dim"]}]

[{C["fg"]}]Quick start:[/{C["fg"]}]
  [{C["yellow"]}]/add 192.168.1.10 11434 home[/{C["yellow"]}]     [{C["dim"]}]register your first server[/{C["dim"]}]
  [{C["yellow"]}]/probe[/{C["yellow"]}]                           [{C["dim"]}]check all servers[/{C["dim"]}]
  [{C["yellow"]}]/models[/{C["yellow"]}]                          [{C["dim"]}]see available models[/{C["dim"]}]
  [{C["yellow"]}]/prompts[/{C["yellow"]}]                         [{C["dim"]}]choose a built-in system prompt[/{C["dim"]}]
  [{C["yellow"]}]just type your message[/{C["yellow"]}]           [{C["dim"]}]start chatting[/{C["dim"]}]

[{C["fg"]}]Help sections:[/{C["fg"]}]
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
