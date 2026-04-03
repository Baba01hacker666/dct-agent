# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

- **Install/Setup**: `pip install -e .`
- **Run Application**: `python -m dct.cli.main` or simply `dct` (if installed globally)
- **Format Code**: `black --line-length 79 dct/`
- **Lint Code**: `flake8 dct/` (Note: `.flake8` ignores E501, E128, E126, W503, W504, F841)
- **Run Tests**: `pytest dct/` 
- **Run Single Test**: `pytest dct/path/to/test_file.py::test_function_name`

## Architecture & Structure

DCT Agent (Doraemon Cyber Team) is a multi-server Ollama agent with automatic failover, load-balancing (routing), and an autonomous "Agent Mode" capable of interacting with the local OS.

- **`dct/core/` (State & APIs)**: 
  - `registry.py`: Manages the thread-safe server list, persisted to `~/.config/dct/servers.json`. Handles model routing logic (fastest online server vs. preferred).
  - `ollama.py`: Low-level streaming HTTP clients for Ollama (`/api/chat`, `/api/tags`, `/api/pull`).
  - `probe.py`: Parallel health checking of registered Ollama endpoints.

- **`dct/cli/` (Interactive REPL)**: 
  - `shell.py`: The main interactive loop built with `prompt_toolkit`. Processes slash commands (e.g., `/servers`, `/use`, `/agent`) and handles auto-failover switching transparently during active chat streams.
  - `display.py` / `theme.py`: Uses `rich` for tables, status indicators, and formatted terminal output.

- **`dct/agent/` (Autonomous Loop)**: 
  - `codeagent.py`: Houses the agent loop. It injects dynamic environment context (OS, cwd, plan mode states) via `get_system_prompt` and parses the output XML tools.
  - `session.py`: Maintains session history, tokens estimates, and current execution `mode` (`execute` vs `plan`).

- **`dct/tools/` (Agent Execution Layer)**: 
  - `executor.py`: Uses `subprocess` to run Python and Bash locally. Includes auto-install handlers via pip when intercepting `ModuleNotFoundError`.
  - `files.py`: File system operations (`read_file`, `write_file`, `patch_file`, `tree`) including a robust `ripgrep` Python wrapper.
  - `web.py`: Basic HTTP fetching and DuckDuckGo search integration.