"""Entry point for the Discord Command Runner bot."""

from __future__ import annotations

import logging
import os
import sys
from pathlib import Path

import yaml

from command_runner.bot import CommandRunnerBot, Config

log = logging.getLogger(__name__)


def load_config() -> Config:
    """Load config from config.yaml falling back to environment variables."""
    config_path = Path(__file__).resolve().parent.parent.parent / "config.yaml"

    file_config: dict = {}
    if config_path.is_file():
        with open(config_path) as f:
            file_config = yaml.safe_load(f) or {}

    bot_token = file_config.get("bot_token") or os.environ.get("DISCORD_BOT_TOKEN")
    if not bot_token:
        print("Error: bot_token not set in config.yaml or DISCORD_BOT_TOKEN env var", file=sys.stderr)
        sys.exit(1)

    raw_channel = file_config.get("command_channel_id") or os.environ.get("COMMAND_CHANNEL_ID")
    if not raw_channel:
        print("Error: command_channel_id not set in config.yaml or COMMAND_CHANNEL_ID env var", file=sys.stderr)
        sys.exit(1)

    raw_guild = file_config.get("guild_id") or os.environ.get("GUILD_ID")

    return Config(
        bot_token=str(bot_token),
        command_channel_id=int(raw_channel),
        guild_id=int(raw_guild) if raw_guild else None,
        plugin_dir=str(file_config.get("plugin_dir") or os.environ.get("PLUGIN_DIR", "/home/dev/projects/DiscordSkill")),
        default_working_dir=str(file_config.get("default_working_dir") or os.environ.get("DEFAULT_WORKING_DIR", "/home/dev/projects")),
    )


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    config = load_config()
    log.info("Starting Command Runner bot (channel=%s, guild=%s)", config.command_channel_id, config.guild_id)

    bot = CommandRunnerBot(config)
    bot.run(config.bot_token, log_handler=None)


if __name__ == "__main__":
    main()
