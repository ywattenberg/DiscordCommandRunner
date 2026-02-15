"""Persistent Discord bot with slash commands for managing Claude sessions."""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from pathlib import Path

import discord
from discord import app_commands

from command_runner import sessions

log = logging.getLogger(__name__)


@dataclass
class Config:
    bot_token: str
    command_channel_id: int
    guild_id: int | None = None
    plugin_dir: str = "/home/dev/projects/DiscordSkill"
    default_working_dir: str = "/home/dev/projects"


class CommandRunnerBot(discord.Client):
    def __init__(self, config: Config) -> None:
        intents = discord.Intents.default()
        intents.guilds = True
        intents.guild_messages = True
        intents.message_content = True
        super().__init__(intents=intents)
        self.config = config
        self.tree = app_commands.CommandTree(self)
        self._register_commands()

    def _register_commands(self) -> None:
        config = self.config

        # --- /claude ---
        @self.tree.command(name="claude", description="Spawn a new Claude Code session in a Discord thread")
        @app_commands.describe(
            project="Project directory (autocomplete)",
            prompt="Initial prompt for Claude",
            working_dir="Override working directory (freeform path)",
        )
        async def claude_cmd(
            interaction: discord.Interaction,
            project: str | None = None,
            prompt: str | None = None,
            working_dir: str | None = None,
        ) -> None:
            if interaction.channel_id != config.command_channel_id:
                await interaction.response.send_message(
                    "This command can only be used in the designated command channel.",
                    ephemeral=True,
                )
                return

            await interaction.response.defer(ephemeral=True)

            # Resolve working directory
            resolved_dir = working_dir or project or config.default_working_dir
            if not Path(resolved_dir).is_dir():
                await interaction.followup.send(
                    f"Directory does not exist: `{resolved_dir}`",
                    ephemeral=True,
                )
                return

            # Create a thread from the interaction channel
            channel = interaction.channel
            assert isinstance(channel, discord.TextChannel)

            thread_name = f"Claude: {prompt[:80]}" if prompt else "Claude Session"
            thread = await channel.create_thread(
                name=thread_name,
                type=discord.ChannelType.public_thread,
            )

            # Spawn session in executor (blocking subprocess calls)
            try:
                session_name = await asyncio.get_event_loop().run_in_executor(
                    None,
                    lambda: sessions.spawn_session(
                        bot_token=config.bot_token,
                        thread_id=thread.id,
                        prompt=prompt,
                        working_dir=resolved_dir,
                        plugin_dir=config.plugin_dir,
                    ),
                )
            except Exception as exc:
                err_msg = str(exc)[:500]
                await thread.send(f"Failed to spawn session: {err_msg}")
                await interaction.followup.send(
                    f"Error spawning session: {err_msg}",
                    ephemeral=True,
                )
                return

            await thread.send(f"Claude session `{session_name}` started. Initializing...")
            await interaction.followup.send(
                f"Session `{session_name}` spawned → {thread.mention}",
                ephemeral=True,
            )

        @claude_cmd.autocomplete("project")
        async def project_autocomplete(
            interaction: discord.Interaction,
            current: str,
        ) -> list[app_commands.Choice[str]]:
            base = Path(config.default_working_dir)
            if not base.is_dir():
                return []
            projects = [
                d.name
                for d in base.iterdir()
                if d.is_dir() and not d.name.startswith(".")
            ]
            return [
                app_commands.Choice(name=p, value=str(base / p))
                for p in sorted(projects)
                if current.lower() in p.lower()
            ][:25]

        # --- /sessions ---
        @self.tree.command(name="sessions", description="List active Claude tmux sessions")
        async def sessions_cmd(interaction: discord.Interaction) -> None:
            active = sessions.list_sessions()
            if not active:
                await interaction.response.send_message("No active Claude sessions.", ephemeral=True)
                return

            lines = [f"**{s['name']}** — started {s['created']}" for s in active]
            await interaction.response.send_message(
                "**Active Sessions:**\n" + "\n".join(lines),
                ephemeral=True,
            )

        # --- /kill ---
        @self.tree.command(name="kill", description="Kill a Claude tmux session")
        @app_commands.describe(session_name="Session to kill (autocomplete)")
        async def kill_cmd(interaction: discord.Interaction, session_name: str) -> None:
            success = sessions.kill_session(session_name)
            if success:
                await interaction.response.send_message(
                    f"Session `{session_name}` killed and cleaned up.",
                    ephemeral=True,
                )
            else:
                await interaction.response.send_message(
                    f"Failed to kill session `{session_name}` (may not exist).",
                    ephemeral=True,
                )

        @kill_cmd.autocomplete("session_name")
        async def kill_autocomplete(
            interaction: discord.Interaction,
            current: str,
        ) -> list[app_commands.Choice[str]]:
            active = sessions.list_sessions()
            return [
                app_commands.Choice(name=s["name"], value=s["name"])
                for s in active
                if current.lower() in s["name"].lower()
            ][:25]

    async def on_ready(self) -> None:
        log.info("Bot ready as %s (id=%s)", self.user, self.user.id if self.user else "?")

        if self.config.guild_id:
            guild = discord.Object(id=self.config.guild_id)
            self.tree.copy_global_to(guild=guild)
            await self.tree.sync(guild=guild)
            log.info("Synced commands to guild %s", self.config.guild_id)
        else:
            await self.tree.sync()
            log.info("Synced commands globally")
