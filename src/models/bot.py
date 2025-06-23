import datetime
import logging
import os
import tomllib
import typing as t
from pathlib import Path

import aiofiles
import hikari
import lightbulb
import miru

from src.config import Config
from src.models.context import *
from src.models.database import Database
from src.models.errors import ApplicationStateError
from src.models.game_session_manager import GameSessionManager
from src.static import DEFAULT_EMBED_COLOUR

logger = logging.getLogger(__name__)


class BattleFrontBot(lightbulb.BotApp):
    """Subclass of lightbulb BotApp to add special functionality.

    Parameters
    ----------
    config : Config
        Bot configuration file; included values will be initialised on startup.

    """

    def __init__(self, config: Config) -> None:
        self._bot_started = False

        token = config.TOKEN

        default_enabled_guilds = config.DEBUG_GUILD_IDS if config.DEBUG_MODE and config.DEBUG_GUILD_IDS else []

        cache_config = hikari.impl.CacheSettings(
            components=hikari.api.CacheComponents.DM_CHANNEL_IDS
            | hikari.api.CacheComponents.GUILDS
            | hikari.api.CacheComponents.GUILD_CHANNELS
            | hikari.api.CacheComponents.ME
            | hikari.api.CacheComponents.MEMBERS
            | hikari.api.CacheComponents.MESSAGES
            | hikari.api.CacheComponents.ROLES,
            max_messages=2000,
            max_dm_channel_ids=50,
        )

        intents = (
            hikari.Intents.ALL_MESSAGES
            | hikari.Intents.MESSAGE_CONTENT
            | hikari.Intents.GUILDS
            | hikari.Intents.GUILD_MEMBERS
        )

        super().__init__(
            token=token,
            prefix=".$",
            ignore_bots=True,
            default_enabled_guilds=default_enabled_guilds,
            help_class=None,
            case_insensitive_prefix_commands=True,
            cache_settings=cache_config,
            intents=intents,
            banner=None,
        )

        self._config = config
        self._user_id: hikari.Snowflake
        self._start_time: datetime.datetime
        self._base_dir = str(Path(os.path.abspath(__file__)).parents[2])
        self._debug_mode = config.DEBUG_MODE
        self._startup_guilds: list = []
        self._version: str

        self._db = Database(self)
        self._miru_client = miru.Client(self, ignore_unknown_interactions=True)
        self._game_session_manager = GameSessionManager(self)

    @property
    def is_started(self) -> bool:
        """A boolean based on whether the bot has started."""
        return self._bot_started

    @property
    def version(self) -> str:
        """Returns the running version of BattlefrontBot."""
        if self._version is None:
            raise ApplicationStateError("App version is unavailable until bot has started.")

        return self._version

    @property
    def base_dir(self) -> str:
        """The path to the root directory."""
        return self._base_dir

    @property
    def config(self) -> Config:
        """The initialised configuration."""
        return self._config

    @property
    def user_id(self) -> hikari.Snowflake:
        """The bots user's discord user id."""
        if self._user_id is None:
            raise ApplicationStateError("Bot user_id is unavailable until bot has started")

        return self._user_id

    @property
    def start_time(self) -> datetime.datetime:
        """The time at which the bot started."""
        if self._start_time is None:
            raise ApplicationStateError("Bot start_time is unavailable until bot has started")

        return self._start_time

    @property
    def db(self) -> Database:
        """The database connection of the bot."""
        return self._db

    @property
    def miru_client(self) -> miru.Client:
        """The miru client of the bot."""
        return self._miru_client

    @property
    def game_session_manager(self) -> GameSessionManager:
        """The game session manager of the bot."""
        return self._game_session_manager

    def run(self) -> None:
        """Start listeners and bot activity."""
        self.subscribe(hikari.StartingEvent, self.on_starting)
        self.subscribe(hikari.StartedEvent, self.on_started)
        self.subscribe(hikari.GuildAvailableEvent, self.on_guild_available)
        self.subscribe(lightbulb.LightbulbStartedEvent, self.on_lightbulb_started)
        self.subscribe(hikari.GuildJoinEvent, self.on_guild_join)
        self.subscribe(hikari.GuildLeaveEvent, self.on_guild_leave)
        self.subscribe(hikari.StoppedEvent, self.on_stop)

        super().run(activity=hikari.Activity(name="Star Wars Battlefront II", type=hikari.ActivityType.PLAYING))

    async def get_slash_context(
        self,
        event: hikari.InteractionCreateEvent,
        command: lightbulb.SlashCommand,
        cls: t.Type[lightbulb.SlashContext] = BattlefrontBotSlashContext,
    ) -> BattlefrontBotSlashContext:
        return await super().get_slash_context(event, command, cls)  # type: ignore

    async def get_prefix_context(
        self,
        event: hikari.MessageCreateEvent,
        cls: t.Type[lightbulb.PrefixContext] = BattlefrontBotPrefixContext,
    ) -> BattlefrontBotPrefixContext:
        return await super().get_prefix_context(event, cls)  # type: ignore

    async def on_starting(self, event: hikari.StartingEvent) -> None:
        logger.info("Initialising BattleFrontBot...")

        await self.db.connect()
        await self.db.migrate_schema()

        self.load_extensions_from(os.path.join(self.base_dir, "src", "extensions"), must_exist=True)

    async def on_started(self, event: hikari.StartedEvent) -> None:
        user = self.get_me()
        if user:
            self._user_id = user.id

        toml_path = os.path.join(self.base_dir, "pyproject.toml")
        version: str = "2.0.0"

        async with aiofiles.open(toml_path, "rb") as file:
            toml_data = await file.read()
            toml = tomllib.loads(toml_data.decode("utf-8"))
            self._version = toml.get("project", {}).get("version", version)

        if self._debug_mode:
            logger.warning("Debug mode is active")

    async def on_guild_available(self, event: hikari.GuildAvailableEvent) -> None:
        if self.is_started:
            return

        self._startup_guilds.append(event.guild_id)

    async def on_lightbulb_started(self, event: lightbulb.LightbulbStartedEvent) -> None:
        async with self.db.pool.acquire() as con:
            for guild in self._startup_guilds:
                await con.execute(
                    """INSERT INTO guilds (guildId) VALUES ($1)
                    ON CONFLICT (guildId) DO NOTHING""",
                    guild,
                )

        logger.info(f"Bot initialised as {self.get_me()} in {len(self._startup_guilds)} guilds")

        self._startup_guilds = []

        self._bot_started = True
        self._start_time = datetime.datetime.now()

        logger.info("BattleFrontBot initialised successfully")

        self.unsubscribe(hikari.GuildAvailableEvent, self.on_guild_available)

    async def on_guild_join(self, event: hikari.GuildJoinEvent) -> None:
        await self.db.add_guild(event.guild_id)

        logger.info(f"BattleFrontBot in new guild: {event.guild.name} ({event.guild_id})")

        me = event.guild.get_my_member()

        if event.guild.system_channel_id is None or me is None:
            return

        system_channel = event.guild.get_channel(event.guild.system_channel_id)
        assert isinstance(system_channel, hikari.TextableGuildChannel)

        welcome_embed = hikari.Embed(
            title="👋  Greetings",
            description="""I'm always listening for commands type / to see what I can do.
Make sure to set the rank roles using `/roles`""",
            colour=DEFAULT_EMBED_COLOUR,
        ).set_thumbnail(me.avatar_url)

        try:
            await system_channel.send(embed=welcome_embed)
        except hikari.ForbiddenError:
            return

    async def on_guild_leave(self, event: hikari.GuildLeaveEvent) -> None:
        await self.db.remove_guild(event.guild_id)
        logger.info(f"BattleFrontBot removed from guild: {event.guild_id}")

    async def on_stop(self, event: hikari.StoppedEvent) -> None:
        self._is_started = False
        await self.db.close()
        logger.info("BattleFrontBot has been shut down")


# Copyright (C) 2025 BBombs

# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.

# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.

# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <https://www.gnu.org/licenses/>.
