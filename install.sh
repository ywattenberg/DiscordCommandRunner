#!/bin/bash
set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "$0")" && pwd)"
CONFIG_FILE="$PROJECT_DIR/config.yaml"
ENTRYPOINT="/home/dev/projects/ClaudeDocker/entrypoint.sh"
STARTUP_MARKER="# command-runner"

echo "==> Installing DiscordCommandRunner"

# 1. Install Python dependencies
echo "  Installing dependencies..."
uv sync --project "$PROJECT_DIR" --quiet

# 2. Create config.yaml from env vars if it doesn't exist
if [ ! -f "$CONFIG_FILE" ]; then
    if [ -z "${DISCORD_BOT_TOKEN:-}" ]; then
        echo "  No config.yaml found and DISCORD_BOT_TOKEN not set."
        echo "  Create config.yaml manually from config.example.yaml, or set env vars:"
        echo "    DISCORD_BOT_TOKEN, COMMAND_CHANNEL_ID, GUILD_ID (optional)"
        echo "  Then re-run this script."
        exit 1
    fi

    echo "  Creating config.yaml from environment variables..."
    cat > "$CONFIG_FILE" <<YAML
bot_token: "${DISCORD_BOT_TOKEN}"
command_channel_id: ${COMMAND_CHANNEL_ID}
${GUILD_ID:+guild_id: $GUILD_ID}
plugin_dir: ${PLUGIN_DIR:-/home/dev/projects/DiscordSkill}
default_working_dir: ${DEFAULT_WORKING_DIR:-/home/dev/projects}
YAML
    echo "  config.yaml created."
else
    echo "  config.yaml already exists, skipping."
fi

# 3. Add startup line to entrypoint.sh if not already present
if [ -f "$ENTRYPOINT" ]; then
    if ! grep -q "$STARTUP_MARKER" "$ENTRYPOINT"; then
        echo "  Adding command-runner to entrypoint.sh..."
        # Insert before the final exec line
        sed -i "/^exec \/usr\/sbin\/sshd/i\\
$STARTUP_MARKER\\
su - dev -c \"cd $PROJECT_DIR && uv run command-runner >> /tmp/command-runner.log 2>&1 &\"\\
" "$ENTRYPOINT"
        echo "  Added to entrypoint.sh (starts on container boot)."
    else
        echo "  entrypoint.sh already configured, skipping."
    fi
else
    echo "  entrypoint.sh not found at $ENTRYPOINT, skipping auto-start setup."
    echo "  To start manually: cd $PROJECT_DIR && uv run command-runner"
fi

echo "==> Done. Start now with: cd $PROJECT_DIR && uv run command-runner"
