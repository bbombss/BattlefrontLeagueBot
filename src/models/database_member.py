from __future__ import annotations

import typing as t

import attr
import hikari

from src.models.database import DatabaseModel


@attr.define
class DatabaseMember(DatabaseModel):
    """Dataclass for stored members in the database."""

    id: hikari.Snowflake
    """The ID for this member."""

    guild_id: hikari.Snowflake
    """The guild ID for this member."""

    rank: int = 1
    """The rank of this member."""

    wins: int = 0
    """The amount of wins for this member."""

    loses: int = 0
    """The amount of loses for this member."""

    async def update(self) -> None:
        """Update this member or add them if not already stored."""
        await self._db.execute(
            """
            INSERT INTO members (userId, guildId, rank, wins  loses)
            VALUES ($1, $2, $3, $4, $5)
            ON CONFLICT (userId, guildId) DO
            UPDATE SET rank = $3, wins = $4, loses = $5
            """,
            self.id,
            self.guild_id,
            self.rank,
            self.wins,
            self.loses,
        )

    @classmethod
    async def fetch(
        cls, user: hikari.SnowflakeishOr[hikari.PartialUser], guild: hikari.SnowflakeishOr[hikari.PartialGuild]
    ) -> t.Self:
        """Fetch this user from the database or add them if not already stored.

        Parameters
        ----------
        user : hikari.Snowflake
            User ID for the member to be fetched.
        guild : hikari.Snowflake
            Guild of the member to be fetched.

        Returns
        -------
        DatabaseMember
            Dataclass for stored members in the database.

        """
        record = await cls._db.fetchrow(
            "SELECT * FROM members WHERE userId = $1 and guildId = $2", hikari.Snowflake(user), hikari.Snowflake(guild)
        )

        if not record:
            member = cls(hikari.Snowflake(user), hikari.Snowflake(guild), rank=1, wins=0, loses=0)
            await member.update()
            return member

        return cls(
            hikari.Snowflake(record["userid"]),
            hikari.Snowflake(record["guildid"]),
            rank=record["rank"],
            wins=record["wins"],
            loses=record["loses"],
        )


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
