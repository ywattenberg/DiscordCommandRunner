#!/usr/bin/env bash
# Hook script for Claude Code sessions spawned by DiscordCommandRunner.
# Adds/removes Discord reactions to show session activity status.
#
# Usage (called by Claude Code hooks):
#   echo '<hook_json>' | session_status.sh pre_tool
#   echo '<hook_json>' | session_status.sh stop
#
# Requires SESSION_CONFIG env var pointing to the session's config.md file.

set -euo pipefail

ACTION="${1:-}"

# Only run for Discord-managed sessions
[ -z "${SESSION_CONFIG:-}" ] && exit 0
[ ! -f "$SESSION_CONFIG" ] && exit 0

SESSION_DIR="$(dirname "$SESSION_CONFIG")"

# Parse bot token and channel ID from config frontmatter
BOT_TOKEN=""
CHANNEL_ID=""
while IFS= read -r line; do
    line="${line#"${line%%[![:space:]]*}"}"  # trim leading whitespace
    case "$line" in
        bot_token:*) BOT_TOKEN="${line#bot_token:}"; BOT_TOKEN="${BOT_TOKEN#"${BOT_TOKEN%%[![:space:]]*}"}" ;;
        channel_id:*) CHANNEL_ID="${line#channel_id:}"; CHANNEL_ID="${CHANNEL_ID#"${CHANNEL_ID%%[![:space:]]*}"}" ;;
    esac
done < "$SESSION_CONFIG"

[ -z "$BOT_TOKEN" ] || [ -z "$CHANNEL_ID" ] && exit 0

API_BASE="https://discord.com/api/v10"
AUTH_HEADER="Authorization: Bot $BOT_TOKEN"

# URL-encoded emoji codes
HOURGLASS="%E2%8F%B3"   # ⏳
CHECK="%E2%9C%85"        # ✅

get_last_message_id() {
    curl -sf -H "$AUTH_HEADER" \
        "$API_BASE/channels/$CHANNEL_ID/messages?limit=1" \
        | python3 -c "import sys,json; msgs=json.load(sys.stdin); print(msgs[0]['id'] if msgs else '')" 2>/dev/null || echo ""
}

add_reaction() {
    local msg_id="$1" emoji="$2"
    curl -sf -X PUT -H "$AUTH_HEADER" -H "Content-Length: 0" \
        "$API_BASE/channels/$CHANNEL_ID/messages/$msg_id/reactions/$emoji/@me" \
        -o /dev/null 2>/dev/null || true
}

remove_reaction() {
    local msg_id="$1" emoji="$2"
    curl -sf -X DELETE -H "$AUTH_HEADER" \
        "$API_BASE/channels/$CHANNEL_ID/messages/$msg_id/reactions/$emoji/@me" \
        -o /dev/null 2>/dev/null || true
}

THROTTLE_FILE="$SESSION_DIR/.react_throttle"
TRACKED_MSG_FILE="$SESSION_DIR/.react_msg_id"
THROTTLE_SECONDS=30

case "$ACTION" in
    pre_tool)
        # Throttle: skip if we reacted recently
        if [ -f "$THROTTLE_FILE" ]; then
            last_ts=$(cat "$THROTTLE_FILE" 2>/dev/null || echo 0)
            now=$(date +%s)
            elapsed=$(( now - last_ts ))
            [ "$elapsed" -lt "$THROTTLE_SECONDS" ] && exit 0
        fi

        msg_id=$(get_last_message_id)
        [ -z "$msg_id" ] && exit 0

        add_reaction "$msg_id" "$HOURGLASS"
        echo "$msg_id" > "$TRACKED_MSG_FILE"
        date +%s > "$THROTTLE_FILE"
        ;;

    stop)
        # Remove ⏳ from the tracked message
        if [ -f "$TRACKED_MSG_FILE" ]; then
            tracked_id=$(cat "$TRACKED_MSG_FILE" 2>/dev/null || echo "")
            if [ -n "$tracked_id" ]; then
                remove_reaction "$tracked_id" "$HOURGLASS"
            fi
            rm -f "$TRACKED_MSG_FILE"
        fi

        # Add ✅ to the last message
        msg_id=$(get_last_message_id)
        [ -z "$msg_id" ] && exit 0
        add_reaction "$msg_id" "$CHECK"

        # Clean up throttle file
        rm -f "$THROTTLE_FILE"
        ;;

    *)
        exit 0
        ;;
esac
