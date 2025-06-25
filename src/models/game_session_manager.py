from __future__ import annotations

import typing as t

import hikari

from src.models.game_session import GamePlayer, GameSession

if t.TYPE_CHECKING:
    from src.models.bot import BattleFrontBot


class PlayerCache:
    """Cache of GamePlayer objects for members."""

    def __init__(self):
        self._cache = {}

    def get(self, user_id: hikari.Snowflake, guild_id: hikari.Snowflake) -> GamePlayer | None:
        return self._cache.get([user_id, guild_id])

    def set(self, user_id: hikari.Snowflake, player: GamePlayer) -> None:
        self._cache[[user_id, player.member.guild_id]] = player

    def clear_guild(self, guild_id: hikari.Snowflake) -> None:
        for key in self._cache:
            if key[1] == guild_id:
                self._cache.pop(key)


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
        self._session_count = 0

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
        return self._session_count

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
