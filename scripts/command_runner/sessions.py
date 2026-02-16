"""Manage tmux sessions running Claude Code instances."""

from __future__ import annotations

import shutil
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path
from textwrap import dedent

SESSIONS_DIR = Path("/tmp/claude-sessions")
TMUX = "/usr/bin/tmux"
CLAUDE = "/usr/local/bin/claude"


def spawn_session(
    *,
    bot_token: str,
    thread_id: int,
    prompt: str | None,
    working_dir: str,
    plugin_dir: str,
) -> str:
    """Spawn a detached tmux session running Claude Code.

    Returns the session name.
    """
    # 1. Generate session name with collision detection
    base_name = f"claude-{datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S')}"
    session_name = base_name
    for suffix in range(2, 11):
        if not _tmux_session_exists(session_name):
            break
        session_name = f"{base_name}-{suffix}"
    else:
        if _tmux_session_exists(session_name):
            raise RuntimeError(f"Could not find available session name (tried {base_name} through {session_name})")

    # 2. Create session directory
    session_dir = SESSIONS_DIR / session_name
    session_dir.mkdir(parents=True, exist_ok=True)

    # 3. Write per-session config
    config_path = session_dir / "config.md"
    config_path.write_text(
        dedent(f"""\
        ---
        bot_token: {bot_token}
        channel_id: {thread_id}
        default_timeout: 86400
        ---
        """)
    )

    # 4. Write prompt file
    prompt_path = session_dir / "prompt.txt"
    config_abs = str(config_path.resolve())

    prompt_text = dedent(f"""\
        You are now in **Discord-only mode**. All communication with the user happens through Discord — not the terminal.

        ## Rules

        1. **Every message goes through Discord.** Use `discord-notify` for all communication: asking questions, reporting progress, sharing results, requesting clarification, or checking in. **Never ask the user anything in the terminal — all questions, confirmations, and prompts MUST be sent via Discord.** Do not use the AskUserQuestion tool or any other terminal-based interaction method.

        2. **Use `--wait` only when you need user input** (asking a question, requesting confirmation, waiting for instructions). Do NOT use `--wait` for one-way status updates or progress reports — just send the message and continue working.

        3. **When using `--wait`, set `--timeout 86400`** (4 hours) so the user has plenty of time to respond. Always set Bash tool timeout to `600000` (maximum) for any discord-notify call that uses `--wait`.

        4. **Minimize terminal output.** Only print brief mechanical status lines like `Sending to Discord...` or `Received reply from user.` Do not duplicate message content or questions in the terminal.

        5. **Parse replies and act on them.** When the user replies on Discord, treat their response exactly as if they typed it in the terminal. Continue working based on their instructions.

        6. **Exit conditions.** If the user replies with "exit", "stop", or "done" (case-insensitive), end the session. Confirm on Discord that the session has ended, then exit.

        ## Command Templates

        For ALL discord-notify calls, you MUST use this exact config path.

        **When you need user input (questions, confirmations):**
        ```bash
        uv run --project ${{CLAUDE_PLUGIN_ROOT}} discord-notify \\
          --message "<your message here>" \\
          --wait \\
          --timeout 86400 \\
          --config "{config_abs}"
        ```

        **When sending a one-way update (progress, status, results):**
        ```bash
        uv run --project ${{CLAUDE_PLUGIN_ROOT}} discord-notify \\
          --message "<your message here>" \\
          --config "{config_abs}"
        ```

        **CRITICAL:** Always use `--config "{config_abs}"` — do NOT use a relative config path. This ensures your messages go to the correct Discord thread.

        ## Getting Started

        Send an initial greeting to Discord now:

        ```bash
        uv run --project ${{CLAUDE_PLUGIN_ROOT}} discord-notify \\
          --message "Claude session `{session_name}` is active. I'll send all messages here. What would you like me to work on?" \\
          --wait \\
          --timeout 86400 \\
          --config "{config_abs}"
        ```

        Then read the user's reply and proceed accordingly.
    """)

    if prompt:
        prompt_text += f"\n## Initial Task\n\nThe user has asked you to work on the following:\n\n{prompt}\n"

    prompt_path.write_text(prompt_text)

    # 5. Spawn tmux session
    #    - Unset CLAUDECODE to avoid "nested session" detection
    #    - Set CLAUDE_PLUGIN_ROOT so discord-notify commands work inside the session
    subprocess.run(
        [
            TMUX, "new-session", "-d",
            "-s", session_name,
            "-c", working_dir,
            f"env -u CLAUDECODE CLAUDE_PLUGIN_ROOT={plugin_dir}"
            f" SESSION_CONFIG={config_path.resolve()}"
            f" {CLAUDE} --dangerously-skip-permissions --plugin-dir {plugin_dir}",
        ],
        check=True,
    )

    # 6. Wait for Claude to initialize, then feed the prompt via load-buffer + paste-buffer
    #    (send-keys has a length limit; load-buffer reads from file with no limit)
    time.sleep(5)
    subprocess.run(
        [TMUX, "load-buffer", "-b", "prompt", str(prompt_path)],
        check=True,
    )
    subprocess.run(
        [TMUX, "paste-buffer", "-b", "prompt", "-t", session_name],
        check=True,
    )
    # paste-buffer inserts text but doesn't submit — send Enter key to submit the prompt
    time.sleep(1)
    subprocess.run(
        [TMUX, "send-keys", "-t", session_name, "", "Enter"],
        check=True,
    )

    return session_name


def list_sessions() -> list[dict[str, str]]:
    """List active claude-* tmux sessions."""
    result = subprocess.run(
        [TMUX, "list-sessions", "-F", "#{session_name} #{session_created}"],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        return []

    sessions = []
    for line in result.stdout.strip().splitlines():
        parts = line.split(" ", 1)
        if len(parts) == 2 and parts[0].startswith("claude-"):
            name, created_ts = parts
            try:
                created = datetime.fromtimestamp(int(created_ts), tz=timezone.utc).strftime(
                    "%Y-%m-%d %H:%M:%S UTC"
                )
            except (ValueError, OSError):
                created = created_ts
            sessions.append({"name": name, "created": created})
    return sessions


def get_session_thread_id(name: str) -> int | None:
    """Read the Discord thread/channel ID from a session's config file."""
    config_path = SESSIONS_DIR / name / "config.md"
    if not config_path.is_file():
        return None
    try:
        for line in config_path.read_text().splitlines():
            line = line.strip()
            if line.startswith("channel_id:"):
                return int(line.split(":", 1)[1].strip())
    except (ValueError, OSError):
        pass
    return None


def kill_session(name: str) -> bool:
    """Kill a tmux session and clean up its temp directory."""
    result = subprocess.run(
        [TMUX, "kill-session", "-t", name],
        capture_output=True,
    )
    # Clean up session directory
    session_dir = SESSIONS_DIR / name
    if session_dir.is_dir():
        shutil.rmtree(session_dir, ignore_errors=True)
    return result.returncode == 0


def _tmux_session_exists(name: str) -> bool:
    result = subprocess.run(
        [TMUX, "has-session", "-t", name],
        capture_output=True,
    )
    return result.returncode == 0
