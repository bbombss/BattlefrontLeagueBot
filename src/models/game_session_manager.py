from __future__ import annotations

import datetime
import typing as t

import hikari
from openskill.models import PlackettLuce

from src.models.game_session import GamePlayer, GameSession

if t.TYPE_CHECKING:
    from src.models.bot import BattleFrontBot


class PlayerCache:
    """Cache of GamePlayer objects for members."""

    def __init__(self):
        self._cache: dict[hikari.Snowflake, dict[hikari.Snowflake, GamePlayer]] = {}
        self._guild_last_reset: dict[hikari.Snowflake, datetime.datetime] = {}

    def get(self, user_id: hikari.Snowflake, guild_id: hikari.Snowflake) -> GamePlayer | None:
        guild_cache = self._cache.get(guild_id)
        if guild_cache:
            return guild_cache.get(user_id)

    def set(self, user_id: hikari.Snowflake, player: GamePlayer) -> None:
        guild_cache = self._cache.get(player.member.guild_id)
        if guild_cache:
            guild_cache[user_id] = player
            return
        self._cache[player.member.guild_id] = {user_id: player}

    def clear_guild(self, guild_id: hikari.Snowflake) -> None:
        if self._cache.get(guild_id):
            self._cache.pop(guild_id)

    def check_cache(self, guild_id: hikari.Snowflake) -> None:
        """Check if the cached players for this guild need to be refreshed."""
        now = datetime.datetime.now()
        last = self._guild_last_reset.get(guild_id)

        if not last:
            self._guild_last_reset[guild_id] = now
            return

        if (now - last) >= datetime.timedelta(hours=24):
            self.clear_guild(guild_id)
            self._guild_last_reset[guild_id] = now


class GameSessionManager:
    """Game session manager that tracks ongoing game sessions for the bot."""

    def __init__(self, app: BattleFrontBot) -> None:
        """Game session manager that tracks ongoing game sessions for the bot.

        Parameters
        ----------
        app : BattleFrontBot
            The app the GameSessionManager is tied to.

        """
        self._app = app
        self._sessions: dict[hikari.Snowflake, GameSession] = {}
        self._player_cache = PlayerCache()
        self._last_registration_message = {}
        self._last_map = {}
        self._session_count: int | None = None
        self._openskill_model = PlackettLuce(balance=True)

    @property
    def app(self) -> BattleFrontBot:
        """The app the GameSessionManager is tied to."""
        return self._app

    @property
    def player_cache(self) -> PlayerCache:
        """The GamePlayer cache."""
        return self._player_cache

    @property
    def session_count(self) -> int:
        """The number of unique sessions that have been active."""
        if self._session_count is None:
            raise AttributeError("Cannot get session count until bot has started")

        return self._session_count

    @property
    def last_registration_message(self) -> dict[hikari.Snowflake, hikari.Snowflake]:
        """A dictionary of guild ids and the id of their most recent registration message."""
        return self._last_registration_message

    @property
    def last_map(self) -> dict[hikari.Snowflake, str]:
        """A dictionary of guild ids and their most recently requested map."""
        return self._last_map

    @property
    def openskill_model(self) -> PlackettLuce:
        """The openskill model used to rate players."""
        return self._openskill_model

    async def set_session_count(self) -> None:
        """Set the number of sessions ever created as fetched from the database."""
        session_count = await self.app.db.fetch("SELECT MAX(matchId) FROM matches")
        if session_count[0]["max"]:
            self._session_count = int(session_count[0]["max"])
            return
        self._session_count = 0

    async def start_session(
        self, guild_id: hikari.Snowflake, session: GameSession, members: list[hikari.Member], force: bool = False
    ) -> None:
        """Start a session.

        Parameters
        ----------
        guild_id : hikari.Snowflake
            The guild id this session is to be bound to.
        session : GameSession
            The game session that is being started.
        members : list[hikari.Member]
            A list of members that belong to this session (i.e. members).
        force : bool
            Whether a set of teams is being forced, defaults to False

        """
        self._sessions[guild_id] = session
        self._session_count += 1
        await self._sessions[guild_id].start(members, force)

    def fetch_session(self, guild_id: hikari.Snowflake) -> GameSession | None:
        """Fetch a session from a guild, returns none if this guild has no session.

        Parameters
        ----------
        guild_id : hikari.Snowflake
            The guild id for the session that is being fetched is bound to.

        Returns
        -------
        GameSession | None
            The game session or None if no game session is bound to this guild.

        """
        return self._sessions.get(guild_id)

    def add_session_score(self, guild_id: hikari.Snowflake, score1: int, score2: int) -> None:
        """Add game results to a session.

        Parameters
        ----------
        guild_id : hikari.Snowflake
            The guild id for the session that is being updated is bound to.
        score1 : int
            The score for the first team.
        score2 : int
            The score for the second team.

        """
        session = self.fetch_session(guild_id)
        session.add_score(score1, score2)
        session.event.set()

    def end_session(self, guild_id: hikari.Snowflake) -> None:
        """End an ongoing session.

        Parameters
        ----------
        guild_id : hikari.Snowflake
            The guild id for the session that is being ended is bound to.

        """
        self.fetch_session(guild_id).end()

    def remove_session(self, guild_id: hikari.Snowflake) -> None:
        """Remove a session from the game session manager if it exists.

        Parameters
        ----------
        guild_id : hikari.Snowflake
            The guild id for the session that is being removed is bound to.

        """
        if self.fetch_session(guild_id):
            self._sessions.pop(guild_id)


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
