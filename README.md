# Discord Command Runner

A persistent Discord bot that spawns interactive [Claude Code](https://docs.anthropic.com/en/docs/claude-code) sessions via slash commands. Each session runs in a detached tmux window and communicates exclusively through its own Discord thread, providing clean isolation for concurrent sessions.

Built to run inside the [ClaudeDocker](https://github.com/ywattenberg/ClaudeDocker) container and uses the [DiscordSkill](https://github.com/ywattenberg/DiscordSkill) plugin for Discord I/O.

## How It Works

```
User sends /claude in Discord
        │
        ▼
┌──────────────────────┐
│  Command Runner Bot   │  persistent discord.py process
│  (slash commands)     │
└────────┬─────────────┘
         │  1. Create Discord thread
         │  2. Write per-session config (channel_id = thread ID)
         │  3. Write prompt with discord-mode rules
         │  4. Spawn detached tmux session running Claude CLI
         │  5. Feed prompt via tmux paste-buffer
         ▼
┌──────────────────────┐
│  Claude Code (tmux)   │  communicates in the thread via discord-notify
│  uses DiscordSkill    │
└──────────────────────┘
```

Each `/claude` invocation creates a Discord thread. The spawned Claude session gets a per-session config with `channel_id` set to the thread ID, so multiple concurrent sessions don't interfere.

## Slash Commands

| Command | Parameters | Description |
|---------|-----------|-------------|
| `/claude` | `project` (autocomplete), `prompt` (optional), `working_dir` (optional) | Spawn a new Claude session in a thread |
| `/sessions` | — | List active Claude tmux sessions |
| `/kill` | `session_name` (autocomplete) | Kill a session and clean up |

## Prerequisites

- Python 3.12+
- [uv](https://docs.astral.sh/uv/)
- [tmux](https://github.com/tmux/tmux)
- [Claude Code CLI](https://docs.anthropic.com/en/docs/claude-code)
- [DiscordSkill](https://github.com/ywattenberg/DiscordSkill) plugin installed
- A Discord bot token with message and thread permissions

## Setup

### 1. Clone the repo

```bash
git clone https://github.com/ywattenberg/DiscordCommandRunner.git
cd DiscordCommandRunner
```

### 2. Install dependencies

```bash
uv sync
```

### 3. Configure

Copy the example config and fill in your values:

```bash
cp config.example.yaml config.yaml
```

```yaml
bot_token: "your-bot-token-here"
command_channel_id: 1234567890       # channel where /claude is allowed
guild_id: 1234567890                 # optional — enables instant slash command sync
plugin_dir: /home/dev/projects/DiscordSkill
default_working_dir: /home/dev/projects
```

Alternatively, set environment variables instead of using `config.yaml`:

| Env Var | Config Key |
|---------|-----------|
| `DISCORD_BOT_TOKEN` | `bot_token` |
| `COMMAND_CHANNEL_ID` | `command_channel_id` |
| `GUILD_ID` | `guild_id` |
| `PLUGIN_DIR` | `plugin_dir` |
| `DEFAULT_WORKING_DIR` | `default_working_dir` |

### 4. Run

```bash
uv run command-runner
```

> **Note:** Without `guild_id`, Discord may take up to an hour to propagate global slash commands. Set `guild_id` for instant sync during development.

## Auto-Start on Boot (Docker)

The included `install.sh` script handles the full setup inside a [ClaudeDocker](https://github.com/ywattenberg/ClaudeDocker) container:

```bash
./install.sh
```

This will:
1. Install Python dependencies via `uv sync`
2. Create `config.yaml` from environment variables (if it doesn't exist)
3. Patch the ClaudeDocker `entrypoint.sh` to start the bot automatically on container boot

The script is idempotent — safe to run multiple times.

### Manual entrypoint setup

If you prefer to patch the entrypoint yourself, add this line before the final `exec /usr/sbin/sshd -D` in your `entrypoint.sh`:

```bash
su - dev -c "cd /home/dev/projects/DiscordCommandRunner && uv run command-runner >> /tmp/command-runner.log 2>&1 &"
```

Logs are written to `/tmp/command-runner.log`.

## Related Repos

- [DiscordSkill](https://github.com/ywattenberg/DiscordSkill) — Claude Code plugin for Discord notifications and interactive communication
- [ClaudeDocker](https://github.com/ywattenberg/ClaudeDocker) — Docker container for running Claude Code with SSH access
