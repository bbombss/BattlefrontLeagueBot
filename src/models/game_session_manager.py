from __future__ import annotations

import typing as t

import hikari

from src.models.game_session import GamePlayer, GameSession

if t.TYPE_CHECKING:
    from src.models.bot import BattleFrontBot


class GamePlayerCache:
    """Cache of GamePlayer objects for members."""

    def __init__(self):
        self._cache = {}

    def get(self, member_id: hikari.Snowflake) -> GamePlayer | None:
        return self._cache.get(member_id)

    def set(self, member_id: hikari.Snowflake, player: GamePlayer) -> None:
        self._cache[member_id] = player


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
        self._sessions: dict[hikari.Guild, GameSession] = {}
        self._player_cache = GamePlayerCache()
        self.session_count = 0

    @property
    def app(self) -> BattleFrontBot:
        """The app the GameSessionManager is tied to."""
        return self._app

    @property
    def player_cache(self) -> GamePlayerCache:
        """The GamePlayer cache."""
        return self._player_cache

    async def bind(self, guild: hikari.Guild, session: GameSession) -> None:
        """Bind this session to its guild.

        Parameters
        ----------
        guild : hikari.Guild
            The guild this session is to be bound to.
        session : GameSession
            The game session that is being bound

        """
        self._sessions[guild] = session
        self.session_count += 1

    def fetch_session(self, guild: hikari.Guild) -> GameSession | None:
        """Fetch a session from a guild, returns none if this guild has no session.

        Parameters
        ----------
        guild : hikari.Guild
            The guild for the session that is being fetched is bound to.

        Returns
        -------
        GameSession | None
            The game session or None if no game session is bound to this guild.

        """
        return self._sessions[guild]


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
